"""Group compiled fighter patches by shared native consumer, not by fighter.

This is a planning report. A table marked imported does not imply the whole
fighter is playable; move behavior and visual effects still need emulator QA.
"""
from collections import defaultdict
from common import BUILD, write_json


IMPORTED_TABLES = frozenset({'default_costume', 'entry_action', 'down_bound_fgm',
                             'winner_bgm', 'winner_fgm', 'str_winner_ptr',
                             'str_winner_lx', 'str_winner_scale', 'str_wins_lx'})


def build_worklist(audit, tables, fireballs, catalog):
    hashes = {source['reference_rom_sha256'] for source in (audit, tables, fireballs)}
    if len(hashes) != 1:
        raise ValueError('Patch reports were generated from different reference ROMs')
    audit_rows = {row['name']: row for row in audit['fighters']}
    enabled = {row['name'] for row in catalog['fighters']}
    fireball_names = {row['name'] for row in fireballs['profiles']}
    families = defaultdict(lambda: {'fighters': [], 'enabled_fighters': [], 'importer_supported_fighters': []})
    candidates = []
    for row in tables['fighters']:
        name = row['name']
        source = audit_rows[name]
        changes = row['changed_from_parent']
        for table in changes:
            family = families[table]
            family['fighters'].append(name)
            if name in enabled:
                family['enabled_fighters'].append(name)
            if table in IMPORTED_TABLES or (table in ('fireball', 'kirby_fireball') and
                                            name in fireball_names):
                family['importer_supported_fighters'].append(name)
        unresolved = [table for table in changes if table not in IMPORTED_TABLES and
                      not (table in ('fireball', 'kirby_fireball') and name in fireball_names)]
        candidates.append({'name': name, 'fkind': row['fkind'], 'enabled': name in enabled,
                           'assets_and_scripts_ready': source['fixture_data_ready'],
                           'vanilla_action_callbacks_suffice':
                               source['action_table']['generic_action_table_compatible'],
                           'remaining_table_families_to_review': unresolved})
    for table, family in families.items():
        family['fighters'].sort()
        family['enabled_fighters'].sort()
        family['importer_supported_fighters'].sort()
    return {'schema': 1, 'reference_rom_sha256': hashes.pop(),
            'families': dict(sorted(families.items(), key=lambda pair:
                                    (-len(pair[1]['fighters']), pair[0]))),
            'fighters': candidates}


def write_worklist(audit, tables, fireballs, catalog):
    report = build_worklist(audit, tables, fireballs, catalog)
    write_json(BUILD / 'native-patch-worklist.json', report)
    return report
