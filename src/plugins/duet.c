/* duet.c -- Electric Duet foreground player: the speaker, or a Mockingboard.
 * Reads/closes the file before playback; writes only MAIN $2400-$3FFF, the
 * speaker and the card. No AUX, files or IRQ vectors.
 *
 * A song is a run of three-byte records: a duration (2..255) then the two
 * voices' pitches (0 = rest); a first byte of 1 sets the original player's
 * two duty-cycle shifts; 0 ends the song. The format is Paul Lutus's
 * Electric Duet; the speaker player is Alex Patalenski's (duet.s); the
 * Mockingboard rendition follows Cybernesto's electric-mock (GPL 3): one
 * AY tone per voice, timed by the VIA on the speaker player's own unit so
 * both outputs keep the same pitch and tempo. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int signature;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[48];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUDIO, plugin_entry,{0,0,0},"Play Electric Duet music; P pauses, ESC returns"};
#pragma rodata-name(pop)
#define LIMIT 7168
#ifdef PLUGIN_HOST
extern unsigned char host_song[LIMIT];
#define SONG host_song
#else
#define SONG ((unsigned char*)0x2400)
#endif
extern unsigned char* ed_pos;
void __fastcall__ ed_pulse(unsigned char);
unsigned char ed_speaker(void);
void __fastcall__ ay_start(unsigned char);
unsigned char ay_tick(void);
void __fastcall__ ay_write(unsigned int);
void ay_silence(void);
void ay_stop(void);
static const struct A2fcApi* A;
#include "hgr_io.h"
#ifndef PLUGIN_HOST
#pragma optimize (push, off)
#pragma warn (unused-param, push, off)
static void __fastcall__ text(const char* s) STUB(cputs)
static void __fastcall__ clear(unsigned int unused) STUB(clrscr)
static unsigned char __fastcall__ mkey(unsigned int key) STUB(media_key)
static char __fastcall__ getc_(unsigned int unused) STUB(cgetc)
#pragma warn (unused-param, pop)
#pragma optimize(pop)
#else
#define text A->cputs
#define clear(unused) A->clrscr()
#define mkey A->media_key
#define getc_(unused) A->cgetc()
#endif
static unsigned int n;
static unsigned char slot,mode,left,pulse;
static const char* const widths[]={"1/16","1/8 ","1/4 "};
static unsigned char* cur;       /* the record on the AY */
/* Every record complete, a terminator before EOF, at least one note.
 * A pointer, not SONG[p]: cc65 2.19 indexes a page-aligned constant
 * address through ptr1 without ever writing its low byte. */
static unsigned char valid(void) {
 const unsigned char* q=SONG;
 unsigned int left=n;
 unsigned char c,notes=0;
 while(left>=3) {
  c=*q;
  if(!c)return notes;
  if(c>1)notes=1;
  q+=3;left-=3;
 }
 return 0;
}
/* The two voices of cur onto the AY: 4.5625 AY clocks per speaker iteration. */
static void emit(void) {
 unsigned char v;
 unsigned int p;
 for(v=0;v<2;++v) {
  p=cur[1+v];
  ay_write(((8+v)<<8)|(p?15:0));
  p=(p<<2)+(p>>1)+(p>>4);
  ay_write((v<<9)|(p&255));
  ay_write(((v<<9)+0x100)|(p>>8));
 }
}
/* The next note record onto the AY; 0 at the terminator. */
static unsigned char next(void) {
 unsigned char c;
 for(;;) {
  c=ed_pos[0];
  if(!c)return 0;
  if(c>1)break;
  ed_pos+=3;            /* a voice record: no duty cycle on the AY */
 }
 left=c;cur=ed_pos;ed_pos+=3;emit();
 return 1;
}
static void mute(void) {if(mode)ay_silence();}
/* The speaker pulse width: 1/16 (Patalenski's), 1/8 or 1/4 of the period. */
static void set_pulse(void) {
 ed_pulse(pulse);text("\rSpeaker pulse ");text(widths[pulse]);   /* the cursor stays on its row */
}
void __fastcall__ plugin_entry(const struct A2fcApi* a) {
 FILE* f;
 unsigned char bad,key;

 A=a;
 f=fopn(A->full,"rb");if(!f){scpy(A->note,"Cannot open the song.");return;}
 n=frd(SONG,1,LIMIT,f);bad=ferror(f)!=0;
 if(frd(A->copy_buf,1,1,f)||ferror(f))bad=1;
 if(fcls(f))bad=1;
 if(bad || !valid()){scpy(A->note,"Bad/large Electric Duet or I/O.");return;}
 slot=A->arg;mode=slot!=0;ed_pos=SONG;left=0;
 clear(0);text("Electric Duet - ");text(A->selected->name);
 text("\r\n\r\nElectric Duet by Paul Lutus\r\nPlayers by Alexander Patalenski and Cybernesto\r\n\r\n1 Speaker  2 Mockingboard  D Pulse width  P Pause/resume  ESC Back  Left/Right Track\r\n\r\n");
 pulse=1;set_pulse();
 if(slot){ay_start(slot);ay_write(0x073C);}   /* mixer: tones A and B, no noise */
 for(;;){
  if(mode){
#ifndef PLUGIN_HOST
   key=*(volatile unsigned char*)0xC000;
   if(key&128)*(volatile unsigned char*)0xC010=0;else key=0;
#else
   key=getc_(0);
#endif
   if(!key){if(ay_tick()){if(left)--left;if(!left && !next())break;}continue;}
  } else {
   key=ed_speaker();if(!key)break;
#ifndef PLUGIN_HOST
   *(volatile unsigned char*)0xC010=0;
#endif
  }
  key&=127;
  if(key=='P'||key=='p'){mute();key=getc_(0)&127;}
  if(mkey(key))break;
  if(key=='D'||key=='d'){if(++pulse>2)pulse=0;set_pulse();}
  if(key=='1'){mute();mode=0;}
  else if(key=='2'&&slot){mode=1;left=0;}
  else if(mode&&left)emit();
 }
 if(slot)ay_stop();
 scpy(A->reselect,A->selected->name);
}
