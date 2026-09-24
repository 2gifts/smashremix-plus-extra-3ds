"""Reject altered MIPS behavior in the shared Lucas movement translator."""

import unittest
from types import SimpleNamespace

from native_lucas_air_move import PATTERN, SYMBOL, decode_air_move, render_native


class LucasAirMoveTests(unittest.TestCase):
    def test_exact_compiled_callback_and_velocity_constant(self):
        words = [0x3c094220 if word is None else word for word in PATTERN]
        ref = SimpleNamespace(symbols={SYMBOL: 0x80581d40},
                              words=lambda address, count: (words + [0] * count)[:count])
        row = decode_air_move(ref)
        self.assertEqual(row['speed'], 40.0)
        self.assertIn('fp->physics.vel_air.x -= 0x1.4000000000000p+5f * fp->lr;',
                      render_native(row))
        for index, replacement in ((7, 0x11000008),  # Different branch target.
                                   (6, 0x8cc80180),  # Different motion flag.
                                   (16, 0xe4c0004c),  # Different velocity field.
                                   (9, 0x3c097f80)):  # Infinite float speed.
            original = words[index]
            words[index] = replacement
            with self.subTest(index=index), self.assertRaises(ValueError):
                decode_air_move(ref)
            words[index] = original


if __name__ == '__main__':
    unittest.main()
