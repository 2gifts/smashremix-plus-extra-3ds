"""Translate checked compiled collision transitions to native C.

Exact templates and a restricted straight-line decoder accept only known
engine calls and side effects. Unknown instructions remain unbound.
"""
import struct
from pathlib import Path

from common import BUILD, sha256, write_json
from classify_action_callbacks import COLLISION_HELPERS, first_return_words, jal_target
from native_straightline_transitions import decode_straightline


# None marks the sole status-ID immediate. Every other instruction must match.
TEMPLATES = {
    'air_and_clamp_a': (
        0x27bdffb0, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037bb2, 0xafa40034, 0x8fa40038, None,
        0x8c860078, 0x3c073f80, 0x0c039bc9, 0xafa00010,
        0x0c0363ae, 0x8fa40034, 0x8fbf001c, 0x03e00008,
        0x27bd0050),
    'air_and_clamp_b': (
        0x27bdffb0, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037bb2, 0xafa40034, 0x8fa40038, None,
        0x8c860078, 0x3c073f80, 0x0c039bc9, 0xafa00010,
        0x0c0363ae, 0x8fa40034, 0x8fbf001c, 0x27bd0050,
        0x03e00008, 0x00000000),
    'ground': (
        0x27bdffb0, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037ba6, 0xafa40034, 0x8fa40038, None,
        0x8c860078, 0x3c073f80, 0x0c039bc9, 0xafa00010,
        0x8fbf001c, 0x03e00008, 0x27bd0050),
    'ground_alt_epilogue': (
        0x27bdffb0, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037ba6, 0xafa40034, 0x8fa40038, None,
        0x8c860078, 0x3c073f80, 0x0c039bc9, 0xafa00010,
        0x8fbf001c, 0x27bd0050, 0x03e00008, 0x00000000),
}

# These compiled forms preserve a specific status flag or derive the next
# status from the live status ID. They are kept separate from the zero-flag
# templates so a new MIPS side effect cannot be accepted accidentally.
SHARED_TEMPLATES = {
    'air_status_plus_3_loop_sfx': (
        0x27bdffc8, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037bb2, 0xafa40034, 0x8fa20034, 0x8fa40038,
        0x8c4f0024, 0x25e50003, 0x8c860078, 0x3c073f80,
        0x340e0800, 0x0c039bc9, 0xafae0010, 0x0c0363ae,
        0x8fa40034, 0x8fbf001c, 0x27bd0038, 0x03e00008,
        0x00000000),
    'ground_status_minus_3_loop_sfx': (
        0x27bdffc8, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037ba6, 0xafa40034, 0x8fa20034, 0x8fa40038,
        0x8c4f0024, 0x25e5fffd, 0x8c860078, 0x3c073f80,
        0x340e0800, 0x0c039bc9, 0xafae0010, 0x8fbf001c,
        0x27bd0038, 0x03e00008, 0x00000000),
    'ground_fixed_preserve_hit': (
        0x27bdffc8, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037ba6, 0xafa40034, 0x8fa20034, 0x8fa40038,
        0x24050000, 0x8c860078, 0x3c073f80, 0x340e0001,
        0x0c039bc9, 0xafae0010, 0x8fbf001c, 0x27bd0038,
        0x03e00008, 0x00000000),
}

# Compiled status-table transitions use the same instruction stream across
# fighters, with only the table address and source-status base changing.
# Match every instruction, including the stack flag and optional air clamp.
TABLE_TEMPLATES = {
    'air_status_table': (
        0x27bdffc8, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037bb2, 0xafa40034, 0x8fa20034, 0x8fa40038,
        None, None, 0x8c4f0024, None, 0x000f7840,
        0x01cf7021, 0x95c50000, 0x8c860078, 0x3c073f80,
        None, 0x0c039bc9, 0xafae0010, 0x0c0363ae,
        0x8fa40034, 0x8fbf001c, 0x03e00008, 0x27bd0038),
    'ground_status_table': (
        0x27bdffc8, 0xafbf001c, 0xafa40038, 0x8c840084,
        0x0c037ba6, 0xafa40034, 0x8fa20034, 0x8fa40038,
        None, None, 0x8c4f0024, None, 0x000f7840,
        0x01cf7021, 0x95c50000, 0x8c860078, 0x3c073f80,
        None, 0x0c039bc9, 0xafae0010, 0x8fbf001c,
        0x03e00008, 0x27bd0038),
}

