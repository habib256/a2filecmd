/* MB1 foreground player. Reads/closes the file before playback; writes only
 * MAIN $3000-$3FFF and the Mockingboard. No AUX, files or IRQ vectors. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int signature;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[48];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUDIO, plugin_entry,{0,0,0},"Play MB1 music; P pauses, ESC returns"};
#pragma rodata-name(pop)
#define LIMIT 4096
#ifdef PLUGIN_HOST
extern unsigned char host_song[LIMIT];
#define SONG host_song
#else
#define SONG ((unsigned char*)0x3000)
#endif
void __fastcall__ mb_hw_start(unsigned char);
unsigned char mb_tick(void);
void mb_output(void);
void mb_silence(void);
void mb_hw_stop(void);
extern unsigned char mb_regs[28];
extern const unsigned int mb_notes[60];
static const struct A2fcApi* A;
#include "hgr_io.h"
static unsigned int n,pos;
static unsigned char delay,vol[6],amp[6],atten,fade,step;
/* Validate the complete packet stream, including every operand and EOF.
 * Loop metadata is ignored: the foreground player plays exactly once. */
static unsigned char valid(void) {
 unsigned int p=8;
 unsigned char c,v,k;
 if(n<9 || memcmp(SONG,"MB1",3))return 0;
 while(p<n) {
  c=SONG[p++];v=c&15;k=c&240;
  if(c<128){if(!c)return 0;continue;}
  if(c==0xE0)return p==n;
  if(c==0xF0)continue;
  if(v>5 || (k!=0x80 && k!=0x90 && k!=0xA0 && k!=0xB0))return 0;
  if(k==0x90)continue;
  if(p==n)return 0;
  c=SONG[p++];
  if((k==0x80 && c>=60)||(k==0xA0 && c>15)||(k==0xB0 && c>31))return 0;
 }
 return 0;
}
static void amplitudes(void) {
 unsigned char v;
 for(v=0;v<6;++v)mb_regs[(v<3?0:14)+8+v%3]=amp[v]>atten?amp[v]-atten:0;
}
static unsigned char frame(void) {
 unsigned char c,k,v,r,b,mask;
 unsigned int period;
 if(fade && !--step){step=3;if(fade==1){if(atten<15)++atten;else fade=0;}else {if(atten)--atten;else fade=0;}}
 if(--delay){amplitudes();return 0;}
 while(pos<n) {
  c=SONG[pos++];v=c&15;k=c&240;
  if(c<128){delay=c;amplitudes();return 0;}
  if(c==0xE0)return 1;
  if(c==0xF0){fade=1;step=1;continue;}
  b=v<3?0:14;r=v%3;mask=1<<r;
  if(k==0x90){amp[v]=0;continue;}
  c=SONG[pos++];
  if(k==0xA0){vol[v]=c;amp[v]=c;continue;}
  if(k==0x80){period=mb_notes[c];mb_regs[b+r*2]=period;mb_regs[b+r*2+1]=period>>8;mb_regs[b+7]=(mb_regs[b+7]&~mask)|(mask<<3);}
  else {mb_regs[b+6]=c;mb_regs[b+7]=(mb_regs[b+7]|mask)&~(mask<<3);}
  amp[v]=vol[v];
 }
 return 1;
}
void __fastcall__ plugin_entry(const struct A2fcApi* a) {
 FILE* f;
 unsigned char bad,key,paused;

 A=a;
 if(!A->arg){scpy(A->note,"No Mockingboard.");return;}
 f=fopn(A->full,"rb");if(!f){scpy(A->note,"Cannot open MB1.");return;}
 n=frd(SONG,1,LIMIT,f);bad=ferror(f)!=0;
 if(frd(A->copy_buf,1,1,f)||ferror(f))bad=1;
 if(fcls(f))bad=1;
 if(bad || !valid()){scpy(A->note,"Bad/large MB1 or I/O.");return;}
 memset(mb_regs,0,28);memset(vol,12,6);memset(amp,0,6);
 mb_regs[7]=mb_regs[21]=0x38;pos=8;delay=1;atten=15;fade=2;step=1;paused=0;
 A->clrscr();A->cputs("MB1 - ");A->cputs(A->selected->name);A->cputs("\r\n\r\nLeft/Right Track  P Pause/resume  ESC Back");
 mb_hw_start(A->arg);mb_output();
 for(;;){
#ifndef PLUGIN_HOST
  key=*(volatile unsigned char*)0xC000;
  if(key&128){*(volatile unsigned char*)0xC010=0;key&=127;
#else
  key=A->cgetc();if(key){
#endif
   if(A->media_key(key))break;
   if(key=='P'||key=='p'){paused=!paused;if(paused)mb_silence();else mb_output();}
  }
  if(mb_tick()&&!paused){if(frame())break;mb_output();}
 }
 mb_hw_stop();scpy(A->reselect,A->selected->name);
}
