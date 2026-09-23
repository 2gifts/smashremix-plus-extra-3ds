"""Group compiled MIPS action callbacks by reusable native behavior.

This is an audit, not an execution or binding layer. In particular, a short
collision wrapper still depends on its mod-owned transition routine.
"""
import hashlib
import json
import struct
from collections import defaultdict

from common import BUILD, sha256, write_json


COLLISION_HELPERS = {
    0x800DDDDC: 'mpCommonProcFighterOnFloor',
    0x800DDE84: 'mpCommonProcFighterOnEdge',
    0x800DE6E4: 'mpCommonProcFighterLanding',
    0x800DE80C: 'mpCommonProcFighterCliff',
}


def first_return_words(words):
    return next((index + 2 for index, word in enumerate(words[:-1])
                 if word == 0x03E00008), None)


def jal_target(pc, word):
    return ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def a1_pointer(words):
    high = pointer = None
    for word in words:
        op, rs, rt, imm = word >> 26, (word >> 21) & 31, (word >> 16) & 31, word & 0xFFFF
        if op == 15 and rt == 5:
            high = imm << 16
        elif op == 9 and rs == rt == 5 and high is not None:
            pointer = (high + ((imm ^ 0x8000) - 0x8000)) & 0xFFFFFFFF
        elif op == 13 and rs == rt == 5 and high is not None:
            pointer = high | imm
    return pointer


def shape_hash(words):
    # Ignore address and literal immediates while retaining register flow.
    normalized = [word if word >> 26 == 0 else
                  word & (0xFC000000 if word >> 26 in (2, 3) else 0xFFFF0000)
                  for word in words]
    return hashlib.sha256(struct.pack('>' + 'I' * len(normalized), *normalized)).hexdigest()


def classify(ref, worklist):
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Callback worklist and pinned reference ROM differ')
    symbol_names = defaultdict(list)
    for name, address in ref.symbols.items():
        symbol_names[address].append(name)
    wrappers = []
    short_one_call = 0
    for row in worklist['targets']:
        address = int(row['address'], 16)
        words = ref.words(address, 128)
        length = first_return_words(words)
        if length is None or length > 12:
            continue
        calls = [(index, jal_target(address + index * 4, word))
                 for index, word in enumerate(words[:length]) if word >> 26 == 3]
        if len(calls) != 1:
            continue
        short_one_call += 1
        call_index, helper = calls[0]
        if helper not in COLLISION_HELPERS:
            continue
        pointer = a1_pointer(words[:call_index + 2])
        if pointer is None or pointer < ref.ram_base:
            raise ValueError(f'Collision wrapper {address:08x} lacks expansion transition')
        ref.words(pointer, 1)
        wrappers.append({'address': f'{address:08x}',
                         'symbols': row['symbols'], 'uses': len(row['uses']),
                         'helper_address': f'{helper:08x}',
                         'helper': COLLISION_HELPERS[helper],
                         'transition_address': f'{pointer:08x}',
                         'transition_symbols': sorted(symbol_names[pointer])})
    transitions = defaultdict(list)
    for wrapper in wrappers:
        transitions[int(wrapper['transition_address'], 16)].append(wrapper)
    shapes = defaultdict(list)
    for address in transitions:
        words = ref.words(address, 128)
        length = first_return_words(words)
        if length is None:
            fingerprint = 'no-return-in-first-128-words'
        else:
            fingerprint = shape_hash(words[:length])
        shapes[fingerprint].append(address)
    grouped = [{'shape_sha256': shape,
                'transition_addresses': [f'{address:08x}' for address in sorted(addresses)],
                'examples': [sorted(symbol_names[address]) for address in sorted(addresses)[:3]]}
               for shape, addresses in shapes.items()]
    grouped.sort(key=lambda row: (-len(row['transition_addresses']), row['shape_sha256']))
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'unique_action_callback_targets': len(worklist['targets']),
            'short_single_call_candidates': short_one_call,
            'collision_wrappers': len(wrappers),
            'unique_collision_transition_targets': len(transitions),
            'collision_transition_shapes': len(shapes),
            'helper_counts': dict(sorted((name, sum(w['helper'] == name for w in wrappers))
                                         for name in COLLISION_HELPERS.values())),
            'wrappers': wrappers, 'transition_shape_groups': grouped}


def main():
    from prepare_fighter_probe import Reference
    ref = Reference()
    worklist = json.loads((BUILD / 'action-callback-worklist.json').read_text())
    report = classify(ref, worklist)
    write_json(BUILD / 'action-callback-families.json', report)
    print({key: report[key] for key in ('unique_action_callback_targets',
          'short_single_call_candidates', 'collision_wrappers',
          'unique_collision_transition_targets', 'collision_transition_shapes')})


if __name__ == '__main__':
    main()
