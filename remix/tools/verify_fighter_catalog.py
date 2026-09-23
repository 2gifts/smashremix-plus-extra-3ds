"""Syntax-check every generated fighter motion set with the ARM11 compiler."""

import subprocess
import sys

from common import BUILD, ROOT


def main():
    sys.path.insert(0, str(ROOT / '3ds/tools'))
    from build import BIN, game_flags
    directory = BUILD / 'fighter-catalog'
    paths = sorted(directory.glob('*.inc'))
    if not paths:
        raise ValueError('Generate the fighter catalog first')
    source = directory / 'compile_catalog.c'
    source.write_text('#include <ft/fighter.h>\n'
                      'extern u32 portRelocRegisterPointer(void *);\n'
                      + ''.join(f'#include "{path.name}"\n' for path in paths))
    result = subprocess.run([str(BIN / 'clang.exe'), *game_flags(), '-fsyntax-only', str(source)],
                            capture_output=True, text=True)
    if result.returncode:
        print((result.stdout + result.stderr)[:6000], file=sys.stderr)
        return result.returncode
    print(f'ARM11 syntax passed for {len(paths)} generated fighter motion sets')
    return 0


if __name__ == '__main__':
    sys.exit(main())
