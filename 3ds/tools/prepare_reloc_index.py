"""Keep size/dependency planning from reading entire assets on the console."""
import struct
from build import ROOT
def prepare(pack_path,index_path):
    pack=pack_path.read_bytes();assert pack[:8]==b'SSB3DPAK'
    version,count=struct.unpack_from('<II',pack,8);assert version==1 and 0<count<=16384
    assert len(pack)>=16+count*20
    offsets=[0];deps=bytearray()
    for i in range(count):
        start,size,n,*_=struct.unpack_from('<IIIHHI',pack,16+i*20)
        assert size<=16*1024*1024 and n<=65536 and start+size+n*2<=len(pack)
        assert not(size or n) or start>=16+count*20
        chunk=pack[start+size:start+size+n*2];assert len(chunk)==n*2
        assert all(dep<count for (dep,) in struct.iter_unpack('<H',chunk))
        deps+=chunk;offsets.append(len(deps)//2)
    assert len(deps)//2<=262144
    data=b'SSB3DIDX'+struct.pack('<II',count,len(deps)//2)+struct.pack('<%dI'%len(offsets),*offsets)+deps
    path=index_path
    if not path.exists() or path.read_bytes()!=data:path.write_bytes(data)
    print('Relocation dependency index:',len(data),'bytes')
def main():
    prepare(ROOT/'assets/reloc.pak',ROOT/'assets/reloc-deps.bin')
if __name__=='__main__':main()
