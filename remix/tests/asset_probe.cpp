/* Diagnostic only: reads raw asset payloads on ARM11. No game or relocation
 * callbacks run, so this does not establish Remix gameplay compatibility. */
#include <3ds.h>
#include <cstdio>
#include <cstdarg>
#include "native_assets.h"

extern "C" {
uint32_t native_asset_reads,native_asset_hits,native_asset_bytes;
volatile uint32_t remix_probe_status,remix_probe_files,remix_probe_expected;
volatile uint32_t remix_probe_failure_id=~0u,remix_probe_ms;
void nativeAssetsShutdown(void);
void port_log(const char* format,...){
    va_list args;va_start(args,format);vprintf(format,args);va_end(args);
}
void __wrap_abort(void){
    remix_probe_status=0xdead0001;
    while(aptMainLoop()){gspWaitForVBlank();}
    __builtin_trap();
}
}

static unsigned checksum(const std::vector<uint8_t>& data){
    static unsigned table[256];static bool ready;
    if(!ready){
        for(unsigned i=0;i<256;i++){
            unsigned c=i;for(int j=0;j<8;j++)c=(c>>1)^(0xedb88320u&-(c&1));
            table[i]=c;
        }
        ready=true;
    }
    unsigned c=~0u;
    for(auto b:data)c=(c>>8)^table[(c^b)&255];
    return ~c;
}

int main(){
    gfxInitDefault();consoleInit(GFX_BOTTOM,nullptr);
    printf("Remix +EXTRA asset diagnostic\nRaw file I/O only; no gameplay.\n");
    if(R_FAILED(romfsInit())){remix_probe_status=0xdead0002;return 1;}
    FILE* checks=fopen("romfs:/checks.bin","rb");
    uint32_t header[2];
    if(!checks||fread(header,4,2,checks)!=2||header[0]!=0x31584252){remix_probe_status=0xdead0003;return 1;}
    remix_probe_status=1;remix_probe_expected=header[1];
    uint64_t started=svcGetSystemTick();
    for(unsigned i=0;i<header[1];i++){
        uint32_t row[4];
        if(fread(row,4,4,checks)!=4){remix_probe_status=0xdead0004;break;}
        remix_probe_failure_id=row[0];
        auto info=nativeRelocInfo(row[0]);
        auto file=nativeLoadReloc(row[0]);
        if(info.size!=row[1]||info.count!=row[2]||file->Data.size()!=row[1]||checksum(file->Data)!=row[3]){
            remix_probe_status=0xdead0005;break;
        }
        remix_probe_files++;
        if((i&127)==0){
            printf("\x1b[4;1HRead %lu/%lu files",(unsigned long)remix_probe_files,(unsigned long)remix_probe_expected);
            gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
        }
    }
    fclose(checks);nativeAssetsShutdown();
    remix_probe_ms=(svcGetSystemTick()-started)*1000/SYSCLOCK_ARM11;
    if(remix_probe_status==1){remix_probe_status=2;remix_probe_failure_id=~0u;}
    printf("\nStatus: %08lx\nFiles: %lu\nTime: %lu ms\n",
        (unsigned long)remix_probe_status,(unsigned long)remix_probe_files,(unsigned long)remix_probe_ms);
    while(aptMainLoop()){
        hidScanInput();if(hidKeysDown()&KEY_START)break;
        gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
    }
    romfsExit();gfxExit();return 0;
}
