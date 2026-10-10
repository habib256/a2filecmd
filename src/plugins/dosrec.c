/* Read-only DOS fixed-record inspector. Writes MAIN and the text screen only;
 * no AUX, disk write, or RAM-disk reconstruction. NUL never means EOF. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[46];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,
 {0,0,0},"Inspect DOS text records, including holes/NUL"};
#pragma rodata-name(pop)
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
static const struct A2fcApi* A;
#define DS_RANDOM_TEXT
#define DS_DATA_BUFFER A->copy_buf
#define DS_MLI A->mli
#define DS_SEEK A->fseek
#include "hgr_io.h"
#ifndef PLUGIN_HOST
#pragma optimize(push,off)
#pragma warn(unused-param,push,off)
static void __fastcall__ dr_message(const char* s) STUB(message)
static void __fastcall__ dr_clear(unsigned int unused) STUB(clrscr)
static char __fastcall__ dr_wait(unsigned int unused) STUB(wait_key)
static void __fastcall__ dr_xy(unsigned char x,unsigned int y) STUB(gotoxy)
static void __fastcall__ dr_put(unsigned int c) STUB(cputc)
#pragma warn(unused-param,pop)
#pragma optimize(pop)
#else
#define dr_message A->message
#define dr_clear(u) A->clrscr()
#define dr_wait(u) A->wait_key()
#define dr_xy A->gotoxy
#define dr_put A->cputc
#endif
#include "dos_source.h"
static unsigned char bytes_[288],holes[36];
static unsigned int length_,used,page;
static unsigned long extent,record;
static unsigned char open_source(void){
 return dv_open(A->panels+*A->active) && ds_open(A->selected);
}
static unsigned char preflight(void){
 unsigned int i,p;unsigned char ok;
 ok=open_source();
 if(ok){
  extent=ds_length;
  for(i=0;i<ds_count;++i){p=ds_map[i];if(p && !sector_read(p>>8,p,A->copy_buf)){ok=0;break;}}
 }
 if(!dv_close())ok=0;return ok;
}
static unsigned char choose_length(void){
 unsigned int value=0;unsigned char digits=0,key;
 dr_clear(0);dr_message("Record length 1-4096 (decimal), Return=256, ESC back");
 for(;;){
  dr_xy(0,2);A->cprintf("Length: %u     ",value);
  key=dr_wait(0);if(key==KEY_ESC)return 0;
  if(key==KEY_RETURN){if(!digits)value=256;if(value && value<=4096){length_=value;return 1;}}
  else if(key==KEY_LEFT || key==127){value/=10;if(digits)--digits;}
  else if(key>='0' && key<='9' && digits<4){value=value*10+key-'0';++digits;}
 }
}
static unsigned char load_page(void){
 unsigned long at,end;unsigned int i;int c;unsigned char ok;
 at=record*length_+page;end=record*length_+length_;
 if(end>extent)end=extent;
 used=end-at>288?288:(unsigned int)(end-at);
 memset(holes,0,sizeof holes);
 ok=open_source();
 if(ok && ds_length!=extent)ok=0;
 if(ok)ok=ds_seek(at);
 if(ok)for(i=0;i<used;++i){
  if(!ds_map[(unsigned int)(ds_pos>>8)])holes[i>>3]|=1U<<(i&7);
  c=ds_get();if(c<0){ok=0;break;}bytes_[i]=c;
 }
 if(!dv_close())ok=0;return ok;
}
static void show(void){
 unsigned int i,j;unsigned char row,c,h;
 dr_clear(0);dr_xy(0,0);
 A->cprintf("DOS record %lu, length %u, +%u",record,length_,page);
 for(row=0;row<18 && (i=(unsigned int)row*16)<used;++row){
  dr_xy(0,row+2);A->cprintf("%06lX: ",record*length_+page+i);
  for(j=i;j<i+16;++j){
   /* Keep the bit test byte-sized. cc65 2.18's native service-call
    * branch otherwise tests only X after its 16-bit AND helper. */
   h=holes[j>>3]&(1U<<(j&7));
   if(j>=used)A->cprintf("   ");
   else if(h)A->cprintf("-- ");
   else A->cprintf("%02X ",(unsigned int)bytes_[j]);
  }
  dr_put(' ');
  for(j=i;j<i+16 && j<used;++j){
   h=holes[j>>3]&(1U<<(j&7));c=bytes_[j]&127;
   dr_put(h?'~':c>=32 && c<127?c:'.');
  }
 }
 dr_xy(0,21);A->cprintf("Allocated extent %lu B; -- hole, 00 NUL; EOF unknown",extent);
 dr_message("N/P record, Space/B page, R first, L length, ESC back");
}
void __fastcall__ plugin_entry(const struct A2fcApi* api){
 unsigned char key;unsigned long at;
 A=api;dv_file=NULL;
 if(!api->selected->name[0] || !preflight())goto bad;
 if(!extent){api->strcpy(api->note,"DOS text has no allocated data sectors.");return;}
 if(!choose_length())return;
 record=0;page=0;
 for(;;){
  if(!load_page())goto bad;
  show();key=api->wait_key();if(key==KEY_ESC)break;
  at=record*length_;
  if(key=='N'||key=='n'||key==KEY_RIGHT){if(at+length_<extent){++record;page=0;}}
  else if(key=='P'||key=='p'||key==KEY_LEFT){if(record){--record;page=0;}}
  else if(key==' '||key==KEY_DOWN){if(page+288<length_ && at+page+288<extent)page+=288;}
  else if(key=='B'||key=='b'||key==KEY_UP){if(page)page-=288;}
  else if(key=='R'||key=='r'){record=0;page=0;}
  else if(key=='L'||key=='l'){if(!choose_length())break;record=0;page=0;}
 }
 api->strcpy(api->reselect,api->selected->name);return;
bad:dv_close();api->strcpy(api->note,"DOS record source read/seek/close/structure error.");
}
