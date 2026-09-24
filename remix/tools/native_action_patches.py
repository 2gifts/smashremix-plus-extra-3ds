"""Bind compiled N64 action-table deltas to shared native C callbacks.

The audit supplies status/role/address, so each source callback is bound once
regardless of how many fighters or statuses use it. This deliberately refuses
unknown flags, added statuses and unbound MIPS callbacks instead of silently
inheriting the parent's behavior.
"""
import json
import re
from pathlib import Path

from common import BUILD, ROOT, sha256, write_json


BINDINGS = ROOT / 'remix/native_callback_bindings.json'
ROLES = {'update': 'proc_update', 'interrupt': 'proc_interrupt',
         'physics': 'proc_physics', 'map': 'proc_map'}


def render_flags(index, word):
    """Translate the packed N64 motion/status word into native fields.

    FTStatusDesc is deliberately not binary-compatible with the N64 record on
    ARM, so copying the word into the C structure would corrupt its fields.
    """
    if not re.fullmatch(r'[0-9A-Fa-f]{8}', word):
        raise ValueError(f'Invalid compiled action flags: {word!r}')
    packed = int(word, 16)
    motion = (packed >> 22) & 0x3ff
    if motion & 0x200:
        motion -= 0x400
    attack = (packed >> 16) & 0x3f
    status = packed & 0xffff
    return [f'NATIVE_REMIX_ACTION_STATUS[{index}].mflags.motion_id = {motion};',
            f'NATIVE_REMIX_ACTION_STATUS[{index}].mflags.attack_id = {attack};',
            f'NATIVE_REMIX_ACTION_STATUS[{index}].sflags.halfword = 0x{status:04x}u;']


def render_callback(index, role, address, bindings):
    if address == 0:
        return None
    native = bindings.get(address)
    if native is None:
        raise ValueError(f'unbound {role} callback {address:08x}')
    return f'NATIVE_REMIX_ACTION_STATUS[{index}].{ROLES[role]} = {native};'


def action_callback_addresses(fighter):
    table = fighter['action_table']
    changed = (int(callback['remix'], 16)
               for status in table['changed_inherited_statuses']
               for callback in status['callbacks'].values() if callback is not None)
    added = (int(word, 16) for status in table['added_status_records']
             for word in status['words'][1:])
    return {address for address in (*changed, *added) if address}


def action_table_bindable(fighter, bindings):
    return action_callback_addresses(fighter) <= bindings.keys()


def vanilla_callback_symbols(root=ROOT / 'src'):
    """Use decomp address comments to bind existing void(GObj *) callbacks."""
    result = {}
    ambiguous = set()
    address_line = re.compile(r'^\s*//\s*0x([0-9A-Fa-f]{8})\s*$')
    signature = re.compile(r'^void\s+([A-Za-z_]\w*)\s*\(\s*GObj\s*\*')
    for path in sorted(Path(root).rglob('*.c')):
        lines = path.read_text(errors='replace').splitlines()
        for index, line in enumerate(lines):
            match = address_line.match(line)
            if match is None:
                continue
            for candidate in lines[index + 1:index + 4]:
                if not candidate.strip():
                    continue
                function = signature.match(candidate)
                if function is not None:
                    address, name = int(match.group(1), 16), function.group(1)
                    if address >= 0x80400000:  # Pinned reference expansion base.
                        break
                    if address in result and result[address] != name:
                        ambiguous.add(address)
                        result.pop(address)
                    elif address not in ambiguous:
                        result[address] = name
                break
    return result


def load_bindings(path=BINDINGS, symbols=None):
    config = json.loads(Path(path).read_text())
    if config.get('schema') != 1 or not isinstance(config.get('bindings'), list):
        raise ValueError('Invalid native action callback binding schema')
    bindings = vanilla_callback_symbols()
    for row in config['bindings']:
        address = int(row['address'], 16)
        native = row['native']
        if not 0 < address < 0x100000000 or not re.fullmatch(r'[A-Za-z_]\w*', native):
            raise ValueError(f'Invalid native action binding: {row}')
        if address in bindings and bindings[address] != native:
            raise ValueError(f'Duplicate action callback binding {address:08x}')
        reference = row.get('reference')
        if reference is not None and (symbols is None or symbols.get(reference) != address):
            raise ValueError(f'Stale reference callback binding: {reference}')
        bindings[address] = native
    return config, bindings


