"""Host checks for parameter-only copies of original game callbacks."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from common import ROOT
from native_vanilla_clone_callbacks import (LAG_WORD_INDEX, MARIO_HI_MAP_WORDS,
                                            decode_lag_clone, extract_clones,
                                            render_native_code)


def original_words():
    words = [0] * MARIO_HI_MAP_WORDS
    words[LAG_WORD_INDEX] = 0x3c063e8f
    words[-2] = 0x03e00008
    return words


class FakeReference:
    def __init__(self, path, code):
        self.path = path
        self.code = code

    def words(self, address, count):
        return (self.code[address] + [0] * count)[:count]


class CloneTests(unittest.TestCase):
    def test_entire_copy_is_checked_and_only_finite_lag_is_extracted(self):
        source = original_words()
        clone = source.copy()
        clone[LAG_WORD_INDEX] = 0x3c063e80
        self.assertEqual(decode_lag_clone(clone, source), 0x3e80)
        clone[12] = 1
        self.assertIsNone(decode_lag_clone(clone, source))
        clone[12] = 0
        clone[LAG_WORD_INDEX] = 0x3c067f80  # infinity
        self.assertIsNone(decode_lag_clone(clone, source))
        clone[LAG_WORD_INDEX] = 0x3c063e80
        clone[-2] = 0
        self.assertIsNone(decode_lag_clone(clone, source))

    def test_all_targets_are_scanned_without_fighter_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reference.z64'
            path.write_bytes(b'pinned fixture')
            source = original_words()
            code = {}
            targets = []
            for index, fighter in enumerate(('FALCO', 'PEACH', 'WOLF')):
                address = 0x80500000 + index * 0x100
                words = source.copy()
                words[LAG_WORD_INDEX] = 0x3c063e80 if index < 2 else 0x3c063ec0
                code[address] = words
                targets.append({'address': f'{address:08x}', 'symbols': [fighter + '.collision'],
                                'uses': [{'fighter': fighter, 'status_id': 220}]})
            worklist = {'reference_rom_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'targets': targets}
            report = extract_clones(FakeReference(path, code), worklist, source)
            self.assertEqual(report['recognized_callbacks'], 3)
            self.assertEqual(report['action_table_uses'], 3)
            self.assertEqual(len({row['native'] for row in report['accepted']}), 2)
            worklist['reference_rom_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'pinned reference ROM differ'):
                extract_clones(FakeReference(path, code), worklist, source)

    def test_generated_native_map_branches(self):
        config = ROOT / '3ds/build-config.json'
        compiler = None
        if config.exists():
            binary = Path(json.loads(config.read_text())['llvm_bin']) / 'clang.exe'
            if binary.exists():
                compiler = str(binary)
        compiler = compiler or shutil.which('clang') or shutil.which('gcc')
        if compiler is None:
            self.skipTest('No host C compiler')
        generated = render_native_code({'accepted': [
            {'landing_lag_bits': '3e800000', 'native': 'nativeRemixMarioHiMapLag_3e80'}]})
        fixture = r'''
#include <assert.h>
typedef float f32;
typedef int sb32;
#define FALSE 0
#define nMPKineticsAir 1
#define MAP_FLAG_CLIFF_MASK 4
typedef struct FTStruct {
    int ga;
    struct { struct { int flag1; } flags; } motion_vars;
    struct { struct { float y; } vel_air; } physics;
    struct { int mask_stat; } coll_data;
} FTStruct;
typedef struct GObj { FTStruct *fp; } GObj;
static int project_calls, pass_calls, cliff_calls, land_calls, fall_calls, pass_result;
static float last_lag;
static FTStruct *ftGetStruct(GObj *g) { return g->fp; }
static sb32 ftMarioSpecialHiProcPass(GObj *g) { (void)g; return 1; }
static sb32 mpCommonCheckFighterProject(GObj *g) { (void)g; project_calls++; return 1; }
static sb32 mpCommonCheckFighterPassCliff(GObj *g, sb32 (*check)(GObj *)) {
    assert(check == ftMarioSpecialHiProcPass); (void)g; pass_calls++; return pass_result;
}
static void ftCommonCliffCatchSetStatus(GObj *g) { (void)g; cliff_calls++; }
static void ftCommonLandingFallSpecialSetStatus(GObj *g, sb32 flag, f32 lag) {
    (void)g; assert(flag == FALSE); land_calls++; last_lag = lag;
}
static void mpCommonSetFighterFallOnEdgeBreak(GObj *g) { (void)g; fall_calls++; }
''' + generated + r'''
int main(void) {
    FTStruct fp = {0}; GObj g = {&fp};
    fp.ga = nMPKineticsAir; fp.physics.vel_air.y = -1;
    nativeRemixMarioHiMapLag_3e80(&g);
    assert(project_calls == 1 && pass_calls == 0);
    fp.motion_vars.flags.flag1 = 1; fp.physics.vel_air.y = 1;
    nativeRemixMarioHiMapLag_3e80(&g);
    assert(project_calls == 2);
    fp.physics.vel_air.y = -1;
    nativeRemixMarioHiMapLag_3e80(&g);
    assert(pass_calls == 1 && land_calls == 0);
    pass_result = 1; fp.coll_data.mask_stat = MAP_FLAG_CLIFF_MASK;
    nativeRemixMarioHiMapLag_3e80(&g);
    assert(cliff_calls == 1);
    fp.coll_data.mask_stat = 0;
    nativeRemixMarioHiMapLag_3e80(&g);
    assert(land_calls == 1 && last_lag == 0.25f);
    fp.ga = 0;
    nativeRemixMarioHiMapLag_3e80(&g);
    assert(fall_calls == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'clone.c'
            executable = Path(directory) / 'clone.exe'
            source.write_text(fixture)
            subprocess.run([compiler, '-std=gnu11', str(source), '-o', str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    unittest.main()
