"""Exercise any catalogued Remix fighter in the isolated Azahar VS fixture.

This is an optional local integration check. It consumes the ignored CIA build
and the sibling native emulator harness; no ROM or extracted assets are tracked.
"""
import argparse
import json
import socket
import struct
import subprocess
import sys
import time

from common import BUILD, ROOT
from native_action_patches import BINDINGS, vanilla_callback_symbols
from native_fighter_catalog import load_catalog

sys.path.insert(0, str(ROOT.parent / 'native/tools'))
import emulator  # noqa: E402
from build import BIN, game_flags  # noqa: E402
from test_inputs import versus  # noqa: E402


OUT = BUILD / 'fighter-probe'
DATA = emulator.EMU / 'user/sdmc/3ds/ssb64-remix-falco-test'
emulator.ELF = ROOT / '3ds/build/falco-test/ssb64-falco-test.elf'
BINARY = ROOT / '3ds/build/falco-test/package/smash64-development.cxi'


def offsets():
    source = '''#include <ft/fighter.h>
#include <sc/scene.h>
#include <stddef.h>
const unsigned layout[] __attribute__((used,section(".rodata.layout")))={
offsetof(SCBattleState,players),sizeof(SCPlayerData),offsetof(SCPlayerData,fkind),
offsetof(SCPlayerData,fighter_gobj),offsetof(GObj,user_data),offsetof(FTStruct,fkind),
offsetof(FTStruct,status_id),offsetof(FTStruct,data),offsetof(FTData,file_main_id),
sizeof(FTStatusDesc),offsetof(FTStatusDesc,proc_update),
offsetof(FTStatusDesc,proc_interrupt),offsetof(FTStatusDesc,proc_physics),
offsetof(FTStatusDesc,proc_map)};'''
    path, obj, raw = (OUT / 'generic-layout.c', OUT / 'generic-layout.o',
                      OUT / 'generic-layout.bin')
    path.write_text(source)
    subprocess.run(list(map(str, [BIN / 'clang.exe', *game_flags(), '-c', path,
                                  '-o', obj])), check=True)
    subprocess.run(list(map(str, [BIN / 'llvm-objcopy.exe', '-O', 'binary',
                                  '--only-section=.rodata.layout', obj, raw])), check=True)
    return struct.unpack('<14I', raw.read_bytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('name', help='Catalogued fighter name, such as DRL')
    parser.add_argument('--through-results', action='store_true')
    args = parser.parse_args()
    name = args.name.upper()
    catalog = {row['name']: row for row in load_catalog()['fighters']}
    if name not in catalog:
        parser.error(f'{name} is not in the development fighter catalog')
    row = next(row for row in json.loads((BUILD / 'fighter-audit.json').read_text())['fighters']
               if row['name'] == name)
    expected_kind, expected_file = row['fkind'], row['files'][0]
    (players, stride, kind, gobj_off, user_off, fighter_kind, status_off,
     data_off, main_off, action_stride, *callback_offsets) = offsets()
    symbols = emulator.symbols()
    # The generated build already checked the pinned ROM and source symbols.
    # Emulator checks use only source bindings and the ignored template report,
    # so they do not need direct access to the user's ROM under another account.
    bindings = vanilla_callback_symbols()
    bindings.update({int(item['address'], 16): item['native']
                     for item in json.loads(BINDINGS.read_text())['bindings']})
    transitions = json.loads((BUILD / 'native-transition-templates.json').read_text())
    bindings.update({int(item['address'], 16): item['native']
                     for item in transitions['wrappers']})
    action_array = symbols.get(f'native_remix_{name.lower()}_actions')
    if not row['action_table']['generic_action_table_compatible'] and action_array is None:
        raise AssertionError(f'{name}: generated action array missing from executable')
    callback_checks = []
    roles = ('update', 'interrupt', 'physics', 'map')
    for status in row['action_table']['changed_inherited_statuses']:
        for role, callback in status['callbacks'].items():
            if callback is not None:
                callback_checks.append((status['status_id'], roles.index(role),
                                        int(callback['remix'], 16)))
    for status in row['action_table']['added_status_records']:
        for role_index, word in enumerate(status['words'][1:]):
            callback_checks.append((status['status_id'], role_index, int(word, 16)))
    actions = versus('fox', 'dreamland', frames=7000 if args.through_results else 2500,
                     one_minute=args.through_results,
                     cpus=3 if args.through_results else 1)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'test-input.txt').write_text(''.join(
        f'{a} {b} {keys:x} {x} {y}\n' for a, b, keys, x, y in actions))
    seen_match = False
    actions_verified = False
    statuses = set()
    result = None
    try:
        emulator.stop()
        emulator.launch('falco-test', stereo=1, frames=0, binary_override=BINARY,
                        no_captures=True)
        deadline = time.monotonic() + (300 if args.through_results else 180)
        while time.monotonic() < deadline:
            time.sleep(1.5)
            with socket.create_connection(('127.0.0.1', emulator.PORT), 3) as connection:
                connection.settimeout(4)
                emulator.command(connection, '?')

                def read(address, size):
                    return bytes.fromhex(emulator.command(connection, f'm{address:x},{size:x}'))

                frame = struct.unpack('<I', read(symbols['ssb_frame_count'], 4))[0]
                scene = read(symbols['gSCManagerSceneData'], 1)[0]
                address = symbols['gSCManagerTransferBattleState'] + players + kind
                if scene == 21:
                    assert emulator.command(connection, f'M{address:x},1:{expected_kind:02x}') == 'OK'
                if scene == 22 and frame > 1100:
                    if action_array is not None and not actions_verified:
                        for status_id, role_index, original_address in callback_checks:
                            expected_symbol = bindings.get(original_address)
                            expected = symbols[expected_symbol] if expected_symbol else 0
                            slot = (action_array + (status_id - 0xdc) * action_stride
                                    + callback_offsets[role_index])
                            actual = struct.unpack('<I', read(slot, 4))[0]
                            if actual != expected:
                                raise AssertionError((name, status_id, roles[role_index],
                                                      hex(actual), hex(expected)))
                        actions_verified = True
                    battle = struct.unpack('<I', read(symbols['gSCManagerBattleState'], 4))[0]
                    player = battle + players
                    selected = read(player + kind, 1)[0]
                    gobj = struct.unpack('<I', read(player + gobj_off, 4))[0]
                    if gobj:
                        fp = struct.unpack('<I', read(gobj + user_off, 4))[0]
                        live_kind = read(fp + fighter_kind, 1)[0] if fp else None
                        status = struct.unpack('<I', read(fp + status_off, 4))[0] if fp else None
                        data = struct.unpack('<I', read(fp + data_off, 4))[0] if fp else None
                        main_file = struct.unpack('<I', read(data + main_off, 4))[0] if data else None
                    else:
                        live_kind = status = main_file = None
                    if selected == live_kind == expected_kind and main_file == expected_file:
                        seen_match = True
                        statuses.add(status)
                    result = {'name': name, 'frame': frame, 'scene': scene,
                              'selected_fkind': selected, 'fighter_fkind': live_kind,
                              'main_file_id': main_file,
                              'compiled_action_callbacks_verified':
                              len(callback_checks) if actions_verified else None}
                    if not args.through_results and seen_match and frame >= 2000 and len(statuses) > 1:
                        result['passed'] = True
                if args.through_results and scene == 24 and seen_match:
                    result = {'name': name, 'frame': frame, 'scene': scene,
                              'fighter_fkind': expected_kind,
                              'main_file_id': expected_file,
                              'compiled_action_callbacks_verified':
                              len(callback_checks) if actions_verified else None,
                              'passed': True}
                emulator.packet(connection, 'c')
                emulator.packet(connection, 'D')
                emulator.receive(connection)
            if result and result.get('passed'):
                break
        if not result or not result.get('passed'):
            raise AssertionError(result or 'Fighter did not enter match')
        result['observed_statuses'] = sorted(statuses)
        assert not any(message in (DATA / 'game.log').read_text(errors='replace')
                       for message in ('ABORT', 'invalid/stale token', 'unported command'))
        log = (emulator.EMU / 'user/log/azahar_log.txt').read_text(errors='replace')
        assert 'unmapped Read' not in log and 'unmapped Write' not in log
        suffix = '-results' if args.through_results else '-match'
        (OUT / f'{name.lower()}-generic{suffix}.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    finally:
        emulator.stop()


if __name__ == '__main__':
    main()
