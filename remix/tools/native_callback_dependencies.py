"""Inventory the compiled MIPS call graph behind every action-table callback.

This is a planning and provenance report, not an ARM binding or an executable
translator. It follows direct calls in the assembled ROM so shared engine
interfaces can be ported across fighters instead of choosing fighters one by
one. Unknown control flow remains visible in the report.
"""

import json
from collections import defaultdict, deque

from classify_action_callbacks import first_return_words, jal_target
from common import BUILD, sha256, write_json


MAX_SCAN_WORDS = 128


def scan_routine(ref, address):
    """Collect direct edges through the first return; never imply full CFG coverage."""
    try:
        words = ref.words(address, MAX_SCAN_WORDS)
    except (ValueError, IndexError):
        return {'address': f'{address:08x}', 'scan': 'unmapped',
                'words': 0, 'original_calls': [], 'expansion_calls': [],
                'indirect_calls': 0, 'direct_jumps': [], 'indirect_jumps': 0}
    length = first_return_words(words)
    body = words[:length] if length is not None else words
    original, expansion, jumps = set(), set(), set()
    indirect_calls = indirect_jumps = 0
    for index, word in enumerate(body):
        opcode = word >> 26
        pc = address + index * 4
        if opcode == 3:  # jal
            target = jal_target(pc, word)
            (expansion if target >= ref.ram_base else original).add(target)
        elif opcode == 2:  # j; may be a local branch or a tail call.
            jumps.add(jal_target(pc, word))
        elif opcode == 0 and word & 63 == 9:  # jalr
            indirect_calls += 1
        elif opcode == 0 and word & 63 == 8 and word != 0x03e00008:
            indirect_jumps += 1
    return {'address': f'{address:08x}',
            'scan': 'first_return_window' if length is not None else 'no_return_in_window',
            'words': len(body),
            'original_calls': [f'{item:08x}' for item in sorted(original)],
            'expansion_calls': [f'{item:08x}' for item in sorted(expansion)],
            'indirect_calls': indirect_calls,
            'direct_jumps': [f'{item:08x}' for item in sorted(jumps)],
            'indirect_jumps': indirect_jumps}


def build_dependency_graph(ref, worklist, native_bindings=()):
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Callback worklist and pinned reference ROM differ')
    bound = set(native_bindings)
    roots = {int(row['address'], 16): row for row in worklist['targets']}
    scans = {}
    original_users = defaultdict(set)
    helper_users = defaultdict(set)
    callbacks = []
    for address, row in sorted(roots.items()):
        reachable = set()
        pending = deque([address])
        while pending:
            target = pending.popleft()
            if target in reachable:
                continue
            reachable.add(target)
            if target not in scans:
                scans[target] = scan_routine(ref, target)
            scan = scans[target]
            for called in scan['expansion_calls']:
                pending.append(int(called, 16))
            # A direct jump outside this routine's scanned window is a
            # possible tail call. Keep it visible but do not follow it as a
            # proven call: it might instead be an internal control-flow edge.
        original = sorted({called for target in reachable
                           for called in scans[target]['original_calls']})
        opaque = sorted(f'{target:08x}' for target in reachable
                        if scans[target]['scan'] != 'first_return_window' or
                        scans[target]['indirect_calls'] or
                        scans[target]['indirect_jumps'] or
                        scans[target]['direct_jumps'])
        if address not in bound:
            for called in original:
                original_users[called].add(address)
            for target in reachable - {address}:
                helper_users[target].add(address)
        callbacks.append({'address': row['address'], 'symbols': row['symbols'],
                          'fighters': sorted({use['fighter'] for use in row['uses']}),
                          'action_table_uses': len(row['uses']),
                          'native_bound': address in bound,
                          'reachable_expansion_routines': len(reachable),
                          'original_engine_calls': original,
                          'opaque_routines': opaque})
    uses = {int(row['address'], 16): len(row['uses']) for row in worklist['targets']}
    def ranked(rows):
        return sorted(({'address': key, 'dependent_callbacks': len(users),
                        'dependent_action_uses': sum(uses[item] for item in users),
                        'example_callbacks': [f'{item:08x}' for item in sorted(users)[:5]]}
                       for key, users in rows.items()),
                      key=lambda item: (-item['dependent_action_uses'],
                                        -item['dependent_callbacks'], item['address']))
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'scope': ('Static first-return-window direct-call graph for prioritizing '
                      'shared native interfaces. Branches, indirect calls, pointer '
                      'callbacks, and engine hooks need further analysis; this report '
                      'does not prove behavior or create ARM bindings.'),
            'callback_count': len(callbacks),
            'native_bound_count': sum(row['native_bound'] for row in callbacks),
            'unique_original_engine_calls_for_unbound': len(original_users),
            'unique_expansion_helpers_for_unbound': len(helper_users),
            'opaque_callback_count': sum(bool(row['opaque_routines']) for row in callbacks),
            'callbacks': callbacks,
            'routines': [scans[key] for key in sorted(scans)],
            'ranked_original_engine_calls_for_unbound': ranked(original_users),
            'ranked_expansion_helpers_for_unbound': ranked(helper_users)}


def write_dependency_graph(ref, worklist, native_bindings=()):
    report = build_dependency_graph(ref, worklist, native_bindings)
    write_json(BUILD / 'native-callback-dependencies.json', report)
    return report


def main():
    from prepare_fighter_probe import Reference
    from native_action_patches import load_bindings
    ref = Reference()
    worklist = json.loads((BUILD / 'action-callback-worklist.json').read_text())
    _, bindings = load_bindings(symbols=ref.symbols)
    generated_path = BUILD / 'native-generated-action-bindings.json'
    if generated_path.exists():
        generated = json.loads(generated_path.read_text())
        if generated.get('reference_rom_sha256') == sha256(ref.path):
            bindings.update((int(row['address'], 16), row['native'])
                            for row in generated['bindings'])
    report = write_dependency_graph(ref, worklist, bindings)
    print({key: report[key] for key in ('callback_count', 'native_bound_count',
          'unique_original_engine_calls_for_unbound',
          'unique_expansion_helpers_for_unbound',
          'opaque_callback_count')})


if __name__ == '__main__':
    main()
