"""Convert the verified reference ROM's relocation assets to native pack format.

This imports data, not MIPS code. A valid pack alone does not make the mod playable.
Zoinkity's SSB.py, retained in the +EXTRA submodule, supplies ROM-table and VPK decoding.
"""
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path
from common import BUILD, ROOT, checked_sources, sha256, write_json

def chain(data, first):
    seen = set()
    while first != 0xffff:
        if first in seen or first * 4 + 4 > len(data):
            raise ValueError(f'Invalid relocation link {first:#x}')
        seen.add(first)
        value = struct.unpack_from('>I', data, first * 4)[0]
        yield first, value & 0xffff
        first = value >> 16

def main():
    lock, sources = checked_sources()
    reference = json.loads((BUILD / 'reference.json').read_text())
    for name in ('extra', 'remix'):
        if reference[name + '_commit'] != lock[name]['commit']:
            raise ValueError('Reference was built from a different source revision')
    rom_path = (ROOT / reference['rom']).resolve()
    if not rom_path.is_relative_to(BUILD.resolve()) or sha256(rom_path) != reference['rom_sha256']:
        raise ValueError('Reference ROM does not match its local build manifest')
    module_path = sources['extra'] / 'SSB.py'
    spec = importlib.util.spec_from_file_location('remix_ssb', module_path)
    ssb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ssb)
    rom = rom_path.read_bytes()
    n64 = ssb.N64(rom)
    table = ssb.fetch(n64, ssb.NALE[0][1][0])
    count = n64.getASMvalue(*ssb.NALEnum[0])
    if not 0 < count <= 16384 or table + (count + 1) * 12 > len(rom):
        raise ValueError('Unsupported relocation table')
    out = BUILD / 'assets'
    out.mkdir(exist_ok=True)
    payload_start = table + (count + 1) * 12
    entries, metadata, offsets, deps = [], [], [0], bytearray()
    relocation_issues = []
    target = out / 'reloc.reference.pak'
    temporary = out / 'reloc.reference.pak.tmp'
    position = 16 + count * 20
    with temporary.open('wb+') as pack:
        pack.write(b'SSB3DPAK' + struct.pack('<II', 1, count))
        pack.write(bytes(count * 20))
        for fid in range(count):
            if fid % 500 == 0:
                print(f'Extracting {fid}/{count} assets', flush=True)
            raw_offset, intern, compressed, external, expanded = struct.unpack_from('>I4H', rom, table + fid * 12)
            next_offset = struct.unpack_from('>I', rom, table + (fid + 1) * 12)[0] & 0x7fffffff
            begin = payload_start + (raw_offset & 0x7fffffff)
            end = payload_start + next_offset
            size = compressed * 4
            if not payload_start <= begin <= begin + size <= end <= len(rom):
                raise ValueError(f'Asset {fid:#x}: ROM bounds')
            raw = rom[begin:begin + size]
            data = bytes(ssb.VPK.dec_file(raw)) if raw_offset & 0x80000000 else raw
            expected = expanded * 4
            if not expected - 3 <= len(data) <= expected:
                raise ValueError(f'Asset {fid:#x}: decompressed size {len(data)} != {expected}')
            data = data.ljust(expected, b'\0')
            def inspect_chain(first, kind):
                links = []
                try:
                    links.extend(chain(data, first))
                except ValueError as error:
                    relocation_issues.append({'file_id': fid, 'kind': kind + '_chain', 'detail': str(error)})
                return links
            internal_links = inspect_chain(intern, 'internal')
            external_links = inspect_chain(external, 'external')
            ids_end = begin + size + len(external_links) * 2
            if ids_end > end:
                raise ValueError(f'Asset {fid:#x}: dependency IDs out of bounds')
            ids = [n for (n,) in struct.iter_unpack('>H', rom[begin + size:ids_end])]
            if any(n >= count for n in ids):
                raise ValueError(f'Asset {fid:#x}: dependency ID out of bounds')
            for slot, offset in internal_links:
                if offset * 4 >= len(data):
                    relocation_issues.append({'file_id': fid, 'kind': 'internal_target_outside_file',
                                              'slot': slot * 4, 'target': offset * 4, 'file_size': len(data)})
            little_ids = struct.pack('<' + str(len(ids)) + 'H', *ids)
            entries.append(struct.pack('<IIIHHI', position, len(data), len(ids), intern, external, 0))
            pack.write(data)
            pack.write(little_ids)
            position += len(data) + len(little_ids)
            offsets.append(offsets[-1] + len(ids))
            deps.extend(little_ids)
            metadata.append({'id': fid, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                             'external_files': ids, 'external_targets': [n for _, n in external_links]})
        for entry in metadata:
            for dep, offset in zip(entry['external_files'], entry.pop('external_targets')):
                if offset * 4 >= metadata[dep]['size']:
                    relocation_issues.append({'file_id': entry['id'], 'kind': 'external_target_outside_file',
                                              'dependency': dep, 'target': offset * 4,
                                              'file_size': metadata[dep]['size']})
        pack.seek(16)
        pack.write(b''.join(entries))
    temporary.replace(target)
    if len(deps) // 2 > 262144:
        raise ValueError('Dependency catalogue exceeds native loader limit')
    index = b'SSB3DIDX' + struct.pack('<II', count, len(deps) // 2)
    index += struct.pack('<' + str(len(offsets)) + 'I', *offsets) + deps
    (out / 'reloc-deps.bin').write_bytes(index)
    summary = {
        'source_rom_sha256': reference['rom_sha256'], 'extra_commit': lock['extra']['commit'],
        'remix_commit': lock['remix']['commit'], 'files': count, 'dependencies': len(deps) // 2,
        'pack_bytes': target.stat().st_size, 'pack_sha256': sha256(target),
        'dependency_index_sha256': sha256(out / 'reloc-deps.bin'),
        'native_3ds_playable': False, 'native_relocations_validated': not relocation_issues,
        'relocation_issues': len(relocation_issues),
    }
    write_json(out / 'manifest.json', {'summary': summary, 'entries': metadata, 'relocation_issues': relocation_issues})
    print(json.dumps(summary, indent=2))
    if relocation_issues:
        print('Reference pack retained for analysis only. Resolve the recorded relocation issues before native use.')
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
