import unittest

from relocation_layout import (dependency_layout, cross_file_target,
                               cross_file_target_contexts, reverse_dependencies,
                               stable_cross_file_target)


class DependencyLayoutTest(unittest.TestCase):
    def test_depth_first_alignment_and_reused_dependency(self):
        entries = [
            {'size': 12, 'external_files': [1, 3, 1]},
            {'size': 20, 'external_files': [2]},
            {'size': 40, 'external_files': []},
            {'size': 8, 'external_files': []},
        ]
        layout = dependency_layout(entries, 0)
        self.assertEqual(layout[0], {0: 0, 1: 16, 2: 48, 3: 96})
        self.assertEqual(cross_file_target(layout, 1, 40), (2, 8))
        self.assertEqual(cross_file_target(layout, 1, 24), None)  # alignment gap
        self.assertEqual(cross_file_target(layout, 1, 1), None)  # unaligned
        self.assertEqual(cross_file_target(layout, 1, 96), None)  # past closure
        self.assertEqual(stable_cross_file_target(entries, reverse_dependencies(entries),
                                                   0, 1, 40), (2, 8))

    def test_rejects_context_dependent_target(self):
        entries = [
            {'size': 8, 'external_files': [3, 1]},
            {'size': 8, 'external_files': [2, 3]},
            {'size': 8, 'external_files': []},
            {'size': 8, 'external_files': []},
        ]
        self.assertEqual(cross_file_target(dependency_layout(entries, 1), 2, 16),
                         (3, 0))
        self.assertIsNone(stable_cross_file_target(entries, reverse_dependencies(entries),
                                                   1, 2, 16))

    def test_cycle_reuses_registered_allocation(self):
        entries = [{'size': 4, 'external_files': [1]},
                   {'size': 4, 'external_files': [0]}]
        # The N64 loader registers an allocation before walking its links;
        # a repeated file ID is therefore reused rather than recursed into.
        self.assertEqual(dependency_layout(entries, 0)[0], {0: 0, 1: 16})

    def test_internal_target_reports_all_load_contexts(self):
        # A leaf can reach a later sibling only when the outer parent loads it.
        entries = [
            {'size': 8, 'external_files': [1, 2]},
            {'size': 8, 'external_files': []},
            {'size': 12, 'external_files': []},
        ]
        contexts = cross_file_target_contexts(
            entries, reverse_dependencies(entries), 1, 1, 16)
        self.assertEqual(contexts, {
            'candidate_owners': [{'file_id': 2, 'offset': 0, 'load_roots': [0]}],
            'unmapped_load_roots': [1],
        })


if __name__ == '__main__':
    unittest.main()
