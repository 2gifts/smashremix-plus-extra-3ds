"""Decode compiled results-screen patch families for native presentation.

The N64 mod stores MIPS routine pointers in Character.winner_bgm rather than
plain track IDs. Recognize the exact add_victory_bgm macro output and carry
only its immediate BGM ID into the ARM build. Other rows contain bounded
winner voice IDs, names, and layout floats from the final assembled tables.
"""
import json
import math
import struct
from pathlib import Path

from common import BUILD, sha256, write_json


WINNER_BGM_WORDS = (0x00002025, 0x0c0082ad, 0x0804e209, 0x8fbf0014)


def extract_victory_bgm(ref, tables, audit):
    if tables['layouts'].get('winner_bgm') != 4:
        raise ValueError('Victory BGM table is not four bytes per fighter')
    source = ref.path.with_name('src') / 'resultsscreen.asm'
    code = source.read_text()
    if ('macro add_victory_bgm(bgm)' not in code or
            'Character.table_patch_start(winner_bgm, {id}, 0x4)' not in code):
        raise ValueError('Pinned victory BGM macro layout changed')
    audited = {row['name']: row['fkind'] for row in audit['fighters']}
    rows, inherited = [], []
    for fighter in tables['fighters']:
        name, fkind = fighter['name'], fighter['fkind']
        if audited.get(name) != fkind:
            raise ValueError(f'{name}: victory BGM fighter does not match audit')
        payload = bytes(fighter['tables']['winner_bgm'])
        if len(payload) != 4:
            raise ValueError(f'{name}: truncated victory BGM pointer')
        address = int.from_bytes(payload, 'big')
        if address < ref.ram_base:
            inherited.append(name)
            continue
        words = ref.words(address, 5)
        if (words[0], words[1], words[3], words[4]) != WINNER_BGM_WORDS:
            raise ValueError(f'{name}: unknown victory BGM thunk at {address:08x}')
        if words[2] & 0xffff0000 != 0x34050000:
            raise ValueError(f'{name}: victory BGM thunk is not ori a1, r0, id')
        bgm = words[2] & 0xffff
        rows.append({'name': name, 'fkind': fkind,
                     'bgm_id': -1 if bgm == 0xffff else bgm})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'resultsscreen.add_victory_bgm',
            'inherited_victory_bgm': inherited, 'fighters': rows}


def render_native_rows(manifest):
    lines = ['/* Decoded from compiled results-screen victory BGM thunks. */',
             'static const NativeRemixVictoryBGM native_remix_victory_bgm[] = {']
    for row in sorted(manifest['fighters'], key=lambda item: item['fkind']):
        lines.append(f'    {{{row["fkind"]}, {row["bgm_id"]}}}, /* {row["name"]} */')
    lines += ['};', '']
    return '\n'.join(lines)


def extract_winner_fgm(ref, tables, audit, microcode_count):
    if tables['layouts'].get('winner_fgm') != 4:
        raise ValueError('Winner voice table is not four bytes per fighter')
    source = ref.path.with_name('src') / 'resultsscreen.asm'
    if 'Character.table_patch_start(winner_fgm, {id}, 0x4)' not in source.read_text():
        raise ValueError('Pinned winner voice macro layout changed')
    if not 0 < microcode_count <= 8192:
        raise ValueError('Invalid FGM microcode count')
    audited = {row['name']: row['fkind'] for row in audit['fighters']}
    rows = []
    for fighter in tables['fighters']:
        name, fkind = fighter['name'], fighter['fkind']
        if audited.get(name) != fkind:
            raise ValueError(f'{name}: winner voice fighter does not match audit')
        payload = bytes(fighter['tables']['winner_fgm'])
        if len(payload) != 4:
            raise ValueError(f'{name}: truncated winner voice ID')
        fgm = int.from_bytes(payload, 'big')
        if fgm >= microcode_count:
            raise ValueError(f'{name}: winner voice {fgm} exceeds FGM microcode')
        rows.append({'name': name, 'fkind': fkind, 'fgm_id': fgm})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'resultsscreen.add_to_results_screen',
            'fgm_microcode_count': microcode_count, 'fighters': rows}


def render_winner_fgm_rows(manifest):
    lines = ['/* Compiled Character.winner_fgm rows, bounded by FGM microcode. */',
             'static const NativeRemixWinnerFGM native_remix_winner_fgm[] = {']
    for row in sorted(manifest['fighters'], key=lambda item: item['fkind']):
        lines.append(f'    {{{row["fkind"]}, {row["fgm_id"]}}}, /* {row["name"]} */')
    lines += ['};', '']
    return '\n'.join(lines)


def microcode_count(ref):
    if len(ref.rom) < 0x3d79c:
        raise ValueError('Reference ROM lacks the FGM microcode pointer')
    offset = struct.unpack_from('>I', ref.rom, 0x3d798)[0]
    if offset < 0 or offset + 4 > len(ref.rom):
        raise ValueError('FGM microcode header outside reference ROM')
    return struct.unpack_from('>I', ref.rom, offset)[0]


