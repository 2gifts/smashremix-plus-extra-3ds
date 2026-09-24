"""Import checked special-entry handlers from compiled Character patch tables.

One reference routine may serve several fighters. Decode it once, bind every
table use, and leave any unrecognized MIPS routine unavailable to the native
roster. These are special-entry handlers, not action-status callbacks.
"""

from collections import defaultdict
from pathlib import Path

from classify_action_callbacks import first_return_words, shape_hash
from common import BUILD, sha256, write_json
from native_straightline_transitions import decode_straightline


DISPATCH_ORDER = (
    ('ground_nsp', 'PORT_FIGHTER_SPECIAL_N'),
    ('ground_usp', 'PORT_FIGHTER_SPECIAL_HI'),
    ('ground_dsp', 'PORT_FIGHTER_SPECIAL_LW'),
    ('air_nsp', 'PORT_FIGHTER_SPECIAL_AIR_N'),
    ('air_usp', 'PORT_FIGHTER_SPECIAL_AIR_HI'),
    ('air_dsp', 'PORT_FIGHTER_SPECIAL_AIR_LW'),
)


def changed_dispatches(row):
    changed = set(row['changed_from_parent'])
    for table, _ in DISPATCH_ORDER:
        if table in changed:
            value = row['tables'][table]
            if len(value) != 4:
                raise ValueError(f'{row["name"]}: malformed {table} pointer')
            yield table, int.from_bytes(bytes(value), 'big')


def extract_special_dispatch(ref, tables):
    if tables['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Special dispatch tables and pinned reference ROM differ')
    uses = defaultdict(list)
    for row in tables['fighters']:
        for table, address in changed_dispatches(row):
            uses[address].append({'fighter': row['name'], 'table': table})
    accepted = []
    rejected = []
    shapes = defaultdict(list)
    for address, slots in sorted(uses.items()):
        decoded = None
        if ref.ram_base <= address < 0x80800000:
            try:
                decoded = decode_straightline(
                    ref, address, allow_status_only=True, allow_entry_resets=True)
            except ValueError:
                pass  # An unmapped or truncated routine is not native code.
        if decoded and decoded['template'] in ('decoded_status_only', 'decoded_entry_reset'):
            accepted.append({**decoded, 'native': f'nativeRemixSpecial_{address:08x}',
                             'uses': slots})
        else:
            row = {'address': f'{address:08x}', 'uses': slots}
            if ref.ram_base <= address < 0x80800000:
                try:
                    words = ref.words(address, 128)
                    length = first_return_words(words)
                    if length is not None and length <= 128:
                        row['instruction_count'] = length
                        row['shape_sha256'] = shape_hash(words[:length])
                        shapes[row['shape_sha256']].append(row)
                except ValueError:
                    pass
            rejected.append(row)
    shape_groups = [{'shape_sha256': shape, 'routines': len(rows),
                     'table_slots': sum(len(row['uses']) for row in rows),
                     'addresses': [row['address'] for row in rows]}
                    for shape, rows in shapes.items()]
    shape_groups.sort(key=lambda row: (-row['table_slots'], -row['routines'],
                                       row['shape_sha256']))
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'changed_table_slots': sum(map(len, uses.values())),
            'unique_routines': len(uses), 'accepted': accepted,
            'unresolved': rejected, 'unresolved_shape_groups': shape_groups}


def dispatch_bindings(manifest):
    return {int(row['address'], 16): row for row in manifest['accepted']}


def unresolved_dispatches(table_row, bindings, fighter_audit=None):
    status_count = None
    if fighter_audit is not None:
        action = fighter_audit['action_table']
        status_count = action['inherited_statuses'] + action['added_statuses']
    missing = []
    for table, address in changed_dispatches(table_row):
        row = bindings.get(address)
        if row is None or (status_count is not None and
                           not (0xdc <= row['status_id'] < 0xdc + status_count)):
            missing.append(table)
    return missing


def render_native_code(manifest, catalog, tables):
    rows = {row['name']: row for row in tables['fighters']}
    bindings = dispatch_bindings(manifest)
    used = {address for fighter in catalog['fighters']
            if fighter['registration'] == 'generic'
            for _, address in changed_dispatches(rows[fighter['name']])}
    if any(address not in bindings for address in used):
        raise ValueError('Catalog includes an unbound compiled special entry')
    lines = ['/* Checked compiled Character special-entry dispatch. */']
    for address in sorted(used):
        row = bindings[address]
        frame = '0.0F' if row['frame_begin'] == 'zero' else 'gobj->anim_frame'
        lines += [f'static void {row["native"]}(GObj *gobj) {{',
                  f'    ftMainSetStatus(gobj, {row["status_id"]}, {frame}, '
                  f'{row["speed"]!r}F, 0x{row["preserve_flags"]:x}u);']
        if row['template'] == 'decoded_entry_reset' or row['play_anim']:
            lines.append('    ftMainPlayAnimEventsAll(gobj);')
        if row['template'] == 'decoded_entry_reset':
            lines.append('    FTStruct *fp = ftGetStruct(gobj);')
            for index in row['reset_motion_flags']:
                lines.append(f'    fp->motion_vars.flags.flag{index} = 0;')
        lines += ['}', '']
    lines += ['static void nativeRemixApplyGenericSpecialDispatch(unsigned kind,',
              '                                                   FighterDescriptor *desc) {',
              '    switch (kind) {']
    for fighter in catalog['fighters']:
        if fighter['registration'] != 'generic':
            continue
        changes = list(changed_dispatches(rows[fighter['name']]))
        if not changes:
            continue
        lines.append(f'    case NATIVE_REMIX_{fighter["name"]}_KIND:')
        for table, address in changes:
            slot = dict(DISPATCH_ORDER)[table]
            lines.append(f'        desc->special_handler[{slot}] = {bindings[address]["native"]};')
        lines.append('        return;')
    lines += ['    default: return;', '    }', '}', '']
    return '\n'.join(lines)


def write_special_dispatch(ref, tables, catalog, out):
    manifest = extract_special_dispatch(ref, tables)
    write_json(BUILD / 'native-special-dispatch.json', manifest)
    (Path(out) / 'native_special_dispatch.inc').write_text(
        render_native_code(manifest, catalog, tables))
    return manifest