def render_action_assignments(fighter, bindings, status_count):
    """Return a complete, deterministic C patch for one already-copied table."""
    table = fighter['action_table']
    if table['inherited_statuses'] != status_count:
        raise ValueError(f"{fighter['name']}: native status count differs from reference")
    added = table['added_status_records']
    if len(added) != table['added_statuses']:
        raise ValueError(f"{fighter['name']}: added status count differs from reference")
    lines = [f'/* Compiled Character.edit_action patches for {fighter["name"]}. */',
             f'_Static_assert(ARRAY_COUNT(NATIVE_REMIX_ACTION_STATUS) == {status_count + len(added)}, '
             '"Compiled action table size changed");']
    for status in sorted(table['changed_inherited_statuses'], key=lambda item: item['status_id']):
        index = status['status_id'] - 0xdc
        if not 0 <= index < status_count:
            raise ValueError(f"{fighter['name']}: action status outside inherited table")
        if status['flags'] is not None:
            lines.extend(render_flags(index, status['flags']['remix']))
        for role in ROLES:
            callback = status['callbacks'].get(role)
            if callback is None:
                continue
            address = int(callback['remix'], 16)
            line = render_callback(index, role, address, bindings)
            lines.append(line or f'NATIVE_REMIX_ACTION_STATUS[{index}].{ROLES[role]} = NULL;')
    for offset, status in enumerate(added):
        index = status_count + offset
        if status['status_id'] != 0xdc + index or len(status['words']) != 5:
            raise ValueError(f"{fighter['name']}: added action status is not contiguous")
        lines.extend(render_flags(index, status['words'][0]))
        for role, word in zip(ROLES, status['words'][1:]):
            line = render_callback(index, role, int(word, 16), bindings)
            if line is not None:
                lines.append(line)
    generated = sorted({bindings[int(callback['remix'], 16)]
                        for status in table['changed_inherited_statuses']
                        for callback in status['callbacks'].values()
                        if callback is not None and int(callback['remix'], 16) in bindings
                        and bindings[int(callback['remix'], 16)].startswith('nativeRemixCollision_')}
                       | {bindings[int(word, 16)]
                          for status in added for word in status['words'][1:]
                          if int(word, 16) in bindings
                          and bindings[int(word, 16)].startswith('nativeRemixCollision_')})
    return '\n'.join([*(f'extern void {name}(GObj *);' for name in generated), *lines]) + '\n'


def render_generic_action_tables(catalog, audit, bindings):
    """Generate one shared native registrar patch for every enabled generic delta."""
    rows = {row['name']: row for row in audit['fighters']}
    patches = []
    for entry in catalog['fighters']:
        if entry['registration'] != 'generic':
            continue
        fighter = rows[entry['name']]
        table = fighter['action_table']
        if table['generic_action_table_compatible']:
            continue
        if not action_table_bindable(fighter, bindings):
            missing = sorted(action_callback_addresses(fighter) - bindings.keys())
            raise ValueError(f"{entry['name']}: unbound generic action callbacks "
                             + ', '.join(f'{address:08x}' for address in missing))
        inherited = table['inherited_statuses']
        count = inherited + table['added_statuses']
        if not 0 < inherited <= count < 512:
            raise ValueError(f"{entry['name']}: invalid compiled action table size")
        patches.append((entry, fighter, inherited, count))
    lines = ['/* Generated native action deltas for catalogued generic fighters. */']
    for entry, _, _, count in patches:
        lines.append(f'static FTStatusDesc native_remix_{entry["name"].lower()}_actions[{count}];')
    lines += ['', 'static void nativeRemixApplyGenericActionTable(unsigned kind, FighterDescriptor *desc) {',
              '    switch (kind) {']
    for entry, fighter, inherited, count in patches:
        name = f'native_remix_{entry["name"].lower()}_actions'
        lines += [f'    case NATIVE_REMIX_{entry["name"]}_KIND:',
                  f'        memcpy({name}, desc->special_descs, {inherited} * sizeof(FTStatusDesc));']
        for address in sorted(action_callback_addresses(fighter)):
            lines.append(f'        extern void {bindings[address]}(GObj *);')
        lines += [f'#define NATIVE_REMIX_ACTION_STATUS {name}',
                  render_action_assignments(fighter, bindings, inherited).rstrip(),
                  '#undef NATIVE_REMIX_ACTION_STATUS',
                  f'        desc->special_descs = {name};',
                  f'        desc->special_descs_count = {count};',
                  '        return;']
    lines += ['    default: return;', '    }', '}', '']
    return '\n'.join(lines)


