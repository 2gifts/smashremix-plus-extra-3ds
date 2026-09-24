"""Translate exact compiled animation-end callback pairs into native C.

The wrapper alone is not sufficient: its target is usually mod-owned MIPS.
Both routines must match before an address is offered to the shared action
table importer. Unknown instructions or side effects remain unbound.
"""
from pathlib import Path

from common import BUILD, sha256, write_json
from classify_action_callbacks import a1_pointer, first_return_words
from native_straightline_transitions import decode_straightline


ANIM_END_CALL = 0x0c036520  # ftAnimEndCheckSetStatus at 0x800D9480.

# The sole variable instruction loads the status ID into a1. All other words
# are compared with the final assembled ROM, including the three temp clears.
STATUS_PLAY_CLEAR = (
    0x27bdffe0, 0xafbf001c, 0x240e0001, 0xafa40020,
    0xafae0010, None, 0x34060000, 0x0c039bc9,
    0x3c073f80, 0x0c03820c, 0x8fa40020, 0x8fa40020,
    0x8c840084, 0xac80017c, 0xac800180, 0xac800184,
    0x8fbf001c, 0x03e00008, 0x27bd0020,
)

# The four compiled Knuckles dive variants share this exact animation-end
# transition: enter the air action, play its events, reset two move variables,
# arm the third, and clear the fast-fall bit. Only the action ID varies.
DIVE_AIR_INITIAL = (
    0x27bdffe0, 0xafbf0014, 0x340e0008, 0xafa40020,
    0xafae0010, None, 0x34060000, 0x0c039bc9,
    0x3c073f80, 0x0c03820c, 0x8fa40020, 0x8fa40020,
    0x8c840084, 0xac80017c, 0xac800180, 0x34030001,
    0xac830184, 0x9083018d, 0x340e0007, 0x006e1824,
    0xa083018d, 0x8fbf0014, 0x03e00008, 0x27bd0020,
)


def exact_anim_end_wrapper(ref, address, target):
    """Accept only the observed no-side-effect call shapes."""
    words = ref.words(address, 12)
    length = first_return_words(words)
    if length is None or a1_pointer(words[:length]) != target:
        return False
    hi, lo = 0x3c050000 | (target >> 16), 0x34a50000 | (target & 0xffff)
    prefix = (0x27bdffe8, 0xafbf0014)
    endings = (
        (0x8fbf0014, 0x27bd0018, 0x03e00008, 0),
        (0x8fbf0014, 0x03e00008, 0x27bd0018),
    )
    middles = (
        (0x8cd8014c, hi, lo, ANIM_END_CALL, 0),
        (hi, lo, ANIM_END_CALL, 0x8cd8014c),
    )
    return any(tuple(words[:length]) == prefix + middle + ending
               for middle in middles for ending in endings)


def exact_plain_anim_end_wrapper(ref, address, target):
    """Accept a pure compiled callback with either legal pointer-load form."""
    words = ref.words(address, 12)
    length = first_return_words(words)
    if length is None:
        return False
    actual = tuple(words[:length])
    for stack_size in (0x18, 0x20):
        prefix = (0x27bd0000 | (0x10000 - stack_size), 0xafbf0014)
        ending = (0x8fbf0014, 0x27bd0000 | stack_size, 0x03e00008, 0)
        alternate = (0x8fbf0014, 0x03e00008, 0x27bd0000 | stack_size)
        high = (target + 0x8000) >> 16
        pointer_loads = ((0x3c050000 | (target >> 16),
                          0x34a50000 | (target & 0xffff), ANIM_END_CALL, 0),
                         (0x3c050000 | high, ANIM_END_CALL,
                          0x24a50000 | (target & 0xffff)))
        if any(actual == prefix + middle + tail
               for middle in pointer_loads for tail in (ending, alternate)):
            return True
    return False


def decode_status_play_clear(ref, address):
    words = ref.words(address, 128)
    length = first_return_words(words)
    if length != len(STATUS_PLAY_CLEAR):
        return None
    actual = words[:length]
    if any(want is not None and got != want
           for got, want in zip(actual, STATUS_PLAY_CLEAR)):
        return None
    if actual[5] & 0xffff0000 != 0x34050000:
        return None
    status = actual[5] & 0xffff
    if not 0xdc <= status < 0x4000:
        raise ValueError(f'Invalid compiled animation-end status {status} at {address:08x}')
    return {'address': f'{address:08x}', 'status_id': status}


def decode_dive_air_initial(ref, address):
    words = ref.words(address, 128)
    length = first_return_words(words)
    if length != len(DIVE_AIR_INITIAL):
        return None
    actual = words[:length]
    if any(want is not None and got != want
           for got, want in zip(actual, DIVE_AIR_INITIAL)):
        return None
    if actual[5] & 0xffff0000 != 0x34050000:
        return None
    status = actual[5] & 0xffff
    if not 0xdc <= status < 0x4000:
        raise ValueError(f'Invalid compiled dive status {status} at {address:08x}')
    return {'address': f'{address:08x}', 'status_id': status,
            'template': 'dive_air_initial'}


