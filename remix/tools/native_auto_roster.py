"""Derive an opt-in development roster from the compiled fighter audit.

This only finds buildable candidates. Native callback coverage and valid assets
do not prove move behavior, so generated entries never enter the release gate.
"""

from copy import deepcopy
from collections import Counter

from native_action_patches import action_callback_addresses
from native_fighter_catalog import load_catalog
from native_special_dispatch import unresolved_dispatches


def select_auto_catalog(source, audit, bindings, table_manifest,
                        special_bindings=None):
    if audit.get('schema') != 2:
        raise ValueError('Unsupported compiled fighter audit')
    if table_manifest.get('reference_rom_sha256') != audit.get('reference_rom_sha256'):
        raise ValueError('Compiled fighter tables and audit differ')
    table_rows = {row['name']: row for row in table_manifest['fighters']}
    catalog = deepcopy(source)
    enabled = {row['name'] for row in catalog['fighters']}
    candidates = []
    rejected = []
    for row in sorted(audit['fighters'], key=lambda fighter: fighter['fkind']):
        name = row['name']
        if name in enabled:
            continue
        missing = action_callback_addresses(row) - bindings.keys()
        special = unresolved_dispatches(table_rows[name], special_bindings or {}, row)
        blockers = []
        if row['fkind'] < 28:
            blockers.append('nonfighter_sentinel')
        if row['parent'] not in catalog['parents']:
            blockers.append('no_native_parent')
        if not row['fixture_data_ready']:
            blockers.append('assets_or_scripts_unready')
        if missing:
            blockers.append(f'{len(missing)}_unbound_action_callbacks')
        if special:
            blockers.append('custom_special_dispatch:' + ','.join(special))
        if blockers:
            rejected.append({'name': name, 'fkind': row['fkind'], 'blockers': blockers})
            continue
        entry = {'name': name, 'fkind': row['fkind'], 'parent': row['parent'],
                 'label': name[:16], 'registration': 'generic'}
        candidates.append(entry)
        catalog['fighters'].append(entry)
    if not candidates:
        raise ValueError('No additional structurally bindable fighters')
    return catalog, candidates, rejected


def write_auto_catalog(source, audit, bindings, table_manifest, path,
                       special_bindings=None):
    import json
    from pathlib import Path

    catalog, candidates, rejected = select_auto_catalog(
        source, audit, bindings, table_manifest, special_bindings)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2) + '\n')
    load_catalog(path)
    report = {'reference_rom_sha256': audit['reference_rom_sha256'],
              'candidate_count': len(candidates),
              'candidates': [{**entry,
                              'compiled_callback_count': len(action_callback_addresses(
                                  next(row for row in audit['fighters']
                                       if row['name'] == entry['name'])))}
                             for entry in candidates],
              'rejected': rejected,
              'blocker_counts': dict(Counter(
                  'unbound_action_callbacks' if reason.endswith('_unbound_action_callbacks')
                  else reason.split(':', 1)[0]
                  for row in rejected for reason in row['blockers'])),
              'scope': 'Development-only structural candidates; native move behavior and full playability are unverified.'}
    (path.parent / 'auto-roster-report.json').write_text(json.dumps(report, indent=2) + '\n')
    return catalog, report
