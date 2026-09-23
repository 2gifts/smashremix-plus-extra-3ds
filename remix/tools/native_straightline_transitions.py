"""Symbolically decode side-effect-limited compiled MIPS status transitions.

This is deliberately a small, offline translator, not a MIPS runtime. It
accepts straight-line routines whose only effects are known original engine
calls and stack writes. Every input to those calls must resolve to a known
constant or a mapped fighter field. Anything else remains unbound.
"""

import math
import struct

from classify_action_callbacks import first_return_words, jal_target


UNKNOWN = object()
GOBJ = ('gobj',)
FIGHTER = ('fighter',)
ANIM_FRAME = ('anim_frame',)
RETURN_ADDRESS = ('return_address',)

ENGINE_CALLS = {
    0x800DEE98: 'ground',
    0x800DEEC8: 'air',
    0x800E6F24: 'status',
    0x800D8EB8: 'clamp_air_speed',
}


def sign16(value):
    value &= 0xffff
    return value - 0x10000 if value & 0x8000 else value


def add_value(value, amount):
    if isinstance(value, int):
        return (value + amount) & 0xffffffff
    if isinstance(value, tuple) and value[0] == 'status':
        return ('status', value[1] + amount)
    return UNKNOWN


def decode_straightline(ref, address, allow_status_only=False):
    words = ref.words(address, 128)
    length = first_return_words(words)
    if length is None or length > 64:
        return None
    words = words[:length]
    registers = [UNKNOWN] * 32
    registers[0] = 0
    registers[4] = GOBJ
    registers[29] = 0  # Stack offsets are relative to the entry SP.
    registers[31] = RETURN_ADDRESS
    stack = {}
    actions = []
    index = 0

    def execute(word):
        opcode = word >> 26
        rs, rt = (word >> 21) & 31, (word >> 16) & 31
        imm = word & 0xffff
        if word == 0:
            return True
        if opcode in (4, 5, 6, 7, 20, 21, 22, 23) or opcode == 1:
            return False  # No branch or branch-likely delay slots.
        if opcode in (9, 12, 13, 15, 35) and rt == 29 and not (opcode == 9 and rs == 29):
            return False  # SP must remain an offset from the entry stack.
        if opcode == 15:  # lui
            registers[rt] = imm << 16
        elif opcode == 13:  # ori
            base = registers[rs]
            registers[rt] = base | imm if isinstance(base, int) else UNKNOWN
        elif opcode == 12:  # andi
            base = registers[rs]
            registers[rt] = base & imm if isinstance(base, int) else UNKNOWN
        elif opcode == 9:  # addiu
            registers[rt] = add_value(registers[rs], sign16(imm))
            if rt == 29 and not (0xfffff000 <= registers[29] <= 0xffffffff or
                                 0 <= registers[29] <= 0x1000):
                return False
        elif opcode == 35:  # lw
            base = registers[rs]
            offset = sign16(imm)
            if rs == 29 and isinstance(base, int):
                registers[rt] = stack.get(base + offset, UNKNOWN)
            elif base == GOBJ and offset == 0x84:
                registers[rt] = FIGHTER
            elif base == GOBJ and offset == 0x78:
                registers[rt] = ANIM_FRAME
            elif base == FIGHTER and offset == 0x24:
                registers[rt] = ('status', 0)
            else:
                registers[rt] = UNKNOWN
        elif opcode == 43:  # sw: the only allowed memory writes are local.
            base = registers[rs]
            if rs != 29 or not isinstance(base, int):
                return False
            stack[base + sign16(imm)] = registers[rt]
        elif opcode == 0:
            funct = word & 63
            rd = (word >> 11) & 31
            if rd == 29:
                return False
            if funct in (33, 37):  # addu / or
                a, b = registers[rs], registers[rt]
                if a == 0:
                    registers[rd] = b
                elif b == 0:
                    registers[rd] = a
                elif isinstance(a, int) and isinstance(b, int):
                    registers[rd] = (a + b if funct == 33 else a | b) & 0xffffffff
                else:
                    registers[rd] = UNKNOWN
            else:
                return False
        else:
            return False
        registers[0] = 0
        return True

    while index < length:
        word = words[index]
        if word == 0x03e00008:  # jr ra, followed by exactly one delay slot.
            if index != length - 2 or not execute(words[index + 1]):
                return None
            if registers[29] != 0 or registers[31] != RETURN_ADDRESS:
                return None
            break
        if word >> 26 == 3:  # jal; delay slot executes before the call.
            if index + 1 >= length or not execute(words[index + 1]):
                return None
            target = jal_target(address + index * 4, word)
            kind = ENGINE_CALLS.get(target)
            if allow_status_only and target == 0x800E0830:
                kind = 'play_anim'
            if kind is None:
                return None
            if kind == 'status':
                value, frame, speed = registers[5], registers[6], registers[7]
                flags = stack.get(registers[29] + 0x10, UNKNOWN)
                if (registers[4] != GOBJ or frame not in (ANIM_FRAME, 0) or
                        not isinstance(speed, int) or not isinstance(flags, int) or
                        flags & ~0x7fff):
                    return None
                speed_float = struct.unpack('>f', struct.pack('>I', speed & 0xffffffff))[0]
                if (not math.isfinite(speed_float) or
                        not 0.0 < speed_float <= 256.0 or
                        (not allow_status_only and speed != 0x3f800000)):
                    return None
                if isinstance(value, int):
                    # Transitions may deliberately return to a vanilla
                    # common status, such as LandingHeavy (0x20).
                    if not 0 <= value < 0x4000:
                        return None
                    status = value
                    delta = None
                elif (isinstance(value, tuple) and value[0] == 'status' and
                      -128 <= value[1] <= 128):
                    status = None
                    delta = value[1]
                else:
                    return None
                actions.append({'kind': kind, 'status_id': status,
                                'status_delta': delta, 'preserve_flags': flags,
                                'frame_begin': 'zero' if frame == 0 else 'current',
                                'speed': speed_float})
            elif kind == 'play_anim' and registers[4] == GOBJ:
                actions.append({'kind': kind})
            elif kind in ('ground', 'air', 'clamp_air_speed') and registers[4] == FIGHTER:
                actions.append({'kind': kind})
            else:
                return None
            for number in (*range(1, 16), 24, 25):
                registers[number] = UNKNOWN  # MIPS caller-saved registers.
            registers[31] = UNKNOWN  # jal overwrites ra; epilogue must restore it.
            # A callee may use its incoming argument home area. Its contents
            # cannot be carried across calls as if they were private locals.
            for offset in range(0, 0x14, 4):
                stack.pop(registers[29] + offset, None)
            index += 2
            continue
        if not execute(word):
            return None
        index += 1
    kinds = [action['kind'] for action in actions]
    if allow_status_only and kinds in (['status'], ['status', 'play_anim']):
        status_action = actions[0]
        if status_action['status_id'] is None:
            return None
        return {'address': f'{address:08x}', 'template': 'decoded_status_only',
                'status_id': status_action['status_id'],
                'preserve_flags': status_action['preserve_flags'],
                'frame_begin': status_action['frame_begin'],
                'speed': status_action['speed'],
                'play_anim': kinds[-1] == 'play_anim'}
    if (kinds not in (['ground', 'status'], ['air', 'status'],
                      ['air', 'status', 'clamp_air_speed'],
                      ['air', 'clamp_air_speed', 'status'])):
        return None
    status_action = next(action for action in actions if action['kind'] == 'status')
    result = {'address': f'{address:08x}', 'template': 'decoded_straightline',
            'status_id': status_action['status_id'],
            'status_delta': status_action['status_delta'],
            'kinetics': kinds[0],
            'clamp_air_speed': 'clamp_air_speed' in kinds,
            'preserve_flags': status_action['preserve_flags'],
            'action_order': kinds}
    if status_action['frame_begin'] == 'zero':
        result['frame_begin'] = 'zero'
    return result
