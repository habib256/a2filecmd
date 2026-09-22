/* Best-effort extraction to another volume. Missing 512-byte chunks are
 * zero filled and listed in a companion log. Source is never written. */
#define UTIL_VOLUME
#define UTIL_CREATE
#define UTIL_DISCARD
#define UTIL_INFO
#include "util.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},"Recover file/disk data with retries and a log"};
#pragma rodata-name(pop)
static char source[PATH_LEN],path[PATH_LEN],logpath[PATH_LEN],base[9];
static FILE *in,*out,*logfile;
static unsigned char unit,disk,part;
static unsigned long size,offset;
static unsigned int bad,retried;
/* The resident has two ProDOS I/O buffers. Release the input before
 * opening the log; read_chunk reopens it at the saved offset. */
static unsigned char logline(const char* text) {
    unsigned int length;unsigned char ok;
    if(in){a.fclose(in);in=0;}
    logfile=a.fopen(logpath,"ab");if(!logfile)return 0;
    length=a.strlen(text);ok=a.fwrite(text,1,length,logfile)==length;
    if(a.fclose(logfile))ok=0;logfile=0;return ok;
}
/* The bar's label: 15 characters show, the escape key among them. */
static const char m_bar[]="Rescue (ESC)";
static unsigned char read_chunk(unsigned int n,unsigned int block) {
    unsigned char t,ok=n==0;
    for(t=0;t<30 && !ok;++t) {
        if(stop())return 0;
        /* A bad block is up to 30 slow retries: the same bar again only
         * turns the resident's activity cell, the bar itself stays. */
        if(t)a.progress_bar(m_bar,offset,size);
        if(!disk && !in)in=a.fopen(source,"rb");
        /* cc65's fread refuses a stream whose error flag is set and fseek
         * clears only EOF: without this, one failure fails all 29 retries. */
        if(in)clearerr(in);
        ok=disk?!readblk(unit,block,buf):(in!=0 && !a.fseek(in,offset,SEEK_SET)&&a.fread(buf,1,n,in)==n);
    }
    if(t>1)++retried;
    if(!ok)a.memset(buf,0,n);
    return ok;
}
/* The file's length as its directory entry says now, not as the panel
 * read it: a stale size would truncate or pad the recovery. */
static unsigned char fresh_size(void) {
    unsigned char i=a.strlen(source),found=0;
    while(i && source[i]!='/')--i;
    if(!i)return 0;
    source[i]=0;
    if(a.dir_open(source)) {
        while(a.dir_next())if(!a.strcmp(a.dir_entry->name,source+i+1)){size=a.dir_entry->size;found=1;break;}
        a.dir_close();
    }
    source[i]='/';return found;
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    unsigned char k,ok,dunit;unsigned int n,block;unsigned long left;
    init(api);in=out=logfile=0;bad=retried=0;offset=0;part=0;
    if(pan->fs || other->fs || !other->path[0]){note("Use a real ProDOS destination in the other panel.");return;}
    a.message("\1RESCUE: F Selected file  V Active volume  ESC Cancel");
    do{k=a.cgetc();if(k==KEY_ESC)return;}while(k!='f'&&k!='F'&&k!='v'&&k!='V');disk=k=='v'||k=='V';
    a.strcpy(source,disk?(pan->path[0]?pan->path:a.selected->name):a.full);
    if(source[0]!='/' || (!disk && (!pan->path[0] || a.selected->type==15))){note("Select a source file or volume.");return;}
    unit=unit_of(source,disk&&!pan->path[0]?(unsigned char)(a.selected->mdate<<4):0);
    dunit=unit_of(other->path,0);
    if(!unit || !dunit || unit==dunit){note("Destination must be on another online volume.");return;}
    if(disk) {if(readblk(unit,2,buf)||(buf[4]>>4)!=15){note("Cannot determine ProDOS volume size.");return;}size=(unsigned long)rd16(buf+41)*512;}
    else {if(getinfo(source)||info.storage>3){note("Extended/unsupported files cannot be rescued in file mode.");return;}
        if(!fresh_size()){note("Cannot read the file's directory entry.");return;}}
    if(!a.prompt("Recovery base name (up to 8 characters)","RESCUED",0))return;
    if(a.strlen(a.input)>8){note("Name too long.");return;}a.strcpy(base,a.input);
    a.sprintf(a.full,"%s.LOG",base);if(!join(logpath,other->path,a.full)){note("Path too long.");return;}
    a.clrscr();a.cprintf("RESCUE\r\nSOURCE: %s\r\nDESTINATION: %s\r\n",source,other->path);
    if(!a.confirm("Recover with 30 read attempts; log and zero-fill unreadable chunks?"))return;
    if(newfile(logpath,4,0,1)){note("Cannot create recovery log (existing name?).");return;}
    if(!logline(disk?"RESCUE raw disk: concatenate .P01, .P02... in order.\r":"RESCUE file: .REC contains recovered bytes.\r"))goto fail;
    do {
        if(!out) {
            ++part;a.sprintf(a.full,disk?"%s.P%02u":"%s.REC",base,part);
            if(!join(path,other->path,a.full) || newfile(path,disk?6:a.selected->type,disk?0:a.selected->aux,1))goto fail;
            out=a.fopen(path,"wb");if(!out){if(!discard(path)){logline("INCOMPLETE: an empty part could not be removed.\r");return;}goto fail;}
        }
        if(stop())goto fail;
        left=size-offset;n=left>512?512:(unsigned int)left;block=(unsigned int)(offset>>9);
        if(!(block&7))a.progress_bar(m_bar,offset,size);
        ok=read_chunk(n,block);if(cancelled)goto fail;
        if(!ok) {
            ++bad;a.sprintf(a.other_full,"ZERO block %u, offset %lu, bytes %u\r",block,offset,n);
            if(!logline(a.other_full))goto fail;
        }
        if(a.fwrite(buf,1,n,out)!=n)goto fail;offset+=n;
        if(disk && (offset%8192000UL)==0) {if(a.fclose(out)){out=0;goto fail;}out=0;}
    }while(offset<size);
    if(out){if(a.fclose(out)){out=0;goto fail;}out=0;}
    if(in){a.fclose(in);in=0;}
    a.sprintf(a.other_full,"COMPLETE %lu bytes, %u zero-filled chunks, %u retried.\r",size,bad,retried);
    if(!logline(a.other_full))goto fail;
    a.sprintf(a.note,"\1RESCUE: %lu bytes, %u missing chunks; see %s.LOG.",size,bad,base);return;
fail:
    if(in){a.fclose(in);in=0;}if(out){a.fclose(out);out=0;}
    logline("INCOMPLETE: cancelled/read-open/write error. Keep partial output.\r");
    a.sprintf(a.note,"RESCUE incomplete at %lu bytes (part %u); see log.",offset,part);
}