# A forward, branch-likely switch on fighter kind selects a copy-action ID
# for Kirby variants and the ordinary grounded action otherwise. The branch
# targets, delay slots, helper call, and status flags must all match.
FKIND_GROUND_BRANCH = (
    0x27bdffc8, 0xafbf001c, 0xafa40038, 0x8c840084,
    0x0c037ba6, 0xafa40034, 0x8fa20034, 0x8fa40038,
    0x8c460008, None, 0x50a60005, None, None,
    0x50a60002, None, None, 0x8c860078, 0x3c073f80,
    0x340e0001, 0x0c039bc9, 0xafae0010, 0x8fbf001c,
    0x27bd0038, 0x03e00008, 0x00000000,
)

FKIND_SELECT_BRANCH = (
    0x27bdffd8, 0xafbf001c, 0xafa40028, 0x8c840084,
    None, 0xafa40024, 0x8fa40028, 0x240f0002,
    0x8c860084, 0x8cc60008, None, 0x50a60002,
    None, None, 0x8c860078, 0x3c073f80,
    0x0c039bc9, 0xafaf0010, 0x8fbf001c,
    0x03e00008, 0x27bd0028,
)


def decode_fkind_branch(address, actual):
    if len(actual) != len(FKIND_GROUND_BRANCH) or any(
            expected is not None and word != expected
            for word, expected in zip(actual, FKIND_GROUND_BRANCH)):
        return None
    for index in (9, 11, 12, 14):
        if actual[index] & 0xffff0000 != 0x34050000:
            return None
    if actual[15] & 0xffff0000 != 0x24050000:
        return None
    kinds = (actual[9] & 0xffff, actual[12] & 0xffff)
    copy_status = actual[11] & 0xffff
    normal_status = actual[15] & 0xffff
    if (kinds[0] == kinds[1] or any(kind > 255 for kind in kinds) or
            actual[14] & 0xffff != copy_status or
            not 0xdc <= copy_status < 0x4000 or
            not 0xdc <= normal_status < 0x4000):
        return None
    return {'address': f'{address:08x}', 'template': 'fkind_ground_branch',
            'status_id': normal_status, 'status_conditional_id': copy_status,
            'conditional_fkind_ids': list(kinds), 'kinetics': 'ground',
            'clamp_air_speed': False, 'preserve_flags': 1}


def decode_fkind_select_branch(address, actual):
    if len(actual) != len(FKIND_SELECT_BRANCH) or any(
            expected is not None and word != expected
            for word, expected in zip(actual, FKIND_SELECT_BRANCH)):
        return None
    kinetics = {0x0c037ba6: 'ground', 0x0c037bb2: 'air'}.get(actual[4])
    if kinetics is None or any(actual[index] & 0xffff0000 != 0x34050000
                               for index in (10, 12, 13)):
        return None
    kind = actual[10] & 0xffff
    conditional = actual[12] & 0xffff
    fallback = actual[13] & 0xffff
    if kind > 255 or not 0xdc <= conditional < 0x4000 or not 0xdc <= fallback < 0x4000:
        return None
    return {'address': f'{address:08x}', 'template': 'fkind_select_branch',
            'status_id': fallback, 'status_conditional_id': conditional,
            'conditional_fkind_ids': [kind], 'kinetics': kinetics,
            'clamp_air_speed': False, 'preserve_flags': 2}


