"""Import the final assembled Remix +EXTRA stage tables for native ARM use.

Source declarations stop at the base Remix roster. The final ROM also has
+EXTRA rows, so infer the count from three independent compiled table spans
and reject disagreement. Stage setup routines are classified, never executed
as MIPS pointers by the 3DS port.
"""

import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from common import BUILD, ROOT, sha256, write_json


BASE_STAGE_FILE_ROM = 0xA7D20
BASE_STAGE_SETUP_RAM = 0x8012E840
BASE_RAM = 0x80084800
VANILLA_STAGE_COUNT = 41
VANILLA_SETUP_COUNT = 9
CLONE_SETUP = 0x801056F8
STAGE_SYMBOLS = {
    'files': ('Stages.stage_file_table', 'Stages.class_table', 8),
    'setup': ('Stages.function_table', 'Stages.icon_offset_table', 4),
    'music': ('Stages.alternate_music_table', 'Stages.variant_table', 8),
}


def stage_count(ref):
    spans = {}
    for label, (begin, end, width) in STAGE_SYMBOLS.items():
        size = ref.symbols[end] - ref.symbols[begin]
        if size <= 0 or size % width:
            raise ValueError(f'Invalid compiled {label} stage-table span')
        spans[label] = size // width
    if len(set(spans.values())) != 1 or not VANILLA_STAGE_COUNT < spans['files'] <= 256:
        raise ValueError(f'Compiled stage-table counts disagree: {spans}')
    return spans['files']


def packed_rows(ref, address, count, format_):
    width = struct.calcsize('>' + format_)
    offset = ref.rom_base + address - ref.ram_base
    if offset < 0 or offset + count * width > len(ref.rom):
        raise ValueError(f'Unmapped compiled stage table at {address:08x}')
    return [struct.unpack_from('>' + format_, ref.rom, offset + i * width)
            for i in range(count)]


def extract_stages(ref, original, asset_manifest, music_sequences):
    count = stage_count(ref)
    files = packed_rows(ref, ref.symbols[STAGE_SYMBOLS['files'][0]], count, 'II')
    setups = ref.words(ref.symbols[STAGE_SYMBOLS['setup'][0]], count)
    classes = packed_rows(ref, ref.symbols['Stages.class_table'], count, 'B')
    defaults = packed_rows(ref, ref.symbols['Stages.default_music_track_table'], count, 'H')
    alternates = packed_rows(ref, ref.symbols[STAGE_SYMBOLS['music'][0]], count, 'hhhh')
    vanilla_files = struct.unpack_from('>' + 'I' * (2 * VANILLA_STAGE_COUNT),
                                       original, BASE_STAGE_FILE_ROM)
    if tuple(value for row in files[:VANILLA_STAGE_COUNT] for value in row) != vanilla_files:
        raise ValueError('Compiled original stage file rows differ from the base ROM')
    vanilla_setups = struct.unpack_from('>9I', original,
                                       BASE_STAGE_SETUP_RAM - BASE_RAM)
    if tuple(setups[:VANILLA_SETUP_COUNT]) != vanilla_setups:
        raise ValueError('Compiled original stage setup functions differ from the base ROM')
    if len(set(vanilla_setups)) != VANILLA_SETUP_COUNT:
        raise ValueError('Original stage setup functions are not distinct')
    assets = asset_manifest['entries']
    if asset_manifest['summary']['source_rom_sha256'] != sha256(ref.path):
        raise ValueError('Stage assets and assembled ROM differ')
    rows = []
    for stage_id, ((file_id, header_offset), setup, stage_class,
                   default, alternate) in enumerate(zip(files, setups, classes, defaults, alternates)):
        stage_class = stage_class[0]
        default = default[0]
        if (not 0 <= file_id < len(assets) or header_offset not in (0, 20) or
                stage_class > 4 or not 0 <= default <= music_sequences or
                any(track != -1 and not 0 <= track < music_sequences for track in alternate)):
            raise ValueError(f'Invalid compiled stage row {stage_id}')
        if file_id and header_offset + 4 > assets[file_id]['size']:
            raise ValueError(f'Stage {stage_id} header outside asset {file_id}')
        if not file_id and stage_id < VANILLA_STAGE_COUNT:
            raise ValueError(f'Original stage {stage_id} lacks its header')
        setup_kind = (vanilla_setups.index(setup) + 1 if setup in vanilla_setups else
                      0 if setup == CLONE_SETUP else 255)
        rows.append({'id': stage_id, 'header_file_id': file_id,
                     'header_offset': header_offset, 'setup_address': f'{setup:08x}',
                     'setup_kind': setup_kind, 'class': stage_class,
                     'default_music_plus_one': default, 'alternate_music': list(alternate)})
    return rows


def stage_asset_closure(rows, manifest):
    entries = manifest['entries']
    required = set()

    def add(file_id):
        if not file_id or file_id in required:
            return
        if not 0 <= file_id < len(entries):
            raise ValueError(f'Stage dependency {file_id} is outside asset pack')
        required.add(file_id)
        for dep in entries[file_id]['external_files']:
            add(dep)

    for row in rows:
        add(row['header_file_id'])
    issues = [issue for issue in manifest['relocation_issues']
              if issue['file_id'] in required]
    if issues:
        raise ValueError(f'Stage assets have unresolved relocations: {issues}')
    return sorted(required)


def render_native(rows):
    lines = ['/* Private compiled Remix +EXTRA stage rows; generated from the pinned ROM. */',
             'const NativeRemixStageRecord native_remix_stages[] = {']
    for row in rows:
        alt = ', '.join(str(track) for track in row['alternate_music'])
        lines.append('    {' + ', '.join((str(row['header_file_id']),
                                     str(row['header_offset']), str(row['setup_kind']),
                                     str(row['class']), str(row['default_music_plus_one']),
                                     '{' + alt + '}')) + '},')
    lines += ['};', f'const unsigned native_remix_stage_count = {len(rows)}u;', '']
    return '\n'.join(lines)


def write_stage_tables(ref, asset_manifest, out):
    config = json.loads((ROOT / '3ds/build-config.json').read_text())
    meta = json.loads((BUILD / 'reference.json').read_text())
    original = Path(config['rom']).read_bytes()
    if hashlib.sha1(original).hexdigest() != meta['base_rom_sha1']:
        raise ValueError('Original ROM does not match the pinned reference')
    audio = json.loads((BUILD / 'audio/manifest.json').read_text())
    rows = extract_stages(ref, original, asset_manifest, audio['music_sequence_count'])
    required = stage_asset_closure(rows, asset_manifest)
    native = render_native(rows)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'native_stage_tables.inc').write_text(native)
    report = {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
              'stage_count': len(rows), 'base_stage_rows': VANILLA_STAGE_COUNT,
              'extra_stage_rows': len(rows) - 216,
              'setup_kinds': dict(Counter(str(row['setup_kind']) for row in rows)),
              'required_stage_files': required,
              'compiled_rows': rows,
              'scope': 'Compiled stage data and asset closure only; custom hazards and full stage gameplay are not ported.'}
    write_json(BUILD / 'native-stage-tables.json', report)
    return report


if __name__ == '__main__':
    from prepare_fighter_probe import Reference

    ref = Reference()
    manifest = json.loads((BUILD / 'assets/manifest.json').read_text())
    result = write_stage_tables(ref, manifest, BUILD / 'fighter-probe')
    print(result['stage_count'], 'compiled stage rows,',
          len(result['required_stage_files']), 'validated stage files')