def write_action_patches(ref, audit, catalog, out, auto_bindings=None):
    if audit.get('reference_rom_sha256') != sha256(ref.path):
        raise ValueError('Action audit does not match the pinned reference')
    config, bindings = load_bindings(symbols=ref.symbols)
    for address, native in (auto_bindings or {}).items():
        if address in bindings and bindings[address] != native:
            raise ValueError(f'Conflicting generated action callback binding {address:08x}')
        bindings[address] = native
    worklist = json.loads((BUILD / 'action-callback-worklist.json').read_text())
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Action callback worklist does not match the pinned reference')
    unresolved = [row for row in worklist['targets']
                  if int(row['address'], 16) not in bindings]
    fighter_coverage = []
    for fighter in audit['fighters']:
        needed = action_callback_addresses(fighter)
        missing = sorted(needed - bindings.keys())
        fighter_coverage.append({
            'name': fighter['name'], 'fkind': fighter['fkind'],
            'mod': fighter['origin']['mod'],
            'fixture_data_ready': fighter['fixture_data_ready'],
            'added_statuses': fighter['action_table']['added_statuses'],
            'callbacks_required': len(needed),
            'callbacks_bound': len(needed) - len(missing),
            'unbound_addresses': [f'{address:08x}' for address in missing],
        })
    fighter_coverage.sort(key=lambda row: (len(row['unbound_addresses']),
                                           not row['fixture_data_ready'], row['fkind']))
    write_json(BUILD / 'native-callback-coverage.json', {
        'schema': 1,
        'reference_rom_sha256': sha256(ref.path),
        'unique_expansion_callbacks': len(worklist['targets']),
        'native_bound_callbacks': len(worklist['targets']) - len(unresolved),
        'unbound_callbacks': len(unresolved),
        'highest_fanout_unbound': [
            {'address': row['address'], 'symbols': row['symbols'],
             'uses': len(row['uses'])}
            for row in sorted(unresolved, key=lambda item: (-len(item['uses']), item['address']))[:30]],
        'fighter_action_coverage': fighter_coverage,
    })
    from native_callback_frontier import rank_callback_frontier
    families = json.loads((BUILD / 'action-callback-families.json').read_text())
    write_json(BUILD / 'native-callback-frontier.json',
               rank_callback_frontier(ref, worklist, audit, bindings, families))
    rows = {row['name']: row for row in audit['fighters']}
    enabled = {row['name']: row for row in catalog['fighters']}
    names = config.get('auto_action_patches')
    if not isinstance(names, list) or len(names) != len(set(names)):
        raise ValueError('Invalid automatic action patch fighter list')
    for name in names:
        if name not in enabled or enabled[name]['registration'] != 'custom':
            raise ValueError(f'Automatic action patches need custom registration: {name}')
        row = rows[name]
        if row['fkind'] != enabled[name]['fkind'] or row['parent'] != enabled[name]['parent']:
            raise ValueError(f'Reference fighter mismatch: {name}')
        data = render_action_assignments(row, bindings, row['action_table']['inherited_statuses'])
        (Path(out) / f'{name.lower()}_action_patches.inc').write_text(data)
    (Path(out) / 'generic_action_tables.inc').write_text(
        render_generic_action_tables(catalog, audit, bindings))
    return names
