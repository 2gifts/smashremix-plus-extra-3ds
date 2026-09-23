"""Translate exact compiled collision-transition templates to native C.

Only the zero-preserve-flags templates below are accepted. Their MIPS
instructions correspond to a ground/air change, ftMainSetStatus at the live
animation frame and unit speed, and optionally clamping air speed. A changed
instruction fails recognition; all other transition routines stay unbound.
"""
from pathlib import Path

from common import BUILD, sha256, write_json
from classify_action_callbacks import COLLISION_HELPERS, first_return_words, jal_target


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
    return None


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
        status = (str(row['status_id']) if row['status_id'] is not None else
                  f'fp->status_id {"+" if row["status_delta"] > 0 else "-"} {abs(row["status_delta"])}')
        flags = {0: 'FTSTATUS_PRESERVE_NONE', 1: 'FTSTATUS_PRESERVE_HIT',
                 0x800: 'FTSTATUS_PRESERVE_LOOPSFX'}[row['preserve_flags']]
        lines += [f'static void nativeRemixTransition_{address}(GObj *fighter_gobj) {{',
                  '    FTStruct *fp = ftGetStruct(fighter_gobj);',
                  f'    mpCommonSetFighter{("Ground" if row["kinetics"] == "ground" else "Air")}(fp);',
                  f'    ftMainSetStatus(fighter_gobj, {status}, fighter_gobj->anim_frame,',
                  f'                    1.0F, {flags});']
        if row['clamp_air_speed']:
            lines.append('    ftPhysicsClampAirVelXMax(fp);')
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
