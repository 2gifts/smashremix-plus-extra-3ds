"""Generate narrow adaptations of the pinned asset bridges to local ROM reads."""
from pathlib import Path
import re
from build import ROOT, UPSTREAM

def write(name, text):
    path=ROOT/'generated'/name
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or path.read_text(encoding='utf-8')!=text:
        path.write_text(text,encoding='utf-8')

def adapt_audio_sequence_loader(source):
    # The expanded Remix SBK is several MiB. AudioBlob already retains its
    # data for the session, so the heap only needs the small sequence index.
    a=source.index('static ALSeqFile* parseSeqFile(')
    b=source.index('/* ========================================================================= */',a)
    replacement='''static ALSeqFile* parseSeqFile(const u8* sbk, size_t sbkSize, ALHeap* heap) {
    if (!sbk || sbkSize < 4) return nullptr;
    const s16 revision = readBE16s(sbk);
    const s16 seqCount = readBE16s(sbk + 2);
    if (revision != 0x5331 || seqCount <= 0 || seqCount > 2048 ||
        (size_t)seqCount > (sbkSize - 4) / 8) return nullptr;
    const size_t headerSize = 4 + (size_t)seqCount * 8;
    for (s16 i = 0; i < seqCount; i++) {
        const u32 off = readBE32(sbk + 4 + i * 8);
        const u32 len = readBE32(sbk + 4 + i * 8 + 4);
        if (off < headerSize || (off & 3) || !len || len > 1024 * 1024 ||
            off > sbkSize || len > sbkSize - off) return nullptr;
    }
    const size_t allocSize = sizeof(ALSeqFile) +
        (seqCount - 1) * sizeof(ALSeqData);
    auto* sf = (ALSeqFile*)alHeapAlloc(heap, 1, (s32)allocSize);
    if (!sf) return nullptr;
    sf->revision = revision;
    sf->seqCount = seqCount;
    for (s16 i = 0; i < seqCount; i++) {
        const u32 off = readBE32(sbk + 4 + i * 8);
        const u32 len = readBE32(sbk + 4 + i * 8 + 4);
        sf->seqArray[i].offset = const_cast<u8*>(sbk + off);
        sf->seqArray[i].len = (s32)len;
    }
    return sf;
}

'''
    source=source[:a]+replacement+source[b:]
    needle='    sSYAudioSeqFile = parseSeqFile(music_sbk.data, music_sbk.size, &sSYAudioHeap);\n'
    if source.count(needle)!=1:
        raise ValueError('Unsupported BattleShip music loader; check the pinned dependency')
    return source.replace(needle,needle+'''    if (!sSYAudioSeqFile) {
        spdlog::error("audio_bridge: invalid or oversized music sequence bank");
        return;
    }
''')

def bridges():
    for name in ['lbreloc_bridge','audio_bridge','particle_bank_bridge']:
        s=(UPSTREAM/'port/bridge'/f'{name}.cpp').read_text(encoding='utf-8')
        s=re.sub(r'^#include <ship/[^\n]+\n','',s,flags=re.M)
        s='#include "native_assets.h"\n'+s
        if name=='lbreloc_bridge':
            animation_hook='static bool portRelocIsFighterFigatreeFile(u32 file_id)\n{'
            if s.count(animation_hook)!=1:
                raise ValueError('Unsupported BattleShip animation classifier; check the pinned dependency')
            s=s.replace(animation_hook,
                'extern "C" int nativeRelocIsFighterAnimation(unsigned int);\n'
                'static bool portRelocIsFighterFigatreeFile(u32 file_id)\n{\n'
                '    if (nativeRelocIsFighterAnimation(file_id)) return true;')
            a=s.index('static std::shared_ptr<RelocFile> portLoadRelocResource(')
            b=s.index('// All game-facing functions have C linkage',a)
            s=s[:a]+'''static std::shared_ptr<RelocFile> portLoadRelocResource(u32 file_id)
{
    return nativeLoadReloc(file_id);
}

'''+s[b:]
            a=s.index('size_t lbRelocGetExternBytesNum(');b=s.index('size_t lbRelocGetFileSize(',a)
            block=s[a:b].replace('auto relocFile = portLoadRelocResource(file_id);','auto info = nativeRelocInfo(file_id);')
            block=block.replace('if (!relocFile) { return 0; }','').replace('relocFile->Data.size()','info.size')
            block=block.replace('for (u16 dep_id : relocFile->ExternFileIds)','for (unsigned dep=0;dep<info.count;dep++)').replace('lbRelocGetExternBytesNum(dep_id)','lbRelocGetExternBytesNum(info.deps[dep])')
            s=s[:a]+block+s[b:]
        elif name=='audio_bridge':
            s=s.replace('std::shared_ptr<Ship::IResource> resource;',
                        'std::shared_ptr<std::vector<uint8_t>> resource;')
            a=s.index('    auto ctx = Ship::Context::GetInstance();',s.index('static bool loadBlob('))
            b=s.index('    spdlog::info(',a)
            s=s[:a]+'''    auto data = nativeLoadBlob(name);
    if (!data) return false;
    out.data = data->data();
    out.size = data->size();
    out.resource = data;
'''+s[b:]
            s=adapt_audio_sequence_loader(s)
        else:
            a=s.index('    auto ctx = Ship::Context::GetInstance();',s.index('static const std::vector<uint8_t> *ensurePristine('))
            b=s.index('    if (is_script_bank)',a)
            s=s[:a]+'''    auto blob = nativeLoadBlob(archive_path);
    if (!blob) return nullptr;
    std::vector<uint8_t> data(*blob);
'''+s[b:]
        write(name+'.cpp',s)

if __name__=='__main__':
    bridges()
