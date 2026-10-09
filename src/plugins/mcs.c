/* mcs.c -- Music Construction Set exported two-staff songs, Mockingboard.
 * Read/close/validate BEFORE card writes. Only MAIN $3000-$38FF, overlay
 * BSS and the two AY/VIA chips are written: no AUX, files or IRQ vectors.
 * The editor's .OBJ notation lists are NOT this format. See MCS-FORMAT.md.
 * Sequencer and note periods follow Will Harvey's published MUSIC SOURCE
 * and Cybernesto's MIT mcs-player, Copyright (c) 2017 cybernesto
 * (data/licenses/NOTICE.TXT). Modified for A2FC: validation, C foreground
 * sequencer, controls and safe I/O. One play-through. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[57];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUDIO,
 plugin_entry,{0,0,0},"Play Music Construction Set exports on Mockingboard"};
#pragma rodata-name(pop)
#define STAFF_SIZE 1152
#define LIMIT (2*STAFF_SIZE)
#ifdef PLUGIN_HOST
extern unsigned char host_song[LIMIT];
#define SONG_BUFFER host_song
#else
#define SONG_BUFFER ((unsigned char*)0x3000)
#endif
/* A runtime pointer avoids cc65's page-aligned constant-pointer shortcut
 * that can leave ptr1's low byte stale in valid(). */
static unsigned char* SONG;
void __fastcall__ mc_hw_start(unsigned char);
unsigned char mc_tick(void);
void mc_output(void);
void mc_silence(void);
void mc_hw_stop(void);
extern unsigned char mc_regs[28];
static const struct A2fcApi* A;
#include "hgr_io.h"
static unsigned int pos[2],end[2];
static unsigned char voice[6],count[2],tied[2];
static unsigned char tempo,tc,dc;
static unsigned int freq;
/* Exact periods from MUSIC SOURCE, with its two ultrasonic rest entries. */
static const unsigned int notes[64]={
 0x1D,0x1E,0x20,0x22,0x24,0x26,0x29,0x2B,
 0x2E,0x30,0x33,0x36,0x3A,0x3D,0x41,0x44,
 0x48,0x4D,0x51,0x56,0x5B,0x61,0x67,0x6D,
 0x73,0x7A,0x81,0x89,0x91,0x9A,0xA3,0xAC,
 0xB7,0xC1,0xCD,0xD9,0xE6,0xF4,0x102,0x112,
 0x122,0x133,0x145,0x159,0x16D,0x183,0x19A,0x1B2,
 0x1CC,0x1E8,0x205,0x223,0x244,0x266,0x28B,0x2B2,
 0x2DB,0x306,0x334,0x365,0x398,0x3CF,1,1};
/* Fixed-size exported buffer, with a complete terminator in each staff.
 * Ignore unused buffer contents AFTER that terminator (real exports retain
 * old notes there). No unterminated chord, zero duration or table overrun. */
static unsigned char valid(void) {
 unsigned char s,d,chain,seen;
 unsigned int p,base;
 for(s=0;s<2;++s){
  base=s?STAFF_SIZE:0;chain=seen=0;
  for(p=base;p<base+STAFF_SIZE;p+=2){
   d=SONG[p+1];
   if(!(SONG[p]>>1)&&!d){if(chain||!seen)return 0;break;}
   if(SONG[p]>=128 || !(d&63))return 0;
   chain=d&128;seen=1;
  }
  if(p==base+STAFF_SIZE)return 0;
  end[s]=p;
 }
 return 1;
}
static void plug(unsigned char v,unsigned char amp){
 unsigned char b,r;
 b=v<3?0:14;r=v%3;
 mc_regs[b+r*2]=freq;mc_regs[b+r*2+1]=freq>>8;
 mc_regs[b+8+r]=amp;
}
static void stop_staff(unsigned char s){
 unsigned char v;
 for(v=0;v<6;++v)if(voice[v]==s){voice[v]=255;plug(v,0);}
}
static unsigned char search(unsigned char s){
 unsigned char v;
 if(!s){for(v=0;v<5 && voice[v]!=255;++v);}
 else {for(v=5;v && voice[v]!=255;--v);}
 return v;
}
static void reset(void){
 memset(mc_regs,0,28);memset(voice,255,6);memset(tied,0,2);
 mc_regs[0]=mc_regs[2]=mc_regs[4]=1;
 mc_regs[14]=mc_regs[16]=mc_regs[18]=1;
 mc_regs[7]=mc_regs[21]=0xF8;
 pos[0]=0;pos[1]=STAFF_SIZE;count[0]=count[1]=1;
 tc=dc=0;freq=1;
}
/* One original VIA tick ($40FF latch, default four ticks per music unit).
 * Return 1 when the original would restart both staffs: play once here. */
static unsigned char frame(void){
 unsigned char s,v,b,d;
 if(++dc==3){
  dc=0;
  for(v=0;v<6;++v)if(voice[v]<2 && !tied[voice[v]]){
   b=(v<3?0:14)+8+v%3;
   if(mc_regs[b]!=8)--mc_regs[b];
  }
 }
 if(++tc!=tempo)return 0;
 tc=0;
 for(s=0;s<2;++s){
  if(--count[s])continue;
  stop_staff(s);
  do {
   if(pos[s]>=end[s])return 1;
   v=search(s);voice[v]=s;
   freq=notes[SONG[pos[s]]>>1];d=SONG[pos[s]+1];pos[s]+=2;
   plug(v,10);tied[s]=d&64;count[s]=d&63;
  }while(d&128);
 }
 return 0;
}
void __fastcall__ plugin_entry(const struct A2fcApi* a){
 FILE* f;
 unsigned int n;
 unsigned char bad,key,paused;
 A=a;SONG=SONG_BUFFER;
 if(!A->arg || A->arg>7 || A->arg==3){scpy(A->note,"No Mockingboard.");return;}
 if(!A->full[0] || !A->selected->name[0] || A->selected->type==15){
  scpy(A->note,"Select an exported MCS song.");return;}
 f=fopn(A->full,"rb");if(!f){scpy(A->note,"Cannot open MCS song.");return;}
 n=frd(SONG,1,LIMIT,f);bad=ferror(f)!=0;
 if(frd(A->copy_buf,1,1,f)||ferror(f))bad=1;
 if(fcls(f))bad=1;
 if(bad || n!=LIMIT || !valid()){
  scpy(A->note,"Bad MCS export/I/O (editor .OBJ not supported).");return;}
 reset();tempo=4;paused=0;
 A->clrscr();A->cputs("Music Construction Set - ");A->cputs(A->selected->name);
 A->cputs("\r\n\r\nMockingboard / exported two-staff song\r\nP/Space Pause/resume  R Restart  +/- Tempo  ESC Back\r\n");
 mc_hw_start(A->arg);mc_output();
 for(;;){
#ifndef PLUGIN_HOST
  key=*(volatile unsigned char*)0xC000;
  if(key&128){*(volatile unsigned char*)0xC010=0;key&=127;
#else
  key=A->cgetc();if(key){
#endif
   if(key==KEY_ESC)break;
   if(key=='P'||key=='p'||key==' '){paused=!paused;if(paused)mc_silence();else mc_output();}
   if(key=='R'||key=='r'){reset();if(!paused)mc_output();}
   if(key=='+' && tempo>1){--tempo;tc=0;}
   if(key=='-' && tempo<32){++tempo;tc=0;}
  }
  if(mc_tick() && !paused){if(frame())break;mc_output();}
 }
 mc_hw_stop();scpy(A->reselect,A->selected->name);
}
