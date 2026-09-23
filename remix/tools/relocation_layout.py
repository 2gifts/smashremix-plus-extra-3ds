"""Resolve N64 relocations that address a later file in one load arena.

lbRelocGetInternBufferFile and lbRelocGetExternBufferFile align each file to
16 bytes, reserve it, then recursively load its external dependencies in
relocation-chain order. Some Remix links use an offset past their named file
and land in a later allocation. The native pack needs a direct file/offset
pair because it cannot rely on that physical adjacency.
"""


def dependency_layout(entries, root):
    cursor = 0
    starts = {}
    segments = []
    active = set()

    def load(file_id):
        nonlocal cursor
        if file_id in starts:
            return
        if file_id in active:
            raise ValueError(f'Relocation dependency cycle at {file_id}')
        if not 0 <= file_id < len(entries):
            raise ValueError(f'Invalid relocation dependency {file_id}')
        active.add(file_id)
        cursor = (cursor + 15) & ~15
        start = cursor
        size = entries[file_id]['size']
        if size < 0:
            raise ValueError(f'Negative relocation file size {file_id}')
        cursor += size
        starts[file_id] = start
        if size:
            segments.append((start, cursor, file_id))
        for dependency in entries[file_id]['external_files']:
            load(dependency)
        active.remove(file_id)

    load(root)
    return starts, segments


def cross_file_target(layout, dependency, byte_offset):
    """Return the actual owner and byte offset, or None for a gap/unknown."""
    starts, segments = layout
    if dependency not in starts or byte_offset < 0 or byte_offset % 4:
        return None
    address = starts[dependency] + byte_offset
    for start, end, owner in segments:
        if start <= address < end:
            return owner, address - start
    return None


def reverse_dependencies(entries):
    parents = [set() for _ in entries]
    for file_id, entry in enumerate(entries):
        for dependency in entry['external_files']:
            if not 0 <= dependency < len(entries):
                raise ValueError(f'Invalid relocation dependency {dependency}')
            parents[dependency].add(file_id)
    return parents


def stable_cross_file_target(entries, parents, source, dependency, byte_offset,
                             layouts=None):
    """Accept a target only if every possible ancestor-root layout agrees."""
    layouts = layouts if layouts is not None else {}
    roots, pending = {source}, [source]
    while pending:
        for parent in parents[pending.pop()]:
            if parent not in roots:
                roots.add(parent)
                pending.append(parent)
    destinations = set()
    for root in roots:
        if root not in layouts:
            layouts[root] = dependency_layout(entries, root)
        destination = cross_file_target(layouts[root], dependency, byte_offset)
        if destination is None:
            return None
        destinations.add(destination)
        if len(destinations) > 1:
            return None
    return next(iter(destinations))
