/* Foreground PT3 playback, all storage in main RAM. No file writes/AUX.
 * Keep the header and eleven cached pages; all decoder pointers are file
 * offsets. Read the complete source once before playback to establish its
 * actual length, then keep the read-only handle until stop/EOF/error. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int signature;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[20];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUDIO, plugin_entry,{0,0,0},"ProTracker 3 music"};
#pragma rodata-name(pop)
#define LIMIT 65535U
#define HEADER_SIZE 512
#define CACHE_COUNT 11
#define HEADER_PAGE 0x33
#define CACHE_PAGE 0x35
#ifdef PLUGIN_HOST
extern unsigned char host_song[HEADER_SIZE], host_cache[CACHE_COUNT][256];
#define SONG host_song
#define CACHE(slot) host_cache[slot]
#else
#define SONG ((unsigned char*)0x3300)
#define CACHE(slot) ((unsigned char*)((unsigned int)(CACHE_PAGE+(slot))<<8))
#endif
void __fastcall__ pt_tables(unsigned char*);
unsigned char pt_init(void);
unsigned char pt_frame(void);
extern unsigned int pt_end;
void __fastcall__ pt_hw_start(unsigned char slot);
unsigned char pt_tick(void);
void pt_output(void);
void pt_silence(void);
void pt_hw_stop(void);
static const struct A2fcApi* A;
#include "hgr_io.h"
unsigned char pt_pages[256];
static unsigned char pages[CACHE_COUNT], next_page, used_pages, io_bad;
static FILE* source;
static unsigned int n;
/* Called only for a cache miss, with the caller's zero page restored by
 * the assembler. Do not publish a mapping until an exact read succeeds. */
unsigned char __fastcall__ pt_page(unsigned char page) {
 unsigned int offset, count;
 unsigned char slot;
 offset=(unsigned int)page<<8;
 if(offset>=n)return 0;
 slot=next_page;
 if(used_pages==CACHE_COUNT)pt_pages[pages[slot]]=0;
 else ++used_pages;
 count=n-offset;if(count>256)count=256;
 if(A->fseek(source,(long)offset,SEEK_SET) ||
    frd(CACHE(slot),1,count,source)!=count || ferror(source)) {io_bad=1;return 0;}
 pages[slot]=page;
 pt_pages[page]=CACHE_PAGE+slot;
 if(++next_page==CACHE_COUNT)next_page=0;
 return pt_pages[page];
}
static unsigned int word(unsigned int p) {return SONG[p]|((unsigned int)SONG[p+1]<<8);}
static unsigned char valid(void) {
 unsigned int p,q,k;
 if(n<202 || (memcmp(SONG,"ProTracker 3.",13) && memcmp(SONG,"Vortex Tracker",14)) ||
    SONG[99]>3 || !SONG[100] || !SONG[101] || SONG[102]>=SONG[101] || 202+SONG[101]>n) return 0;
 p=word(103);
 for(k=0;k<SONG[101];++k) {
  q=SONG[201+k];
  if(q==255 || q%3 || p>=n || q*2+6>n-p)return 0;
 }
 if(SONG[201+k]!=255)return 0;
 /* Sample/ornament and pattern reads are bounded at each access by
  * the decoder, including changing positions and malformed effect commands. */
 return word(107)!=0 && word(169)!=0;
}
void __fastcall__ plugin_entry(const struct A2fcApi* a) {
 unsigned int count;
 unsigned char bad,paused,r,key;

 A=a;
 if(!A->arg) {scpy(A->note,"No Mockingboard.");return;}
 source=fopn(A->full,"rb");if(!source){scpy(A->note,"Cannot open PT3.");return;}
 n=0;io_bad=r=0;
 do {
#ifndef PLUGIN_HOST
  if(*(volatile unsigned char*)0xC000==0x9B) {
   *(volatile unsigned char*)0xC010=0;goto done;
  }
#else
  if(A->cgetc()==27)goto done;
#endif
  count=n<HEADER_SIZE?HEADER_SIZE-n:HEADER_SIZE;
  count=frd(n<HEADER_SIZE?SONG+n:CACHE(0),1,count,source);
  bad=ferror(source)!=0 || count>LIMIT-n;
  if(!bad)n+=count;
 } while(!bad && count);
 /* cc65 sets EOF only on a zero-byte read, not on the final short read. */
 if(!feof(source))bad=1;
 if(bad || !valid()) {
  fcls(source);scpy(A->note,"Bad/large PT3 or I/O.");return;
 }
 memset(pt_pages,0,sizeof pt_pages);
 pt_pages[0]=HEADER_PAGE;pt_pages[1]=HEADER_PAGE+1;
 used_pages=next_page=0;
 pt_end=n;
 pt_tables(A->copy_buf);
 r=pt_init();if(r)goto done;
 A->music_info(SONG);
 pt_hw_start(A->arg);paused=0;
 for(;;) {
#ifndef PLUGIN_HOST
  key=*(volatile unsigned char*)0xC000;
  if(key&128) {
   *(volatile unsigned char*)0xC010=0;key&=127;
#else
  key=A->cgetc(); if(key) {
#endif
   if(A->media_key(key))break;
   if(key=='P' || key=='p'){paused=!paused;if(paused)pt_silence();}
  }
  if(pt_tick() && !paused) {r=pt_frame();if(r)break;pt_output();}
 }
 pt_hw_stop();
 scpy(A->reselect,A->selected->name);
done:
 if(fcls(source))io_bad=1;
 if(r==1)scpy(A->note,"Invalid PT3.");
 if(io_bad)scpy(A->note,"PT3 read/seek/close error.");
}
