"""Bind compiled N64 action-table deltas to shared native C callbacks.

The audit supplies status/role/address, so each source callback is bound once
regardless of how many fighters or statuses use it. This deliberately refuses
unknown flags, added statuses and unbound MIPS callbacks instead of silently
inheriting the parent's behavior.
"""
import json
import re
from pathlib import Path

from common import ROOT, sha256


BINDINGS = ROOT / 'remix/native_callback_bindings.json'
ROLES = {'update': 'proc_update', 'interrupt': 'proc_interrupt',
         'physics': 'proc_physics', 'map': 'proc_map'}


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
    if table['added_statuses'] or table['added_status_records']:
        raise ValueError(f"{fighter['name']}: added statuses need native descriptors")
    if table['inherited_statuses'] != status_count:
        raise ValueError(f"{fighter['name']}: native status count differs from reference")
    lines = [f'/* Compiled Character.edit_action patches for {fighter["name"]}. */',
             f'_Static_assert(ARRAY_COUNT(NATIVE_REMIX_ACTION_STATUS) == {status_count}, '
             '"Compiled action table size changed");']
    for status in sorted(table['changed_inherited_statuses'], key=lambda item: item['status_id']):
        index = status['status_id'] - 0xdc
        if not 0 <= index < status_count:
            raise ValueError(f"{fighter['name']}: action status outside inherited table")
        if status['flags'] is not None:
            raise ValueError(f"{fighter['name']}: changed action flags need native translation")
        for role in ROLES:
            callback = status['callbacks'].get(role)
            if callback is None:
                continue
            address = int(callback['remix'], 16)
            native = bindings.get(address)
            if native is None:
                raise ValueError(f"{fighter['name']}: unbound {role} callback {address:08x}")
            lines.append(f'NATIVE_REMIX_ACTION_STATUS[{index}].{ROLES[role]} = {native};')
    return '\n'.join(lines) + '\n'


def write_action_patches(ref, audit, catalog, out):
    if audit.get('reference_rom_sha256') != sha256(ref.path):
        raise ValueError('Action audit does not match the pinned reference')
    config, bindings = load_bindings(symbols=ref.symbols)
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
    return names