def extract_results_text(ref, tables, audit):
    expected = ('str_winner_ptr', 'str_winner_lx', 'str_winner_scale',
                'str_wins_lx', 'sound_type')
    if any(tables['layouts'].get(key) != (1 if key == 'sound_type' else 4)
           for key in expected):
        raise ValueError('Compiled results text tables have unexpected widths')
    source = (ref.path.with_name('src') / 'resultsscreen.asm').read_text()
    character = (ref.path.with_name('src') / 'Character.asm').read_text()
    if (any(f'Character.table_patch_start({key}, {{id}}, 0x4)' not in source
            for key in expected[:4]) or 'Character.id.DRAGONKING' not in source or
            'Character.id.BANJO' not in source or
            '0x8348 + 0x0010' not in source or
            'constant J(0x1)' not in character):
        raise ValueError('Pinned results text macro layout changed')
    audited = {row['name']: row['fkind'] for row in audit['fighters']}
    rows, inherited = [], []
    for fighter in tables['fighters']:
        name, fkind = fighter['name'], fighter['fkind']
        if audited.get(name) != fkind:
            raise ValueError(f'{name}: results text fighter does not match audit')
        pointer = int.from_bytes(bytes(fighter['tables']['str_winner_ptr']), 'big')
        if pointer < ref.ram_base:
            if name != 'RANDOM':
                raise ValueError(f'{name}: unexpected inherited results name pointer')
            inherited.append(name)
            continue
        offset = ref.rom_base + pointer - ref.ram_base
        if not 0 <= offset <= len(ref.rom) - 33:
            raise ValueError(f'{name}: results name pointer outside reference ROM')
        raw = ref.rom[offset:offset + 33]
        end = raw.find(b'\0')
        if not 0 < end <= 32:
            raise ValueError(f'{name}: results name is not bounded')
        label = raw[:end].decode('ascii')
        if any(char not in ' ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.&-' for char in label):
            raise ValueError(f'{name}: unsupported results name glyph')
        values = [struct.unpack('>f', bytes(fighter['tables'][key]))[0]
                  for key in expected[1:4]]
        name_lx, name_scale, wins_lx = values
        if (any(not math.isfinite(value) for value in values) or
                not 0 <= name_lx <= 320 or not .1 <= name_scale <= 2 or
                not 0 <= wins_lx <= 320):
            raise ValueError(f'{name}: invalid results text geometry')
        sound_type = bytes(fighter['tables']['sound_type'])
        if len(sound_type) != 1 or sound_type[0] not in (0, 1):
            raise ValueError(f'{name}: invalid results sound type')
        rows.append({'name': name, 'fkind': fkind, 'label': label,
                     'name_lx': name_lx, 'name_scale': name_scale,
                     'wins_lx': wins_lx,
                     'singular_win': (sound_type[0] == 1 and name != 'DRAGONKING') or
                                     name == 'BANJO'})
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'source_macro': 'resultsscreen.add_to_results_screen',
            'inherited_results_text': inherited, 'fighters': rows}


def _cfloat(value):
    result = format(value, '.9g')
    if '.' not in result and 'e' not in result:
        result += '.0'
    return result + 'F'


def render_results_text_rows(manifest):
    lines = ['/* Compiled results name, position, scale and WIN/WINS selection. */',
             'static const NativeRemixResultsText native_remix_results_text[] = {']
    for row in sorted(manifest['fighters'], key=lambda item: item['fkind']):
        lines.append(f'    {{{row["fkind"]}, {json.dumps(row["label"])}, '
                     f'{_cfloat(row["name_lx"])}, {_cfloat(row["name_scale"])}, '
                     f'{_cfloat(row["wins_lx"])}, {int(row["singular_win"])}}}, '
                     f'/* {row["name"]} */')
    lines += ['};', '']
    return '\n'.join(lines)


def write_results_patches(ref, tables, audit, out):
    manifest = extract_victory_bgm(ref, tables, audit)
    if manifest['reference_rom_sha256'] != tables['reference_rom_sha256']:
        raise ValueError('Victory BGM and table patches use different ROMs')
    write_json(BUILD / 'fighter-victory-bgm-patches.json', manifest)
    (Path(out) / 'native_victory_bgm_rows.inc').write_text(render_native_rows(manifest))
    voices = extract_winner_fgm(ref, tables, audit, microcode_count(ref))
    if voices['reference_rom_sha256'] != tables['reference_rom_sha256']:
        raise ValueError('Winner voice and table patches use different ROMs')
    write_json(BUILD / 'fighter-winner-fgm-patches.json', voices)
    (Path(out) / 'native_winner_fgm_rows.inc').write_text(render_winner_fgm_rows(voices))
    text = extract_results_text(ref, tables, audit)
    if text['reference_rom_sha256'] != tables['reference_rom_sha256']:
        raise ValueError('Results text and table patches use different ROMs')
    write_json(BUILD / 'fighter-results-text-patches.json', text)
    (Path(out) / 'native_results_text_rows.inc').write_text(render_results_text_rows(text))
    return manifest, voices, text
