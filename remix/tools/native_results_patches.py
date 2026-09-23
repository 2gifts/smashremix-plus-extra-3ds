"""Decode compiled results-screen victory BGM thunks for native playback.

The N64 mod stores MIPS routine pointers in Character.winner_bgm rather than
plain track IDs. Recognize the exact add_victory_bgm macro output and carry
only its immediate BGM ID into the ARM build.
"""
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


def write_results_audio(ref, tables, audit, out):
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
    return manifest, voices
