"""Audit every assembled +EXTRA fighter before importing it into ARM code.

The report is local build evidence, not a playable roster. It uses the final
ROM's character table rather than assuming source declaration order or IDs.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from common import BUILD, ROOT, write_json
from prepare_fighter_probe import Reference, Scripts


STRUCT_TABLE_ROM = 0x92610
FIRST_NEW_FKIND = 27  # Random occupies 27; 28 is unused; roster resumes at 29.
NATIVE_CUSTOM_COMMANDS = set(range(0xd0, 0xdf))


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


def audit_fighter(ref, name, fkind, manifest, issue_map, origin, external_scripts):
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
    definitions = re.findall(r'(?m)^\s*define_character\((\w+),\s*(\w+),', source.read_text())
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
    final_fkind = FIRST_NEW_FKIND + len(names) + 1
    for fkind in (FIRST_NEW_FKIND, *range(FIRST_NEW_FKIND + 2, final_fkind)):
        address = int.from_bytes(ref.rom[STRUCT_TABLE_ROM + 4 * fkind:STRUCT_TABLE_ROM + 4 * fkind + 4], 'big')
        name = symbolic.get(address)
        if name is None:
            raise ValueError(f'Unknown character table entry {fkind}: {address:08x}')
        fighters.append(audit_fighter(ref, name, fkind, asset_manifest, issue_map, names[name], external_scripts))
    if len({fighter['name'] for fighter in fighters}) != len(names):
        raise ValueError('Character table has duplicate or missing fighters')
    summary = {
        'new_fighters': len(fighters),
        'plus_extra_fighters': sum(f['origin']['mod'] == 'plus_extra' for f in fighters),
        'fixture_data_ready': sum(f['fixture_data_ready'] for f in fighters),
        'script_failures': sum(sum(f['script_failures'].values()) for f in fighters),
        'fighters_with_relocation_issues': sum(bool(f['asset_relocation_issues']) for f in fighters),
        'fighters_requiring_more_custom_commands': sum(bool(f['unported_custom_commands']) for f in fighters),
        'native_gameplay_implemented': 0,
    }
    write_json(args.output, {'schema': 1, 'reference_rom_sha256': json.loads((BUILD / 'reference.json').read_text())['rom_sha256'],
                             'summary': summary, 'fighters': fighters})
    print(json.dumps(summary, indent=2))
    print(f'Report: {args.output}')


if __name__ == '__main__':
    main()
