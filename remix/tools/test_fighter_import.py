"""Asset-free regression tests for motion pointer and split audio conversion."""
import struct
import subprocess
import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from common import ROOT, BUILD
from prepare_fighter_probe import Scripts, Reference
from prepare_reference_audio import Bank, package, repack_sequence_bank, verify_bank
from test_asset_loader import compiler_path
from native_fighter_catalog import load_catalog, render_header, render_ui, render_generic_data, validate_reference, HEADER, UI
from audit_reference_fighters import ActionTableAudit, callback_worklist
from reference_table_patches import (discover_layouts, extract_table_patches,
                                     render_native_tables, source_layouts,
                                     validate_generic_dispatch)
from native_action_patches import (load_bindings, render_action_assignments, render_flags,
                                   vanilla_callback_symbols)
from native_fireball_patches import FIREBALL_BASE, extract_fireballs, render_rows, render_lookup
from native_patch_worklist import build_worklist
from native_kirby_patches import extract_kirby_rows, render_native_rows


class WordReference:
    def __init__(self, words):
        self.data = words

    def words(self, address, count):
        return [self.data[address + i * 4] for i in range(count)]


class MotionTests(unittest.TestCase):
    def test_kirby_inhale_rows_decode_without_vanilla_table_overrun(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / 'reference.z64').write_bytes(b'private fixture')
            (root / 'src').mkdir()
            (root / 'src/Character.asm').write_text('''
                scope kirby_inhale_struct {
                origin kirby_inhale_struct.TABLE_ORIGIN + (id.{name} * 0xC)
                }
            ''')
            ref = SimpleNamespace(path=root / 'reference.z64')
            payload = list(struct.pack('>HhfI', 77, 18, 1.5, 25))
            tables = {'layouts': {'kirby_inhale_struct': 12}, 'fighters': [
                {'name': 'TEST', 'fkind': 77, 'tables': {'kirby_inhale_struct': payload}}]}
            audit = {'fighters': [{'name': 'TEST', 'fkind': 77}]}
            manifest = extract_kirby_rows(ref, tables, audit)
            self.assertEqual(manifest['fighters'][0]['star_damage'], 25)
            self.assertIn('[77] = {77, 18, 1.5F, 25}', render_native_rows(manifest))
            tables['fighters'][0]['tables']['kirby_inhale_struct'] = list(
                struct.pack('>HhfI', 77, 18, 1.5, 0))
            with self.assertRaisesRegex(ValueError, 'invalid Kirby star damage'):
                extract_kirby_rows(ref, tables, audit)

    def test_patch_worklist_groups_shared_consumer_coverage(self):
        row = {'name': 'TEST', 'fkind': 77, 'changed_from_parent':
               ['default_costume', 'fireball', 'recovery_logic']}
        audit = {'reference_rom_sha256': 'same', 'fighters': [{'name': 'TEST',
                 'fixture_data_ready': True, 'action_table':
                 {'generic_action_table_compatible': True}}]}
        tables = {'reference_rom_sha256': 'same', 'fighters': [row]}
        fireballs = {'reference_rom_sha256': 'same', 'profiles': [{'name': 'TEST'}]}
        report = build_worklist(audit, tables, fireballs, {'fighters': [{'name': 'TEST'}]})
        self.assertEqual(report['fighters'][0]['remaining_table_families_to_review'],
                         ['recovery_logic'])
        self.assertEqual(report['families']['fireball']['importer_supported_fighters'], ['TEST'])
        fireballs['reference_rom_sha256'] = 'different'
        with self.assertRaisesRegex(ValueError, 'different reference ROMs'):
            build_worklist(audit, tables, fireballs, {'fighters': [{'name': 'TEST'}]})

    def test_fireball_macro_profiles_decode_as_shared_native_data(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / 'reference.z64').write_bytes(b'private fixture')
            (root / 'src').mkdir()
            (root / 'src/fireball.asm').write_text('''
                macro struct(name, defaults, duration, max_speed) {}
                macro add_to_character(id, struct) {}
                add_to_character(Character.id.TEST, struct_test)
            ''')
            profile_id = 1
            profile_addr = FIREBALL_BASE + profile_id * 0x30
            asset_ptr = 0x80400300
            payload = struct.unpack('>12I', struct.pack('>I8fIIf', 90, 55, 30, 0, .85,
                .4363323, 0, 0, 36, asset_ptr, 0, 1))
            data = {profile_addr + i * 4: word for i, word in enumerate(payload)}
            data[asset_ptr] = 0
            for table, thunk, jump in [('fireball', 0x80400100, 0x80155ee4),
                                       ('kirby_fireball', 0x80400120, 0x80156a54)]:
                words = [0x3c040000, 0x34840000 | profile_id, 0xafa4001c,
                         0x08000000 | ((jump >> 2) & 0x03ffffff), 0]
                data.update({thunk + i * 4: word for i, word in enumerate(words)})
            ref = WordReference(data)
            ref.path, ref.ram_base = root / 'reference.z64', 0x80400000
            row = {'name': 'TEST', 'fkind': 77, 'changed_from_parent':
                   ['fireball', 'kirby_fireball'], 'tables': {
                       'fireball': list((0x80400100).to_bytes(4, 'big')),
                       'kirby_fireball': list((0x80400120).to_bytes(4, 'big'))}}
            tables = {'layouts': {'fireball': 4, 'kirby_fireball': 4}, 'fighters': [row]}
            audit = {'fighters': [{'name': 'TEST', 'files': [0, 0, 0, 0, 0, 2159]}]}
            catalog = {'fighters': [{'name': 'TEST'}]}
            manifest = extract_fireballs(ref, tables, audit, catalog)
            self.assertEqual(manifest['profiles'][0]['lifetime'], 90)
            self.assertIn('0.85', render_rows(catalog, manifest))
            self.assertIn('NATIVE_REMIX_TEST_KIND: return 2', render_lookup(catalog, manifest))
            data[0x80400100] = 0
            with self.assertRaisesRegex(ValueError, 'not li a0'):
                extract_fireballs(ref, tables, audit, catalog)

    def test_vanilla_callback_addresses_bind_by_decomp_function_comment(self):
        callbacks = vanilla_callback_symbols()
        self.assertEqual(callbacks[0x800d94c4], 'ftAnimEndSetWait')
        self.assertEqual(callbacks[0x8015c750], 'ftFoxSpecialAirHiEndProcUpdate')
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / 'one.c').write_text('// 0x80100000\nvoid first(GObj *gobj) {}\n')
            (root / 'two.c').write_text('// 0x80100000\nvoid second(GObj *gobj) {}\n')
            self.assertNotIn(0x80100000, vanilla_callback_symbols(root))

    def test_action_callback_bindings_apply_shared_symbols_once_and_fail_closed(self):
        fighter = {'name': 'TEST', 'action_table': {
            'inherited_statuses': 2, 'added_statuses': 0, 'added_status_records': [],
            'changed_inherited_statuses': [
                {'status_id': 0xdd, 'flags': None,
                 'callbacks': {'interrupt': {'original': '00000000', 'remix': '80500000'}}},
            ]}}
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / 'bindings.json'
            path.write_text(json.dumps({'schema': 1, 'auto_action_patches': [],
                                        'bindings': [{'address': '80500000',
                                                      'reference': 'Shared.interrupt',
                                                      'native': 'nativeInterrupt'}]}))
            _, bindings = load_bindings(path, {'Shared.interrupt': 0x80500000})
            output = render_action_assignments(fighter, bindings, 2)
            self.assertIn('NATIVE_REMIX_ACTION_STATUS[1].proc_interrupt = nativeInterrupt;', output)
            self.assertIn('ARRAY_COUNT(NATIVE_REMIX_ACTION_STATUS) == 2', output)
            with self.assertRaisesRegex(ValueError, 'Stale reference callback'):
                load_bindings(path, {'Shared.interrupt': 0x80500004})
            with self.assertRaisesRegex(ValueError, 'unbound interrupt'):
                render_action_assignments(fighter, {}, 2)
            fighter['action_table']['changed_inherited_statuses'][0]['flags'] = {
                'original': '30c40010', 'remix': '30c80011'}
            output = render_action_assignments(fighter, bindings, 2)
            self.assertIn('NATIVE_REMIX_ACTION_STATUS[1].mflags.motion_id = 195;', output)
            self.assertIn('NATIVE_REMIX_ACTION_STATUS[1].mflags.attack_id = 8;', output)
            self.assertIn('NATIVE_REMIX_ACTION_STATUS[1].sflags.halfword = 0x0011u;', output)
            fighter['action_table']['added_statuses'] = 1
            fighter['action_table']['added_status_records'] = [{
                'status_id': 0xde,
                'words': ['ff800012', '00000000', '80500000', '00000000', '00000000']
            }]
            output = render_action_assignments(fighter, bindings, 2)
            self.assertIn('ARRAY_COUNT(NATIVE_REMIX_ACTION_STATUS) == 3', output)
            self.assertIn('NATIVE_REMIX_ACTION_STATUS[2].mflags.motion_id = -2;', output)
            self.assertIn('NATIVE_REMIX_ACTION_STATUS[2].proc_interrupt = nativeInterrupt;', output)
            self.assertNotIn('NATIVE_REMIX_ACTION_STATUS[2].proc_update', output)
            fighter['action_table']['added_status_records'][0]['status_id'] = 0xdf
            with self.assertRaisesRegex(ValueError, 'not contiguous'):
                render_action_assignments(fighter, bindings, 2)

    def test_compiled_status_flags_reject_incomplete_words(self):
        self.assertEqual(render_flags(0, '30c40010'), [
            'NATIVE_REMIX_ACTION_STATUS[0].mflags.motion_id = 195;',
            'NATIVE_REMIX_ACTION_STATUS[0].mflags.attack_id = 4;',
            'NATIVE_REMIX_ACTION_STATUS[0].sflags.halfword = 0x0010u;'])
        with self.assertRaisesRegex(ValueError, 'Invalid compiled action flags'):
            render_flags(0, '30c4')

    def test_character_table_macro_widths_override_ambiguous_symbol_gaps(self):
        source = '''
            move_table(yoshi_egg, 0x103160, 0x1C)
            move_table_12(default_costume, 0xA7030, 0x8)
            id_table(variant_original)
            scope magnifying_glass_zoom {
                table:
                constant TABLE_ORIGIN(origin())
                fill table + (NUM_CHARACTERS * 2) - pc()
                scope hook: { }
            }
        '''
        widths = source_layouts(source)
        self.assertEqual(widths['yoshi_egg'], 28)
        self.assertEqual(widths['default_costume'], 8)
        self.assertEqual(widths['variant_original'], 4)
        self.assertEqual(widths['magnifying_glass_zoom'], 2)
        ref = SimpleNamespace(symbols={
            'Character.yoshi_egg.table': 0x80400000,
            'Character.default_costume.table': 0x80402000,
            'Character.variant_original.table': 0x80403000,
            'Character.magnifying_glass_zoom.table': 0x80404000,
        })
        self.assertEqual(discover_layouts(ref, 116, source)['yoshi_egg'], 28)
        ref.symbols['Character.default_costume.table'] = 0x80400100
        with self.assertRaisesRegex(ValueError, 'source width exceeds'):
            discover_layouts(ref, 116, source)

    def test_compiled_table_patch_imports_costumes_for_entire_generic_roster(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / 'assembled.z64'
            base = 0x80400000
            rom = bytearray(256 * 18)
            for fighter in catalog['fighters']:
                kind = fighter['fkind']
                rom[kind * 8:kind * 8 + 8] = bytes((0, 1, 2, 3, 4, 5, 6, kind))
                struct.pack_into('>II', rom, 2048 + kind * 8, 220, 221)
                struct.pack_into('>H', rom, 4096 + kind * 2, 300)
            path.write_bytes(rom)
            ref = SimpleNamespace(path=path, rom=rom, rom_base=0, ram_base=base,
                                  symbols={'Character.default_costume.table': base,
                                           'Character.entry_action.table': base + 2048,
                                           'Character.down_bound_fgm.table': base + 4096})
            audit = {'fighters': [{'name': row['name'], 'fkind': row['fkind'],
                                   'parent': row['parent']} for row in catalog['fighters']]}
            manifest = extract_table_patches(ref, audit)
            output = render_native_tables(catalog, manifest)
            generic = [row for row in catalog['fighters'] if row['registration'] == 'generic']
            self.assertEqual(output.count('static FTCostume'), len(generic))
            self.assertIn(f'{{4, 5, 6}}, {generic[0]["fkind"]}', output)
            self.assertIn('{220, 221}, 300', output)
            manifest['layouts'].update({name: 4 for name in (
                'ground_nsp', 'ground_usp', 'ground_dsp',
                'air_nsp', 'air_usp', 'air_dsp')})
            validate_generic_dispatch(catalog, manifest)
            generic_row = next(row for row in manifest['fighters'] if row['name'] == generic[0]['name'])
            generic_row['changed_from_parent'].append('ground_nsp')
            with self.assertRaisesRegex(ValueError, 'custom special-entry dispatch'):
                validate_generic_dispatch(catalog, manifest)
            generic_row['changed_from_parent'].remove('ground_nsp')
            tampered = json.loads(json.dumps(manifest))
            tampered['fighters'][next(i for i, row in enumerate(tampered['fighters'])
                                     if row['name'] == generic[0]['name'])]['fkind'] += 1
            with self.assertRaisesRegex(ValueError, 'Costume patch mismatch'):
                render_native_tables(catalog, tampered)

    def test_action_table_audit_separates_inherited_and_custom_callbacks(self):
        original = bytearray(0xa6f48)
        base = 0x80084800
        struct.pack_into('>I', original, 0x92614, base + 0x100)  # Fox struct
        struct.pack_into('>I', original, 0xa6f44, base + 0x200)  # Fox actions
        struct.pack_into('>I', original, 0x16c, 4)  # Parent motion count
        parent_words = [0x11, 0x80100000, 0x80100004, 0x80100008, 0x8010000c,
                        0x22, 0x80100010, 0x80100014, 0x80100018, 0x8010001c]
        struct.pack_into('>10I', original, 0x200, *parent_words)
        action_addr = 0x80400000
        ref = WordReference({action_addr + i * 4: word for i, word in enumerate(parent_words)})
        ref.symbols = {'Character.TEST_action_array': action_addr,
                       'Character.TEST_menu_array': action_addr + 48}
        audit = ActionTableAudit.__new__(ActionTableAudit)
        audit.original, audit.ref, audit.sizes = bytes(original), ref, {'FOX': 40}
        self.assertTrue(audit.audit('TEST', 'FOX', 4)['generic_action_table_compatible'])
        ref.data[action_addr + 6 * 4] = 0x8040abcd
        changed = audit.audit('TEST', 'FOX', 4)
        self.assertFalse(changed['generic_action_table_compatible'])
        self.assertEqual(changed['changed_inherited_statuses'][0]['status_id'], 0xdd)
        self.assertEqual(changed['changed_inherited_statuses'][0]['callbacks']['update']['remix'], '8040abcd')
        ref.symbols['Character.TEST_menu_array'] = action_addr + 64
        ref.data.update({action_addr + (10 + i) * 4: i for i in range(5)})
        added = audit.audit('TEST', 'FOX', 5)
        self.assertEqual(added['added_statuses'], 1)
        self.assertEqual(added['added_status_records'][0]['status_id'], 0xde)
        with tempfile.TemporaryDirectory() as dirname:
            ref.path = Path(dirname) / 'reference.z64'
            ref.path.write_bytes(b'test-reference')
            ref.ram_base = action_addr
            ref.symbols['Shared.native_candidate'] = 0x8040abcd
            work = callback_worklist(ref, [{'name': name, 'action_table': changed}
                                           for name in ('ONE', 'TWO')])
            self.assertEqual(work['unique_expansion_targets'], 1)
            self.assertEqual(len(work['targets'][0]['uses']), 2)

    def test_fighter_catalog_generates_roster_and_rejects_unvalidated_ids(self):
        catalog = load_catalog()
        self.assertEqual(HEADER.read_text(), render_header(catalog))
        self.assertEqual(UI.read_text(), render_ui(catalog))
        generic = [row for row in catalog['fighters'] if row['registration'] == 'generic']
        generated = render_generic_data(catalog)
        self.assertEqual(generated.count('_data.inc"'), len(generic) + 1)
        self.assertEqual(generated.count('_relocate_scripts}'), len(generic))
        augmented = json.loads(json.dumps(catalog))
        augmented['fighters'].append({'name': 'TEST', 'fkind': 199, 'parent': 'FOX',
                                      'label': 'TEST', 'registration': 'generic'})
        self.assertIn('#define NATIVE_REMIX_TEST_KIND 199u', render_header(augmented))
        self.assertIn('#include "test_data.inc"', render_generic_data(augmented))
        self.assertIn('{199u, 1u, "TEST"}', render_ui(augmented))
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / 'catalog.json'
            invalid = json.loads(json.dumps(catalog))
            invalid['fighters'][1]['fkind'] = invalid['fighters'][0]['fkind']
            path.write_text(json.dumps(invalid))
            with self.assertRaisesRegex(ValueError, 'duplicate fighter ID'):
                load_catalog(path)
            audit = Path(dirname) / 'audit.json'
            audit.write_text(json.dumps({'schema': 2, 'fighters': [
                {'name': row['name'], 'fkind': row['fkind'], 'parent': row['parent'],
                 'fixture_data_ready': row['name'] != generic[0]['name'],
                 'action_table': {'generic_action_table_compatible': True}}
                for row in catalog['fighters']]}))
            with self.assertRaisesRegex(ValueError, 'assets/scripts unready'):
                validate_reference(catalog, audit)
            with self.assertRaisesRegex(ValueError, 'does not match the pinned reference'):
                validate_reference(catalog, audit, 'stale-reference')
            report = json.loads(audit.read_text())
            for row in report['fighters']:
                row['fixture_data_ready'] = True
            audit.write_text(json.dumps(report))
            validate_reference(catalog, audit)
            report['fighters'][next(i for i, row in enumerate(report['fighters'])
                                    if row['name'] == generic[0]['name'])]['action_table']['generic_action_table_compatible'] = False
            audit.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'action table requires a custom registration'):
                validate_reference(catalog, audit)

    def test_roster_cycle_match_and_results_share_parent(self):
        fixture = '''#include <assert.h>
#include "native_remix_roster.h"
int main(void) {
    assert(nativeRemixNextKind(NATIVE_REMIX_DONKEY_KIND, 0) == NATIVE_REMIX_DKULT_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_DKULT_KIND, NATIVE_REMIX_DKULT_KIND) == NATIVE_REMIX_JDK_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_JDK_KIND, NATIVE_REMIX_JDK_KIND) == 0);
    assert(nativeRemixNextKind(NATIVE_REMIX_PIKACHU_KIND, 0) == NATIVE_REMIX_JPIKA_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_JPIKA_KIND, NATIVE_REMIX_JPIKA_KIND) == NATIVE_REMIX_EPIKA_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_EPIKA_KIND, NATIVE_REMIX_EPIKA_KIND) == 0);
    assert(nativeRemixNextKind(NATIVE_REMIX_MARIO_KIND, 0) == NATIVE_REMIX_JMARIO_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_SAMUS_KIND, 0) == NATIVE_REMIX_JSAMUS_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_JSAMUS_KIND, NATIVE_REMIX_JSAMUS_KIND) == NATIVE_REMIX_ESAMUS_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_ESAMUS_KIND, NATIVE_REMIX_ESAMUS_KIND) == 0);
    assert(nativeRemixNextKind(NATIVE_REMIX_LINK_KIND, 0) == NATIVE_REMIX_ELINK_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_ELINK_KIND, NATIVE_REMIX_ELINK_KIND) == NATIVE_REMIX_JLINK_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_JLINK_KIND, NATIVE_REMIX_JLINK_KIND) == 0);
    assert(nativeRemixNextKind(NATIVE_REMIX_YOSHI_KIND, 0) == NATIVE_REMIX_JYOSHI_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_JYOSHI_KIND, NATIVE_REMIX_JYOSHI_KIND) == 0);
    assert(nativeRemixNextKind(NATIVE_REMIX_NESS_KIND, 0) == NATIVE_REMIX_JNESS_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_JNESS_KIND, NATIVE_REMIX_JNESS_KIND) == 0);
    assert(nativeRemixNextKind(NATIVE_REMIX_JIGGLYPUFF_KIND, 0) == NATIVE_REMIX_JPUFF_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_JPUFF_KIND, NATIVE_REMIX_JPUFF_KIND) == NATIVE_REMIX_EPUFF_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_EPUFF_KIND, NATIVE_REMIX_EPUFF_KIND) == 0);
    assert(nativeRemixParentKind(NATIVE_REMIX_EPUFF_KIND) == NATIVE_REMIX_JIGGLYPUFF_KIND);
    assert(nativeRemixResolveKind(NATIVE_REMIX_NESS_KIND, NATIVE_REMIX_JNESS_KIND) == NATIVE_REMIX_JNESS_KIND);
    assert(nativeRemixParentKind(NATIVE_REMIX_JNESS_KIND) == NATIVE_REMIX_NESS_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_FOX_KIND, NATIVE_REMIX_FALCO_KIND) == NATIVE_REMIX_JFOX_KIND);
    assert(nativeRemixNextKind(NATIVE_REMIX_JFOX_KIND, NATIVE_REMIX_JFOX_KIND) == 0);
    assert(nativeRemixParentKind(NATIVE_REMIX_JFOX_KIND) == NATIVE_REMIX_FOX_KIND);
    assert(nativeRemixNextKind(999, 0) == 0);
    assert(nativeRemixResolveKind(NATIVE_REMIX_DONKEY_KIND, NATIVE_REMIX_JDK_KIND) == NATIVE_REMIX_JDK_KIND);
    assert(nativeRemixResolveKind(NATIVE_REMIX_DONKEY_KIND, NATIVE_REMIX_EPIKA_KIND) == NATIVE_REMIX_DONKEY_KIND);
    assert(nativeRemixResolveKind(NATIVE_REMIX_MARIO_KIND, NATIVE_REMIX_JMARIO_KIND) == NATIVE_REMIX_JMARIO_KIND);
    assert(nativeRemixParentKind(NATIVE_REMIX_EPIKA_KIND) == NATIVE_REMIX_PIKACHU_KIND);
    assert(nativeRemixParentKind(NATIVE_REMIX_JMARIO_KIND) == NATIVE_REMIX_MARIO_KIND);
    assert(nativeRemixParentKind(NATIVE_REMIX_ESAMUS_KIND) == NATIVE_REMIX_SAMUS_KIND);
    assert(nativeRemixParentKind(NATIVE_REMIX_JSAMUS_KIND) == NATIVE_REMIX_SAMUS_KIND);
    assert(nativeRemixParentKind(NATIVE_REMIX_ELINK_KIND) == NATIVE_REMIX_LINK_KIND);
    assert(nativeRemixParentKind(NATIVE_REMIX_JLINK_KIND) == NATIVE_REMIX_LINK_KIND);
    assert(nativeRemixParentKind(NATIVE_REMIX_JYOSHI_KIND) == NATIVE_REMIX_YOSHI_KIND);
    assert(nativeRemixIsVariant(NATIVE_REMIX_EPIKA_KIND));
    assert(!nativeRemixIsVariant(NATIVE_REMIX_PIKACHU_KIND));
    return 0;
}'''
        out = BUILD / 'fighter-import-test'
        out.mkdir(parents=True, exist_ok=True)
        path, exe = out / 'roster_cycle.c', out / 'roster-cycle-test.exe'
        path.write_text(fixture)
        cc = compiler_path(None).replace('clang++', 'clang')
        subprocess.run([cc, '-std=gnu11', '-I' + str(ROOT / '3ds/include'),
                        str(path), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

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
    f.fkind = NATIVE_REMIX_EPIKA_KIND;
    assert(wpPikachuThunderJoltLifetime(&g) == 100);
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
       nFTKindKirby, nFTKindPikachu, nFTKindNess = 11, nFTKindGDonkey = 27 };
#define FTKIRBY_COPY_TABLE_COUNT 27
''' + function + '''
int main(void) {
    assert(ftKirbySpecialNGetCopyTableKind(nFTKindMario) == nFTKindMario);
    assert(ftKirbySpecialNGetCopyTableKind(nFTKindFox) == nFTKindFox);
    assert(ftKirbySpecialNGetCopyTableKind(nFTKindGDonkey) == nFTKindDonkey);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_FALCO_KIND) == nFTKindFox);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_DKULT_KIND) == nFTKindDonkey);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JPIKA_KIND) == nFTKindPikachu);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_EPIKA_KIND) == nFTKindPikachu);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_ESAMUS_KIND) == nFTKindSamus);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JSAMUS_KIND) == nFTKindSamus);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_ELINK_KIND) == nFTKindLink);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JLINK_KIND) == nFTKindLink);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JYOSHI_KIND) == nFTKindYoshi);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JMARIO_KIND) == nFTKindMario);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JFALCON_KIND) == nFTKindCaptain);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JLUIGI_KIND) == nFTKindLuigi);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JDK_KIND) == nFTKindDonkey);
    assert(ftKirbySpecialNGetCopyTableKind(NATIVE_REMIX_JNESS_KIND) == nFTKindNess);
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
        def extract(path, signature):
            source = (ROOT / path).read_text()
            start = source.index(signature)
            return source[start:source.index('\n}', start) + 2]

        helper = extract('3ds/src/remix_variants.c', 'static int has_animation(')
        predicate = extract('3ds/src/remix_variants.c', 'int nativeRemixGenericIsAnimation(')
        falco = extract('3ds/src/remix_falco_probe.c', 'int nativeRelocIsFighterAnimation(')
        dk = extract('3ds/src/remix_dkult_probe.c', 'int nativeRemixDKUltIsAnimation(')
        jp = extract('3ds/src/remix_jpika_probe.c', 'int nativeRemixJPikaIsAnimation(')
        fixture = '''#include <cassert>
#define ARRAY_COUNT(a) (sizeof(a)/sizeof((a)[0]))
struct Motion {unsigned anim_file_id;struct {unsigned word;} anim_desc;};
typedef Motion FTMotionDesc;
struct NativeRemixGenericDef {
    unsigned kind, parent;
    const unsigned *file_ids;
    long attribute_offset;
    FTMotionDesc *main_motions;
    unsigned main_count;
    FTMotionDesc *menu_motions;
    int *menu_count;
    void (*relocate_scripts)();
};
static Motion remix_main_motions[]={{0,{0}},{4,{0}},{5,{8}},{6,{2}}};
static Motion remix_menu_motions[]={{0,{0}},{8,{0}}};
static Motion remix_dkult_main_motions[]={{0,{0}},{10,{0}},{11,{8}}};
static Motion remix_dkult_menu_motions[]={{0,{0}},{12,{0}}};
static Motion remix_jpika_main_motions[]={{0,{0}},{13,{0}},{14,{8}}};
static Motion remix_jpika_menu_motions[]={{0,{0}},{15,{0}}};
static Motion generic_a_main[]={{0,{0}},{16,{0}},{17,{8}}};
static Motion generic_a_menu[]={{0,{0}},{18,{0}}};
static Motion generic_b_main[]={{0,{0}},{31,{0}},{32,{2}}};
static Motion generic_b_menu[]={{0,{0}},{33,{0}}};
static int a_menu_count=2, b_menu_count=2;
static NativeRemixGenericDef native_remix_generic_defs[]={
    {0,0,0,0,generic_a_main,ARRAY_COUNT(generic_a_main),generic_a_menu,&a_menu_count,0},
    {0,0,0,0,generic_b_main,ARRAY_COUNT(generic_b_main),generic_b_menu,&b_menu_count,0}
};
'''
        for line in (ROOT / 'src/ft/ftdef.h').read_text().splitlines():
            if line.startswith('#define FTANIM_FLAG_ANIMJOINT ') or line.startswith('#define FTANIM_FLAG_SHIELDPOSE '):
                fixture += line + '\n'
        fixture += '\n'.join((helper, predicate, dk, jp, falco)) + '''
int main(){
    assert(!nativeRelocIsFighterAnimation(0));
    assert(nativeRelocIsFighterAnimation(4));
    assert(!nativeRelocIsFighterAnimation(5));
    assert(!nativeRelocIsFighterAnimation(6));
    assert(nativeRelocIsFighterAnimation(8));
    assert(nativeRelocIsFighterAnimation(10));
    assert(!nativeRelocIsFighterAnimation(11));
    assert(nativeRelocIsFighterAnimation(12));
    assert(nativeRelocIsFighterAnimation(13));
    assert(!nativeRelocIsFighterAnimation(14));
    assert(nativeRelocIsFighterAnimation(15));
    assert(nativeRelocIsFighterAnimation(16));
    assert(!nativeRelocIsFighterAnimation(17));
    assert(nativeRelocIsFighterAnimation(18));
    assert(nativeRelocIsFighterAnimation(31));
    assert(!nativeRelocIsFighterAnimation(32));
    assert(nativeRelocIsFighterAnimation(33));
    assert(!nativeRemixGenericIsAnimation(0));
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
    def test_repacked_music_preserves_sparse_sequences_and_rejects_bad_ranges(self):
        rom = bytearray(160)
        struct.pack_into('>HHIIII', rom, 16, 0x5331, 2, 80, 5, 48, 7)
        rom[96:101] = b'first'
        rom[64:71] = b'second!'
        output, count = repack_sequence_bank(rom, 16)
        self.assertEqual(count, 2)
        self.assertEqual(struct.unpack_from('>HH', output), (0x5331, 2))
        for i, expected in enumerate((b'first', b'second!')):
            offset, length = struct.unpack_from('>II', output, 4 + i * 8)
            self.assertEqual(output[offset:offset + length], expected)
        struct.pack_into('>I', rom, 20, 4)
        with self.assertRaisesRegex(ValueError, 'outside reference ROM'):
            repack_sequence_bank(rom, 16)
        struct.pack_into('>I', rom, 20, 80)
        struct.pack_into('>I', rom, 24, 1000)
        with self.assertRaisesRegex(ValueError, 'outside reference ROM'):
            repack_sequence_bank(rom, 16)

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
