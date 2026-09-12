/* Foreground PT3 playback, all storage in main RAM. No file writes/AUX.
 * The loader closes and validates the module before starting playback.
 * The assembler bounds every indirect module read during playback. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int signature;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[20];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUDIO, plugin_entry,{0,0,0},"ProTracker 3 music"};
#pragma rodata-name(pop)
#define LIMIT 4608
#ifdef PLUGIN_HOST
extern unsigned char host_song[LIMIT];
#define SONG host_song
#else
#define SONG ((unsigned char*)0x2E00)
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
static unsigned int n;
static unsigned int word(unsigned int p) {return SONG[p]|((unsigned int)SONG[p+1]<<8);}
static unsigned char valid(void) {
 unsigned int p,q,k;
 if(n<202 || (memcmp(SONG,"ProTracker 3.",13) && memcmp(SONG,"Vortex Tracker",14)) ||
    SONG[99]>3 || !SONG[100] || !SONG[101] || SONG[102]>=SONG[101] || 202+SONG[101]>n) return 0;
 if(SONG[13]>='0' && SONG[13]<'4' && SONG[99]!=1)return 0;
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
 FILE* f;
 unsigned char bad,paused,r,key;

 A=a;
 if(!A->arg) {scpy(A->note,"No Mockingboard.");return;}
 f=fopn(A->full,"rb");if(!f){scpy(A->note,"Cannot open PT3.");return;}
 n=frd(SONG,1,LIMIT,f);
 bad=ferror(f)!=0;
 if(frd(A->copy_buf,1,1,f) || ferror(f))bad=1;
 if(fcls(f))bad=1;
 if(bad || !valid()){scpy(A->note,"Bad/large PT3 or I/O.");return;}
 pt_end=0x2E00+n;
 pt_tables(A->copy_buf);
 r=pt_init();if(r){scpy(A->note,"Invalid PT3.");return;}
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
 if(r==1)scpy(A->note,"Invalid PT3.");
}
