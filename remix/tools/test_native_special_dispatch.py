"""Source-only checks for the compiled special-entry importer."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from common import sha256
from native_special_dispatch import (dispatch_bindings, extract_special_dispatch,
                                     render_native_code, unresolved_dispatches)


ENTRY = [
    0x27bdffe0, 0xafbf001c, 0xafa40020, 0x340500e5,
    0x8fa40020, 0x00003025, 0x3c073f80, 0x24010001,
    0x0c039bc9, 0xafa10010, 0x0c03820c, 0x8fa40020,
    0x8fa40020, 0x8c840084, 0xac80017c, 0x8fbf001c, 0x03e00008,
    0x27bd0020,
]


class SpecialDispatchTests(unittest.TestCase):
    def test_shared_compiled_routine_binds_by_table_and_rejects_unknown_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reference.z64'
            path.write_bytes(b'pinned reference fixture')
            code = {0x80500000: ENTRY,
                    0x80500100: ENTRY[:15] + [0xac80018c] + ENTRY[16:]}

            def words(address, count):
                return (code[address] + [0] * count)[:count]

            ref = SimpleNamespace(path=path, ram_base=0x80400000, words=words)
            rows = [
                {'name': 'A', 'changed_from_parent': ['ground_nsp'],
                 'tables': {'ground_nsp': [0x80, 0x50, 0, 0]}},
                {'name': 'B', 'changed_from_parent': ['air_nsp'],
                 'tables': {'air_nsp': [0x80, 0x50, 0, 0]}},
                {'name': 'C', 'changed_from_parent': ['ground_dsp'],
                 'tables': {'ground_dsp': [0x80, 0x50, 1, 0]}},
            ]
            tables = {'reference_rom_sha256': sha256(path), 'fighters': rows}
            manifest = extract_special_dispatch(ref, tables)
            self.assertEqual((manifest['changed_table_slots'], manifest['unique_routines']),
                             (3, 2))
            self.assertEqual(len(manifest['accepted']), 1)
            self.assertEqual(len(manifest['unresolved']), 1)
            self.assertEqual(len(manifest['unresolved_shape_groups']), 1)
            self.assertEqual(len(manifest['accepted'][0]['uses']), 2)
            self.assertEqual(manifest['accepted'][0]['reset_motion_flags'], [0])
            bindings = dispatch_bindings(manifest)
            audit = {'action_table': {'inherited_statuses': 25, 'added_statuses': 0}}
            self.assertEqual(unresolved_dispatches(rows[0], bindings, audit), [])
            self.assertEqual(unresolved_dispatches(rows[2], bindings, audit), ['ground_dsp'])
            catalog = {'fighters': [{'name': 'A', 'registration': 'generic'},
                                    {'name': 'B', 'registration': 'generic'}]}
            source = render_native_code(manifest, catalog, tables)
            self.assertIn('fp->motion_vars.flags.flag0 = 0;', source)
            self.assertIn('desc->special_handler[PORT_FIGHTER_SPECIAL_N]', source)
            self.assertIn('desc->special_handler[PORT_FIGHTER_SPECIAL_AIR_N]', source)
            catalog['fighters'].append({'name': 'C', 'registration': 'generic'})
            with self.assertRaisesRegex(ValueError, 'unbound compiled special'):
                render_native_code(manifest, catalog, tables)


if __name__ == '__main__':
    unittest.main()
