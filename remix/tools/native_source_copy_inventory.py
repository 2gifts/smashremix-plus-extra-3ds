"""Link upstream OS.copy_segment patch scopes to compiled action callbacks.

The assembly source documents which original routines a mod author copied.
This report is a discovery aid for native adapters; only the pinned compiled
ROM and checked semantic decoders may create runtime bindings.
"""

import re
from collections import defaultdict
from pathlib import Path

from common import BUILD, sha256, write_json


SCOPE = re.compile(r'\bscope\s+([A-Za-z_]\w*)\s*:?\s*\{')
COPY = re.compile(r'\bOS\.copy_segment\s*\(([^)]*)\)')


def source_copies(source_root):
    """Yield enclosing scope and source location for active copy macro calls."""
    for path in sorted(Path(source_root).rglob('*.asm')):
        depth = 0
        stack = []
        for line_number, raw in enumerate(path.read_text(errors='replace').splitlines(), 1):
            line = raw.split('//', 1)[0]
            scope = SCOPE.search(line)
            if scope:
                stack.append((scope.group(1), depth + 1))
            for copy in COPY.finditer(line):
                if stack:
                    yield { 'symbol': '.'.join(item[0] for item in stack),
                            'source': path.relative_to(source_root).as_posix(),
                            'line': line_number, 'arguments': copy.group(1).strip() }
            depth += line.count('{') - line.count('}')
            while stack and stack[-1][1] > depth:
                stack.pop()


def build_inventory(ref, worklist, bindings, source_root=None):
    if worklist['reference_rom_sha256'] != sha256(ref.path):
        raise ValueError('Source-copy worklist and pinned reference ROM differ')
    source_root = Path(source_root) if source_root else ref.path.with_name('src')
    by_address = {int(row['address'], 16): row for row in worklist['targets']}
    matched = defaultdict(list)
    total = 0
    for copy in source_copies(source_root):
        total += 1
        address = ref.symbols.get(copy['symbol'])
        if address in by_address:
            matched[address].append(copy)
    rows = []
    for address, copies in matched.items():
        target = by_address[address]
        rows.append({'address': target['address'], 'symbols': target['symbols'],
                     'action_table_uses': len(target['uses']),
                     'fighters': sorted({use['fighter'] for use in target['uses']}),
                     'native_bound': address in bindings,
                     'copy_segments': copies})
    rows.sort(key=lambda row: (row['native_bound'], -row['action_table_uses'], row['address']))
    return {'schema': 1, 'reference_rom_sha256': sha256(ref.path),
            'scope': ('Source copy macros identify candidate original-code adaptations. '
                      'Scope matching and source comments do not prove compiled behavior '
                      'or create native bindings.'),
            'active_copy_macro_calls': total,
            'matched_action_callback_scopes': len(rows),
            'matched_callback_copy_segments': sum(len(row['copy_segments']) for row in rows),
            'unbound_matched_callback_scopes': sum(not row['native_bound'] for row in rows),
            'callbacks': rows}


def write_inventory(ref, worklist, bindings):
    report = build_inventory(ref, worklist, bindings)
    write_json(BUILD / 'native-source-copy-inventory.json', report)
    return report
