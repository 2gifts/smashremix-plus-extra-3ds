"""Test the actual C++ loader with an expanded pack, malformed indexes, and optionally real mod data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import zlib
from common import BUILD, ROOT, sha256, write_json
from extract_reference_assets import chain

SHIM = '''#include <memory>
#include <vector>
#include <string>
#include <cstdint>
#include <cassert>
#include <cstdio>
struct RelocFile {uint32_t FileId;uint16_t RelocInternOffset,RelocExternOffset;std::vector<uint8_t> Data;std::vector<uint16_t> ExternFileIds;};
struct NativeRelocInfo {uint32_t size,count;const uint16_t* deps;};
extern "C" {uint32_t native_asset_reads,native_asset_hits,native_asset_bytes;void port_log(const char*,...) {}}
'''

def compiler_path(requested):
    if requested:
        return requested
    config = ROOT / '3ds/build-config.json'
    if config.exists():
        cfg = json.loads(config.read_text())
        if 'llvm_bin' in cfg:
            return str(Path(cfg['llvm_bin']) / 'clang++.exe')
    value = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
    if not value:
        raise RuntimeError('Provide --compiler /path/to/clang++ or g++')
    return value

def compile_test(compiler, directory, pack, index, body):
    native = (ROOT / '3ds/src/native_assets.cpp').read_text()
    native = native.replace('#include "native_assets.h"', '')
    # Keep all parser/loader logic intact. Use an exit code for expected
    # validation failures instead of opening the Windows crash reporter.
    native = native.replace('std::abort();', 'std::exit(86);')
    native = native.replace('"romfs:/reloc.pak"', json.dumps(pack.as_posix()))
    native = native.replace('"romfs:/reloc-deps.bin"', json.dumps(index.as_posix()))
    source = directory / 'loader.cpp'
    source.write_text(SHIM + native + body)
    exe = directory / ('loader.exe' if os.name == 'nt' else 'loader')
    subprocess.run([compiler, '-std=c++17', '-O2', '-I' + str(ROOT / '3ds/include'),
                    str(source), '-o', str(exe)], check=True)
    return exe

def run(exe, *args, expected=0):
    result = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=90)
    if result.returncode != expected:
        raise AssertionError(f'{args}: expected {expected}, got {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result.stdout.strip()

def fixtures(compiler, out):
    count = 7564
    pack, index = out / 'fixture.pak', out / 'fixture.idx'
    header = b'SSB3DPAK' + struct.pack('<II', 1, count)
    table = bytearray()
    payload_start = 16 + count * 20
    chosen = {0: 1, 2131: 2, 2132: 3, count-1: 4}
    for fid in range(count):
        value = chosen.get(fid)
        table += struct.pack('<IIIHHI', payload_start + (value-1)*262144 if value else 0,
                             262144 if value else 0, 0, 0xffff, 0xffff, 0)
    valid_index = b'SSB3DIDX' + struct.pack('<II', count, 0) + bytes((count+1)*4)
    def restore():
        with pack.open('wb') as stream:
            stream.write(header + table)
            for value in range(1,5):
                stream.write(bytes([value]) * 262144)
            stream.truncate(33*1024*1024)
        index.write_bytes(valid_index)
    restore()
    body = '''
int main(int argc,char**){
    openPack(); if(argc>1){nativeAssetsShutdown();return 0;}
    assert(FileCount==7564&&!residentPack&&pack&&native_asset_reads==0);
    unsigned ids[]={0,2131,2132,7563};
    for(unsigned j=0;j<100;j++)for(unsigned i=0;i<4;i++){
        auto p=nativeLoadReloc(ids[i]);assert(p->Data.size()==262144);
        assert(p->Data.front()==i+1&&p->Data.back()==i+1);
        assert(retainedBytes<=CacheBudget);
    }
    assert(native_asset_reads==4&&native_asset_hits==396);
    auto held=nativeLoadReloc(7563);nativeAssetsShutdown();
    assert(held->Data[0]==4&&cached.empty()&&retained.empty());
    auto reloaded=nativeLoadReloc(7563);assert(reloaded!=held&&reloaded->Data[0]==4);
    nativeAssetsShutdown();puts("expanded IDs, bounded streaming cache, live handles and reopen passed");
}
'''
    exe = compile_test(compiler, out, pack, index, body)
    details = [run(exe)]
    cases = {
        'zero_file_count': ('pack', 12, struct.pack('<I',0)),
        'excessive_file_count': ('pack', 12, struct.pack('<I',16385)),
        'payload_out_of_bounds': ('pack',16,struct.pack('<I',0xffffffff)),
        'payload_overlaps_header': ('pack',16,struct.pack('<I',1)),
        'dependency_count_over_limit': ('index',12,struct.pack('<I',262145)),
        'dependency_offset_nonzero_start': ('index',16,struct.pack('<I',1)),
        'dependency_offset_out_of_bounds': ('index',20,struct.pack('<I',1)),
    }
    for name,(which,offset,value) in cases.items():
        restore()
        with (pack if which=='pack' else index).open('r+b') as stream:
            stream.seek(offset);stream.write(value)
        run(exe,'probe',expected=86)
        details.append(name)
    restore()
    return {'passed': True, 'cases': details}

def reference(compiler, out):
    assets = BUILD / 'assets'
    pack = assets / 'reloc.reference.pak'
    manifest = json.loads((assets / 'manifest.json').read_text())
    if sha256(pack) != manifest['summary']['pack_sha256']:
        raise ValueError('Reference pack hash mismatch')
    if sha256(assets / 'reloc-deps.bin') != manifest['summary']['dependency_index_sha256']:
        raise ValueError('Reference dependency index hash mismatch')
    rows = []
    internal_outside = []
    with pack.open('rb') as stream:
        stream.seek(16)
        entries = [struct.unpack('<IIIHHI', stream.read(20)) for _ in manifest['entries']]
        for info, entry in zip(manifest['entries'], entries):
            offset,size,count,internal,external,_ = entry
            stream.seek(offset);data=stream.read(size)
            if hashlib.sha256(data).hexdigest()!=info['sha256']:
                raise ValueError(f'Asset {info["id"]} hash mismatch')
            for slot, target in chain(data, internal):
                if target * 4 >= size:
                    internal_outside.append((info['id'], slot * 4, target * 4))
            links = list(chain(data, external))
            if len(links) != count:
                raise ValueError(f'Asset {info["id"]}: external chain/count mismatch')
            stream.seek(offset + size)
            ids = struct.unpack('<' + str(count) + 'H', stream.read(count * 2))
            if list(ids) != info['external_files']:
                raise ValueError(f'Asset {info["id"]}: dependency index differs from manifest')
            for (_, target), dependency in zip(links, ids):
                if target * 4 >= entries[dependency][1]:
                    raise ValueError(f'Asset {info["id"]}: external target outside dependency')
            rows.append('{%d,%d,%d,%du}' % (info['id'],size,count,zlib.crc32(data)))
        reported = [(issue['file_id'], issue['slot'], issue['target'])
                    for issue in manifest['relocation_issues']
                    if issue['kind'] == 'internal_target_outside_file']
        if sorted(internal_outside) != sorted(reported):
            raise ValueError('Internal relocation findings differ from packed data')
        corrections = manifest.get('canonicalized_cross_file', [])
        if len(corrections) != manifest['summary'].get('cross_file_relocations_canonicalized', 0):
            raise ValueError('Cross-file relocation correction count mismatch')
        for correction in corrections:
            file_id = correction['file_id']
            offset, size, count, _, first, _ = entries[file_id]
            slot, index, found = first, 0, False
            while slot != 0xffff:
                if index >= count or slot * 4 + 4 > size:
                    raise ValueError(f'Asset {file_id}: corrected external chain is invalid')
                stream.seek(offset + slot * 4)
                next_slot, target = struct.unpack('>HH', stream.read(4))
                if slot * 4 == correction['slot']:
                    stream.seek(offset + size + index * 2)
                    owner = struct.unpack('<H', stream.read(2))[0]
                    if (owner != correction['resolved_dependency'] or
                            target * 4 != correction['resolved_target'] or
                            manifest['entries'][file_id]['external_files'][index] != owner):
                        raise ValueError(f'Asset {file_id}: corrected external target differs from manifest')
                    found = True
                    break
                slot, index = next_slot, index + 1
            if not found:
                raise ValueError(f'Asset {file_id}: corrected external slot missing')
    body = '\nstruct Expected {unsigned id,size,deps,crc;};\nstatic Expected expected[]={'+','.join(rows)+'};\n'
    body += '''
unsigned crc(const std::vector<uint8_t>& data){
    static unsigned table[256];static bool ready;
    if(!ready){for(unsigned i=0;i<256;i++){unsigned c=i;for(int j=0;j<8;j++)c=(c>>1)^(0xedb88320u&-(c&1));table[i]=c;}ready=true;}
    unsigned c=~0u;for(auto b:data)c=(c>>8)^table[(c^b)&255];return ~c;
}
int main(){
    openPack();assert(!residentPack&&pack);
    for(const auto& e:expected){
        auto info=nativeRelocInfo(e.id);assert(info.size==e.size&&info.count==e.deps);
        auto file=nativeLoadReloc(e.id);assert(file->Data.size()==e.size&&file->ExternFileIds.size()==e.deps);
        assert(crc(file->Data)==e.crc&&retainedBytes<=CacheBudget);
    }
    assert(FileCount==sizeof(expected)/sizeof(*expected));nativeAssetsShutdown();
    puts("all reference asset payloads and dependency counts match; cache remains bounded");
}
'''
    exe=compile_test(compiler,out,pack,assets/'reloc-deps.bin',body)
    return {'passed': True, 'detail': run(exe), 'files': len(rows),
            'pack_sha256': manifest['summary']['pack_sha256'],
            'scope': 'Raw I/O and cache only; does not execute relocations, game code, or rendering.',
            'native_relocation_issues_remaining': manifest['summary']['relocation_issues']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler');parser.add_argument('--reference',action='store_true')
    args=parser.parse_args()
    compiler=compiler_path(args.compiler)
    os.environ['PATH']=str(Path(compiler).resolve().parent)+os.pathsep+os.environ.get('PATH','')
    out=BUILD/'loader-test';out.mkdir(parents=True,exist_ok=True)
    report={'fixtures': fixtures(compiler,out)}
    if args.reference:report['reference']=reference(compiler,out)
    report['passed']=True
    write_json(out/'verified.json',report)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
