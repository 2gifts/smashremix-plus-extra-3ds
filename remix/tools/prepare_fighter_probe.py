"""Extract a native fighter integration fixture from the pinned reference build.

This is deliberately separate from release packaging. Integrated fighters are
selectable via their parent bottom-screen cards in VS mode. No ROM
addresses are executed: motion bytecode is decoded and its pointers relocated,
and special callbacks are supplied by native C implementations.
"""
import json
import re
import shutil
import struct
from collections import Counter
from pathlib import Path
from common import BUILD, ROOT, checked_sources, sha256, write_json


class Reference:
    def __init__(self):
        lock, _ = checked_sources()
        meta = json.loads((BUILD / 'reference.json').read_text())
        for name in ('extra', 'remix'):
            if meta[name + '_commit'] != lock[name]['commit']:
                raise ValueError('Reference revision mismatch')
        self.path = (ROOT / meta['rom']).resolve()
        if not self.path.is_relative_to(BUILD.resolve()) or sha256(self.path) != meta['rom_sha256']:
            raise ValueError('Reference ROM hash mismatch')
        self.rom = self.path.read_bytes()
        self.symbols = {}
        symbols_path = self.path.with_name('symbols.log')
        if sha256(symbols_path) != meta['symbols_sha256']:
            raise ValueError('Reference symbol hash mismatch')
        for line in symbols_path.read_text().splitlines():
            value, name = line.split(maxsplit=1)
            self.symbols[name] = int(value, 16)
        main = self.path.with_name('main.asm').read_text()
        match = re.search(r'origin\s+(0x\w+)\s+base\s+(0x\w+)', main)
        if not match:
            raise ValueError('Missing reference expansion mapping')
        self.rom_base, self.ram_base = (int(x, 16) for x in match.groups())
        if (self.rom_base, self.ram_base) != (0x03800000, 0x80400000):
            raise ValueError('Unexpected mapping for the pinned reference revision')

    def words(self, address, count):
        # Only the assembled expansion is accepted here; overlay addresses need
        # an explicit mapping, never a guessed subtraction.
        offset = address - self.ram_base + self.rom_base
        if address % 4 or count < 0 or address < self.ram_base or offset < 0 or offset + count * 4 > len(self.rom):
            raise ValueError(f'Unmapped reference address {address:08x}')
        return list(struct.unpack_from('>' + str(count) + 'I', self.rom, offset))


