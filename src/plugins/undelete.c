/* Recover deleted standard ProDOS files to ANOTHER volume. The source
 * directory/bitmap are never changed. Deleted storage types are inferred
 * conservatively from EOF and checked against the retained block count. */
#define UTIL_VOLUME
#define UTIL_INFO
#define UTIL_CREATE
#include "util.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},"Recover deleted ProDOS files to another volume"};
#pragma rodata-name(pop)
static unsigned char seen[512],bits[512],idx[512],master[512],e[39];
#define db buf
static char dir[PATH_LEN],dest[PATH_LEN],name[16];
static unsigned char unit,kind,invalid,writing,swapped;
static unsigned int total,bitmap,base,refs,key,need,logical;
static unsigned long size,written;
static FILE* out;
static void touch(unsigned int b) {
    unsigned int n;unsigned char mask;
    if(b<bitmap+(total-1)/4096+1 || b>=total){invalid=1;return;}
    ++refs;
    if(writing || b<base || b-base>=4096)return;
    n=b-base;mask=0x80>>(n&7);n>>=3;
    if(!(bits[n]&mask)||(seen[n]&mask))invalid=1;seen[n]|=mask;
}
static void data(unsigned int b) {
    unsigned int n;
    if(logical>=need){if(b)invalid=1;return;}
    ++logical;if(b)touch(b);
    if(!writing || invalid)return;
    n=size-written>512?512:(unsigned int)(size-written);
    if(b){if(readblk(unit,b,buf)){invalid=1;return;}}
    else a.memset(buf,0,512);
    if(a.fwrite(buf,1,n,out)!=n)invalid=1;written+=n;
}
/* DESTROY swaps index halves: https://prodos8.com/docs/technote/23/
 * Normalize in RAM; never rewrite a freed source index. */
static void unflip(unsigned char* p) {
    unsigned int i;unsigned char t;
    if(swapped)for(i=0;i<256;++i){t=p[i];p[i]=p[i+256];p[i+256]=t;}
}
static void indexblock(unsigned int b) {
    unsigned int i;
    if(b){touch(b);if(invalid||readblk(unit,b,idx)){invalid=1;return;}}
    else a.memset(idx,0,512);
    unflip(idx);
    for(i=0;i<256 && !invalid;++i)data(idx[i]|((unsigned int)idx[i+256]<<8));
}
static void walk(void) {
    unsigned int i,b;
    refs=logical=0;written=0;
    if(kind==1){if(!key && size){invalid=1;return;}data(key);if(!size && key)touch(key);}
    else if(!key)invalid=1;
    else if(kind==2)indexblock(key);
    else {
        touch(key);if(invalid||readblk(unit,key,master)){invalid=1;return;}
        unflip(master);
        for(i=0;i<256 && !invalid;++i) {
            b=master[i]|((unsigned int)master[i+256]<<8);
            if(logical>=need){if(b)invalid=1;continue;}
            indexblock(b);if(stop())invalid=1;
        }
    }
    if(refs!=rd16(e+19))invalid=1;
}
static unsigned char validate_layout(void) {
    size=rd24(e+21);need=(unsigned int)((size+511)>>9);key=rd16(e+17);
    kind=size<=512?1:(size<=131072UL?2:3);invalid=writing=0;base=0;
    if(e[16]==15 || !key || !rd16(e+19))return 0;
    do {
        if(stop()||readblk(unit,bitmap+base/4096,bits))return 0;
        a.memset(seen,0,512);walk();if(invalid)return 0;
        if(total-base<=4096)break;base+=4096;
    }while(1);
    return 1;
}
static unsigned char valid(void) {
    unsigned char normal,reversed;
    swapped=0;normal=validate_layout();
    if(kind==1)return normal;
    swapped=1;reversed=validate_layout();
    if(normal==reversed)return 0; /* no interpretation, or ambiguous */
    swapped=reversed;return 1;
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    FILE* f;unsigned int blocks,b;unsigned char slot,n,k,eligible,dunit;
    init(api);out=0;
    if(pan->fs || other->fs || !other->path[0]){note("Open a recovery directory on another ProDOS volume.");return;}
    a.strcpy(dir,pan->path[0]?pan->path:a.selected->name);
    if(dir[0]!='/' || getinfo(dir) || (info.storage!=13 && info.storage!=15)){note("Select a ProDOS source directory.");return;}
    blocks=info.blocks;unit=unit_of(dir,pan->path[0]?0:(unsigned char)(a.selected->mdate<<4));dunit=unit_of(other->path,0);
    if(!unit||!dunit||unit==dunit){note("UNDELETE destination must be on another online volume.");return;}
    if(readblk(unit,2,buf)||(buf[4]>>4)!=15){note("Cannot read volume header.");return;}
    total=rd16(buf+41);bitmap=rd16(buf+39);
    if(total<7 || bitmap<3 || bitmap>=total || (total-1)/4096+1>total-bitmap){note("Invalid volume bitmap.");return;}
    for(b=0;b<blocks && !stop();++b) {
        for(slot=b?0:1;slot<13 && !stop();++slot) {
        f=a.fopen(dir,"rb");if(!f){note("Cannot read source directory.");return;}
        if(a.fseek(f,(unsigned long)b*512,SEEK_SET)||a.fread(db,1,512,f)!=512){a.fclose(f);note("Directory read failed.");return;}a.fclose(f);
            a.memcpy(e,db+4+39*slot,39);
            if(e[0]>>4 || e[1]<'A' || e[1]>'Z')continue;
            n=e[0]&15;
            if(!n)for(n=0;n<15 && ((e[n+1]>='A'&&e[n+1]<='Z') || (e[n+1]>='0'&&e[n+1]<='9') || e[n+1]=='.');++n);
            if(!n)continue;a.memcpy(name,e+1,n);name[n]=0;
            eligible=valid();if(cancelled)break;
            a.clrscr();a.cprintf("UNDELETE - SOURCE READ ONLY\r\n%s/%s\r\n%lu bytes, %u retained blocks\r\n",dir,name,rd24(e+21),rd16(e+19));
            a.cputs(eligible?"Candidate: all referenced blocks are free.\r\n":"REFUSED: reused, ambiguous or inconsistent blocks.\r\n");
            a.cprintf("Recover into: %s\r\n",other->path);
            a.cputs("N Next  R Recover candidate  ESC Back");
            do{k=a.cgetc();}while(k!='n'&&k!='N'&&k!='r'&&k!='R'&&k!=KEY_ESC);
            if(k==KEY_ESC){note("UNDELETE finished; source unchanged.");return;}
            if((k=='r'||k=='R') && eligible) {
                if(!a.confirm("Recover this candidate to the other volume?"))continue;
                if(!valid()){a.message("Candidate is no longer recoverable.");continue;}
                if(!join(dest,other->path,name)||newfile(dest,e[16],rd16(e+31),1)){a.message("Cannot create destination (existing name?).");continue;}
                out=a.fopen(dest,"wb");if(!out){a.remove(dest);a.message("Cannot open recovery file.");continue;}
                invalid=0;writing=1;walk();writing=0;
                if(a.fclose(out))invalid=1;out=0;
                if(invalid){a.remove(dest);a.message("Recovery failed; incomplete destination removed.");}
                else {a.sprintf(a.note,"Recovered %s to other volume; source unchanged.",name);return;}
            }
        }
    }
    note(cancelled?"UNDELETE cancelled; source unchanged.":"No more deleted entries; source unchanged.");
}
