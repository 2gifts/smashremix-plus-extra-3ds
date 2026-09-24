"""Host checks for the compiled callback dependency inventory."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from native_callback_dependencies import build_dependency_graph, scan_routine


class FakeReference:
    ram_base = 0x80400000

    def __init__(self, path):
        self.path = path
        self.code = {
            0x80400000: [0x0c100010, 0x03e00008, 0],
            0x80400020: [0x0c100010, 0x0320f809, 0, 0x03e00008, 0],
            0x80400040: [0x0c039bc9, 0x03e00008, 0],
        }

    def words(self, address, count):
        if address not in self.code:
            raise ValueError('outside reference')
        return self.code[address] + [0] * (count - len(self.code[address]))


class DependencyTests(unittest.TestCase):
    def test_shared_expansion_helper_and_opaque_indirect_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pinned.z64'
            path.write_bytes(b'pinned reference')
            ref = FakeReference(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            worklist = {'reference_rom_sha256': digest, 'targets': [
                {'address': '80400000', 'symbols': ['A'],
                 'uses': [{'fighter': 'A', 'status_id': 220}]},
                {'address': '80400020', 'symbols': ['B'],
                 'uses': [{'fighter': 'B', 'status_id': 220},
                          {'fighter': 'B', 'status_id': 221}]},
            ]}
            report = build_dependency_graph(ref, worklist, {0x80400000})
            self.assertEqual(report['callback_count'], 2)
            self.assertEqual(report['native_bound_count'], 1)
            self.assertEqual(report['unique_expansion_helpers_for_unbound'], 1)
            self.assertEqual(report['unique_original_engine_calls_for_unbound'], 1)
            self.assertEqual(report['opaque_callback_count'], 1)
            self.assertEqual(report['callbacks'][1]['original_engine_calls'],
                             ['800e6f24'])
            self.assertEqual(report['ranked_original_engine_calls_for_unbound'][0]
                             ['dependent_action_uses'], 2)
            worklist['reference_rom_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'pinned reference ROM differ'):
                build_dependency_graph(ref, worklist)

    def test_unmapped_routine_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            row = scan_routine(FakeReference(Path(directory)), 0x80401000)
        self.assertEqual(row['scan'], 'unmapped')


if __name__ == '__main__':
    unittest.main()
