"""Build a private fighter integration CIA, not a complete Remix +EXTRA release."""
import json
import os
import shutil
import subprocess
import sys
import wave
from common import BUILD, ROOT, sha256, write_json
from native_fighter_catalog import load_catalog


def main():
    fighter_count = len(load_catalog()['fighters'])
    os.environ['SSB_REMIX_PROBE'] = 'falco'
    sys.path.insert(0, str(ROOT / '3ds/tools'))
    from build import OUT, tool
    def run(*args):
        subprocess.run(list(map(str, args)), cwd=ROOT, check=True)
    audit_path = BUILD / 'fighter-audit.json'
    reference_sha = json.loads((BUILD / 'reference.json').read_text())['rom_sha256']
    if not audit_path.exists() or json.loads(audit_path.read_text()).get('reference_rom_sha256') != reference_sha:
        run(sys.executable, ROOT / 'remix/tools/audit_reference_fighters.py')
    run(sys.executable, ROOT / 'remix/tools/prepare_fighter_probe.py')
    config_path = ROOT / '3ds/build-config.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if config.get('save'):
        run(sys.executable, ROOT / '3ds/tools/import_save.py', config['save'])
    run(sys.executable, ROOT / '3ds/tools/build.py', '--prepare')
    run(sys.executable, ROOT / '3ds/tools/build_support.py')
    run(sys.executable, ROOT / '3ds/tools/build_runtime.py', '--standalone-probe')
    dst = OUT / 'falco-test/package'
    dst.mkdir(parents=True, exist_ok=True)
    elf = OUT / 'falco-test/ssb64-falco-test.elf'
    shutil.copy2(elf, dst / 'ssb64-package.elf')

    # A plainly labeled development icon/banner cannot be mistaken for the
    # finished mod. These contain no imported HOME Menu artwork.
    from PIL import Image, ImageDraw, ImageFont
    def art(size, label, font_size, path):
        image = Image.new('RGB', size, (24, 32, 48))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, size[0]-3, size[1]-3), outline=(238, 185, 59), width=2)
        draw.multiline_text((size[0]/2, size[1]/2), label,
                            font=ImageFont.load_default(size=font_size), fill=(245, 239, 219),
                            anchor='mm', align='center', spacing=5)
        image.save(path)
    art((48, 48), 'REMIX\nTEST', 11, dst / 'icon.png')
    art((256, 128), f'REMIX +EXTRA\n{fighter_count} FIGHTER TEST\nNATIVE 3DS DEVELOPMENT\nFULL MOD IN PROGRESS', 15, dst / 'banner.png')
    with wave.open(str(dst / 'silent.wav'), 'wb') as sound:
        sound.setparams((2, 2, 32000, 0, 'NONE', 'not compressed'))
        sound.writeframes(bytes(32000 * 4))
    run(tool('bannertool'), 'makesmdh', '-s', 'Remix fighter test', '-l',
        f'{fighter_count} fighter integrations via VS bottom screen - full port unfinished', '-p', 'Remix / decomp / port contributors',
        '-i', dst / 'icon.png', '-o', dst / 'icon.smdh', '-r', 'regionfree',
        '-f', 'visible,allow3d,new3ds,recordusage')
    run(tool('bannertool'), 'makebanner', '-i', dst / 'banner.png', '-a', dst / 'silent.wav', '-o', dst / 'banner.bin')
    rsf = (ROOT / '3ds/smash64.rsf').read_text()
    rsf = rsf.replace('Title: RemixExtra', 'Title: FighterTest').replace('CTR-P-SMXE', 'CTR-P-SMFT').replace('0xFF641', '0xFF642')
    rsf += '\nRomFs:\n  RootPath: "' + (OUT / 'romfs').as_posix() + '"\n'
    (dst / 'smash64.rsf').write_text(rsf)
    flags = ['-target', 't', '-exefslogo', '-elf', dst / 'ssb64-package.elf',
             '-rsf', dst / 'smash64.rsf', '-icon', dst / 'icon.smdh', '-banner', dst / 'banner.bin']
    for fmt, suffix in [('cia', 'cia'), ('ncch', 'cxi')]:
        run(tool('makerom'), '-f', fmt, *flags, *(['-ver', '1'] if fmt == 'cia' else []),
            '-o', dst / ('smash64-development.' + suffix))
    report = {'development_only': True, 'build_variant': 'fighter-test', 'fully_playable': False,
              'scope': f'{fighter_count} imported fighters selectable from their parent VS bottom cards; full Remix roster and menus unfinished',
              'elf_sha256': sha256(elf), 'title_id': '000400000ff64200', 'files': {}}
    for suffix in ('cia', 'cxi'):
        path = dst / ('smash64-development.' + suffix)
        report['files'][path.name] = {'bytes': path.stat().st_size, 'sha256': sha256(path)}
    write_json(dst / 'package.json', report)
    from verify_package import main as verify
    verify(dst, expected_title=0x000400000ff64200, verify_startup=True)
    target = OUT / 'falco-test/Remix-Fighter-Integration-Test.cia'
    shutil.copy2(dst / 'smash64-development.cia', target)
    write_json(BUILD / 'fighter-probe/package.json', report)
    print('Development CIA (not the full mod):', target)


if __name__ == '__main__':
    main()
