"""Build an ARM11 asset-loader diagnostic 3DSX; never a playable Remix package."""
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zlib
from common import BUILD, ROOT, sha256, write_json

def main():
    sys.path.insert(0,str(ROOT/'3ds/tools'))
    from build import ARM,SDK,BIN,ARCH,GCC_VERSION,tool,configured
    assets=BUILD/'assets';report=json.loads((assets/'manifest.json').read_text())
    pack=assets/'reloc.reference.pak'
    if sha256(pack)!=report['summary']['pack_sha256']:raise ValueError('Pack hash mismatch')
    if sha256(assets/'reloc-deps.bin')!=report['summary']['dependency_index_sha256']:raise ValueError('Dependency index hash mismatch')
    out=BUILD/'asset-probe';out.mkdir(exist_ok=True)
    romfs=out/'romfs';romfs.mkdir(exist_ok=True)
    shutil.copy2(pack,romfs/'reloc.pak');shutil.copy2(assets/'reloc-deps.bin',romfs/'reloc-deps.bin')
    checks=bytearray(struct.pack('<II',0x31584252,len(report['entries'])))
    with pack.open('rb') as stream:
        stream.seek(16)
        entries=[struct.unpack('<IIIHHI',stream.read(20)) for _ in report['entries']]
        for expected,entry in zip(report['entries'],entries):
            offset,size,count,*_=entry;stream.seek(offset);data=stream.read(size)
            if hashlib.sha256(data).hexdigest()!=expected['sha256']:raise ValueError('Payload hash mismatch')
            checks+=struct.pack('<IIII',expected['id'],size,count,zlib.crc32(data))
    (romfs/'checks.bin').write_bytes(checks)
    cxx=configured('cxx_include',ARM/'arm-none-eabi/include/c++'/GCC_VERSION)
    flags=[*ARCH,'-std=c++17','-O2','-g','-D__3DS__','-fno-short-enums',
           '-fno-exceptions','-fno-rtti','-ffunction-sections','-fdata-sections',
           '-I'+str(ROOT/'3ds/include'),'-I'+str(SDK/'libctru/include'),
           '-nostdinc++','-isystem',str(cxx),'-isystem',str(cxx/'arm-none-eabi/armv6k/fpu'),
           '-isystem',str(cxx/'backward'),'-isystem',str(ARM/'arm-none-eabi/include')]
    objects=[]
    for source in [ROOT/'remix/tests/asset_probe.cpp',ROOT/'3ds/src/native_assets.cpp']:
        obj=out/(source.stem+'.o')
        subprocess.run(list(map(str,[BIN/'clang++.exe',*flags,'-c',source,'-o',obj])),check=True)
        objects.append(obj)
    libs=ARM/'arm-none-eabi/lib/armv6k/fpu';gcc=ARM/'lib/gcc/arm-none-eabi'/GCC_VERSION/'armv6k/fpu'
    script=(ARM/'arm-none-eabi/lib/3dsx.ld').read_text()
    script=script.replace('data   PT_LOAD FLAGS(6)','tls    PT_TLS FLAGS(4);\n\tdata   PT_LOAD FLAGS(6)')
    for start,end in [('\t.tdata :','\t.tbss :'),('\t.tbss :','\t/*')]:
        a=script.index(start);b=script.index(end,a+len(start));script=script[:a]+script[a:b].replace(': data',': data : tls')+script[b:]
    script=script.replace('.bss ALIGN(4)','.bss ALIGN(32)').replace('*(.data.*)','*(.data.*)\n\t\t*(.got .got.*)')
    layout=out/'3dsx-lld.ld';layout.write_text(script)
    elf=out/'remix-asset-probe.elf'
    command=[BIN/'ld.lld.exe','-T',layout,'--gc-sections','--emit-relocs','--wrap=abort',
             '-Map='+str(out/'probe.map'),libs/'3dsx_crt0.o',gcc/'crti.o',gcc/'crtbegin.o',
             *objects,'-L'+str(SDK/'libctru/lib'),'-L'+str(libs),'-L'+str(gcc),
             '--start-group','-lstdc++','-lctru','-lm','-lc','-lsysbase','-lgcc','--end-group',
             gcc/'crtend.o',gcc/'crtn.o','-o',elf]
    subprocess.run(list(map(str,command)),check=True)
    binary=out/'remix-asset-probe.3dsx'
    metadata=bytearray(0x36c0);metadata[:4]=b'SMDH'
    for language in range(16):
        for offset,label in [(0,'Remix asset test'),(0x80,'Raw asset loader diagnostic - no gameplay'),(0x180,'Smash port and upstream contributors')]:
            data=label.encode('utf-16le');start=8+language*0x200+offset
            metadata[start:start+len(data)]=data
    struct.pack_into('<I',metadata,0x2018,0x7fffffff);struct.pack_into('<I',metadata,0x2028,1)
    smdh=out/'probe.smdh';smdh.write_bytes(metadata)
    subprocess.run(list(map(str,[tool('3dsxtool'),elf,binary,'--smdh='+str(smdh),'--romfs='+str(romfs)])),check=True)
    result={'diagnostic_only':True,'native_gameplay':False,'elf_sha256':sha256(elf),
            'binary_sha256':sha256(binary),'pack_sha256':report['summary']['pack_sha256'],
            'expected_files':len(entries)}
    write_json(out/'build.json',result)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
