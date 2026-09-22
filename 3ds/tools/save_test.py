"""Exercise first save, rotation and failed-rename recovery in the actual writer."""
import json
import subprocess
from build import ROOT, OUT, BIN


def main():
    dst = OUT / 'save-host-test'
    dst.mkdir(exist_ok=True)
    source = (ROOT / 'src/platform_3ds.c').read_text()
    writer = source[source.index('static void writeSave('):source.index('int port_save_write(')]
    shim = '''#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include <assert.h>
static uint8_t saveBytes[32768];
static uint32_t native_perf_error;
static int failCommit;
static int checkedRename(const char* a,const char* b){
    struct stat st;
    /* Some FS implementations do not map missing rename sources to ENOENT. */
    if(stat(a,&st)){errno=EIO;return -1;}
    if(failCommit&&strstr(a,"save.tmp")){failCommit=0;errno=EIO;return -1;}
    return rename(a,b);
}
#define rename checkedRename
'''
    shim += '#define NATIVE_SD_DIRECTORY "' + dst.as_posix() + '"\n'
    cases = '''
static void check(const char* file,int value){
    FILE* f=fopen(file,"rb");assert(f);
    for(int i=0;i<32768;i++)assert(fgetc(f)==value);
    assert(fgetc(f)==EOF);fclose(f);
}
int main(void){
    remove(NATIVE_SD_DIRECTORY "/save.bin");remove(NATIVE_SD_DIRECTORY "/save.bak");
    memset(saveBytes,1,sizeof(saveBytes));writeSave(saveBytes);assert(!native_perf_error);
    check(NATIVE_SD_DIRECTORY "/save.bin",1);
    memset(saveBytes,2,sizeof(saveBytes));writeSave(saveBytes);assert(!native_perf_error);
    check(NATIVE_SD_DIRECTORY "/save.bin",2);check(NATIVE_SD_DIRECTORY "/save.bak",1);
    failCommit=1;memset(saveBytes,3,sizeof(saveBytes));writeSave(saveBytes);
    assert(native_perf_error==1);check(NATIVE_SD_DIRECTORY "/save.bin",2);
    writeSave(saveBytes);assert(native_perf_error==1);check(NATIVE_SD_DIRECTORY "/save.bin",3);
    check(NATIVE_SD_DIRECTORY "/save.bak",2);
    puts("First save, backup rotation, failed commit rollback and retry passed");
}
'''
    c = dst / 'test.c'
    c.write_text(shim + writer + cases)
    exe = dst / 'test.exe'
    subprocess.run([str(BIN / 'clang.exe'), '-std=gnu11', '-O2', str(c), '-o', str(exe)], check=True)
    run = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
    report = {'passed': True, 'detail': run.stdout.strip()}
    (dst / 'verified.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report)


if __name__ == '__main__':
    main()
