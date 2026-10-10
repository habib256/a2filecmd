/* Streaming legacy-text reader shared by PASTEXT, SCASM and MERLIN.
 * Read-only: writes overlay BSS/copy_buf and text screen through services.
 * No disk, AUX, IRQ or raw graphics writes. A complete structural pass and
 * successful close precede display. Reopen/seek/read/close faults are distinct
 * from EOF. Panel sizes are never used as input bounds.
 * Format rules and LISA table adapted from CiderPress II,
 * Copyright 2023 faddenSoft (Apache-2.0; data/licenses/NOTICE.TXT).
 * Modified for A2FC: streaming C, two-pass validation and text paging. */
#include "../a2fc_plugin.h"
#ifdef RT_DOS
#include <string.h>
#endif
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct RtHeader {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
static struct A2fcApi rt_api;
static FILE* rt_file;
#ifdef RT_DOS
/* S-C sources saved as DOS Integer BASIC have a two-byte exact EOF.
 * Sources stay read-only; the two validation/display passes reopen them. */
static unsigned char rt_dos;
#define A (&rt_api)
#define DS_SECTORS 257
#define DS_NO_SEEK
#define DS_DATA_BUFFER rt_api.copy_buf
#define DS_MLI rt_api.mli
#define DS_SEEK rt_api.fseek
#define frd rt_api.fread
#define fopn rt_api.fopen
#define fcls rt_api.fclose
#include "dos_source.h"
#endif
static unsigned int rt_pos,rt_len;
static unsigned long rt_off;
static unsigned char rt_bad,rt_render,rt_cancel,rt_row,rt_col;
#if RT_FORMAT == 2 || RT_FORMAT == 4
static unsigned char rt_line[255];
#endif
static void rt_invalid(void){if(!rt_bad)rt_bad=2;}

static int rt_get(void){
#ifdef RT_DOS
 if(rt_dos){
  int c=ds_get();if(ds_bad)rt_bad=1;if(c>=0)++rt_off;return c;
 }
#endif
 if(rt_pos==rt_len){
  rt_pos=0;rt_len=rt_api.fread(rt_api.copy_buf,1,512,rt_file);
  if(ferror(rt_file)){rt_bad=1;return -1;}
  if(!rt_len)return -1;
 }
 ++rt_off;return rt_api.copy_buf[rt_pos++];
}
static unsigned char rt_page(void){
 unsigned char k;
 rt_api.message("Space/Down next page, ESC back");
 do{k=rt_api.wait_key();}while(k!=KEY_ESC && k!=' ' && k!=KEY_DOWN && k!=KEY_RETURN);
 if(k==KEY_ESC){rt_cancel=1;return 0;}
 rt_api.clrscr();rt_row=1;rt_col=0;return 1;
}
static void rt_put(unsigned char c){
 if(!rt_render || rt_cancel)return;
 if(rt_row==22 && !rt_page())return;
 if(c=='\r'||c=='\n'){
  ++rt_row;rt_col=0;return;
 }
 if(rt_col==79){++rt_row;rt_col=0;if(rt_row==22 && !rt_page())return;}
 rt_api.gotoxy(rt_col++,rt_row);rt_api.cputc(c>=32 && c<127?c:'?');
}
#if RT_FORMAT != 3 && RT_FORMAT != 5 && RT_FORMAT != 6
static void rt_spaces(unsigned char n){while(n-- && !rt_cancel)rt_put(' ');}
#endif

#if RT_FORMAT == 20
#include "multplan_decode.h"
#elif RT_FORMAT == 19
#include "bsfiler_decode.h"
#elif RT_FORMAT == 17 || RT_FORMAT == 18
#include "v1word_decode.h"
#elif RT_FORMAT == 16
#include "pfsplan_decode.h"
#elif RT_FORMAT == 15
#include "pfsfile_decode.h"
#elif RT_FORMAT == 14
#include "pfswrite_decode.h"
#elif RT_FORMAT == 13
#include "lisa4_decode.h"
#elif RT_FORMAT == 11 || RT_FORMAT == 12
#include "nexttext_decode.h"
#elif RT_FORMAT == 9 || RT_FORMAT == 10
#include "worddoc_decode.h"
#elif RT_FORMAT == 7 || RT_FORMAT == 8
#include "newsdoc_decode.h"
#elif RT_FORMAT == 1
/* Pascal: editor header followed by independent 1K chunks. NUL padding
 * consumes the remainder of a chunk; DLE+32+count only at a line start.
 * A final partial chunk is allowed, but a DLE count may not cross one. */
static void rt_decode(void){
 unsigned int i,at;
 unsigned char sol=1,padding=0;
 int c,n;
 for(i=0;i<1024;++i)if(rt_get()<0){rt_invalid();return;}
 while(!rt_cancel && (c=rt_get())>=0){
  at=(unsigned int)((rt_off-1)&1023);
  if(!at){if(!sol){rt_invalid();return;}sol=1;padding=0;}
  if(padding){if(c){rt_invalid();return;}continue;}
  if(!c){if(!sol){rt_invalid();return;}padding=1;continue;}
  if(c==16){
   if(!sol || at==1023 || (n=rt_get())<32){rt_invalid();return;}
   rt_spaces((unsigned char)(n-32));sol=0;
  }else if(c==13){rt_put(13);sol=1;}
  else {rt_put((unsigned char)c);sol=0;}
 }
 if(!sol && !rt_cancel)rt_invalid();
}
#elif RT_FORMAT == 2
/* S-C Assembler: byte length (including header and $00), LE line number,
 * literals, $80-$BF spaces, $C0 count character. Bounds before operands. */
static void rt_decode(void){
 int n,c,lo,hi;
 unsigned int i;
 unsigned char k,v,seen=0;
 char number[8];
 while(!rt_cancel && (n=rt_get())>=0){
  if(n<4){rt_invalid();return;}
  lo=rt_get();hi=rt_get();if(lo<0 || hi<0){rt_invalid();return;}
  for(i=0;i<(unsigned int)n-3;++i){c=rt_get();if(c<0){rt_invalid();return;}rt_line[i]=c;}
  n-=4;if(rt_line[n]){rt_invalid();return;}
  rt_api.sprintf(number,"%04u ",(unsigned int)lo|((unsigned int)hi<<8));
  for(i=0;number[i];++i)rt_put(number[i]);
  for(i=0;i<(unsigned int)n;++i){
   c=rt_line[i];
   if(c>=32 && c<128)rt_put(c);
   else if(c>=128 && c<192)rt_spaces(c-128);
   else if(c==192 && i+2<(unsigned int)n){
    k=rt_line[++i];v=rt_line[++i];
    if(v<32 || v>=127){rt_invalid();return;}
    while(k-- && !rt_cancel)rt_put(v);
   }else {rt_invalid();return;}
  }
  rt_put(13);
  seen=1;
 }
 if(!seen && !rt_cancel)rt_invalid();
}
#elif RT_FORMAT == 3
/* Merlin / DOS ED/ASM high-bit sources. Only high-bit spaces delimit
 * fields; spaces inside quotes/comments remain literal. No token guesses. */
static void rt_decode(void){
 int raw;
 unsigned char c,field=0,quote=0,start=1,previous=0,col=0,target;
 static const unsigned char stops[4]={0,9,15,26};
 while(!rt_cancel && (raw=rt_get())>=0){
  if(raw<128 && raw!=32){rt_invalid();return;}
  c=raw&127;
  /* Macro comparisons can contain a single quote (IF "=]1). Match
   * Merlin's listing: end-of-line resets quote state, without refusing. */
  if(c==13){rt_put(13);field=quote=col=previous=0;start=1;continue;}
  if(c<32 || c==127){rt_invalid();return;}
  if(start && c=='*')field=3;
  if(field<3 && !quote && raw==0xBB && (start||previous==0xA0)){
   field=3;target=stops[3];
   do{rt_put(' ');if(col<255)++col;}while(col<target);
  }
  if(field<3 && !quote && raw==0xA0){
   target=stops[++field];
   do{rt_put(' ');if(col<255)++col;}while(col<target);
  }else {
   if(field==2 && (c=='\''||c=='"')){if(!quote)quote=c;else if(quote==c)quote=0;}
   rt_put(c);if(col<255)++col;
  }
  previous=raw;start=0;
 }
}
#elif RT_FORMAT == 4
/* LISA v2 alternate-B: four-byte header, length-prefixed lines and $FF
 * $FF $FF terminator follows the declared code end. No v3/v4 guess. */
static const char rt_lisa_ops[]=
 "BGEBLTBMIBCCBCSBPLBNEBEQBVSBVCBSBBNMBM1BNZBIZBIM"
 "BIPBICBNCBRABTRBFLBRKBKSCLVCLCCLDCLIDEXDEYINXINY"
 "NOPPHAPLAPHPPLPRTSRTIRSBRTNSECSEISEDTAXTAYTSXTXA"
 "TXSTYAADDCPRDCRINRSUBLDDPOPPPDSTDSTPLDRSTOSET___"
 "ADCANDORABITCMPCPXCPYDECEORINCJMPJSR___LDALDXLDY"
 "STASTXSTYXORLSRRORROLASLADREQUORGOBJEPZSTRDCMASC"
 "ICLENDLSTNLSHEXBYTHBYPAUDFSDCI...PAGINVBLKDBYTTL"
 "SBC___LET.IF.EL.FI=  PHSDPH.DAGENNOGUSR_________";
static void rt_decode(void){
 unsigned int length,i,op;
 unsigned char n,c,p,col;
 int lo,hi,x;
 lo=rt_get();hi=rt_get();if(lo<0||hi<0){rt_invalid();return;}
 /* Public v2 samples have $1800 or nearby editor versions, not a
  * v3 code/symbol-size pair. The exact version is retained in the header. */
 lo=rt_get();hi=rt_get();if(lo<0||hi<0){rt_invalid();return;}
 length=(unsigned int)lo|((unsigned int)hi<<8);
 /* Real DOS v2 files count from the length word (offset 2), excluding
  * the version and three-byte EOF marker. Bound before adding 2. */
 if(length<2 || length>65533U){rt_invalid();return;}
 length+=2;
 while(!rt_cancel && rt_off<length){
  x=rt_get();if(x<0){rt_invalid();return;}n=x;
  if(!n || rt_off+n>length){rt_invalid();return;}
  for(i=0;i<n;++i){x=rt_get();if(x<0){rt_invalid();return;}rt_line[i]=x;}
  if(rt_line[n-1]!=13){rt_invalid();return;}
  p=col=0;c=rt_line[0];
  if(c=='*'||c==';'){
   /* Comments can contain literal control bytes; show '?' through
    * rt_put instead of rejecting the complete source. */
   for(i=0;i+1<n;++i)rt_put(rt_line[i]);
   rt_put(13);continue;
  }
  if(c==' '){++p;}
  else if((c>='A' && c<='Z') || c=='^'){
   while(p+1<n && rt_line[p]<128){
    c=rt_line[p++];if(c<32||c>=127){rt_invalid();return;}
    if(c!=' '){rt_put(c);++col;}
   }
  }else if(c<128 && c!=13){rt_invalid();return;}
  if(p==n-1){rt_put(13);continue;}
  if(rt_line[p]<128 || p+2>=n){rt_invalid();return;}
  if(col<9)rt_spaces(9-col);else rt_put(' ');
  op=(rt_line[p++]-128)*3;
  for(i=0;i<3;++i)rt_put(rt_lisa_ops[op+i]);
  rt_put(' ');col=col<9?13:col+4;
  c=rt_line[p++];if(c>32){rt_invalid();return;}
  if(c){
   while(p+1<n && rt_line[p]<128){
    c=rt_line[p++];if(c<32||c>=127){rt_invalid();return;}
    rt_put(c);if(col<255)++col;
   }
  }
  if(p+1<n){
   if(rt_line[p++]!=0xBB){rt_invalid();return;}
   if(col<29)rt_spaces(29-col);else rt_put(' ');
   rt_put(';');
   while(p+1<n)rt_put(rt_line[p++]);
  }
  rt_put(13);
 }
 if(!rt_cancel){
  if(rt_off!=length || rt_get()!=255 || rt_get()!=255 || rt_get()!=255){rt_invalid();return;}
  /* DOS alternate-B retains sector padding after the mandatory marker. */
  while(rt_get()>=0);
 }
}
#elif RT_FORMAT == 5
/* Gutenberg data already extracted from its custom file system. Low-bit
 * alternate glyphs need its external fonts: show '?' rather than invent a
 * mapping. A NUL terminates text, but drain and check all physical reads. */
static void rt_decode(void){
 int raw;
 unsigned char c,ended=0;
 while(!rt_cancel && (raw=rt_get())>=0){
  if(ended)continue;
  if(!raw){ended=1;continue;}
  if(raw<128){rt_put('?');continue;}
  c=raw&127;
  if(c==13)rt_put(13);
  else if(c==9){rt_put(' ');rt_put(' ');rt_put(' ');rt_put(' ');}
  else rt_put(c);
 }
}
#elif RT_FORMAT == 6
/* Teach data fork only: styles live in rStyleBlock in the resource fork.
 * MacRoman accented Latin characters map to plain ASCII on an Apple IIe;
 * symbols outside the machine's character set are shown as '?'. */
static const char rt_mac_latin[]="AACENOUaaaaaaceeeeiiiinooooouuuu";
static void rt_decode(void){
 int raw;
 unsigned char c,lf=0;
 while(!rt_cancel && (raw=rt_get())>=0){
  c=raw;
  if(c==13){rt_put(13);lf=1;continue;}
  if(c==10){if(!lf)rt_put(13);lf=0;continue;}
  lf=0;
  if(c==9){rt_put(' ');rt_put(' ');rt_put(' ');rt_put(' ');}
  else if(c>=128 && c<160)rt_put(rt_mac_latin[c-128]);
  else rt_put(c);
 }
}
#endif

static unsigned char rt_pass(unsigned char render){
 rt_bad=rt_cancel=0;rt_off=0;rt_pos=rt_len=0;rt_row=1;rt_col=0;rt_render=render;
#ifdef RT_DOS
 if(rt_dos){
  dv_file=NULL;
  if(!dv_open(&rt_api.panels[*rt_api.active]) || !ds_open(rt_api.selected) ||
#if RT_FORMAT == 10
     ds_kind!=0){
#elif RT_FORMAT == 11
     ds_kind!=4){
#elif RT_FORMAT == 7
     ds_kind!=4 || ds_aux!=0x4000U){
#elif RT_FORMAT == 8
     ds_kind!=4 || ds_aux!=0x98A5U){
#else
     ds_kind!=1){
#endif
   dv_close();rt_bad=1;return 0;
  }
  rt_decode();if(!dv_close())rt_bad=1;return !rt_bad;
 }
#endif
 rt_file=rt_api.fopen(rt_api.full,"rb");
 if(!rt_file){rt_bad=1;return 0;}
 rt_decode();
 if(rt_api.fclose(rt_file))rt_bad=1;
 return !rt_bad;
}
void __fastcall__ plugin_entry(const struct A2fcApi* a){
 rt_api=*a;
#ifdef RT_DOS
 rt_dos=a->panels!=NULL && a->active!=NULL && a->panels[*a->active].fs==FS_DOS33;
 if(rt_dos && a->selected->type!=
#if RT_FORMAT == 10
    4
#elif RT_FORMAT == 7 || RT_FORMAT == 8 || RT_FORMAT == 11
    6
#else
    0xFA
#endif
    ){a->strcpy(a->note,"Incorrect DOS file type.");return;}
#endif
 if(
#ifdef RT_DOS
    (!rt_dos && !a->full[0]) ||
#else
    !a->full[0] ||
#endif
    !a->selected->name[0] || a->selected->type==15){
  a->strcpy(a->note,"Select a file.");return;}
 if(!rt_pass(0)){a->strcpy(a->note,rt_bad==1?"Read/open/close error.":"Malformed " RT_LABEL " file.");return;}
 a->clrscr();
 if(!rt_pass(1))a->strcpy(a->note,rt_bad==1?"Read/open/close error.":"Malformed " RT_LABEL " file.");
 else if(!rt_cancel){a->message("End - press a key to return");a->wait_key();}
 a->strcpy(a->reselect,a->selected->name);
}