def decode_status_table(ref, address, actual):
    for name, pattern in TABLE_TEMPLATES.items():
        if len(actual) != len(pattern) or any(
                expected is not None and word != expected
                for word, expected in zip(actual, pattern)):
            continue
        # lui/ori t6 and addiu t7,t7,-base are the only variable
        # instructions. Reject register changes and alternate arithmetic.
        if (actual[8] & 0xffff0000 != 0x3c0e0000 or
                actual[9] & 0xffff0000 != 0x35ce0000 or
                actual[11] & 0xffff0000 != 0x25ef0000 or
                actual[17] not in (0x340e0802, 0x340e0803)):
            continue
        base = -(struct.unpack('>h', struct.pack('>H', actual[11] & 0xffff))[0])
        table_address = ((actual[8] & 0xffff) << 16) | (actual[9] & 0xffff)
        if not 0xdc <= base < 0x4000 or not hasattr(ref, 'symbols'):
            continue
        names = [symbol for symbol, value in ref.symbols.items()
                 if value == table_address and symbol.endswith('_table')]
        later = [value for value in ref.symbols.values() if value > table_address]
        if not names or not later:
            continue
        end = min(later)
        size = end - table_address
        if (size < 6 or size > 64 or size % 2 or table_address % 2 or
                not hasattr(ref, 'rom') or not hasattr(ref, 'ram_base') or
                not hasattr(ref, 'rom_base')):
            continue
        offset = table_address - ref.ram_base + ref.rom_base
        if offset < 0 or offset + size > len(ref.rom):
            continue
        values = list(struct.unpack_from('>' + str(size // 2) + 'H', ref.rom, offset))
        # Tables are padded with one zero halfword when necessary. A zero
        # anywhere else would be an unmodelled source-status entry.
        if values[-1] == 0:
            values.pop()
        if (len(values) < 2 or base + len(values) > 0x4000 or
                any(value < 0xdc or value >= 0x4000 for value in values)):
            continue
        return {'address': f'{address:08x}', 'template': name,
                'status_id': None, 'status_base': base,
                'status_table': values, 'kinetics': 'air' if name.startswith('air') else 'ground',
                'clamp_air_speed': name.startswith('air'),
                'preserve_flags': actual[17] & 0xffff}
    return None

WRAPPER_ENDINGS = (
    (0x27bd0018, 0x03e00008, 0x00000000),
    (0x03e00008, 0x27bd0018),
)


def exact_collision_wrapper(ref, row):
    """Require an unmodified call through the original collision helper."""
    address = int(row['address'], 16)
    transition = int(row['transition_address'], 16)
    helper = int(row['helper_address'], 16)
    if COLLISION_HELPERS.get(helper) != row['helper']:
        return False
    words = ref.words(address, 12)
    length = first_return_words(words)
    if length is None:
        return False
    actual = words[:length]
    if len(actual) not in (9, 10):
        return False
    if actual[:2] != [0x27bdffe8, 0xafbf0014]:
        return False
    if actual[2] != 0x3c050000 | (transition >> 16):
        return False
    if actual[3] != 0x34a50000 | (transition & 0xffff):
        return False
    if actual[4] >> 26 != 3 or jal_target(address + 16, actual[4]) != helper:
        return False
    return (actual[5:7] == [0x00000000, 0x8fbf0014]
            and tuple(actual[7:]) in WRAPPER_ENDINGS)


def decode_transition(ref, address):
    words = ref.words(address, 128)
    length = first_return_words(words)
    if length is None:
        return None
    actual = words[:length]
    for name, pattern in TEMPLATES.items():
        if len(actual) != len(pattern):
            continue
        if any(want is not None and got != want
               for got, want in zip(actual, pattern)):
            continue
        status_word = actual[7]
        if status_word & 0xffff0000 != 0x34050000:
            continue
        status_id = status_word & 0xffff
        if not 0xdc <= status_id < 0x4000:
            raise ValueError(f'Invalid compiled transition status {status_id} at {address:08x}')
        return {'address': f'{address:08x}', 'template': name,
                'status_id': status_id,
                'kinetics': 'ground' if name.startswith('ground') else 'air',
                'clamp_air_speed': not name.startswith('ground'),
                'preserve_flags': 0}
    for name, pattern in SHARED_TEMPLATES.items():
        if len(actual) != len(pattern):
            continue
        if name == 'ground_fixed_preserve_hit':
            if actual[8] & 0xffff0000 != 0x24050000:
                continue
            status_id = actual[8] & 0xffff
            if not 0xdc <= status_id < 0x4000:
                raise ValueError(f'Invalid compiled transition status {status_id} at {address:08x}')
            expected = list(pattern)
            expected[8] = actual[8]
        else:
            status_id = None
            expected = pattern
        if tuple(actual) != tuple(expected):
            continue
        return {'address': f'{address:08x}', 'template': name,
                'status_id': status_id,
                'status_delta': (3 if name.startswith('air_status') else -3)
                                if status_id is None else None,
                'kinetics': 'ground' if name.startswith('ground') else 'air',
                'clamp_air_speed': name.startswith('air'),
                'preserve_flags': 1 if name == 'ground_fixed_preserve_hit' else 0x800}
    return (decode_status_table(ref, address, actual) or
            decode_fkind_branch(address, actual) or
            decode_fkind_select_branch(address, actual) or
            decode_straightline(ref, address))


def extract_native_transitions(ref, families):
    if families['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Callback families and pinned reference ROM differ')
    transitions = {}
    wrappers = []
    for row in families['wrappers']:
        if not exact_collision_wrapper(ref, row):
            continue
        address = int(row['transition_address'], 16)
        if address not in transitions:
            transitions[address] = decode_transition(ref, address)
        transition = transitions[address]
        if transition is None:
            continue
        if transition['template'] not in ('decoded_straightline', 'fkind_ground_branch',
                                          'fkind_select_branch',
                                          *TABLE_TEMPLATES):
            # Keep the hand-checked examples as an independent semantic
            # oracle for the more general instruction decoder.
            decoded = decode_straightline(ref, address)
            fields = ('status_id', 'status_delta', 'kinetics',
                      'clamp_air_speed', 'preserve_flags')
            if decoded is None or any(transition.get(key) != decoded.get(key)
                                      for key in fields):
                raise ValueError(f'Compiled transition decoder disagrees at {address:08x}')
        wrappers.append({'address': row['address'], 'symbols': row['symbols'],
                         'helper': row['helper'], 'transition_address': row['transition_address'],
                         'native': f'nativeRemixCollision_{row["address"]}'})
    accepted = sorted((row for row in transitions.values() if row is not None),
                      key=lambda row: row['address'])
    wrappers.sort(key=lambda row: row['address'])
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'recognized_transition_count': len(accepted),
            'recognized_collision_callback_count': len(wrappers),
            'transitions': accepted, 'wrappers': wrappers}


def render_native_code(manifest):
    lines = ['/* Exact compiled MIPS collision-transition templates. */']
    for row in manifest['transitions']:
        address = row['address']
        if 'status_table' in row:
            values = ', '.join(str(value) for value in row['status_table'])
            lines += [f'static const u16 nativeRemixStatusTable_{address}[] = {{{values}}};']
            status = f'nativeRemixStatusTable_{address}[fp->status_id - {row["status_base"]}]'
        elif 'status_conditional_id' in row:
            kinds = row['conditional_fkind_ids']
            condition = ' || '.join(f'fp->fkind == {kind}' for kind in kinds)
            status = (f'(({condition}) ? '
                      f'{row["status_conditional_id"]} : {row["status_id"]})')
        else:
            status = (str(row['status_id']) if row['status_id'] is not None else
                      f'fp->status_id {"+" if row["status_delta"] > 0 else "-"} {abs(row["status_delta"])}')
        flags = {0: 'FTSTATUS_PRESERVE_NONE', 1: 'FTSTATUS_PRESERVE_HIT',
                 0x800: 'FTSTATUS_PRESERVE_LOOPSFX'}.get(
                     row['preserve_flags'], f'0x{row["preserve_flags"]:x}u')
        lines += [f'static void nativeRemixTransition_{address}(GObj *fighter_gobj) {{',
                  '    FTStruct *fp = ftGetStruct(fighter_gobj);']
        if 'status_table' in row:
            lines += [f'    if (fp->status_id < {row["status_base"]} ||',
                      f'        fp->status_id >= {row["status_base"] + len(row["status_table"])}) return;']
        for action in row.get('action_order',
                              [row['kinetics'], 'status'] +
                              (['clamp_air_speed'] if row['clamp_air_speed'] else [])):
            if action == 'status':
                lines += [f'    ftMainSetStatus(fighter_gobj, {status}, fighter_gobj->anim_frame,',
                          f'                    1.0F, {flags});']
            elif action == 'clamp_air_speed':
                lines.append('    ftPhysicsClampAirVelXMax(fp);')
            else:
                lines.append(f'    mpCommonSetFighter{("Ground" if action == "ground" else "Air")}(fp);')
        lines += ['}', '']
    for row in manifest['wrappers']:
        lines += [f'void {row["native"]}(GObj *fighter_gobj) {{',
                  f'    {row["helper"]}(fighter_gobj, '
                  f'nativeRemixTransition_{row["transition_address"]});',
                  '}', '']
    return '\n'.join(lines)


def write_native_transitions(ref, families, out):
    manifest = extract_native_transitions(ref, families)
    write_json(BUILD / 'native-transition-templates.json', manifest)
    (Path(out) / 'native_collision_templates.inc').write_text(render_native_code(manifest))
    return manifest
