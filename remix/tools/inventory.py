"""Inventory the pinned mod's native-port requirements without importing ROM data."""
import argparse
import json
import re
from pathlib import Path
import yaml
from common import BUILD, ROOT, checked_sources, write_json

def assembly_stats(folder):
    files = sorted(folder.rglob('*.asm'))
    lines = patches = literal = 0
    for path in files:
        source = path.read_text(encoding='utf-8', errors='replace')
        lines += len(source.splitlines())
        patches += len(re.findall(r'(?m)^\s*OS\.patch_start\(', source))
        literal += len(re.findall(r'(?m)^\s*OS\.patch_start\(0x[\da-fA-F]+,\s*0x[\da-fA-F]+\)', source))
    return {'assembly_files': len(files), 'assembly_lines': lines,
            'patch_start_calls': patches, 'literal_patch_sites': literal}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BUILD / 'inventory.json')
    args = parser.parse_args()
    lock, sources = checked_sources()
    fighters = []
    for directory in sorted((sources['extra'] / 'extra_characters').iterdir()):
        if not directory.is_dir() or directory.name.startswith('_'):
            continue
        config = yaml.safe_load((directory / 'config.yaml').read_text(encoding='utf-8'))
        fighters.append({
            'id': directory.name, 'base_character': config['definitions']['base_character'],
            'source': f'{lock["extra"]["repository"]}/tree/{lock["extra"]["commit"]}/extra_characters/{directory.name}',
            'native_gameplay_implemented': False, **assembly_stats(directory),
        })
    character_source = (sources['remix'] / 'src/Character.asm').read_text(encoding='utf-8')
    base_fighters = [{'id': name, 'parent': parent, 'native_gameplay_implemented': False}
                     for name, parent in re.findall(r'(?m)^\s*define_character\((\w+),\s*(\w+),', character_source)]
    stages = [p.parent.relative_to(sources['extra'] / 'extra_stages').as_posix()
              for p in sorted((sources['extra'] / 'extra_stages').rglob('config.yaml'))]
    report = {
        'schema': 1, 'extra': lock['extra'], 'remix': lock['remix'],
        'base_remix_assembly': assembly_stats(sources['remix'] / 'src'),
        'extra_assembly': {folder: assembly_stats(sources['extra'] / folder)
                           for folder in ('extra_characters', 'extra_stages', 'smashremix_overwrite')},
        'base_remix_character_definitions': base_fighters,
        'extra_character_definitions': fighters, 'extra_stage_configurations': stages,
        'native_runtime': {'playable': False,
                           'unported': ['expanded fighter registry and actions',
                                        'MIPS engine patches and new special-move callbacks',
                                        'moveset extensions, projectiles, and items',
                                        'expanded menu, stage, audio, and save integration']},
    }
    write_json(args.output, report)
    print(json.dumps({'extra_definitions': len(fighters), 'extra_stage_configs': len(stages),
                      'remix_assembly': report['base_remix_assembly'],
                      'output': str(args.output), 'native_playable': False}, indent=2))

if __name__ == '__main__':
    main()
