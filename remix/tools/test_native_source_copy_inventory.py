"""Host checks for linking upstream copy macros to callback use sites."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from native_source_copy_inventory import build_inventory


class InventoryTests(unittest.TestCase):
    def test_nested_scope_ignores_comments_and_ranks_unbound_uses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rom = root / 'reference.z64'
            rom.write_bytes(b'pinned reference')
            source = root / 'src'
            source.mkdir()
            (source / 'fighter.asm').write_text('''scope Fighter {
    scope physics_: {
        // OS.copy_segment(0x111, 0x40)
        OS.copy_segment(0x548F0, 0x40)
    }
    scope other_: {
        OS.copy_segment(0x100, 0x20)
    }
}
''')
            ref = SimpleNamespace(path=rom,
                                  symbols={'Fighter.physics_': 0x80500000,
                                           'Fighter.other_': 0x80500040})
            worklist = {'reference_rom_sha256': hashlib.sha256(rom.read_bytes()).hexdigest(),
                        'targets': [
                            {'address': '80500000', 'symbols': ['Fighter.physics_'],
                             'uses': [{'fighter': 'A'}, {'fighter': 'B'}]},
                            {'address': '80500040', 'symbols': ['Fighter.other_'],
                             'uses': [{'fighter': 'A'}]}]}
            report = build_inventory(ref, worklist, {0x80500040}, source)
            self.assertEqual((report['active_copy_macro_calls'],
                              report['matched_action_callback_scopes'],
                              report['matched_callback_copy_segments'],
                              report['unbound_matched_callback_scopes']), (2, 2, 2, 1))
            self.assertEqual(report['callbacks'][0]['symbols'], ['Fighter.physics_'])
            self.assertEqual(report['callbacks'][0]['copy_segments'][0]['arguments'],
                             '0x548F0, 0x40')
            worklist['reference_rom_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'pinned reference ROM differ'):
                build_inventory(ref, worklist, {}, source)


if __name__ == '__main__':
    unittest.main()
