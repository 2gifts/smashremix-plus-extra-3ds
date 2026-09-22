"""Build the pinned N64 mod for native-port development. This does not build a CIA.

The upstream generator rewrites src/ and build/. Run it only in a fresh, ignored
archive export; never run it over this repository's decompiled C source.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from common import BUILD, ROOT, checked_sources, sha256, write_json

def export_source(source, revision, target, archive):
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', '-c', 'safe.directory=' + str(source.resolve()),
                    '-C', str(source), 'archive', '--format=zip',
                    '--output=' + str(archive), revision], check=True)
    with zipfile.ZipFile(archive) as contents:
        for item in contents.infolist():
            destination = (target / item.filename).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise ValueError('Archive member escapes reference build directory')
        contents.extractall(target)

def run_logged(argv, cwd, log):
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=stream,
                                stderr=subprocess.STDOUT)
    if result.returncode:
        tail = '\n'.join(log.read_text(errors='replace').splitlines()[-20:])
        raise RuntimeError(f'Reference build failed; see {log}\n{tail}')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    args = parser.parse_args()
    lock, sources = checked_sources()
    if os.name != 'nt':
        raise RuntimeError('This wrapper currently uses the upstream Windows assembler tools')
    rom = args.rom.resolve()
    if rom.stat().st_size != lock['base_rom']['bytes'] or hashlib.sha1(rom.read_bytes()).hexdigest() != lock['base_rom']['sha1']:
        raise ValueError('Expected your own unmodified US 1.0 big-endian ROM')
    for module in ('yaml', 'PIL', 'lineinfile'):
        __import__(module)
    BUILD.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='reference-', dir=BUILD)).resolve()
    if not stage.is_relative_to(BUILD.resolve()):
        raise RuntimeError('Reference build directory must remain inside remix/build')
    print('Exporting pinned upstream sources to', stage, flush=True)
    export_source(sources['extra'], lock['extra']['commit'], stage, stage / 'extra-source.zip')
    export_source(sources['remix'], lock['remix']['commit'], stage / 'smashremix', stage / 'remix-source.zip')
    base = stage / 'smashremix'
    (base / 'roms').mkdir(exist_ok=True)
    shutil.copyfile(rom, base / 'roms/ssb.rom')
    print('Preparing the base Remix ROM', flush=True)
    run_logged([base / 'xdelta.exe', '-d', '-s', base / 'roms/ssb.rom',
                base / 'original.xdelta', base / 'roms/original.z64'], stage, stage / 'patch.log')
    # The appender removes ./src and ./build. Both resolve inside the fresh
    # archive export, never ROOT/src or the maintained upstream submodule.
    for name in ('src', 'build'):
        if not (stage / name).resolve().is_relative_to(stage):
            raise RuntimeError('Unsafe upstream generation path')
    print('Generating +EXTRA characters, stages, and audio', flush=True)
    run_logged([sys.executable, stage / 'character_appender.py'], stage, stage / 'appender.log')
    output = stage / 'smashremix-extra-reference.z64'
    print('Assembling the reference N64 mod', flush=True)
    run_logged([base / 'assembler/bass.exe', '-o', output, 'main.asm', '-sym', 'symbols.log'],
               stage, stage / 'assembler.log')
    run_logged([base / 'assembler/rn64crc.exe', '-u', output], stage, stage / 'crc.log')
    if output.read_bytes()[:4] != b'\x80\x37\x12\x40':
        raise ValueError('Reference output is not a big-endian N64 ROM')
    report = {
        'kind': 'n64-reference-only', 'native_3ds_playable': False,
        'extra_commit': lock['extra']['commit'], 'remix_commit': lock['remix']['commit'],
        'base_rom_sha1': lock['base_rom']['sha1'],
        'directory': stage.relative_to(ROOT).as_posix(),
        'rom': output.relative_to(ROOT).as_posix(), 'rom_bytes': output.stat().st_size,
        'rom_sha256': sha256(output), 'symbols_sha256': sha256(stage / 'symbols.log'),
    }
    write_json(stage / 'reference.json', report)
    write_json(BUILD / 'reference.json', report)
    print('Reference build verified:', output, flush=True)
    print('This is N64 development input, not an installable 3DS game.', flush=True)

if __name__ == '__main__':
    main()
