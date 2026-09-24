"""Source-only safety checks for batch development-roster generation."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from native_auto_roster import select_auto_catalog, write_auto_catalog
from native_callback_frontier import rank_callback_frontier
from common import sha256


def fighter(name, kind, callback=0, ready=True, parent='FOX'):
    return {'name': name, 'fkind': kind, 'parent': parent,
            'fixture_data_ready': ready,
            'action_table': {'inherited_statuses': 25,
                             'added_statuses': 1 if callback else 0,
                             'changed_inherited_statuses': [],
                             'added_status_records': [
                                 {'words': ['00000000', f'{callback:08x}',
                                            '00000000', '00000000', '00000000']}
                             ] if callback else []}}


class AutoRosterTests(unittest.TestCase):
    def test_callback_frontier_groups_shapes_and_ranks_fighter_unlocks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reference.z64'
            path.write_bytes(b'callback frontier fixture')
            pinned = sha256(path)
            code = {0x80500000: [0x340500e5, 0x03e00008, 0],
                    0x80500020: [0x340500e6, 0x03e00008, 0],
                    0x80500040: [0x00001025, 0x03e00008, 0]}
            ref = SimpleNamespace(path=path, words=lambda address, count:
                                  (code[address] + [0] * count)[:count])
            worklist = {'reference_rom_sha256': pinned, 'targets': [
                {'address': f'{address:08x}', 'symbols': [f'Fixture{index}'],
                 'uses': [{'fighter': 'READY', 'status_id': 229 + index,
                           'role': 'update'}]}
                for index, address in enumerate(code)]}
            audit = {'reference_rom_sha256': pinned, 'fighters': [
                fighter('READY', 30, 0x80500000),
                fighter('OTHER', 31, 0x80500040)]}
            report = rank_callback_frontier(ref, worklist, audit, {})
            self.assertEqual(report['unbound_shape_count'], 2)
            self.assertEqual(report['groups'][0]['callback_count'], 2)
            self.assertEqual(report['groups'][0]['callback_only_unlocks'], ['READY'])
            self.assertEqual(report['groups'][0]['addresses'],
                             ['80500000', '80500020'])
            code[0x80500100] = [0x340500e5, 0x03e00008, 0]
            code[0x80500120] = [0x00001025, 0x03e00008, 0]
            families = {'reference_rom_sha256': pinned, 'wrappers': [
                {'address': '80500000', 'helper_address': '800ddddc',
                 'transition_address': '80500100'},
                {'address': '80500020', 'helper_address': '800ddddc',
                 'transition_address': '80500120'}]}
            split = rank_callback_frontier(ref, worklist, audit, {}, families)
            self.assertEqual(split['unbound_shape_count'], 3)
            self.assertEqual(sum(row['callback_count'] for row in split['groups']), 3)
            rebound = rank_callback_frontier(ref, worklist, audit,
                                             {0x80500000: 'nativeFixture'})
            self.assertIn(['80500020'], [row['addresses'] for row in rebound['groups']])
            audit['reference_rom_sha256'] = 'stale'
            with self.assertRaisesRegex(ValueError, 'pinned ROM'):
                rank_callback_frontier(ref, worklist, audit, {})

    def test_only_validated_bound_candidates_enter_private_roster(self):
        source = {'schema': 1, 'parents': {'FOX': 1}, 'fighters': [
            {'name': 'FALCO', 'fkind': 29, 'parent': 'FOX',
             'label': 'FALCO', 'registration': 'custom'}]}
        audit = {'schema': 2, 'reference_rom_sha256': 'reference', 'fighters': [
            fighter('RANDOM', 27), fighter('FALCO', 29),
            fighter('READY', 30, 0x80500000),
            fighter('UNBOUND', 31, 0x80500004),
            fighter('UNREADY', 32, ready=False),
            fighter('NOFAMILY', 33, parent='KIRBY'),
            fighter('CUSTOMDISPATCH', 34)]}
        tables = {'reference_rom_sha256': 'reference', 'fighters': [
            {'name': row['name'], 'changed_from_parent':
             ['ground_nsp'] if row['name'] == 'CUSTOMDISPATCH' else [],
             'tables': {'ground_nsp': [0x80, 0x50, 0, 0]}}
            for row in audit['fighters']]}
        with tempfile.TemporaryDirectory() as folder:
            catalog, report = write_auto_catalog(
                source, audit, {0x80500000: 'nativeReady'}, tables,
                Path(folder) / 'auto-roster.json')
            self.assertEqual([row['name'] for row in catalog['fighters']],
                             ['FALCO', 'READY'])
            self.assertEqual(report['candidate_count'], 1)
            self.assertEqual(report['candidates'][0]['compiled_callback_count'], 1)
            blocked = {row['name']: row['blockers'] for row in report['rejected']}
            self.assertIn('1_unbound_action_callbacks', blocked['UNBOUND'])
            self.assertIn('custom_special_dispatch:ground_nsp',
                          blocked['CUSTOMDISPATCH'])
            self.assertEqual(source['fighters'][0]['name'], 'FALCO')
            self.assertEqual(len(source['fighters']), 1)

    def test_empty_candidate_set_fails_closed(self):
        source = {'schema': 1, 'parents': {'FOX': 1}, 'fighters': []}
        audit = {'schema': 2, 'reference_rom_sha256': 'reference',
                 'fighters': [fighter('UNBOUND', 30, 0x80500004)]}
        tables = {'reference_rom_sha256': 'reference', 'fighters': [
            {'name': 'UNBOUND', 'changed_from_parent': [], 'tables': {}}]}
        with self.assertRaisesRegex(ValueError, 'No additional'):
            select_auto_catalog(source, audit, {}, tables)


if __name__ == '__main__':
    unittest.main()
