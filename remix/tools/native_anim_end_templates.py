"""Translate exact compiled animation-end callback pairs into native C.

The wrapper alone is not sufficient: its target is usually mod-owned MIPS.
Both routines must match before an address is offered to the shared action
table importer. Unknown instructions or side effects remain unbound.
"""
from pathlib import Path

from common import BUILD, sha256, write_json
from classify_action_callbacks import a1_pointer, first_return_words


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
        if target is None or target < ref.ram_base or not exact_anim_end_wrapper(ref, address, target):
            continue
        if target not in accepted_targets:
            accepted_targets[target] = (decode_status_play_clear(ref, target) or
                                        decode_dive_air_initial(ref, target))
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
        dive = row.get('template') == 'dive_air_initial'
        lines += [f'static void nativeRemixAnimStatus_{row["address"]}(GObj *fighter_gobj) {{',
                  '    FTStruct *fp = ftGetStruct(fighter_gobj);',
                  f'    ftMainSetStatus(fighter_gobj, {row["status_id"]}, 0.0F, 1.0F, '
                  f'{"FTSTATUS_PRESERVE_FASTFALL" if dive else "FTSTATUS_PRESERVE_HIT"});',
                  '    ftMainPlayAnimEventsAll(fighter_gobj);',
                  '    _Static_assert(sizeof(fp->status_vars) >= 3 * sizeof(s32),',
                  '                   "Three compiled move variables need storage");',
                  '    memset(&fp->status_vars, 0, 3 * sizeof(s32));']
        if dive:
            lines += ['    const s32 dive_armed = 1;',
                      '    memcpy((u8*)&fp->status_vars + 2 * sizeof(s32),',
                      '           &dive_armed, sizeof(dive_armed));',
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
