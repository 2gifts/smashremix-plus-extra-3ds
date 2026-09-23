"""Source-only checks for the conservative raw display-list normalization."""
import unittest

from extract_reference_assets import unrelocated_end_display_list


class RawDisplayListTest(unittest.TestCase):
    def test_exact_unlinked_end_display_list(self):
        payload = bytes.fromhex('df00000000000000') + bytes(132952)
        self.assertTrue(unrelocated_end_display_list(payload, 0, 0xffff))
        self.assertFalse(unrelocated_end_display_list(payload, 0, 0))
        self.assertFalse(unrelocated_end_display_list(payload, 4, 0xffff))
        self.assertTrue(unrelocated_end_display_list(payload[:8], 0, 0xffff))

    def test_valid_relocation_is_not_reclassified(self):
        # A relocation at word zero can point to a real in-file target.
        self.assertFalse(unrelocated_end_display_list(bytes.fromhex('ffff000100000000'),
                                                        0, 0xffff))


if __name__ == '__main__':
    unittest.main()
