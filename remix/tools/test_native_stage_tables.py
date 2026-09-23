"""Source-only checks for the compiled stage-table import contract."""

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from common import sha256
from native_stage_tables import (BASE_RAM, BASE_STAGE_FILE_ROM, BASE_STAGE_SETUP_RAM,
                                 CLONE_SETUP, extract_stages, render_native,
                                 stage_asset_closure, stage_count)


class StageTableTests(unittest.TestCase):
    def fixture(self, folder):
        count = 42
        rom = bytearray(0x800)
        original = bytearray(BASE_STAGE_SETUP_RAM - BASE_RAM + 36)
        files = [(i + 1, 20) for i in range(count)]
        setups = [0x80100000 + i * 4 for i in range(9)] + [0] * 32 + [CLONE_SETUP]
        for i, (file_id, offset) in enumerate(files):
            struct.pack_into('>II', rom, 0x100 + i * 8, file_id, offset)
            if i < 41:
                struct.pack_into('>II', original, BASE_STAGE_FILE_ROM + i * 8,
                                 file_id, offset)
            struct.pack_into('>I', rom, 0x300 + i * 4, setups[i])
            rom[0x250 + i] = 0
            struct.pack_into('>H', rom, 0x600 + i * 2, 0 if i < 41 else 3)
            struct.pack_into('>hhhh', rom, 0x400 + i * 8,
                             -1, -1, -1, -1)
        struct.pack_into('>9I', original, BASE_STAGE_SETUP_RAM - BASE_RAM, *setups[:9])
        path = Path(folder) / 'reference.z64'
        path.write_bytes(rom)
        ref = SimpleNamespace(path=path, rom=rom, rom_base=0, ram_base=0x80400000,
                              symbols={
                                  'Stages.stage_file_table': 0x80400100,
                                  'Stages.class_table': 0x80400250,
                                  'Stages.function_table': 0x80400300,
                                  'Stages.icon_offset_table': 0x804003a8,
                                  'Stages.alternate_music_table': 0x80400400,
                                  'Stages.variant_table': 0x80400550,
                                  'Stages.default_music_track_table': 0x80400600,
                              },
                              words=lambda address, n: list(struct.unpack_from(
                                  '>' + 'I' * n, rom, address - 0x80400000)))
        manifest = {'summary': {'source_rom_sha256': sha256(path)},
                    'entries': [{'size': 64, 'external_files': []}
                                for _ in range(43)],
                    'relocation_issues': []}
        return ref, original, manifest

    def test_compiled_span_and_asset_closure_cover_added_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            ref, original, manifest = self.fixture(folder)
            self.assertEqual(stage_count(ref), 42)
            rows = extract_stages(ref, original, manifest, 417)
            self.assertEqual(rows[-1]['header_file_id'], 42)
            self.assertEqual(rows[-1]['setup_kind'], 0)
            self.assertEqual(rows[-1]['default_music_plus_one'], 3)
            self.assertEqual(len(stage_asset_closure(rows, manifest)), 42)
            self.assertIn('const unsigned native_remix_stage_count = 42u;',
                          render_native(rows))
            manifest['entries'][42]['external_files'] = [2]
            manifest['relocation_issues'] = [{'file_id': 2, 'reason': 'fixture'}]
            with self.assertRaisesRegex(ValueError, 'unresolved relocations'):
                stage_asset_closure(rows, manifest)

    def test_mismatched_or_invalid_compiled_stage_rows_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            ref, original, manifest = self.fixture(folder)
            ref.symbols['Stages.variant_table'] += 8
            with self.assertRaisesRegex(ValueError, 'counts disagree'):
                stage_count(ref)
            ref.symbols['Stages.variant_table'] -= 8
            ref.rom[0x100] ^= 1
            with self.assertRaisesRegex(ValueError, 'differ from the base ROM'):
                extract_stages(ref, original, manifest, 417)
            ref.rom[0x100] ^= 1
            struct.pack_into('>I', ref.rom, 0x100 + 41 * 8, 999)
            with self.assertRaisesRegex(ValueError, 'Invalid compiled stage row'):
                extract_stages(ref, original, manifest, 417)


if __name__ == '__main__':
    unittest.main()
