/* Foreground PT3 playback, all storage in main RAM. No file writes/AUX.
 * Keep each live header and 5-8 cached pages; decoder pointers are bounded
 * offsets within their own subfile. Read the complete source once before playback to establish its
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
#define CACHE_COUNT 8
#define HEADER_PAGE 0x37
#define CACHE_PAGE 0x3B
#ifdef PLUGIN_HOST
extern unsigned char host_song[HEADER_SIZE], host_cache[CACHE_COUNT][256];
#define SONG host_song
extern unsigned char host_second[512],host_tables2[448];
#define SECOND host_second
#define TABLES2 host_tables2
#define CACHE(slot) host_cache[slot]
#else
#define SONG ((unsigned char*)0x3700)
#define SECOND ((unsigned char*)0x3900)
#define TABLES2 ((unsigned char*)0x3E00)
#define CACHE(slot) ((unsigned char*)((unsigned int)pt_cache_pages[slot]<<8))
#endif
void __fastcall__ pt_tables(unsigned char*);
unsigned char pt_init(void);
unsigned char pt_frame(void);
extern unsigned int pt_end, pt_base;
extern unsigned char pt_chip, pt_dual, pt_running, pt_regs[14], pt_cache_pages[8];
void pt_swap(void);
void __fastcall__ pt_play_tables(unsigned char*);
void __fastcall__ pt_hw_start(unsigned char slot);
unsigned char pt_tick(void);
void pt_output(void);
void pt_silence(void);
void pt_mute(void);
void pt_hw_stop(void);
static const struct A2fcApi* A;
#include "hgr_io.h"
unsigned char pt_pages[256];
static unsigned char pages[CACHE_COUNT], next_page, io_bad;
static FILE* source;
static unsigned int n, file_length, second_base;
#define cache_limit pt_running
static unsigned char current, ended[2];
static unsigned char* header;
static unsigned char read_at(void* out, unsigned int offset, unsigned int count) {
 if(A->fseek(source,(long)offset,SEEK_SET) || frd(out,1,count,source)!=count || ferror(source)) {io_bad=1;return 0;}
 return 1;
}
static void select_song(void) {
 pt_swap();current^=1;
 pt_chip^=128;
 pt_base=current?second_base:0;
 pt_end=current?n:second_base;
 pt_play_tables(current?TABLES2:A->copy_buf);
}
/* Called only for a cache miss, with the caller's zero page restored by
 * the assembler. Do not publish a mapping until an exact read succeeds. */
unsigned char __fastcall__ pt_page(unsigned char page) {
 unsigned int offset, count;
 unsigned char slot;
 offset=(unsigned int)page<<8;
 if(offset>=file_length)return 0;
 slot=next_page;
 if(pt_pages[pages[slot]]==pt_cache_pages[slot])pt_pages[pages[slot]]=0;
 count=file_length-offset;if(count>256)count=256;
 if(!read_at(CACHE(slot),offset,count))return 0;
 pages[slot]=page;
 pt_pages[page]=pt_cache_pages[slot];
 if(++next_page==cache_limit)next_page=0;
 return pt_pages[page];
}
static unsigned int word(unsigned int p) {return header[p]|((unsigned int)header[p+1]<<8);}
static unsigned char valid(void) {
 unsigned int p,q,k;
 if(n<202 || (memcmp(header,"ProTracker 3.",13) && memcmp(header,"Vortex Tracker",14)) ||
    header[99]>3 || !header[100] || !header[101] || header[102]>=header[101] || 202+header[101]>n) return 0;
 p=word(103);
 for(k=0;k<header[101];++k) {
  q=header[201+k];
  if(q==255 || q%3 || p>=n || q*2+6>n-p)return 0;
 }
 if(header[201+k]!=255)return 0;
 /* Sample/ornament and pattern reads are bounded at each access by
  * the decoder, including changing positions and malformed effect commands. */
 return word(107)!=0 && word(169)!=0;
}
void __fastcall__ plugin_entry(const struct A2fcApi* a) {
 unsigned int count;
 unsigned char bad,paused,r,key;

 A=a;header=SONG;current=pt_chip=pt_dual=0;pt_base=0;ended[0]=ended[1]=0;
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
 file_length=second_base=n;
 /* A standard TurboSound footer gives exact, disjoint PT3 subfile lengths. */
 if(!read_at(CACHE(0),n-16,16))goto done;
 if(!memcmp(CACHE(0)+12,"02TS",4)) {
  header=CACHE(0);
  second_base=word(4);
  if(memcmp(header,"PT3!",4) || memcmp(header+6,"PT3!",4) ||
     second_base<202 || second_base>file_length-16 ||
     word(10)!=file_length-16-second_base) {r=1;goto done;}
  n=second_base;header=SONG;if(!valid()){r=1;goto done;}
  n=file_length-16-second_base;
  if(!read_at(SECOND,second_base,n<512?n:512))goto done;
  header=SECOND;if(!valid()){r=1;goto done;}
  pt_dual=1;
 }
 memset(pt_pages,0,sizeof pt_pages);
 pt_pages[0]=HEADER_PAGE;pt_pages[1]=HEADER_PAGE+1;
 cache_limit=3;next_page=0;
 pt_end=second_base;
 pt_tables(A->copy_buf);
 r=pt_init();if(r)goto done;
 if(pt_dual) {
  select_song();pt_tables(TABLES2);
  r=pt_init();if(r)goto done;
  select_song();
 }
 cache_limit=5;next_page=3;
 if(SONG[101]<55) {pt_pages[1]=0;pt_cache_pages[cache_limit++]=0x38;}
 if(!pt_dual)pt_cache_pages[cache_limit++]=0x39;
 if(!pt_dual || SECOND[101]<55)pt_cache_pages[cache_limit++]=0x3A;
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
  if(pt_tick() && !paused) {
   key=pt_dual;
   do {
    r=pt_frame();if(r==1)goto stop;
    if(r==2) {ended[current]=1;pt_mute();}
    else pt_output();
    /* Once one module ends, keep the remaining context live: no swaps. */
    if(!pt_dual || ended[current^1])break;
    /* Alternate the processing order: one context swap per tick. */
    if(key || r==2)select_song();
   } while(key--);
   if(ended[0] && (!pt_dual || ended[1]))break;
  }
 }
stop:
 pt_hw_stop();
 scpy(A->reselect,A->selected->name);
done:
 if(fcls(source))io_bad=1;
 if(r==1)scpy(A->note,"Invalid PT3.");
 if(io_bad)scpy(A->note,"PT3 read/seek/close error.");
}
