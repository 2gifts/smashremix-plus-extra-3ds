"""Smoke-test every automatically selected fighter in stereo Azahar.

Runs candidates independently so one crash cannot hide later results. Reports
are private build artifacts and do not establish full move compatibility.
"""

import argparse
import json
import subprocess
import sys
import time

from common import BUILD, ROOT, sha256, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--names', nargs='*', help='Subset of generated candidate names')
    parser.add_argument('--through-results', action='store_true')
    args = parser.parse_args()
    output = BUILD / 'fighter-probe'
    candidates = json.loads((output / 'auto-roster-report.json').read_text())['candidates']
    available = {row['name'] for row in candidates}
    names = args.names or [row['name'] for row in candidates]
    if not names or len(names) != len(set(names)) or any(name not in available for name in names):
        parser.error('Choose unique names from the generated candidate roster')
    cxi = ROOT / '3ds/build/falco-test/package/smash64-development.cxi'
    package = json.loads((output / 'package.json').read_text())
    if package['build_variant'] != 'auto-bindable-test' or sha256(cxi) != package['files'][cxi.name]['sha256']:
        raise ValueError('The installed development package is not the generated batch roster')
    results = []
    for name in names:
        started = time.monotonic()
        command = [sys.executable, str(ROOT / 'remix/tools/emulator_generic_match.py'),
                   name, '--auto-bindable']
        if args.through_results:
            command.append('--through-results')
        process = subprocess.run(command, cwd=ROOT, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        suffix = 'results' if args.through_results else 'match'
        path = output / f'{name.lower()}-generic-{suffix}.json'
        passed = process.returncode == 0 and path.exists() and json.loads(path.read_text()).get('passed') is True
        item = {'name': name, 'passed': passed,
                'elapsed_seconds': round(time.monotonic() - started, 1),
                'result_path': str(path) if passed else None,
                'failure_tail': None if passed else process.stdout[-1800:]}
        results.append(item)
        write_json(output / 'auto-roster-emulator.json',
                   {'development_cxi_sha256': sha256(cxi), 'through_results': args.through_results,
                    'results': results, 'completed': len(results) == len(names)})
        print(f'{name}: {"PASS" if passed else "FAIL"} ({item["elapsed_seconds"]}s)', flush=True)
    if not all(item['passed'] for item in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
