"""Source-only safety checks for batch development-roster generation."""

import tempfile
import unittest
from pathlib import Path

from native_auto_roster import select_auto_catalog, write_auto_catalog


def fighter(name, kind, callback=0, ready=True, parent='FOX'):
    return {'name': name, 'fkind': kind, 'parent': parent,
            'fixture_data_ready': ready,
            'action_table': {'changed_inherited_statuses': [],
                             'added_status_records': [
                                 {'words': ['00000000', f'{callback:08x}',
                                            '00000000', '00000000', '00000000']}
                             ] if callback else []}}


class AutoRosterTests(unittest.TestCase):
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
             ['ground_nsp'] if row['name'] == 'CUSTOMDISPATCH' else []}
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
            {'name': 'UNBOUND', 'changed_from_parent': []}]}
        with self.assertRaisesRegex(ValueError, 'No additional'):
            select_auto_catalog(source, audit, {}, tables)


if __name__ == '__main__':
    unittest.main()
