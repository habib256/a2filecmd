/* Direct DOS 3.3 viewers: real drives first, DOS-order images.
 * Writes MAIN overlay/BSS and text/lo-res/HGR bytes, no AUX RAM-disk
 * storage, temporary file, source write or IRQ vector. All MLI calls are
 * READ_BLOCK. */
#include <string.h>
struct A2fcApi;
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[34];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,{0,0,0},
 "Direct DOS 3.3 text/hex/lo-res/HGR"};
#pragma rodata-name(pop)
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
static const struct A2fcApi* A;
#include "hgr_io.h"
#ifndef PLUGIN_HOST
#pragma optimize(push,off)
#pragma warn(unused-param,push,off)
static void __fastcall__ dv_message(const char* s) STUB(message)
static void __fastcall__ dv_clear(unsigned int unused) STUB(clrscr)
static char __fastcall__ dv_wait(unsigned int unused) STUB(wait_key)
static void __fastcall__ dv_xy(unsigned char x,unsigned int y) STUB(gotoxy)
static void __fastcall__ dv_put(unsigned int c) STUB(cputc)
static unsigned char __fastcall__ dv_mli(unsigned char cmd,void* p) STUB(mli)
static int __fastcall__ dv_seek(FILE* f,long at,int whence) STUB(fseek)
#pragma warn(unused-param,pop)
#pragma optimize(pop)
#else
#define dv_message A->message
#define dv_clear(u) A->clrscr()
#define dv_wait(u) A->wait_key()
#define dv_xy A->gotoxy
#define dv_put A->cputc
#define dv_mli A->mli
#define dv_seek A->fseek
#endif
#ifndef PLUGIN_HOST
#if SEEK_SET != 2
#error DOSVIEW HGR handoff requires the cc65 SEEK_SET convention
#endif
/* Tests compare these compiler-produced offsets with the handoff ABI. */
const unsigned char dh_api_offsets[]={offsetof(struct A2fcApi,wait_key),
 offsetof(struct A2fcApi,mli),offsetof(struct A2fcApi,fread),
 offsetof(struct A2fcApi,fclose),offsetof(struct A2fcApi,fseek),
 offsetof(struct A2fcApi,note)};
