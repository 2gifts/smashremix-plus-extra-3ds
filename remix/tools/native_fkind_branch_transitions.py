"""Bounded symbolic decoder for fighter-kind status-selection branches.

Only forward equality branches on the compiled fighter kind, stack-local
writes, and allowlisted original engine calls are accepted. Every possible
fighter kind must reach the same side-effect sequence with known arguments.
The result is generated native C, never an emulated MIPS callback at runtime.
"""

from collections import Counter

from classify_action_callbacks import first_return_words, jal_target
from native_straightline_transitions import (ANIM_FRAME, ENGINE_CALLS, FIGHTER,
                                             GOBJ, RETURN_ADDRESS, UNKNOWN,
                                             add_value, sign16)


FKIND = ('fkind',)
ALL_KINDS = frozenset(range(256))
ALLOWED_ORDERS = (
    ('ground', 'status'), ('air', 'status'),
    ('air', 'status', 'clamp_air_speed'),
    ('air', 'clamp_air_speed', 'status'),
)


def decode_fkind_branches(ref, address):
    words = ref.words(address, 128)
    length = first_return_words(words)
    if length is None or length > 64:
        return None
    words = words[:length]
    registers = [UNKNOWN] * 32
    registers[0], registers[4], registers[29], registers[31] = (
        0, GOBJ, 0, RETURN_ADDRESS)
    pending = [(0, registers, {}, [], ALL_KINDS, False)]
    terminals = []
    steps = 0

    def execute(word, regs, stack):
        opcode = word >> 26
        rs, rt = (word >> 21) & 31, (word >> 16) & 31
        imm = word & 0xffff
        if word == 0:
            return True
        if opcode in (1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23):
            return False  # Calls/branches inside a delay slot are unmodelled.
        if opcode in (9, 12, 13, 15, 35) and rt == 29 and not (opcode == 9 and rs == 29):
            return False
        if opcode == 15:
            regs[rt] = imm << 16
        elif opcode == 13:
            base = regs[rs]
            regs[rt] = base | imm if isinstance(base, int) else UNKNOWN
        elif opcode == 12:
            base = regs[rs]
            regs[rt] = base & imm if isinstance(base, int) else UNKNOWN
        elif opcode == 9:
            regs[rt] = add_value(regs[rs], sign16(imm))
            if rt == 29 and not (0xfffff000 <= regs[29] <= 0xffffffff or
                                 0 <= regs[29] <= 0x1000):
                return False
        elif opcode == 35:
            base = regs[rs]
            offset = sign16(imm)
            if rs == 29 and isinstance(base, int):
                regs[rt] = stack.get(base + offset, UNKNOWN)
            elif base == GOBJ and offset == 0x84:
                regs[rt] = FIGHTER
            elif base == GOBJ and offset == 0x78:
                regs[rt] = ANIM_FRAME
            elif base == FIGHTER and offset == 0x8:
                regs[rt] = FKIND
            elif base == FIGHTER and offset == 0x24:
                regs[rt] = ('status', 0)
            else:
                regs[rt] = UNKNOWN
        elif opcode == 43:
            base = regs[rs]
            if rs != 29 or not isinstance(base, int):
                return False
            stack[base + sign16(imm)] = regs[rt]
        elif opcode == 0:
            funct = word & 63
            rd = (word >> 11) & 31
            if rd == 29 or funct not in (33, 37):
                return False
            a, b = regs[rs], regs[rt]
            if a == 0:
                regs[rd] = b
            elif b == 0:
                regs[rd] = a
            elif isinstance(a, int) and isinstance(b, int):
                regs[rd] = (a + b if funct == 33 else a | b) & 0xffffffff
            else:
                regs[rd] = UNKNOWN
        else:
            return False
        regs[0] = 0
        return True

    while pending:
        index, regs, stack, actions, kinds, branched = pending.pop()
        steps += 1
        if steps > 512 or not 0 <= index < length or not kinds:
            return None
        word = words[index]
        opcode = word >> 26
        if word == 0x03e00008:
            if (index != length - 2 or not execute(words[index + 1], regs, stack) or
                    regs[29] != 0 or regs[31] != RETURN_ADDRESS):
                return None
            terminals.append((kinds, actions, branched))
            continue
        if opcode in (4, 5, 20, 21):  # beq/bne and their likely forms.
            if index + 1 >= length:
                return None
            rs, rt = (word >> 21) & 31, (word >> 16) & 31
            left, right = regs[rs], regs[rt]
            if left == FKIND and isinstance(right, int):
                comparison = right
            elif right == FKIND and isinstance(left, int):
                comparison = left
            else:
                return None
            if not 0 <= comparison < 256:
                return None
            destination = index + 1 + sign16(word)
            if not index + 1 < destination < length - 1:
                return None  # No loops or jumps outside this routine.
            equal = frozenset(kind for kind in kinds if kind == comparison)
            other = kinds - equal
            true_kinds, false_kinds = (equal, other) if opcode in (4, 20) else (other, equal)
            if true_kinds:
                taken_regs, taken_stack = regs.copy(), stack.copy()
                if not execute(words[index + 1], taken_regs, taken_stack):
                    return None
                pending.append((destination, taken_regs, taken_stack,
                                actions.copy(), true_kinds, True))
            if false_kinds:
                false_regs, false_stack = regs.copy(), stack.copy()
                if opcode in (4, 5) and not execute(words[index + 1], false_regs, false_stack):
                    return None
                pending.append((index + 2, false_regs, false_stack,
                                actions.copy(), false_kinds, True))
            continue
        if opcode == 3:  # jal; execute its delay slot before the call.
            if index + 1 >= length or not execute(words[index + 1], regs, stack):
                return None
            kind = ENGINE_CALLS.get(jal_target(address + index * 4, word))
            if kind is None:
                return None
            if kind == 'status':
                value, frame, speed = regs[5], regs[6], regs[7]
                flags = stack.get(regs[29] + 0x10, UNKNOWN)
                if (regs[4] != GOBJ or frame != ANIM_FRAME or
                        speed != 0x3f800000 or not isinstance(flags, int) or
                        flags & ~0x7fff or not isinstance(value, int) or
                        not 0xdc <= value < 0x4000):
                    return None
                actions.append((kind, value, flags))
            elif regs[4] == FIGHTER:
                actions.append((kind, None, None))
            else:
                return None
            for number in (*range(1, 16), 24, 25):
                regs[number] = UNKNOWN
            regs[31] = UNKNOWN
            for offset in range(0, 0x14, 4):
                stack.pop(regs[29] + offset, None)
            pending.append((index + 2, regs, stack, actions, kinds, branched))
            continue
        if not execute(word, regs, stack):
            return None
        pending.append((index + 1, regs, stack, actions, kinds, branched))

    if not terminals or not all(branched for _, _, branched in terminals):
        return None
    kind_status = {}
    signature = None
    for kinds, actions, _ in terminals:
        order = tuple(action[0] for action in actions)
        if order not in ALLOWED_ORDERS:
            return None
        status_action = next(action for action in actions if action[0] == 'status')
        current_signature = (order, status_action[2])
        if signature is None:
            signature = current_signature
        elif signature != current_signature:
            return None
        for kind in kinds:
            if kind in kind_status and kind_status[kind] != status_action[1]:
                return None
            kind_status[kind] = status_action[1]
    if set(kind_status) != set(ALL_KINDS):
        return None
    counts = Counter(kind_status.values())
    fallback = max(counts, key=lambda status: (counts[status], -status))
    cases = [{'fkind': kind, 'status_id': status}
             for kind, status in sorted(kind_status.items()) if status != fallback]
    if len(cases) > 16:
        return None  # Avoid a hidden broad behavior split.
    order, flags = signature
    return {'address': f'{address:08x}', 'template': 'decoded_fkind_branch',
            'status_id': fallback, 'status_cases': cases, 'status_delta': None,
            'kinetics': order[0], 'clamp_air_speed': 'clamp_air_speed' in order,
            'preserve_flags': flags, 'action_order': list(order)}
