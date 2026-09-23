"""Audit every assembled +EXTRA fighter before importing it into ARM code.

The report is local build evidence, not a playable roster. It uses the final
ROM's character table rather than assuming source declaration order or IDs.
"""

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path

from common import BUILD, ROOT, sha256, write_json
from prepare_fighter_probe import Reference, Scripts


STRUCT_TABLE_ROM = 0x92610
FIRST_NEW_FKIND = 27  # Random occupies 27; 28 is unused; roster resumes at 29.
NATIVE_CUSTOM_COMMANDS = set(range(0xd0, 0xdf))
ORIGINAL_STRUCT_TABLE_ROM = 0x92610
ORIGINAL_ACTION_TABLE_ROM = 0xA6F40
ORIGINAL_RAM_BASE = 0x80084800
VANILLA_FKINDS = {'MARIO': 0, 'FOX': 1, 'DONKEY': 2, 'SAMUS': 3,
                  'LUIGI': 4, 'LINK': 5, 'YOSHI': 6, 'CAPTAIN': 7,
                  'KIRBY': 8, 'PIKACHU': 9, 'JIGGLYPUFF': 10, 'NESS': 11}


class ActionTableAudit:
    """Compare assembled mod action callbacks against the original parent.

    Each N64 special-action record is five words: flags followed by update,
    interrupt, physics and map callbacks. Generic ARM registration clones the
    parent's native table, so a changed record cannot silently be called ported.
    """

    def __init__(self, ref, source):
        meta = json.loads((BUILD / 'reference.json').read_text())
        config = json.loads((ROOT / '3ds/build-config.json').read_text())
        original = Path(config['rom']).read_bytes()
        if hashlib.sha1(original).hexdigest() != meta['base_rom_sha1']:
            raise ValueError('Original ROM does not match the pinned reference')
        self.original = original
        self.ref = ref
        block = re.search(r'scope action_array_size\s*\{([^}]*)\}', source)
        if block is None:
            raise ValueError('Missing parent action-array sizes')
        sizes = {name: int(value, 16) for name, value in
                 re.findall(r'constant\s+(\w+)\(0x([0-9A-Fa-f]+)\)', block.group(1))}
        self.sizes = {name: sizes[name] for name in VANILLA_FKINDS}
        if any(size % 20 for size in self.sizes.values()):
            raise ValueError('Parent action-array size is not a multiple of 20')

    def word(self, offset):
        if not 0 <= offset <= len(self.original) - 4:
            raise ValueError(f'Original ROM offset outside file: {offset:#x}')
        return struct.unpack_from('>I', self.original, offset)[0]

    def parent_data(self, name):
        fkind = VANILLA_FKINDS[name]
        struct_addr = self.word(ORIGINAL_STRUCT_TABLE_ROM + fkind * 4)
        struct_offset = struct_addr - ORIGINAL_RAM_BASE
        action_addr = self.word(ORIGINAL_ACTION_TABLE_ROM + fkind * 4)
        action_offset = action_addr - ORIGINAL_RAM_BASE
        size = self.sizes[name]
        count = self.word(struct_offset + 0x6c)
        if not 0 < count <= 512 or not 0 <= action_offset <= len(self.original) - size:
            raise ValueError(f'Invalid original action table for {name}')
        return count, struct.unpack_from('>' + str(size // 4) + 'I', self.original, action_offset)

    def audit(self, name, parent, new_motion_count):
        old_motion_count, old = self.parent_data(parent)
        added = new_motion_count - old_motion_count
        if not 0 <= added <= 256:
            raise ValueError(f'{name}: invalid added action count {added}')
        action_addr = self.ref.symbols[f'Character.{name}_action_array']
        menu_addr = self.ref.symbols[f'Character.{name}_menu_array']
        size = self.sizes[parent] + added * 20
        if not size <= menu_addr - action_addr <= size + 15:
            raise ValueError(f'{name}: action array length disagrees with character struct')
        words = self.ref.words(action_addr, size // 4)
        changed = []
        callback_names = ('update', 'interrupt', 'physics', 'map')
        for i in range(self.sizes[parent] // 20):
            original = old[i * 5:(i + 1) * 5]
            revised = words[i * 5:(i + 1) * 5]
            if tuple(original) != tuple(revised):
                changed.append({
                    'status_id': 0xdc + i,
                    'flags': {'original': f'{original[0]:08x}', 'remix': f'{revised[0]:08x}'
                              } if original[0] != revised[0] else None,
                    'callbacks': {callback_names[j]: {'original': f'{original[j + 1]:08x}',
                                                       'remix': f'{revised[j + 1]:08x}'}
                                  for j in range(4) if original[j + 1] != revised[j + 1]},
                })
        return {'inherited_statuses': self.sizes[parent] // 20,
                'added_statuses': added,
                'added_status_records': [
                    {'status_id': 0xdc + self.sizes[parent] // 20 + i,
                     'words': [f'{word:08x}' for word in words[start:start + 5]]}
                    for i in range(added)
                    for start in [self.sizes[parent] // 4 + i * 5]],
                'changed_inherited_statuses': changed,
                'generic_action_table_compatible': not added and not changed}


def callback_worklist(ref, fighters):
    """Group mod-owned action callbacks by target, not by fighter slot."""
    uses = {}
    roles = ('update', 'interrupt', 'physics', 'map')
    for fighter in fighters:
        table = fighter['action_table']
        for status in table['changed_inherited_statuses']:
            for role, callback in status['callbacks'].items():
                target = int(callback['remix'], 16)
                if target >= ref.ram_base:
                    uses.setdefault(target, []).append({'fighter': fighter['name'],
                                                         'status_id': status['status_id'], 'role': role})
        for status in table['added_status_records']:
            for role, word in zip(roles, status['words'][1:]):
                target = int(word, 16)
                if target >= ref.ram_base:
                    uses.setdefault(target, []).append({'fighter': fighter['name'],
                                                         'status_id': status['status_id'], 'role': role})
    symbol_names = {}
    for name, address in ref.symbols.items():
        if address in uses:
            symbol_names.setdefault(address, []).append(name)
    missing = uses.keys() - symbol_names.keys()
    if missing:
        raise ValueError(f'{len(missing)} action callback targets lack reference symbols')
    return {'reference_rom_sha256': sha256(ref.path),
            'unique_expansion_targets': len(uses),
            'targets': [{'address': f'{address:08x}', 'symbols': symbol_names[address],
                         'uses': entries}
                        for address, entries in sorted(uses.items(),
                                                       key=lambda item: (-len(item[1]), item[0]))]}


def dependency_closure(entries, roots):
    found = set()
    pending = list(roots)
    while pending:
        fid = pending.pop()
        if not fid or fid in found:
            continue
        if not 0 <= fid < len(entries):
            raise ValueError(f'File ID {fid} exceeds the reference pack')
        found.add(fid)
        pending.extend(entries[fid]['external_files'])
    return found


def known_native_script_symbols():
    symbols = {}
    for path in (ROOT / 'src/sc/scsubsys').glob('*.c'):
        for address in re.findall(r'(?m)^\s*s32\s+D_ovl1_(803[0-9A-F]{5})\[\]', path.read_text()):
            symbols[int(address, 16)] = f'D_ovl1_{address}'
    return symbols


def audit_fighter(ref, name, fkind, manifest, issue_map, origin, external_scripts, actions):
    data = ref.words(ref.symbols[f'Character.{name}_character_struct'], 30)
    if not 0 < data[27] <= 512:
        raise ValueError(f'{name}: invalid main motion count {data[27]}')
    menu_count = ref.words(data[28], 1)[0]
    if not 0 < menu_count <= 64:
        raise ValueError(f'{name}: invalid menu motion count {menu_count}')
    main = [ref.words(data[25] + i * 12, 3) for i in range(data[27])]
    menu = [ref.words(data[26] + i * 12, 3) for i in range(menu_count)]
    roots = data[:9] + [row[0] for row in main + menu]
    required = dependency_closure(manifest['entries'], roots)
    scripts = Scripts(ref, allow_custom=True, external_scripts=external_scripts)
    failures = Counter()
    pointers = set()
    for _, pointer, _ in main + menu:
        # 0x80000000 is the engine's "no command stream" sentinel.
        if pointer > 0x80000000:
            pointers.add(pointer)
    for pointer in sorted(pointers):
        try:
            scripts.script(pointer)
        except ValueError as exc:
            # Keep auditing the rest of the roster. Unmapped parent-overlay
            # pointers and new commands both need explicit native handling.
            failures[str(exc).split(' at ')[0]] += 1
    issues = [issue for fid in sorted(required) for issue in issue_map[fid]]
    return {
        'name': name, 'fkind': fkind, 'origin': origin,
        'parent': origin['parent'], 'files': data[:9],
        'attribute_offset': data[24],
        'action_table': actions.audit(name, origin['parent'], data[27]),
        'main_motions': len(main), 'menu_motions': len(menu),
        'script_entrypoints': len(pointers),
        'decoded_script_words': len(scripts.words),
        'script_pointer_fixups': len(scripts.pointers),
        'custom_commands': {f'{byte:02x}': count for byte, count in sorted(scripts.custom_commands.items())},
        'unported_custom_commands': [f'{byte:02x}' for byte in sorted(scripts.custom_commands)
                                     if byte not in NATIVE_CUSTOM_COMMANDS],
        'script_failures': dict(sorted(failures.items())),
        'asset_closure_count': len(required),
        'asset_closure_bytes': sum(manifest['entries'][fid]['size'] for fid in required),
        'asset_relocation_issues': issues,
        'fixture_data_ready': not failures and not issues,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BUILD / 'fighter-audit.json')
    args = parser.parse_args()
    ref = Reference()
    asset_manifest = json.loads((BUILD / 'assets/manifest.json').read_text())
    issue_map = {fid: [] for fid in range(len(asset_manifest['entries']))}
    for issue in asset_manifest['relocation_issues']:
        issue_map[issue['file_id']].append(issue)
    external_scripts = known_native_script_symbols()
    source = ref.path.with_name('src') / 'Character.asm'
    source_text = source.read_text()
    definitions = re.findall(r'(?m)^\s*define_character\((\w+),\s*(\w+),', source_text)
    if len(definitions) != len(set(name for name, _ in definitions)):
        raise ValueError('Duplicate character definitions in final source')
    extra_names = {path.name.upper() for path in (ROOT / 'remix/upstream/extra_characters').iterdir()
                   if path.is_dir() and (path / 'config.yaml').exists()}
    names = {name: {'parent': parent, 'mod': 'plus_extra' if name in extra_names else 'base_remix'}
             for name, parent in definitions}
    symbolic = {address: name for name in names
                if (address := ref.symbols.get(f'Character.{name}_character_struct')) is not None}
    if len(symbolic) != len(names):
        raise ValueError(f'Missing {len(names) - len(symbolic)} character symbols')
    fighters = []
    actions = ActionTableAudit(ref, source_text)
    final_fkind = FIRST_NEW_FKIND + len(names) + 1
    for fkind in (FIRST_NEW_FKIND, *range(FIRST_NEW_FKIND + 2, final_fkind)):
        address = int.from_bytes(ref.rom[STRUCT_TABLE_ROM + 4 * fkind:STRUCT_TABLE_ROM + 4 * fkind + 4], 'big')
        name = symbolic.get(address)
        if name is None:
            raise ValueError(f'Unknown character table entry {fkind}: {address:08x}')
        fighters.append(audit_fighter(ref, name, fkind, asset_manifest, issue_map, names[name], external_scripts, actions))
    if len({fighter['name'] for fighter in fighters}) != len(names):
        raise ValueError('Character table has duplicate or missing fighters')
    worklist = callback_worklist(ref, fighters)
    write_json(BUILD / 'action-callback-worklist.json', worklist)
    summary = {
        'new_fighters': len(fighters),
        'plus_extra_fighters': sum(f['origin']['mod'] == 'plus_extra' for f in fighters),
        'fixture_data_ready': sum(f['fixture_data_ready'] for f in fighters),
        'script_failures': sum(sum(f['script_failures'].values()) for f in fighters),
        'fighters_with_relocation_issues': sum(bool(f['asset_relocation_issues']) for f in fighters),
        'fighters_requiring_more_custom_commands': sum(bool(f['unported_custom_commands']) for f in fighters),
        'fighters_with_unported_action_table_changes': sum(not f['action_table']['generic_action_table_compatible'] for f in fighters),
        'data_ready_with_inherited_action_tables': sum(f['fixture_data_ready'] and
                                                       f['action_table']['generic_action_table_compatible'] for f in fighters),
        'unique_expansion_action_callback_targets': worklist['unique_expansion_targets'],
        'native_gameplay_implemented': 0,
    }
    write_json(args.output, {'schema': 2, 'audit_script_sha256': sha256(Path(__file__)),
                             'reference_rom_sha256': json.loads((BUILD / 'reference.json').read_text())['rom_sha256'],
                             'summary': summary, 'fighters': fighters})
    print(json.dumps(summary, indent=2))
    print(f'Report: {args.output}')


if __name__ == '__main__':
    main()
