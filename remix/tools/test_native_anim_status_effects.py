"""Check restricted animation-end status decoding and generated ARM behavior."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from common import ROOT
from native_anim_end_templates import render_native_code
from native_straightline_transitions import decode_straightline


FLAG_ADDRESS = 0x805F2FBC
FRAME_ADDRESS = 0x805F32AC
FLAG_WORDS = [
    0x27bdffc0, 0xafbf001c, 0xafa40020, 0x8fa40020,
    0x340500ed, 0x00003025, 0x3c073f80, 0x0c039bc9,
    0xafa00010, 0x8fa40020, 0x8c880084, 0x34010001,
    0xad01017c, 0x8fbf001c, 0x03e00008, 0x27bd0040,
]
FRAME_WORDS = [
    0x27bdffc0, 0xafbf001c, 0xafa40020, 0x8fa40020,
    0x340500de, 0x3c0640c0, 0x3c073f80, 0x0c039bc9,
    0xafa00010, 0x0c03820c, 0x8fa40020, 0x8fbf001c,
    0x03e00008, 0x27bd0040,
]


class FakeReference:
    def __init__(self):
        self.code = {FLAG_ADDRESS: FLAG_WORDS.copy(), FRAME_ADDRESS: FRAME_WORDS.copy()}

    def words(self, address, count):
        return (self.code[address] + [0] * count)[:count]


def decode(ref, address):
    return decode_straightline(ref, address, allow_status_only=True,
                               allow_entry_resets=True, allow_motion_flag_writes=True,
                               allow_constant_frame=True)


class AnimationStatusTests(unittest.TestCase):
    def test_constant_flag_and_start_frame_are_explicit_and_fail_closed(self):
        ref = FakeReference()
        flag = decode(ref, FLAG_ADDRESS)
        frame = decode(ref, FRAME_ADDRESS)
        self.assertEqual(flag['template'], 'decoded_status_motion_flags')
        self.assertEqual((flag['status_id'], flag['set_motion_flags']),
                         (237, [{'index': 0, 'value': 1}]))
        self.assertEqual((frame['status_id'], frame['frame_begin'], frame['frame_value'],
                          frame['play_anim']), (222, 'constant', 6.0, True))
        ref.code[FLAG_ADDRESS][11] = 0x34010002
        self.assertIsNone(decode(ref, FLAG_ADDRESS))
        ref.code[FLAG_ADDRESS][11] = FLAG_WORDS[11]
        ref.code[FRAME_ADDRESS][5] = 0x3c067f80  # non-finite start frame
        self.assertIsNone(decode(ref, FRAME_ADDRESS))
        ref.code[FRAME_ADDRESS][5] = FRAME_WORDS[5]
        ref.code[FRAME_ADDRESS][3] = 0x14800001  # new branch
        self.assertIsNone(decode(ref, FRAME_ADDRESS))
        ref.code[FLAG_ADDRESS] = (FLAG_WORDS[:9] + [0x0c03820c, 0x8fa40020]
                                  + FLAG_WORDS[9:])
        self.assertTrue(decode(ref, FLAG_ADDRESS)['play_anim'])

    def test_generated_callbacks_apply_the_decoded_effects(self):
        config = ROOT / '3ds/build-config.json'
        compiler = None
        if config.exists():
            binary = Path(json.loads(config.read_text())['llvm_bin']) / 'clang.exe'
            if binary.exists():
                compiler = str(binary)
        compiler = compiler or shutil.which('clang') or shutil.which('gcc')
        if compiler is None:
            self.skipTest('No host C compiler')
        ref = FakeReference()
        code = render_native_code({'transitions': [decode(ref, FLAG_ADDRESS),
                                                    decode(ref, FRAME_ADDRESS)],
                                   'wrappers': [
                                       {'native': 'testFlagEnd',
                                        'transition_address': f'{FLAG_ADDRESS:08x}'},
                                       {'native': 'testFrameEnd',
                                        'transition_address': f'{FRAME_ADDRESS:08x}'}]})
        fixture = r'''
#include <assert.h>
#define FTSTATUS_PRESERVE_NONE 0
#define FTSTATUS_PRESERVE_HIT 1
typedef struct FTStruct { struct { struct { int flag0; } flags; } motion_vars; } FTStruct;
typedef struct GObj { FTStruct *fp; float anim_frame; } GObj;
static int status, play_count; static float frame, speed;
static FTStruct *ftGetStruct(GObj *g) { return g->fp; }
static void ftMainSetStatus(GObj *g, int s, float f, float v, unsigned flags) {
    (void)g; assert(flags == 0); status = s; frame = f; speed = v;
}
static void ftMainPlayAnimEventsAll(GObj *g) { (void)g; play_count++; }
static void ftAnimEndCheckSetStatus(GObj *g, void (*callback)(GObj *)) { callback(g); }
''' + code + r'''
int main(void) {
    FTStruct fp = {0}; GObj g = {&fp, 9.0f};
    testFlagEnd(&g);
    assert(status == 237 && frame == 0.0f && speed == 1.0f);
    assert(fp.motion_vars.flags.flag0 == 1 && play_count == 0);
    testFrameEnd(&g);
    assert(status == 222 && frame == 6.0f && speed == 1.0f);
    assert(play_count == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'animation.c'
            executable = Path(directory) / 'animation.exe'
            source.write_text(fixture)
            subprocess.run([compiler, '-std=gnu11', str(source), '-o', str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    unittest.main()