def extract_native_anim_ends(ref, worklist):
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Action worklist and pinned reference ROM differ')
    accepted_targets = {}
    wrappers = []
    candidates = 0
    for row in worklist['targets']:
        address = int(row['address'], 16)
        words = ref.words(address, 128)
        length = first_return_words(words)
        if length is None or length > 12 or ANIM_END_CALL not in words[:length]:
            continue
        candidates += 1
        target = a1_pointer(words[:length])
        if (target is None or target < ref.ram_base or
                not (exact_anim_end_wrapper(ref, address, target) or
                     exact_plain_anim_end_wrapper(ref, address, target))):
            continue
        if target not in accepted_targets:
            decoded = decode_straightline(ref, target, allow_status_only=True,
                                          allow_entry_resets=True)
            exact_clear = decode_status_play_clear(ref, target)
            if exact_clear and (not decoded or
                                decoded.get('template') != 'decoded_entry_reset' or
                                decoded['status_id'] != exact_clear['status_id'] or
                                decoded['preserve_flags'] != 1 or
                                decoded['reset_motion_flags'] != [0, 1, 2]):
                raise ValueError(f'Animation-end decoder disagrees with exact pattern at {target:08x}')
            accepted_targets[target] = decoded or decode_dive_air_initial(ref, target)
        if accepted_targets[target] is None:
            continue
        wrappers.append({'address': f'{address:08x}', 'symbols': row['symbols'],
                         'transition_address': f'{target:08x}',
                         'native': f'nativeRemixAnimEnd_{address:08x}'})
    transitions = sorted((item for item in accepted_targets.values() if item),
                         key=lambda item: item['address'])
    wrappers.sort(key=lambda item: item['address'])
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'animation_end_candidates': candidates,
            'recognized_transition_count': len(transitions),
            'recognized_action_callback_count': len(wrappers),
            'transitions': transitions, 'wrappers': wrappers}


def render_native_code(manifest):
    lines = ['/* Exact compiled animation-end callback and status templates. */']
    for row in manifest['transitions']:
        if row.get('template') in ('decoded_status_only', 'decoded_entry_reset'):
            flags = {0: 'FTSTATUS_PRESERVE_NONE', 1: 'FTSTATUS_PRESERVE_HIT'}.get(
                row['preserve_flags'], f'0x{row["preserve_flags"]:x}u')
            frame = '0.0F' if row['frame_begin'] == 'zero' else 'fighter_gobj->anim_frame'
            lines += [f'static void nativeRemixAnimStatus_{row["address"]}(GObj *fighter_gobj) {{',
                      f'    ftMainSetStatus(fighter_gobj, {row["status_id"]}, {frame}, '
                      f'{row["speed"]!r}F, {flags});']
            if row['template'] == 'decoded_entry_reset' or row['play_anim']:
                lines.append('    ftMainPlayAnimEventsAll(fighter_gobj);')
            if row['template'] == 'decoded_entry_reset':
                lines.append('    FTStruct *fp = ftGetStruct(fighter_gobj);')
                for index in row['reset_motion_flags']:
                    lines.append(f'    fp->motion_vars.flags.flag{index} = 0;')
            lines += ['}', '']
            continue
        if row.get('template') != 'dive_air_initial':
            raise ValueError(f'Unrecognized animation-end template {row.get("template")}')
        lines += [f'static void nativeRemixAnimStatus_{row["address"]}(GObj *fighter_gobj) {{',
                  '    FTStruct *fp = ftGetStruct(fighter_gobj);',
                  f'    ftMainSetStatus(fighter_gobj, {row["status_id"]}, 0.0F, 1.0F, '
                  'FTSTATUS_PRESERVE_FASTFALL);',
                  '    ftMainPlayAnimEventsAll(fighter_gobj);',
                  '    fp->motion_vars.flags.flag0 = 0;',
                  '    fp->motion_vars.flags.flag1 = 0;',
                  '    fp->motion_vars.flags.flag2 = 1;',
                  '    fp->is_fastfall = FALSE;']
        lines += ['}', '']
    for row in manifest['wrappers']:
        lines += [f'void {row["native"]}(GObj *fighter_gobj) {{',
                  f'    ftAnimEndCheckSetStatus(fighter_gobj, '
                  f'nativeRemixAnimStatus_{row["transition_address"]});',
                  '}', '']
    return '\n'.join(lines)


def write_native_anim_ends(ref, worklist, out):
    manifest = extract_native_anim_ends(ref, worklist)
    write_json(BUILD / 'native-anim-end-templates.json', manifest)
    (Path(out) / 'native_anim_end_templates.inc').write_text(render_native_code(manifest))
    return manifest
