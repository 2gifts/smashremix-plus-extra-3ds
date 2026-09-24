"""Extract a native fighter integration fixture from the pinned reference build.

This is deliberately separate from release packaging. Integrated fighters are
selectable via their parent bottom-screen cards in VS mode. No ROM
addresses are executed: motion bytecode is decoded and its pointers relocated,
and special callbacks are supplied by native C implementations.
"""
import argparse
import json
import re
import shutil
import struct
from collections import Counter
from pathlib import Path
from common import BUILD, ROOT, checked_sources, sha256, write_json
from native_fighter_catalog import load_catalog, render_generic_data, render_header, render_ui, validate_reference, HEADER, UI
from reference_table_patches import extract_table_patches, write_reference_tables
from native_fireball_patches import write_fireballs
from native_kirby_patches import write_kirby_rows
from native_results_patches import write_results_patches
from native_crowd_patches import write_crowd_chants
from native_hit_sound_patches import write_hit_sounds
from native_entry_patches import write_entry_effects
from native_patch_worklist import write_worklist
from native_action_patches import (action_table_bindable, load_bindings,
                                   write_action_patches)
from classify_action_callbacks import classify as classify_action_callbacks
from native_transition_templates import write_native_transitions
from native_variant_metadata import write_variant_metadata
from native_anim_end_templates import write_native_anim_ends
from native_guarded_original_callbacks import write_guarded_original_callbacks
from native_stage_tables import write_stage_tables
from native_auto_roster import write_auto_catalog
from native_lucas_air_move import write_lucas_air_move
from native_special_dispatch import (dispatch_bindings, extract_special_dispatch,
                                     write_special_dispatch)


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
        self.null_subroutines = set()

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
            if op == 13:
                operand = self.ref.words(address + 4, 1)[0]
                raise ValueError(f'Unsupported SetDamageThrown operand {operand:08x} at {address:08x}')
            if op > 51 and not known_custom:
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
                    if op == 34 and word == 34 << 26:
                        # The compiled subroutine command may have a zero
                        # operand. The native event loop then ends this script;
                        # there is no target to visit or relocate.
                        self.null_subroutines.add(address)
                        return
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--auto-bindable', action='store_true',
                        help='Include all structurally bindable fighters in a private test roster')
    args = parser.parse_args()
    from audit_reference_fighters import known_native_script_symbols
    ref = Reference()
    catalog = load_catalog()
    audit = json.loads((BUILD / 'fighter-audit.json').read_text())
    out = BUILD / 'fighter-probe'
    out.mkdir(exist_ok=True)
    worklist = json.loads((BUILD / 'action-callback-worklist.json').read_text())
    families = classify_action_callbacks(ref, worklist)
    native_transitions = write_native_transitions(ref, families, out)
    auto_bindings = {int(row['address'], 16): row['native']
                     for row in native_transitions['wrappers']}
    native_anim_ends = write_native_anim_ends(ref, worklist, out)
    for row in native_anim_ends['wrappers']:
        address = int(row['address'], 16)
        if address in auto_bindings:
            raise ValueError(f'Duplicate generated action callback {address:08x}')
        auto_bindings[address] = row['native']
    guarded_originals = write_guarded_original_callbacks(ref, worklist, out)
    for row in guarded_originals['accepted']:
        address = int(row['address'], 16)
        if address in auto_bindings:
            raise ValueError(f'Duplicate guarded original callback {address:08x}')
        auto_bindings[address] = row['native']
    lucas_air_move = write_lucas_air_move(ref, out)
    lucas_address = int(lucas_air_move['address'], 16)
    if lucas_address in auto_bindings:
        raise ValueError(f'Duplicate generated action callback {lucas_address:08x}')
    auto_bindings[lucas_address] = lucas_air_move['native']
    write_json(BUILD / 'native-generated-action-bindings.json', {
        'schema': 1,
        'reference_rom_sha256': sha256(ref.path),
        'bindings': [{'address': f'{address:08x}', 'native': native}
                     for address, native in sorted(auto_bindings.items())],
    })
    _, bindings = load_bindings(symbols=ref.symbols)
    bindings.update(auto_bindings)
    bindable = {row['name'] for row in audit['fighters']
                if action_table_bindable(row, bindings)}
    if args.auto_bindable:
        table_source = (ref.path.with_name('src') / 'Character.asm').read_text()
        compiled_tables = extract_table_patches(ref, audit, table_source)
        special_manifest = extract_special_dispatch(ref, compiled_tables)
        catalog, auto_report = write_auto_catalog(
            catalog, audit, bindings, compiled_tables, out / 'auto-roster.json',
            dispatch_bindings(special_manifest))
        auto_include = out / 'auto-include'
        auto_include.mkdir(exist_ok=True)
        (auto_include / HEADER.name).write_text(render_header(catalog))
        (auto_include / UI.name).write_text(render_ui(catalog))
    validate_reference(catalog, BUILD / 'fighter-audit.json', sha256(ref.path), bindable)
    if not args.auto_bindable and (HEADER.read_text() != render_header(catalog) or
                                   UI.read_text() != render_ui(catalog)):
        raise ValueError('Native fighter tables are stale; run native_fighter_catalog.py')
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
    write_action_patches(ref, audit, catalog, out, auto_bindings=auto_bindings)
    (out / 'falco_data.inc').write_text('\n'.join(lines) + '\n')

    # Custom fighters use the same compiled-data path as generic variants;
    # their move callbacks and selection bridges remain separate native code.
    native_scripts = known_native_script_symbols()
    dk_data, dk_motion, dk_menus, dk_scripts = emit_variant(ref, 'DKULT', native_scripts, out)
    jp_data, jp_motion, jp_menus, jp_scripts = emit_variant(ref, 'JPIKA', native_scripts, out)

    generic = {row['name']: emit_variant(ref, row['name'], native_scripts, out)
               for row in catalog['fighters'] if row['registration'] == 'generic'}
    if not args.auto_bindable:
        table_source = (ref.path.with_name('src') / 'Character.asm').read_text()
        compiled_tables = extract_table_patches(ref, audit, table_source)
    special_manifest = write_special_dispatch(ref, compiled_tables, catalog, out)
    special_bindings = dispatch_bindings(special_manifest)
    table_manifest = write_reference_tables(ref, audit, catalog, out, special_bindings)
    write_variant_metadata(ref, table_manifest, out)
    fireball_manifest = write_fireballs(ref, table_manifest, audit, catalog, out)
    write_kirby_rows(ref, table_manifest, audit, out)
    _, winner_voices, _ = write_results_patches(ref, table_manifest, audit, out)
    crowd_chants = write_crowd_chants(ref, table_manifest, audit, out)
    write_hit_sounds(ref, table_manifest, audit, out)
    entry_effects = write_entry_effects(ref, table_manifest, audit, out)
    write_worklist(audit, table_manifest, fireball_manifest, catalog, entry_effects)
    (out / 'generic_variants_data.inc').write_text(render_generic_data(catalog))

    # Keep the proven vanilla UI assets. Add only the validated dependency
    # closure required by enabled fighters, never ship unresolved reference files.
    config = json.loads((ROOT / '3ds/build-config.json').read_text())
    if 'vanilla_assets' in config:
        vanilla = Path(config['vanilla_assets']).resolve()
    else:
        battleship = Path(config.get('battleship', ROOT / '3ds/vendor/BattleShip')).resolve()
        vanilla = battleship.parents[1] / 'assets'
    base = (vanilla / 'reloc.pak').read_bytes()
    expansion = (BUILD / 'assets/reloc.reference.pak').read_bytes()
    from prepare_reference_audio import main as prepare_audio
    prepare_audio()
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
    rows = [(data, motion, menus), (dk_data, dk_motion, dk_menus), (jp_data, jp_motion, jp_menus)]
    rows += [(record[0], record[1], record[2]) for record in generic.values()]
    for fid in [fid for fighter_data, fighter_motion, fighter_menus in rows
                for fid in fighter_data[:9] + [row[0] for row in fighter_motion + fighter_menus]]:
        add(fid)
    stage_report = write_stage_tables(ref, manifest, out)
    for fid in stage_report['required_stage_files']:
        add(fid)
    # The mod extends the shared results announcer file with the ampersand
    # glyph used by Banjo's compiled winner string.
    if entries[0x25]['size'] < 0x8358 + 0x40:
        raise ValueError('Compiled announcer asset lacks the ampersand sprite')
    add(0x25)
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
    if json.loads((BUILD / 'audio/manifest.json').read_text())['fgm_microcode_count'] != winner_voices['fgm_microcode_count']:
        raise ValueError('Winner voice IDs and native audio package disagree')
    if crowd_chants['fgm_microcode_count'] != winner_voices['fgm_microcode_count']:
        raise ValueError('Crowd chant IDs and native audio package disagree')
    for path in (BUILD / 'audio').glob('*.bin'):
        shutil.copy2(path, assets / 'audio' / path.name)
    for name in ('initial-save.bin', 'bottom-ui.bin'):
        shutil.copy2(vanilla / name, assets / name)
    metrics = {}
    for name, (fighter_data, fighter_motion, fighter_menus, fighter_scripts) in generic.items():
        key = name.lower()
        metrics.update({f'{key}_motion_count': len(fighter_motion),
                        f'{key}_menu_motion_count': len(fighter_menus),
                        f'{key}_script_words': len(fighter_scripts.words),
                        f'{key}_script_pointers': len(fighter_scripts.pointers)})
    write_json(out / 'manifest.json', {
        'fixture': f"{len(catalog['fighters'])} independently backed fighters selectable beside vanilla parents in VS; not the complete mod",
        'motion_count': len(motion), 'menu_motion_count': len(menus),
        'script_words': len(scripts.words), 'script_pointers': len(scripts.pointers),
        'dkult_motion_count': len(dk_motion), 'dkult_menu_motion_count': len(dk_menus),
        'dkult_script_words': len(dk_scripts.words),
        'dkult_script_pointers': len(dk_scripts.pointers),
        'jpika_motion_count': len(jp_motion), 'jpika_menu_motion_count': len(jp_menus),
        'jpika_script_words': len(jp_scripts.words),
        'jpika_script_pointers': len(jp_scripts.pointers),
        **metrics,
        'required_files': sorted(required), 'unresolved_relocations': bad,
        'compiled_stage_rows': stage_report['stage_count'],
        'required_stage_files': len(stage_report['required_stage_files']),
        'auto_bindable_candidates': auto_report['candidate_count'] if args.auto_bindable else 0,
        'pack_sha256': sha256(assets / 'reloc.pak'),
    })
    print(f"{len(catalog['fighters'])} fighters: {sum(len(row[1]) for row in rows)} actions, {len(required)} validated assets")


if __name__ == '__main__':
    main()