class Scripts:
    # Vanilla motion commands. Reject unported Remix commands instead of
    # interpreting them as four-byte no-ops and corrupting script alignment.
    LENGTHS = {3: 5, 4: 5, 7: 2, 12: 2, 13: 2, 31: 4,
               34: 2, 36: 2, 38: 4, 39: 4, 46: 2}
    # Structural decoding only. Runtime support is a separate requirement.
    # D6's second word points at halfword FGM IDs; DB jumps into file 2.
    CUSTOM_LENGTHS = {**{op: 1 for op in range(0xd0, 0xdf)},
                      0xd6: 2, 0xd9: 2, 0xdc: 2}

    def __init__(self, reference, allow_custom=False, external_scripts=None):
        self.ref = reference
        self.allow_custom = allow_custom
        self.external_scripts = external_scripts or {}
        self.words = {}
        self.pointers = {}
        self.visited = set()
        self.custom_commands = Counter()

    def script(self, address):
        if address in self.external_scripts:
            return
        while address not in self.visited:
            self.visited.add(address)
            word = self.ref.words(address, 1)[0]
            op = word >> 26
            byte = word >> 24
            known_custom = byte in ((self.CUSTOM_LENGTHS if self.allow_custom else
                                     {0xd0: 1, 0xd2: 1, 0xd3: 1}))
            if (op > 51 and not known_custom) or op == 13:
                raise ValueError(f'Unported command byte {byte:#x} at {address:08x}')
            count = self.CUSTOM_LENGTHS[byte] if op > 51 else self.LENGTHS.get(op, 1)
            if byte in (0xdd, 0xde) and known_custom:
                flags = (word >> 16) & 0xff
                half = word & 0xffff
                if (flags >> 4) == 0 and (flags & 0xf) >= 4:
                    raise ValueError(f'Invalid hitbox slot in command {word:08x} at {address:08x}')
                if (half & 0x8000) == 0 and (half & 0x7f80) == 0x7f80:
                    raise ValueError(f'Nonfinite hit multiplier in command {word:08x} at {address:08x}')
            self.copy(address, count)
            if op > 51:
                self.custom_commands[byte] += 1
                if byte == 0xd6:
                    target = self.words[address + 4]
                    ids = word & 0xff
                    if not ids or ids > 64:
                        raise ValueError(f'Invalid random SFX count {ids} at {address:08x}')
                    self.copy(target, (ids + 1) // 2)
                    self.pointers[address + 4] = target
            if op == 12:
                target = self.words[address + 4]
                # Two FTThrowHitDesc records, seven 32-bit values each.
                self.copy(target, 14)
                self.pointers[address + 4] = target
            if op in (34, 36, 46):
                target = self.words[address + 4]
                if not target:
                    raise ValueError(f'Null branch target from {address:08x}')
                self.pointers[address + 4] = target
                self.script(target)
            if op in (0, 35, 36) or byte == 0xdb:
                return
            address += count * 4
            if len(self.visited) > 16384:
                raise ValueError('Unbounded motion script graph')

    def copy(self, address, count):
        for i, word in enumerate(self.ref.words(address, count)):
            slot = address + i * 4
            if slot in self.words and self.words[slot] != word:
                raise ValueError('Conflicting motion payload')
            self.words[slot] = word

    def emit(self, prefix='remix', extern_entrypoints=()):
        addresses = sorted(self.words)
        indices = {a: i for i, a in enumerate(addresses)}
        # Compact only at gaps. Every decoded instruction's words must retain
        # adjacency, including fallthrough at shared script entry points.
        externs = sorted({self.external_scripts[target] for target in (*self.pointers.values(), *extern_entrypoints)
                          if target in self.external_scripts})
        lines = [f'extern s32 {name}[];' for name in externs]
        lines += [f'static u32 {prefix}_script_words[] = {{']
        lines += ['    ' + ','.join(f'0x{self.words[a]:08x}u' for a in addresses[i:i+8]) + ','
                  for i in range(0, len(addresses), 8)]
        lines += ['};', f'static void {prefix}_relocate_scripts(void) {{']
        for slot, target in sorted(self.pointers.items()):
            if target in self.external_scripts:
                expression = self.external_scripts[target]
            else:
                expression = f'&{prefix}_script_words[{indices[target]}]'
            lines.append(f'    {prefix}_script_words[{indices[slot]}] = portRelocRegisterPointer({expression});')
        lines += ['}']
        return lines, indices


def emit_variant(ref, name, native_scripts, out):
    """Generate one independently backed regional fighter from the pinned ROM."""
    prefix = name.lower()
    data = ref.words(ref.symbols[f'Character.{name}_character_struct'], 30)
    motion = [ref.words(data[25] + i * 12, 3) for i in range(data[27])]
    menu_count = ref.words(data[28], 1)[0]
    menus = [ref.words(data[26] + i * 12, 3) for i in range(menu_count)]
    scripts = Scripts(ref, allow_custom=True, external_scripts=native_scripts)
    entrypoints = {row[1] for row in motion + menus if row[1] > 0x80000000}
    for address in sorted(entrypoints):
        scripts.script(address)
    lines, indices = scripts.emit(f'remix_{prefix}', entrypoints)
    def pointer(address):
        if address in native_scripts:
            return f'(intptr_t){native_scripts[address]}'
        if address > 0x80000000:
            return f'(intptr_t)&remix_{prefix}_script_words[{indices[address]}]'
        return f'(intptr_t)0x{address:08x}u'
    for label, rows in (('main', motion), ('menu', menus)):
        lines.append(f'static FTMotionDesc remix_{prefix}_{label}_motions[] = {{')
        for fid, ptr, flags in rows:
            lines.append(f'    {{{fid}, {pointer(ptr)}, {{.word = 0x{flags:08x}u}}}},')
        lines.append('};')
    lines += [f'static const u32 remix_{prefix}_files[9] = {{{", ".join(map(str, data[:9]))}}};',
              f'static s32 remix_{prefix}_menu_count = {menu_count};',
              f'#define REMIX_{name}_ATTRIBUTE_OFFSET 0x{data[24]:x}']
    (out / f'{prefix}_data.inc').write_text('\n'.join(lines) + '\n')
    return data, motion, menus, scripts


def main():
    from audit_reference_fighters import known_native_script_symbols
    ref = Reference()
    data = ref.words(ref.symbols['Character.FALCO_character_struct'], 30)
    motion = [ref.words(data[25] + i * 12, 3) for i in range(data[27])]
    menus = [ref.words(data[26] + i * 12, 3) for i in range(ref.words(data[28], 1)[0])]
    scripts = Scripts(ref)
    for row in motion + menus:
        if row[1] > 0x80000000:
            scripts.script(row[1])
    lines, indices = scripts.emit()
    for name, rows in [('main', motion), ('menu', menus)]:
        lines.append(f'static FTMotionDesc remix_{name}_motions[] = {{')
        for fid, ptr, flags in rows:
            offset = f'(intptr_t)&remix_script_words[{indices[ptr]}]' if ptr > 0x80000000 else f'(intptr_t)0x{ptr:08x}u'
            lines.append(f'    {{{fid}, {offset}, {{.word = 0x{flags:08x}u}}}},')
        lines.append('};')
    lines += [f'static const u32 remix_probe_files[9] = {{{",".join(map(str, data[:9]))}}};',
              f'#define REMIX_PROBE_ATTRIBUTE_OFFSET 0x{data[24]:x}']
    out = BUILD / 'fighter-probe'
    out.mkdir(exist_ok=True)
    (out / 'falco_data.inc').write_text('\n'.join(lines) + '\n')

    # Bring the first +EXTRA fighter's data into the same private fixture.
    # A generated motion table alone must never mark a fighter as playable;
    # its native callbacks and selection bridge are built separately.
    dk_data = ref.words(ref.symbols['Character.DKULT_character_struct'], 30)
    dk_motion = [ref.words(dk_data[25] + i * 12, 3) for i in range(dk_data[27])]
    dk_menu_count = ref.words(dk_data[28], 1)[0]
    dk_menus = [ref.words(dk_data[26] + i * 12, 3) for i in range(dk_menu_count)]
    dk_external = known_native_script_symbols()
    dk_scripts = Scripts(ref, allow_custom=True, external_scripts=dk_external)
    dk_entrypoints = {row[1] for row in dk_motion + dk_menus if row[1] > 0x80000000}
    for address in sorted(dk_entrypoints):
        dk_scripts.script(address)
    dk_lines, dk_indices = dk_scripts.emit('remix_dkult', dk_entrypoints)
    def dk_pointer(address):
        if address in dk_external:
            return f'(intptr_t){dk_external[address]}'
        if address > 0x80000000:
            return f'(intptr_t)&remix_dkult_script_words[{dk_indices[address]}]'
        return f'(intptr_t)0x{address:08x}u'
    for label, rows in (('main', dk_motion), ('menu', dk_menus)):
        dk_lines.append(f'static FTMotionDesc remix_dkult_{label}_motions[] = {{')
        for fid, ptr, flags in rows:
            dk_lines.append(f'    {{{fid}, {dk_pointer(ptr)}, {{.word = 0x{flags:08x}u}}}},')
        dk_lines.append('};')
    dk_lines += [f'static const u32 remix_dkult_files[9] = {{{", ".join(map(str, dk_data[:9]))}}};',
                 f'static s32 remix_dkult_menu_count = {dk_menu_count};',
                 f'#define REMIX_DKULT_ATTRIBUTE_OFFSET 0x{dk_data[24]:x}']
    (out / 'dkult_data.inc').write_text('\n'.join(dk_lines) + '\n')

    jp_data = ref.words(ref.symbols['Character.JPIKA_character_struct'], 30)
    jp_motion = [ref.words(jp_data[25] + i * 12, 3) for i in range(jp_data[27])]
    jp_menu_count = ref.words(jp_data[28], 1)[0]
    jp_menus = [ref.words(jp_data[26] + i * 12, 3) for i in range(jp_menu_count)]
    jp_scripts = Scripts(ref, allow_custom=True, external_scripts=dk_external)
    jp_entrypoints = {row[1] for row in jp_motion + jp_menus if row[1] > 0x80000000}
    for address in sorted(jp_entrypoints):
        jp_scripts.script(address)
    jp_lines, jp_indices = jp_scripts.emit('remix_jpika', jp_entrypoints)
    def jp_pointer(address):
        if address in dk_external:
            return f'(intptr_t){dk_external[address]}'
        if address > 0x80000000:
            return f'(intptr_t)&remix_jpika_script_words[{jp_indices[address]}]'
        return f'(intptr_t)0x{address:08x}u'
    for label, rows in (('main', jp_motion), ('menu', jp_menus)):
        jp_lines.append(f'static FTMotionDesc remix_jpika_{label}_motions[] = {{')
        for fid, ptr, flags in rows:
            jp_lines.append(f'    {{{fid}, {jp_pointer(ptr)}, {{.word = 0x{flags:08x}u}}}},')
        jp_lines.append('};')
    jp_lines += [f'static const u32 remix_jpika_files[9] = {{{", ".join(map(str, jp_data[:9]))}}};',
                 f'static s32 remix_jpika_menu_count = {jp_menu_count};',
                 f'#define REMIX_JPIKA_ATTRIBUTE_OFFSET 0x{jp_data[24]:x}']
    (out / 'jpika_data.inc').write_text('\n'.join(jp_lines) + '\n')

    mario_data, mario_motion, mario_menus, mario_scripts = emit_variant(ref, 'JMARIO', dk_external, out)
    falcon_data, falcon_motion, falcon_menus, falcon_scripts = emit_variant(ref, 'JFALCON', dk_external, out)
    luigi_data, luigi_motion, luigi_menus, luigi_scripts = emit_variant(ref, 'JLUIGI', dk_external, out)
    jdk_data, jdk_motion, jdk_menus, jdk_scripts = emit_variant(ref, 'JDK', dk_external, out)

    # Keep the proven vanilla UI assets. Add only the validated dependency
    # closure required by this fighter, never ship unresolved reference files.
    config = json.loads((ROOT / '3ds/build-config.json').read_text())
    if 'vanilla_assets' in config:
        vanilla = Path(config['vanilla_assets']).resolve()
    else:
        battleship = Path(config.get('battleship', ROOT / '3ds/vendor/BattleShip')).resolve()
        vanilla = battleship.parents[1] / 'assets'
    base = (vanilla / 'reloc.pak').read_bytes()
    expansion = (BUILD / 'assets/reloc.reference.pak').read_bytes()
    manifest = json.loads((BUILD / 'assets/manifest.json').read_text())
    if sha256(BUILD / 'assets/reloc.reference.pak') != manifest['summary']['pack_sha256']:
        raise ValueError('Reference pack hash mismatch')
    entries = manifest['entries']
    required = set()
    def add(fid):
        if not fid or fid in required:
            return
        if not 0 <= fid < len(entries):
            raise ValueError('Animation file outside pack')
        required.add(fid)
        for dep in entries[fid]['external_files']:
            add(dep)
    for fid in data[:9] + dk_data[:9] + jp_data[:9] + mario_data[:9] + falcon_data[:9] + luigi_data[:9] + jdk_data[:9] + [r[0] for r in motion + menus + dk_motion + dk_menus + jp_motion + jp_menus + mario_motion + mario_menus + falcon_motion + falcon_menus + luigi_motion + luigi_menus + jdk_motion + jdk_menus]:
        add(fid)
    bad = [issue for issue in manifest['relocation_issues'] if issue['file_id'] in required]
    if bad:
        raise ValueError(f'Fighter reaches invalid relocations: {bad}')
    count = len(entries)
    old_count = struct.unpack_from('<I', base, 12)[0]
    pack = bytearray(b'SSB3DPAK' + struct.pack('<II', 1, count) + bytes(count * 20))
    for fid in range(count):
        src = expansion if fid in required else base if fid < old_count else None
        if src is None:
            # A deliberately absent file cannot be mistaken for valid assets.
            fields = [len(pack), 0, 0, 0xffff, 0xffff, 0]
        else:
            fields = list(struct.unpack_from('<IIIHHI', src, 16 + fid * 20))
            start, size, deps = fields[:3]
            fields[0] = len(pack)
            pack.extend(src[start:start + size + deps * 2])
        struct.pack_into('<IIIHHI', pack, 16 + fid * 20, *fields)
    assets = ROOT / '3ds/assets'
    assets.mkdir(exist_ok=True)
    (assets / 'reloc.pak').write_bytes(pack)
    for name in ('audio', 'particles'):
        shutil.copytree(vanilla / name, assets / name, dirs_exist_ok=True)
    from prepare_reference_audio import main as prepare_audio
    prepare_audio()
    for path in (BUILD / 'audio').glob('*.bin'):
        shutil.copy2(path, assets / 'audio' / path.name)
    for name in ('initial-save.bin', 'bottom-ui.bin'):
        shutil.copy2(vanilla / name, assets / name)
    write_json(out / 'manifest.json', {
        'fixture': 'Falco, DK Ult, J Pikachu, J Mario, J Falcon, J Luigi and J DK selectable beside their vanilla parents in VS; not the complete mod',
        'motion_count': len(motion), 'menu_motion_count': len(menus),
        'script_words': len(scripts.words), 'script_pointers': len(scripts.pointers),
        'dkult_motion_count': len(dk_motion), 'dkult_menu_motion_count': len(dk_menus),
        'dkult_script_words': len(dk_scripts.words),
        'dkult_script_pointers': len(dk_scripts.pointers),
        'jpika_motion_count': len(jp_motion), 'jpika_menu_motion_count': len(jp_menus),
        'jpika_script_words': len(jp_scripts.words),
        'jpika_script_pointers': len(jp_scripts.pointers),
        'jmario_motion_count': len(mario_motion), 'jmario_menu_motion_count': len(mario_menus),
        'jmario_script_words': len(mario_scripts.words),
        'jmario_script_pointers': len(mario_scripts.pointers),
        'jfalcon_motion_count': len(falcon_motion), 'jfalcon_menu_motion_count': len(falcon_menus),
        'jfalcon_script_words': len(falcon_scripts.words),
        'jfalcon_script_pointers': len(falcon_scripts.pointers),
        'jluigi_motion_count': len(luigi_motion), 'jluigi_menu_motion_count': len(luigi_menus),
        'jluigi_script_words': len(luigi_scripts.words),
        'jluigi_script_pointers': len(luigi_scripts.pointers),
        'jdk_motion_count': len(jdk_motion), 'jdk_menu_motion_count': len(jdk_menus),
        'jdk_script_words': len(jdk_scripts.words),
        'jdk_script_pointers': len(jdk_scripts.pointers),
        'required_files': sorted(required), 'unresolved_relocations': bad,
        'pack_sha256': sha256(assets / 'reloc.pak'),
    })
    print(f'Falco, DK Ult, J Pikachu, J Mario, J Falcon, J Luigi and J DK: {len(motion)} + {len(dk_motion)} + {len(jp_motion)} + {len(mario_motion)} + {len(falcon_motion)} + {len(luigi_motion)} + {len(jdk_motion)} actions, {len(required)} validated assets')


if __name__ == '__main__':
    main()
