"""Host checks for verified original air-drift speed overrides."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from common import ROOT
from native_air_drift_overrides import (HELPER, MAIN, decode_air_drift,
                                        extract_air_drift, render_native_code)


MAIN_ADDRESS = 0x805A8818
HELPER_ADDRESS = 0x805A8898


class FakeReference:
    ram_base = 0x80400000

    def __init__(self, path):
        self.path = path
        self.main = list(MAIN)
        self.main[22] = 0x0c000000 | ((HELPER_ADDRESS & 0x0fffffff) >> 2)
        self.helper = list(HELPER)
        self.helper[5] = 0x3c0741e0

    def words(self, address, count):
        data = {MAIN_ADDRESS: self.main, HELPER_ADDRESS: self.helper}[address]
        return (data + [0] * count)[:count]


class AirDriftTests(unittest.TestCase):
    def test_copied_segment_helper_and_value_must_all_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reference.z64'
            path.write_bytes(b'pinned air drift fixture')
            ref = FakeReference(path)
            original = ref.main[4:20].copy()
            self.assertEqual(decode_air_drift(ref, MAIN_ADDRESS, original),
                             {'helper_address': '805a8898', 'max_speed_bits': '41e00000'})
            worklist = {'reference_rom_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'targets': [{'address': f'{MAIN_ADDRESS:08x}',
                                     'symbols': ['GoemonNSP.air_physics_'],
                                     'uses': [{'fighter': 'GOEMON', 'status_id': 220}] * 15}]}
            report = extract_air_drift(ref, worklist, original)
            self.assertEqual((report['recognized_callbacks'], report['action_table_uses']),
                             (1, 15))
            ref.main[12] ^= 1
            self.assertIsNone(decode_air_drift(ref, MAIN_ADDRESS, original))
            ref.main[12] ^= 1
            ref.helper[3] = 0x24050009
            self.assertIsNone(decode_air_drift(ref, MAIN_ADDRESS, original))
            ref.helper[3] = HELPER[3]
            ref.helper[5] = 0x3c077f80  # infinity
            self.assertIsNone(decode_air_drift(ref, MAIN_ADDRESS, original))
            worklist['reference_rom_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'pinned reference ROM differ'):
                extract_air_drift(ref, worklist, original)

    def test_generated_native_drift_paths(self):
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
            {'max_speed_bits': '41e00000', 'native': 'nativeRemixAirDriftMax_41e0'}]})
        source = r'''
#include <assert.h>
typedef float f32;
#define FALSE 0
typedef struct FTAttributes { float air_accel; } FTAttributes;
typedef struct FTStruct { int is_fastfall; FTAttributes *attr; } FTStruct;
typedef struct GObj { FTStruct *fp; } GObj;
static int fast, gravity, check, drift, friction, clamp_result;
static FTStruct *ftGetStruct(GObj *g) { return g->fp; }
static void ftPhysicsApplyFastFall(FTStruct *fp, FTAttributes *attr) {
    assert(fp->attr == attr); fast++;
}
static void ftPhysicsApplyGravityDefault(FTStruct *fp, FTAttributes *attr) {
    assert(fp->attr == attr); gravity++;
}
static int ftPhysicsCheckClampAirVelXDecMax(FTStruct *fp, FTAttributes *attr) {
    assert(fp->attr == attr); check++; return clamp_result;
}
static void ftPhysicsClampAirVelXStickRange(FTStruct *fp, int minimum, float accel, float max) {
    assert(fp->attr->air_accel == accel && minimum == 8 && max == 28.0f); drift++;
}
static void ftPhysicsApplyAirVelXFriction(FTStruct *fp, FTAttributes *attr) {
    assert(fp->attr == attr); friction++;
}
''' + generated + r'''
int main(void) {
    FTAttributes attr = {0.5f}; FTStruct fp = {0, &attr}; GObj g = {&fp};
    nativeRemixAirDriftMax_41e0(&g);
    assert(gravity == 1 && fast == 0 && check == 1 && drift == 1 && friction == 1);
    fp.is_fastfall = 1; clamp_result = 1;
    nativeRemixAirDriftMax_41e0(&g);
    assert(gravity == 1 && fast == 1 && check == 2 && drift == 1 && friction == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'drift.c'
            executable = Path(directory) / 'drift.exe'
            path.write_text(source)
            subprocess.run([compiler, '-std=gnu11', str(path), '-o', str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    unittest.main()
