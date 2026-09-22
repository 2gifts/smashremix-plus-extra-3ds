#include "native_assets.h"
/* Expanded animation IDs have no entry in the original filename catalogue.
 * The native roster supplies their type explicitly when one is installed. */
extern "C" __attribute__((weak)) int nativeRelocIsFighterAnimation(unsigned int) { return 0; }
#include "native_perf.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

extern "C" void port_log(const char*, ...);
namespace {
constexpr size_t MaxFileCount=16384;
constexpr size_t MaxDependencies=262144;
constexpr size_t ResidentBudget=24*1024*1024;
size_t FileCount;
struct Entry { uint32_t offset,size,deps; uint16_t internal,external; uint32_t reserved; };
static_assert(sizeof(Entry)==20);
std::vector<Entry> assetIndex;
std::vector<uint32_t> dependencyOffsets;
std::vector<uint16_t> dependencies;
std::vector<std::weak_ptr<RelocFile>> cached;
// These bytes are pristine: relocation always copies them into the scene
// arena. Retaining a bounded working set is safe across arena replacement.
std::vector<std::shared_ptr<RelocFile>> retained;
std::vector<uint32_t> age;
size_t retainedBytes;
uint32_t cacheClock;
constexpr size_t CacheBudget=1024*1024;
FILE* pack;
uint8_t* residentPack;
size_t packBytes;
bool packReady;
[[noreturn]] void fail(const char* message) {
    port_log("ASSET FAILURE: %s\n",message);
    std::abort();
}
void openPack() {
    if(packReady) return;
    pack=std::fopen("romfs:/reloc.pak","rb");
    if(!pack) fail("cannot open romfs:/reloc.pak");
    uint32_t header[4];
    if(std::fread(header,1,16,pack)!=16 || std::memcmp(header,"SSB3DPAK",8)
       || header[2]!=1 || !header[3] || header[3]>MaxFileCount) fail("invalid asset pack header");
    FileCount=header[3];
    assetIndex.resize(FileCount);dependencyOffsets.resize(FileCount+1);
    cached.resize(FileCount);retained.resize(FileCount);age.assign(FileCount,0);
    if(std::fread(assetIndex.data(),sizeof(Entry),FileCount,pack)!=FileCount) fail("truncated asset pack index");
    FILE* index=std::fopen("romfs:/reloc-deps.bin","rb");
    uint32_t meta[4];
    if(!index||std::fread(meta,1,16,index)!=16||std::memcmp(meta,"SSB3DIDX",8)||meta[2]!=FileCount||meta[3]>MaxDependencies)
        fail("invalid dependency index");
    dependencies.resize(meta[3]+1);
    if(std::fread(dependencyOffsets.data(),4,FileCount+1,index)!=FileCount+1||
       std::fread(dependencies.data(),2,meta[3],index)!=meta[3])fail("truncated dependency index");
    std::fclose(index);
    if(dependencyOffsets[0]!=0||dependencyOffsets[FileCount]!=meta[3])fail("dependency index endpoints");
    for(unsigned i=0;i<meta[3];i++)if(dependencies[i]>=FileCount)fail("dependency id outside pack");
    for(unsigned i=0;i<FileCount;i++)if(dependencyOffsets[i]>dependencyOffsets[i+1]||dependencyOffsets[i+1]>meta[3]||
        dependencyOffsets[i+1]-dependencyOffsets[i]!=assetIndex[i].deps)fail("dependency index mismatch");
    // Vanilla's small pack still remains resident. Remix's larger catalogue
    // must be streamed: reserving its entire ROM/pack would crowd out scene
    // memory on New 3DS. Both paths share the bounded pristine-file cache.
    if(std::fseek(pack,0,SEEK_END))fail("pack length seek failed");
    long length=std::ftell(pack);if(length<16||length>512*1024*1024)fail("invalid pack length");
    packBytes=(size_t)length;
    for(const auto& e:assetIndex)if(e.size>16*1024*1024||e.deps>65536||e.offset>packBytes||e.size>packBytes-e.offset||e.deps*2>packBytes-e.offset-e.size||
        ((e.size||e.deps)&&e.offset<16+FileCount*sizeof(Entry)))
        fail("pack entry outside payload");
    residentPack=packBytes<=ResidentBudget?(uint8_t*)std::malloc(packBytes):nullptr;
    if(residentPack){
        std::rewind(pack);
        if(std::fread(residentPack,1,packBytes,pack)!=packBytes)fail("truncated resident pack");
        native_asset_reads++;native_asset_bytes+=packBytes;
        std::fclose(pack);pack=nullptr;
    }
    packReady=true;
}
}
NativeRelocInfo nativeRelocInfo(uint32_t id){
    openPack();if(id>=FileCount)fail("metadata id outside pack");
    return {assetIndex[id].size,assetIndex[id].deps,dependencies.data()+dependencyOffsets[id]};
}
extern "C" void nativeAssetsShutdown(void) {
    for(auto& p:retained)p.reset();retainedBytes=0;
    if(pack){std::fclose(pack);pack=nullptr;}
    std::free(residentPack);residentPack=nullptr;packReady=false;
    cached.clear();retained.clear();age.clear();assetIndex.clear();dependencyOffsets.clear();dependencies.clear();
    FileCount=0;packBytes=0;cacheClock=0;
}
std::shared_ptr<RelocFile> nativeLoadReloc(uint32_t id) {
    openPack();
    if(id>=FileCount) fail("file id outside asset pack");
    age[id]=++cacheClock;
    if(auto p=cached[id].lock()){native_asset_hits++;return p;}
    const auto& e=assetIndex[id];
    if(e.size>16*1024*1024 || e.deps>65536) fail("invalid pack entry length");
    size_t bytes=e.size+e.deps*2;
    while(retainedBytes+bytes>CacheBudget&&retainedBytes){
        unsigned oldest=FileCount;
        for(unsigned i=0;i<FileCount;i++)if(retained[i]&&(oldest==FileCount||age[i]<age[oldest]))oldest=i;
        if(oldest==FileCount)break;
        retainedBytes-=assetIndex[oldest].size+assetIndex[oldest].deps*2;retained[oldest].reset();
    }
    auto p=std::make_shared<RelocFile>();
    p->FileId=id; p->RelocInternOffset=e.internal; p->RelocExternOffset=e.external;
    p->Data.resize(e.size);
    auto info=nativeRelocInfo(id);p->ExternFileIds.assign(info.deps,info.deps+info.count);
    if(residentPack)std::memcpy(p->Data.data(),residentPack+e.offset,e.size);
    else{
        if(std::fseek(pack,e.offset,SEEK_SET)||std::fread(p->Data.data(),1,e.size,pack)!=e.size)fail("truncated asset payload");
        native_asset_reads++;native_asset_bytes+=e.size;
    }
    cached[id]=p;
    if(bytes<=CacheBudget){retained[id]=p;retainedBytes+=bytes;}
    return p;
}
std::shared_ptr<std::vector<uint8_t>> nativeLoadBlob(const std::string& name) {
    if(name.find("..")!=std::string::npos) fail("invalid blob path");
    std::string path="romfs:/"+name+".bin";
    FILE* f=std::fopen(path.c_str(),"rb");
    if(!f) {port_log("Missing blob: %s\n",path.c_str()); fail("cannot open blob");}
    if(std::fseek(f,0,SEEK_END)) fail("blob seek failed");
    long size=std::ftell(f);
    if(size<0 || size>16*1024*1024) fail("invalid blob size");
    std::rewind(f);
    auto data=std::make_shared<std::vector<uint8_t>>(size);
    if(std::fread(data->data(),1,size,f)!=(size_t)size) fail("truncated blob");
    std::fclose(f);
    return data;
}
