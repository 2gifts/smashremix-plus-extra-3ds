"""Generate private ARM-side motion data for structurally importable fighters.

Generated files contain derived ROM data and remain under remix/build/. They
are not linked into a release until each fighter's status callbacks, engine
hooks, assets, menu identity, and gameplay have been ported and verified.
"""

import json
from pathlib import Path

from common import BUILD, sha256, write_json
from audit_reference_fighters import known_native_script_symbols
from prepare_fighter_probe import Reference, Scripts


def export_fighter(ref, record, external_scripts, directory):
    name = record['name']
    prefix = f'remix_{name.lower()}'
    data = ref.words(ref.symbols[f'Character.{name}_character_struct'], 30)
    main = [ref.words(data[25] + i * 12, 3) for i in range(data[27])]
    menu_count = ref.words(data[28], 1)[0]
    menu = [ref.words(data[26] + i * 12, 3) for i in range(menu_count)]
    scripts = Scripts(ref, allow_custom=True, external_scripts=external_scripts)
    entrypoints = {row[1] for row in main + menu if row[1] > 0x80000000}
    for address in sorted(entrypoints):
        scripts.script(address)
    lines, indices = scripts.emit(prefix, entrypoints)

    def command_pointer(address):
        if address in external_scripts:
            return f'(intptr_t){external_scripts[address]}'
        if address > 0x80000000:
            return f'(intptr_t)&{prefix}_script_words[{indices[address]}]'
        return f'(intptr_t)0x{address:08x}u'

    for label, rows in (('main', main), ('menu', menu)):
        lines.append(f'static FTMotionDesc {prefix}_{label}_motions[] = {{')
        for fid, pointer, flags in rows:
            lines.append(f'    {{{fid}, {command_pointer(pointer)}, {{.word = 0x{flags:08x}u}}}},')
        lines.append('};')
    lines += [f'static const u32 {prefix}_files[9] = {{{", ".join(map(str, data[:9]))}}};',
              f'static s32 {prefix}_menu_count = {menu_count};',
              f'#define {prefix.upper()}_ATTRIBUTE_OFFSET 0x{data[24]:x}']
    path = directory / f'{name.lower()}.inc'
    path.write_text('\n'.join(lines) + '\n')
    return {'name': name, 'fkind': record['fkind'], 'parent': record['parent'],
            'source': path.name, 'bytes': path.stat().st_size,
            'sha256': sha256(path), 'script_words': len(scripts.words),
            'native_callbacks_ported': False}


def main():
    ref = Reference()
    audit = json.loads((BUILD / 'fighter-audit.json').read_text())
    reference_hash = json.loads((BUILD / 'reference.json').read_text())['rom_sha256']
    if audit['reference_rom_sha256'] != reference_hash:
        raise ValueError('Fighter audit uses a different reference build')
    output = BUILD / 'fighter-catalog'
    output.mkdir(parents=True, exist_ok=True)
    external_scripts = known_native_script_symbols()
    generated = []
    for record in audit['fighters']:
        if record['fixture_data_ready']:
            generated.append(export_fighter(ref, record, external_scripts, output))
    write_json(output / 'manifest.json', {
        'schema': 1, 'reference_rom_sha256': reference_hash,
        'generated_fighters': len(generated),
        'not_generated': [r['name'] for r in audit['fighters'] if not r['fixture_data_ready']],
        'runtime_roster_enabled': False,
        'fighters': generated,
    })
    print(f'Generated {len(generated)} structurally importable native motion sets; none enabled in the roster.')


if __name__ == '__main__':
    main()
