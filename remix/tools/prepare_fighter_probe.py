"""Extract a native fighter integration fixture from the pinned reference build.

This is deliberately separate from release packaging. Falco occupies the Fox
slot in this fixture, while menus and all other fighters remain vanilla. No ROM
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


def main():
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
    for fid in data[:9] + [r[0] for r in motion + menus]:
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
        'fixture': 'Falco in Fox slot; not the complete Remix mod',
        'motion_count': len(motion), 'menu_motion_count': len(menus),
        'script_words': len(scripts.words), 'script_pointers': len(scripts.pointers),
        'required_files': sorted(required), 'unresolved_relocations': bad,
        'pack_sha256': sha256(assets / 'reloc.pak'),
    })
    print(f'Falco: {len(motion)} actions, {len(scripts.words)} script words, {len(required)} validated assets')


if __name__ == '__main__':
    main()
