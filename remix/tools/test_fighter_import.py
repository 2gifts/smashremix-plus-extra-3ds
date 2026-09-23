"""Asset-free regression tests for motion pointer and split audio conversion."""
import struct
import subprocess
import unittest
from types import SimpleNamespace
from common import ROOT, BUILD
from prepare_fighter_probe import Scripts, Reference
from prepare_reference_audio import Bank, package, verify_bank
from test_asset_loader import compiler_path


class WordReference:
    def __init__(self, words):
        self.data = words

    def words(self, address, count):
        return [self.data[address + i * 4] for i in range(count)]


class MotionTests(unittest.TestCase):
    def test_jpika_quick_attack_collision_follows_japanese_flow(self):
        source = (ROOT / '3ds/src/remix_jpika_probe.c').read_text()
        start = source.index('static void jpikaQuickAttackMap(')
        function = source[start:source.index('\n}', start) + 2]
        fixture = '''#include <assert.h>
typedef struct { unsigned mask_curr; } Coll;
typedef struct { Coll coll_data; } FTStruct;
typedef struct { FTStruct fighter; } GObj;
#define FALSE 0
#define MAP_FLAG_RWALL 1
#define MAP_FLAG_LWALL 2
static int on_floor, calls[4], count;
static FTStruct *ftGetStruct(GObj *g) { return &g->fighter; }
static int mpCommonCheckFighterOnFloor(GObj *g) { (void)g; return on_floor; }
static void mpCommonSetFighterAir(FTStruct *f) { (void)f; calls[count++] = 1; }
static void ftPikachuSpecialAirHiEndSetStatus(GObj *g) { (void)g; calls[count++] = 2; }
static void ftPikachuSpecialHiSwitchStatusAir(GObj *g) { (void)g; calls[count++] = 3; }
static void ftPikachuSpecialHiEndSetStatus(GObj *g) { (void)g; calls[count++] = 4; }
''' + function + '''
int main(void) {
    GObj g = {0};
    on_floor = 1; count = 0; jpikaQuickAttackMap(&g); assert(count == 0);
    g.fighter.coll_data.mask_curr = MAP_FLAG_RWALL;
    on_floor = 1; count = 0; jpikaQuickAttackMap(&g); assert(count == 1 && calls[0] == 4);
    g.fighter.coll_data.mask_curr = 0;
    on_floor = 0; count = 0; jpikaQuickAttackMap(&g); assert(count == 1 && calls[0] == 3);
    g.fighter.coll_data.mask_curr = MAP_FLAG_LWALL;
    on_floor = 0; count = 0; jpikaQuickAttackMap(&g);
    assert(count == 3 && calls[0] == 1 && calls[1] == 2 && calls[2] == 4);
    return 0;
}
'''
        out = BUILD / 'fighter-import-test'
        out.mkdir(parents=True, exist_ok=True)
        path, exe = out / 'jpika_collision.c', out / 'jpika-collision-test.exe'
        path.write_text(fixture)
        cc = compiler_path(None).replace('clang++', 'clang')
        subprocess.run([cc, '-std=gnu11', str(path), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

    def test_jpika_thunder_jolt_lifetime_preserves_vanilla(self):
        source = (ROOT / 'src/wp/wppikachu/wppikachuthunderjolt.c').read_text()
        start = source.index('static s32 wpPikachuThunderJoltLifetime(')
        function = source[start:source.index('\n}', start) + 2]
        fixture = '''#include <assert.h>
#include "native_remix_roster.h"
typedef int s32;
typedef struct { unsigned fkind; } FTStruct;
typedef struct { FTStruct *fighter; } GObj;
static FTStruct *ftGetStruct(GObj *g) { return g->fighter; }
#define WPPIKACHUJOLT_LIFETIME 100
''' + function + '''
int main(void) {
    FTStruct f = {NATIVE_REMIX_PIKACHU_KIND}; GObj g = {&f};
    assert(wpPikachuThunderJoltLifetime(&g) == 100);
    f.fkind = NATIVE_REMIX_JPIKA_KIND;
    assert(wpPikachuThunderJoltLifetime(&g) == 120);
    return 0;
}
'''
        out = BUILD / 'fighter-import-test'
        out.mkdir(parents=True, exist_ok=True)
        path, exe = out / 'jpika_jolt.c', out / 'jpika-jolt-test.exe'
        path.write_text(fixture)
        cc = compiler_path(None).replace('clang++', 'clang')
        subprocess.run([cc, '-std=gnu11', '-I' + str(ROOT / '3ds/include'),
                        str(path), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

    def test_kirby_copy_table_bounds_and_parent_fallback(self):
        source = (ROOT / 'src/ft/ftchar/ftkirby/ftkirbyspecialn.c').read_text()
        start = source.index('static s32 ftKirbySpecialNGetCopyTableKind(')
        function = source[start:source.index('\n}', start) + 2]
        fixture = '''#include <assert.h>
#include <stdint.h>
#include "native_remix_roster.h"
typedef int32_t s32;
typedef uint32_t u32;
enum { nFTKindMario, nFTKindFox, nFTKindDonkey, nFTKindSamus,
       nFTKindLuigi, nFTKindLink, nFTKindYoshi, nFTKindCaptain,
       nFTKindKirby, nFTKindPikachu, nFTKindGDonkey = 27 };
#define FTKIRBY_COPY_TABLE_COUNT 27
''' + function + '''
int main(void) {
    assert(ftKirbySpecialNGetCopyTableKind(nFTKindMario) == nFTKindMario);
    assert(ftKirbySpecialNGetCopyTableKind(nFTKindFox) == nFTKindFox);
    assert(ftKirbySpecialNGetCopyTableKind(nFTKindGDonkey) == nFTKindDonkey);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_FALCO_KIND) == nFTKindFox);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_DKULT_KIND) == nFTKindDonkey);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JPIKA_KIND) == nFTKindPikachu);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JMARIO_KIND) == nFTKindMario);
    assert(ftKirbySpecialNGetCopyTableKind(28) == nFTKindKirby);
    assert(ftKirbySpecialNGetCopyTableKind(999) == nFTKindKirby);
    assert(ftKirbySpecialNGetCopyTableKind(-1) == nFTKindKirby);
    return 0;
}
'''
        out = BUILD / 'fighter-import-test'
        out.mkdir(parents=True, exist_ok=True)
        path, exe = out / 'kirby_copy.c', out / 'kirby-copy-test.exe'
        path.write_text(fixture)
        cc = compiler_path(None).replace('clang++', 'clang')
        subprocess.run([cc, '-std=gnu11', '-DSSB_REMIX_PROBE',
                        '-I' + str(ROOT / '3ds/include'),
                        str(path), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

    def test_native_animation_classification_does_not_touch_menu_file_zero(self):
        source = (ROOT / '3ds/src/remix_falco_probe.c').read_text()
        start = source.index('int nativeRelocIsFighterAnimation(')
        function = source[start:source.index('\n}', start) + 2]
        dk_source = (ROOT / '3ds/src/remix_dkult_probe.c').read_text()
        dk_start = dk_source.index('int nativeRemixDKUltIsAnimation(')
        dk_function = dk_source[dk_start:dk_source.index('\n}', dk_start) + 2]
        jp_source = (ROOT / '3ds/src/remix_jpika_probe.c').read_text()
        jp_start = jp_source.index('int nativeRemixJPikaIsAnimation(')
        jp_function = jp_source[jp_start:jp_source.index('\n}', jp_start) + 2]
        mario_source = (ROOT / '3ds/src/remix_jmario_probe.c').read_text()
        mario_start = mario_source.index('int nativeRemixJMarioIsAnimation(')
        mario_function = mario_source[mario_start:mario_source.index('\n}', mario_start) + 2]
        # Compile the actual native predicate against a small motion catalogue.
        fixture = '''#include <cassert>
#define ARRAY_COUNT(a) (sizeof(a)/sizeof((a)[0]))
struct Motion {unsigned anim_file_id;struct {unsigned word;} anim_desc;};
static Motion remix_main_motions[]={{0,{0}},{4,{0}},{5,{8}},{6,{2}},{7,{10}}};
static Motion remix_menu_motions[]={{0,{0}},{8,{0}}};
static Motion remix_dkult_main_motions[]={{0,{0}},{10,{0}},{11,{8}}};
static Motion remix_dkult_menu_motions[]={{0,{0}},{12,{0}}};
static Motion remix_jpika_main_motions[]={{0,{0}},{13,{0}},{14,{8}}};
static Motion remix_jpika_menu_motions[]={{0,{0}},{15,{0}}};
static Motion remix_jmario_main_motions[]={{0,{0}},{16,{0}},{17,{8}}};
static Motion remix_jmario_menu_motions[]={{0,{0}},{18,{0}}};
'''
        for line in (ROOT / 'src/ft/ftdef.h').read_text().splitlines():
            if line.startswith('#define FTANIM_FLAG_ANIMJOINT ') or line.startswith('#define FTANIM_FLAG_SHIELDPOSE '):
                fixture += line + '\n'
        fixture += dk_function + '\n' + jp_function + '\n' + mario_function + '\n' + function + '''
int main(){
    assert(!nativeRelocIsFighterAnimation(0));
    assert(nativeRelocIsFighterAnimation(4));
    assert(!nativeRelocIsFighterAnimation(5));
    assert(!nativeRelocIsFighterAnimation(6));
    assert(!nativeRelocIsFighterAnimation(7));
    assert(nativeRelocIsFighterAnimation(8));
    assert(!nativeRelocIsFighterAnimation(9));
    assert(nativeRelocIsFighterAnimation(10));
    assert(!nativeRelocIsFighterAnimation(11));
    assert(nativeRelocIsFighterAnimation(12));
    assert(nativeRelocIsFighterAnimation(13));
    assert(!nativeRelocIsFighterAnimation(14));
    assert(nativeRelocIsFighterAnimation(15));
    assert(nativeRelocIsFighterAnimation(16));
    assert(!nativeRelocIsFighterAnimation(17));
    assert(nativeRelocIsFighterAnimation(18));
    assert(!nativeRemixDKUltIsAnimation(0));
    assert(!nativeRemixJPikaIsAnimation(0));
    assert(!nativeRemixJMarioIsAnimation(0));
}
'''
        out = BUILD / 'fighter-import-test'
        out.mkdir(parents=True, exist_ok=True)
        path, exe = out / 'animation.cpp', out / 'animation-test.exe'
        path.write_text(fixture)
        subprocess.run([compiler_path(None), '-std=c++17', str(path), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

    def test_shared_subroutine_cycle_and_throw_records(self):
        words = {0x100: 0xd0003f80, 0x104: 34 << 26, 0x108: 0x200, 0x10c: 0,
                 0x200: 12 << 26, 0x204: 0x300, 0x208: 36 << 26, 0x20c: 0x100}
        words.update({0x300 + i * 4: i + 1 for i in range(14)})
        scripts = Scripts(WordReference(words))
        scripts.script(0x100)
        scripts.script(0x200)
        lines, indices = scripts.emit()
        self.assertEqual(len(scripts.visited), 5)
        self.assertEqual(scripts.pointers, {0x108: 0x200, 0x204: 0x300, 0x20c: 0x100})
        self.assertEqual(indices[0x10c], indices[0x104] + 2)
        self.assertEqual(indices[0x334], indices[0x300] + 13)
        self.assertEqual(sum('portRelocRegisterPointer' in s for s in lines), 3)

    def test_unknown_extended_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unported command'):
            Scripts(WordReference({0x100: 0xd4000000})).script(0x100)

    def test_extra_hit_multipliers_decode_and_validate(self):
        valid = {0x100: 0xdd003f80, 0x104: 0xde103f00, 0x108: 0}
        scripts = Scripts(WordReference(valid), allow_custom=True)
        scripts.script(0x100)
        self.assertEqual(scripts.custom_commands[0xdd], 1)
        self.assertEqual(scripts.custom_commands[0xde], 1)
        for word, reason in ((0xdd043f80, 'Invalid hitbox slot'),
                             (0xde007f80, 'Nonfinite hit multiplier')):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, reason):
                Scripts(WordReference({0x100: word}), allow_custom=True).script(0x100)

    def test_native_extra_hit_multipliers_apply_to_hit_and_di(self):
        source = (ROOT / '3ds/src/remix_falco_probe.c').read_text()
        def function(name):
            start = source.index(name + '(')
            start = source.rfind('\n', 0, start) + 1
            return source[start:source.index('\n}', start) + 2]
        fixture = '''#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
typedef uint32_t u32;
typedef struct FTAttackColl { int unused; } FTAttackColl;
typedef struct FTStruct {
    unsigned player;
    FTAttackColl attack_colls[4];
    float hitlag_mul;
} FTStruct;
static unsigned short hitlag_mul[4][4];
static unsigned short hit_di_mul[4][4];
static float victim_di_mul[4] = {1, 1, 1, 1};
'''
        for name in ('upperHalfFloat', 'setHitMultiplier',
                     'nativeRemixProbeApplyHitMultipliers', 'nativeRemixProbeDiMultiplier'):
            fixture += function(name) + '\n'
        fixture += '''int main(void) {
    FTStruct attacker = {.player = 0, .hitlag_mul = 1.5f};
    FTStruct victim = {.player = 1, .hitlag_mul = 1.5f};
    for (unsigned p = 0; p < 4; p++) for (unsigned s = 0; s < 4; s++) {
        hitlag_mul[p][s] = 0xffffu;
        hit_di_mul[p][s] = 0xffffu;
    }
    setHitMultiplier(hitlag_mul, 0, 0x10, 0x3f00u); /* all slots: 0.5 */
    setHitMultiplier(hit_di_mul, 0, 0x02, 0x4000u); /* slot 2: 2.0 */
    nativeRemixProbeApplyHitMultipliers(&victim, &attacker, &attacker.attack_colls[2]);
    assert(attacker.hitlag_mul == 0.5f && victim.hitlag_mul == 0.5f);
    assert(nativeRemixProbeDiMultiplier(&victim) == 2.0f);
    nativeRemixProbeApplyHitMultipliers(&victim, &attacker, &attacker.attack_colls[1]);
    assert(nativeRemixProbeDiMultiplier(&victim) == 1.0f);
    setHitMultiplier(hitlag_mul, 0, 0x10, 0xffffu);
    attacker.hitlag_mul = victim.hitlag_mul = 1.5f;
    nativeRemixProbeApplyHitMultipliers(&victim, &attacker, &attacker.attack_colls[1]);
    assert(attacker.hitlag_mul == 1.5f && victim.hitlag_mul == 1.5f);
    nativeRemixProbeApplyHitMultipliers(&victim, 0, 0);
    assert(nativeRemixProbeDiMultiplier(&victim) == 1.0f);
    return 0;
}
'''
        out = BUILD / 'fighter-import-test'
        out.mkdir(parents=True, exist_ok=True)
        path, exe = out / 'multipliers.c', out / 'multipliers-test.exe'
        path.write_text(fixture)
        cc = compiler_path(None).replace('clang++', 'clang')
        subprocess.run([cc, '-std=gnu11', str(path), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

    def test_reference_import_retains_random_sound_array_and_native_menu_script(self):
        words = {0x100: 0xd6ff0003, 0x104: 0x400,
                 0x108: 34 << 26, 0x10c: 0x300, 0x110: 0,
                 0x400: 0x12345678, 0x404: 0x9abc0000}
        scripts = Scripts(WordReference(words), allow_custom=True,
                          external_scripts={0x300: 'D_ovl1_803918A4'})
        scripts.script(0x100)
        lines, indices = scripts.emit()
        self.assertEqual(scripts.pointers, {0x104: 0x400, 0x10c: 0x300})
        self.assertEqual(scripts.custom_commands[0xd6], 1)
        self.assertEqual(indices[0x404], indices[0x400] + 1)
        self.assertIn('extern s32 D_ovl1_803918A4[];', lines)
        self.assertTrue(any('portRelocRegisterPointer(D_ovl1_803918A4)' in line for line in lines))

    def test_seek_replay_skips_reference_excluded_commands(self):
        source = (ROOT / '3ds/src/remix_falco_probe.c').read_text()
        start = source.index('void nativeRemixProbeSeekCommand(')
        function = source[start:source.index('\n}', start) + 2]
        fixture = '''#include <cassert>
#include <initializer_list>
using u32 = unsigned;
struct GObj {};
struct FTStruct {};
struct FTMotionScript {unsigned *p_script;};
static int dispatched;
void nativeRemixProbeCommand(GObj *, FTStruct *, FTMotionScript *ms) {
    dispatched++;
    ms->p_script++;
}
''' + function + '''
int main() {
    GObj g; FTStruct f;
    unsigned words[3] = {0, 0x12345678, 0};
    FTMotionScript ms;
    for (unsigned byte : {0xd4u,0xd5u,0xdau}) {
        words[0]=byte<<24; ms.p_script=words; dispatched=0;
        nativeRemixProbeSeekCommand(&g,&f,&ms);
        assert(ms.p_script==words+1 && dispatched==0);
    }
    for (unsigned byte : {0xd6u,0xd9u,0xdcu}) {
        words[0]=byte<<24; ms.p_script=words; dispatched=0;
        nativeRemixProbeSeekCommand(&g,&f,&ms);
        assert(ms.p_script==words+2 && dispatched==0);
    }
    for (unsigned byte : {0xd0u,0xd1u,0xd2u,0xd3u,0xd7u,0xd8u,0xdbu,0xddu,0xdeu}) {
        words[0]=byte<<24; ms.p_script=words; dispatched=0;
        nativeRemixProbeSeekCommand(&g,&f,&ms);
        assert(ms.p_script==words+1 && dispatched==1);
    }
}
'''
        out = BUILD / 'fighter-import-test'
        out.mkdir(parents=True, exist_ok=True)
        path, exe = out / 'seek.cpp', out / 'seek-test.exe'
        path.write_text(fixture)
        subprocess.run([compiler_path(None), '-std=c++17', str(path), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

    def test_reference_rejects_unaligned_or_unmapped_data(self):
        ref = Reference.__new__(Reference)
        ref.rom_base, ref.ram_base, ref.rom = 16, 0x2000, bytes(64)
        self.assertEqual(ref.words(0x2000, 2), [0, 0])
        for address, count in [(0x2001, 1), (0x1ffc, 1), (0x2000, -1), (0x2030, 1)]:
            with self.assertRaises(ValueError):
                ref.words(address, count)


def bank_fixture():
    rom = bytearray(0x1100)
    ctl = bytearray(144)
    struct.pack_into('>HHI', ctl, 0, 0x4231, 1, 8)
    struct.pack_into('>HBBIII', ctl, 8, 1, 0, 0, 44100, 0, 24)
    struct.pack_into('>HI', ctl, 38, 1, 0x1000)  # sound moved to expansion RAM
    struct.pack_into('>III', ctl, 44, 60, 76, 84)
    struct.pack_into('>IIBB2xII', ctl, 84, 0, 9, 0, 0, 0, 104)
    struct.pack_into('>II', ctl, 104, 2, 1)
    rom[0x100:0x190] = ctl
    rom[0x1000:0x1010] = ctl[44:60]
    rom[0x300:0x309] = b'123456789'
    return SimpleNamespace(rom=rom, rom_base=0x1000, ram_base=0x2000, symbols={})


class AudioTests(unittest.TestCase):
    def test_split_bank_relocates_and_preserves_samples(self):
        bank = Bank(bank_fixture(), 0x100, 0x1000, 144, 0x300)
        self.assertEqual(bank.record('file', 0), 0)
        self.assertEqual(verify_bank(bank.ctl, bank.tbl), {'sound_records': 1, 'wave_records': 1})
        self.assertEqual(bank.tbl, b'123456789' + bytes(7))
        size = len(bank.ctl)
        bank.record('file', 0)
        self.assertEqual(size, len(bank.ctl))
        broken = bytearray(bank.ctl)
        struct.pack_into('>I', broken, 4, 0xfffffffc)
        with self.assertRaisesRegex(ValueError, 'outside CTL'):
            verify_bank(broken, bank.tbl)

    def test_bad_source_ranges_are_rejected(self):
        for mutation in ('pointer', 'sample', 'book'):
            ref = bank_fixture()
            offset, value = {'pointer': (0x1000, 0x300), 'sample': (0x158, 0xffffffff),
                             'book': (0x168, 0)}[mutation]
            struct.pack_into('>I', ref.rom, offset, value)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                Bank(ref, 0x100, 0x1000, 144, 0x300).record('file', 0)

    def test_package_preserves_relative_bytecode(self):
        ref = bank_fixture()
        struct.pack_into('>III', ref.rom, 0x400, 2, 12, 0x1000)
        ref.rom[0x40c:0x410] = b'ABCD'
        ref.rom[0x1000:0x1008] = b'EFGHIJKL'
        ref.symbols = {'begin': 0x2000, 'end': 0x2008}
        result = package(ref, 0x400, 0x1000, 16, 'begin', 'end')
        self.assertEqual(struct.unpack_from('>III', result), (2, 24, 28))
        self.assertEqual(result[24:], b'ABCDEFGHIJKL')
        struct.pack_into('>I', ref.rom, 0x408, 0x800)
        with self.assertRaisesRegex(ValueError, 'unrecognized pointer'):
            package(ref, 0x400, 0x1000, 16, 'begin', 'end')
        ref.symbols['end'] = 0x3000
        with self.assertRaisesRegex(ValueError, 'outside ROM'):
            package(ref, 0x400, 0x1000, 16, 'begin', 'end')


if __name__ == '__main__':
    unittest.main(verbosity=2)
