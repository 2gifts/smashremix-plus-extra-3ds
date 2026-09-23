"""Compare every compiled Remix variant identity row with Azahar guest memory."""

import json
import socket
import sys
from pathlib import Path

from common import BUILD, ROOT, sha256, write_json

sys.path.insert(0, str(ROOT.parent / 'native/tools'))
import emulator  # noqa: E402


ELF = ROOT / '3ds/build/falco-test/ssb64-falco-test.elf'
BINARY = ROOT / '3ds/build/falco-test/package/smash64-development.cxi'
OUT = BUILD / 'fighter-probe/variant-metadata-emulator.json'


def main():
    report = json.loads((BUILD / 'variant-metadata.json').read_text())
    reference = json.loads((BUILD / 'reference.json').read_text())
    if report['reference_rom_sha256'] != reference['rom_sha256']:
        raise ValueError('Variant metadata and pinned reference differ')
    rows = report['rows']
    expected = bytes(value for row in rows for value in
                     (row['original'], row['variant_type'], *row['same_model']))
    emulator.ELF = ELF
    symbols = emulator.symbols()
    address = symbols['native_remix_variant_metadata']
    try:
        emulator.stop()
        emulator.launch('falco-test', stereo=1, frames=0,
                        binary_override=BINARY, no_captures=True)
        with socket.create_connection(('127.0.0.1', emulator.PORT), 3) as connection:
            connection.settimeout(4)
            emulator.command(connection, '?')
            actual = bytes.fromhex(emulator.command(
                connection, f'm{address:x},{len(expected):x}'))
            if actual != expected:
                offset = next((index for index, pair in enumerate(zip(actual, expected))
                               if pair[0] != pair[1]), min(len(actual), len(expected)))
                raise AssertionError(f'Guest variant row differs at byte {offset}')
        result = {'passed': True, 'compiled_rows': len(rows),
                  'guest_bytes_verified': len(actual),
                  'stereo': True, 'development_only': True,
                  'elf_sha256': sha256(ELF), 'binary_sha256': sha256(BINARY),
                  'scope': 'Compiled variant table bytes in Azahar guest memory; '
                           'expanded character select and gameplay are not tested.'}
        write_json(OUT, result)
        print(json.dumps(result, indent=2))
    finally:
        emulator.stop()


if __name__ == '__main__':
    main()
