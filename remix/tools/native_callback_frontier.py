"""Rank unbound compiled callback shapes for shared native implementation.

Instruction-shape hashes are planning hints, never proof of equivalent MIPS
behavior. A shape must still pass a semantic decoder before it can be bound.
"""

from collections import defaultdict

from classify_action_callbacks import first_return_words, shape_hash
from common import sha256
from native_action_patches import action_callback_addresses


def rank_callback_frontier(ref, worklist, audit, bindings, families=None):
    pinned = sha256(ref.path)
    if worklist['reference_rom_sha256'] != pinned or audit['reference_rom_sha256'] != pinned:
        raise ValueError('Callback frontier sources do not match the pinned ROM')
    if families is not None and families['reference_rom_sha256'] != pinned:
        raise ValueError('Callback families do not match the pinned ROM')
    collision_wrappers = ({row['address']: row for row in families['wrappers']}
                          if families is not None else {})
    bound = set(bindings)
    groups = defaultdict(list)
    no_return = []
    for row in worklist['targets']:
        address = int(row['address'], 16)
        if address in bound:
            continue
        words = ref.words(address, 128)
        length = first_return_words(words)
        if length is None:
            no_return.append(row['address'])
            continue
        callback_shape = shape_hash(words[:length])
        wrapper = collision_wrappers.get(row['address'])
        if wrapper is None:
            key = (callback_shape, None, None)
        else:
            target_words = ref.words(int(wrapper['transition_address'], 16), 128)
            target_length = first_return_words(target_words)
            target_shape = (shape_hash(target_words[:target_length])
                            if target_length is not None else 'no-return-in-first-128-words')
            key = (callback_shape, wrapper['helper_address'], target_shape)
        groups[key].append(row)
    ranked = []
    for (shape, helper, target_shape), rows in groups.items():
        addresses = {int(row['address'], 16) for row in rows}
        fighters = sorted({use['fighter'] for row in rows for use in row['uses']})
        near_unlock = []
        for fighter in audit['fighters']:
            if not fighter['fixture_data_ready']:
                continue
            missing = action_callback_addresses(fighter) - bound
            if missing and missing <= addresses:
                near_unlock.append(fighter['name'])
        ranked.append({
            'shape_sha256': shape,
            'collision_helper_address': helper,
            'collision_transition_shape_sha256': target_shape,
            'callback_count': len(rows),
            'action_table_uses': sum(len(row['uses']) for row in rows),
            'affected_fighters': fighters,
            'callback_only_unlocks': sorted(near_unlock),
            'addresses': sorted(row['address'] for row in rows),
            'symbol_examples': [symbol for row in rows[:3] for symbol in row['symbols'][:1]],
        })
    ranked.sort(key=lambda row: (-len(row['callback_only_unlocks']),
                                 -row['action_table_uses'],
                                 -len(row['affected_fighters']), row['shape_sha256'],
                                 row['collision_helper_address'] or '',
                                 row['collision_transition_shape_sha256'] or ''))
    return {'schema': 1, 'reference_rom_sha256': pinned,
            'scope': ('Planning only: matching instruction shapes can have different semantics; '
                      'callback-only unlocks omit special-dispatch and gameplay validation.'),
            'unbound_shape_count': len(ranked), 'no_return_addresses': sorted(no_return),
            'groups': ranked}