extern unsigned int dh_map[33],dh_length;
extern unsigned char dh_unit;
extern unsigned long dh_base;
extern FILE* dh_file;
extern unsigned char* dh_buffer;
#else
extern void host_hgr(const unsigned char*,unsigned int);
#endif
#ifdef PLUGIN_HOST
extern void host_lores(const unsigned char*);
#endif
#define DS_OTHER_TYPES
#define DS_MLI dv_mli
#define DS_SEEK dv_seek
#include "dos_source.h"
#define dv_pages ds_metadata.pages
static unsigned char dv_key(void){return dv_wait(0);}
static unsigned char dv_picture(void){
 unsigned int n=(unsigned int)ds_length;
 if(ds_kind!=4)return 0; /* BIN EOF is a freshly read 16-bit word. */
 if(ds_aux==0x0400&&n==1024)return 1;
 if((ds_aux==0x2000||ds_aux==0x4000)&&(n==8192||n==8184))return 2;
 return 0;
}
static void dv_text(void){
 unsigned char page=0,known=1,row,col,key,done;
 int c;
 dv_pages[0]=0;
 for(;;){
  if(!ds_seek(dv_pages[page]))break;dv_clear(0);row=col=done=0;
  while(row<22){
   c=ds_get();if(c<0){done=1;break;}c&=127;
   if(c==13||c==10){++row;col=0;continue;}
   if(col==80){++row;col=0;if(row==22){--ds_pos;break;}}
   dv_xy(col,row);++col;dv_put(c>=32?c:'.');
  }
  if(ds_bad)break;
  if(!done && page+1<80 && known==page+1){dv_pages[known]=ds_pos;++known;}
  dv_xy(0,22);A->cprintf("Direct DOS text: %s, page %u%s",A->selected->name,page+1,done?" (end)":"");
  dv_message("Space next, B previous, R first, ESC back");key=dv_key();
  if(key==KEY_ESC)break;if(key=='R'||key=='r')page=0;
  if((key==' '||key==KEY_RETURN||key==KEY_DOWN)&&page+1<known)++page;
  if((key=='B'||key=='b'||key==KEY_UP)&&page)--page;
 }
}
static void dv_hex(void){
 unsigned long at=0;unsigned char row,col,key;int c;
 for(;;){
  if(!ds_seek(at))break;dv_clear(0);
  for(row=0;row<19 && ds_pos<ds_length;++row){
   dv_xy(0,row);A->cprintf("%06lX: ",ds_pos);
   for(col=0;col<16;++col){c=ds_get();if(c<0)break;A->cprintf("%02X ",(unsigned int)c);}
  }
  if(ds_bad)break;
  dv_message("Direct DOS hex: Space next, B previous, R first, ESC back");key=dv_key();
  if(key==KEY_ESC)break;if(key=='R'||key=='r')at=0;
  if((key==' '||key==KEY_RETURN||key==KEY_DOWN)&&at+304<ds_length)at+=304;
  if((key=='B'||key=='b'||key==KEY_UP)&&at)at-=304;
 }
}
static unsigned char dv_lores(void){
 unsigned int i,at;unsigned char row;int c;
 unsigned char* picture;
 if(ds_kind!=4||ds_aux!=0x0400||(unsigned int)ds_length!=1024)return 0;
 /* Five sectors contain the four-byte header plus the page. Preserve
  * their pointers, then reuse the retired 1120-byte map for the picture. */
 for(i=0;i<5;++i)ds_picture_map[i]=ds_map[i];
 ds_map=ds_picture_map;picture=(unsigned char*)ds_slots;
 for(i=0;i<1024;++i){c=ds_get();if(c<0)return 0;picture[i]=c;}
 if(!dv_close()){ds_bad=1;return 0;}
#ifdef PLUGIN_HOST
 host_lores(picture);
#else
 *(volatile unsigned char*)0xC000=0; /* 80STORE off: $0400 stays MAIN */
 *(volatile unsigned char*)0xC004=0; /* RAMWRT main */
 for(row=0;row<24;++row){
  unsigned char* dest;
  at=(unsigned int)(row&7)*128+(unsigned int)(row>>3)*40;
  dest=(unsigned char*)(0x0400+at);
  memcpy(dest,picture+at,40); /* never screen holes / live firmware */
 }
 *(volatile unsigned char*)0xC00C=0; /* 40 columns */
 *(volatile unsigned char*)0xC05F=0; /* double graphics off */
 *(volatile unsigned char*)0xC050=0; /* graphics */
 *(volatile unsigned char*)0xC052=0; /* full screen */
 *(volatile unsigned char*)0xC054=0; /* page 1 */
 *(volatile unsigned char*)0xC056=0; /* lo-res */
#endif
 dv_wait(0);
#ifndef PLUGIN_HOST
 *(volatile unsigned char*)0xC051=0;
 *(volatile unsigned char*)0xC00D=0;
#endif
 return 1;
}
/* The assembly entry stays below $2000. Only after this C driver returns
 * does it overwrite the graphics page, including this driver's code. */
unsigned char __fastcall__ dv_entry(const struct A2fcApi* api){
 unsigned char key,picture_kind;
 A=api;
 if(!A->selected->name[0]||!dv_open(A->panels+*A->active)){
  scpy(A->note,"Select a DOS 3.3 file.");return 0;}
 if(!ds_open(A->selected))goto bad;
 picture_kind=dv_picture();
 key=A->arg;
 if(!key){dv_clear(0);dv_message("Direct DOS: T text, H hex, I image, ESC back");key=dv_key();}
 if(key==KEY_RETURN)key=ds_kind==0?'T':picture_kind?'I':'H';
 if((key=='I'||key=='i')&&picture_kind==2){
  scpy(A->reselect,A->selected->name);
#ifndef PLUGIN_HOST
  memcpy(dh_map,ds_map,66);dh_length=(unsigned int)ds_length;
  dh_unit=dv_unit;dh_base=dv_base;dh_file=dv_file;dh_buffer=A->copy_buf;
  dv_file=NULL;return 1;
#else
  {static unsigned char picture[8192];unsigned int i;int c;
   memset(picture,0,8192);
   for(i=0;i<ds_length;++i){c=ds_get();if(c<0)goto bad;picture[i]=c;}
   if(!dv_close())goto bad;
   host_hgr(picture,8192);dv_wait(0);return 0;}
#endif
 }
 if(key=='T'||key=='t')dv_text();
 if(key=='H'||key=='h')dv_hex();
 if(key=='I'||key=='i')if(!dv_lores()&&!ds_bad)scpy(A->note,"DOS image: raw BIN lo-res/HGR only.");
 if(ds_bad)goto bad;
 if(!dv_close())scpy(A->note,"DOS source close error.");
 scpy(A->reselect,A->selected->name);return 0;
bad:dv_close();scpy(A->note,"DOS source read/structure error.");return 0;
}
#ifdef PLUGIN_HOST
void __fastcall__ plugin_entry(const struct A2fcApi* api){dv_entry(api);}
#endif
