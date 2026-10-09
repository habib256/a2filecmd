/* Feasibility prototype: !/DOSVIEW, real DOS 3.3 first, DOS-order images.
 * Writes MAIN overlay/BSS and visible text/lo-res bytes, no AUX RAM-disk
 * storage, temporary file, source write or IRQ vector. All MLI calls are
 * READ_BLOCK. Native binary is built explicitly, not shipped by Makefile. */
#include <string.h>
struct A2fcApi;
#include "../../src/a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[61];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,{0,0,0},
 "Prototype: direct DOS 3.3 text/hex/lo-res (no extraction)"};
#pragma rodata-name(pop)
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
static const struct A2fcApi* A;
static FILE* dv_file;
static unsigned char dv_unit;
static unsigned long dv_base;
static unsigned long dv_pages[80];
#ifdef PLUGIN_HOST
extern void host_lores(const unsigned char*);
#endif
static unsigned char sector_read(unsigned char t,unsigned char s,unsigned char* out){
 static const unsigned char order[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};
 unsigned int block;unsigned char code,parms[6];
 if(t>=35||s>=16)return 0;
 if(dv_unit){
  code=order[s];block=(unsigned int)t*8+(code>>1);
  parms[0]=3;parms[1]=dv_unit;
  parms[2]=(unsigned char)((unsigned int)A->copy_buf&255);
  parms[3]=(unsigned char)((unsigned int)A->copy_buf>>8);
  parms[4]=block;parms[5]=block>>8;
  if(A->mli(0x80,parms))return 0;
  memcpy(out,A->copy_buf+(code&1?256:0),256);
 }else{
  if(A->fseek(dv_file,dv_base+(((unsigned long)t*16+s)<<8),SEEK_SET)||
     A->fread(out,1,256,dv_file)!=256||ferror(dv_file))return 0;
 }
 return 1;
}
#include "dos_stream.h"
static unsigned char dv_close(void){
 unsigned char ok=1;if(dv_file && A->fclose(dv_file))ok=0;dv_file=NULL;return ok;
}
static unsigned char dv_open(const struct Panel* p){
 char path[64];unsigned char n;
 dv_file=NULL;dv_unit=0;dv_base=0;
 if(p->fs!=FS_DOS33)return 0;
 if(!p->img_len){dv_unit=p->dir_key;if(!(dv_unit&0x70)||(dv_unit&15))return 0;return 1;}
 n=p->img_len;if(n>=64)return 0;memcpy(path,p->path,n);path[n]=0;
 dv_file=A->fopen(path,"rb");if(!dv_file)return 0;
 if(n>4 && !strcmp(path+n-4,".2MG")){
  if(A->fread(A->copy_buf,1,64,dv_file)!=64||ferror(dv_file)||memcmp(A->copy_buf,"2IMG",4)||
     A->copy_buf[12]||A->copy_buf[13]||A->copy_buf[14]||A->copy_buf[15])goto bad;
  dv_base=(unsigned long)ds_word(A->copy_buf+24)|((unsigned long)ds_word(A->copy_buf+26)<<16);
  if(dv_base<64 || dv_base>0xFC0000UL || ds_word(A->copy_buf+28)!=0x3000 ||
     ds_word(A->copy_buf+30)!=2)goto bad; /* 143360 bytes */
 }
 return 1;
bad:dv_close();return 0;
}
static unsigned char dv_key(void){return A->wait_key();}
static void dv_text(void){
 unsigned char page=0,known=1,row,col,key,done;
 int c;
 dv_pages[0]=0;
 for(;;){
  if(!ds_seek(dv_pages[page]))break;A->clrscr();row=col=done=0;
  while(row<22){
   c=ds_get();if(c<0){done=1;break;}c&=127;
   if(c==13||c==10){++row;col=0;continue;}
   if(col==80){++row;col=0;if(row==22){--ds_pos;break;}}
   A->gotoxy(col,row);++col;A->cputc(c>=32?c:'.');
  }
  if(ds_bad)break;
  if(!done && page+1<80 && known==page+1){dv_pages[known]=ds_pos;++known;}
  A->gotoxy(0,22);A->cprintf("Direct DOS text: %s, page %u%s",A->selected->name,page+1,done?" (end)":"");
  A->message("Space next, B previous, R first, ESC back");key=dv_key();
  if(key==KEY_ESC)break;if(key=='R'||key=='r')page=0;
  if((key==' '||key==KEY_RETURN||key==KEY_DOWN)&&page+1<known)++page;
  if((key=='B'||key=='b'||key==KEY_UP)&&page)--page;
 }
}
static void dv_hex(void){
 unsigned long at=0;unsigned char row,col,key;int c;
 for(;;){
  if(!ds_seek(at))break;A->clrscr();
  for(row=0;row<19 && ds_pos<ds_length;++row){
   A->gotoxy(0,row);A->cprintf("%06lX: ",ds_pos);
   for(col=0;col<16;++col){c=ds_get();if(c<0)break;A->cprintf("%02X ",(unsigned int)c);}
  }
  if(ds_bad)break;
  A->message("Direct DOS hex: Space next, B previous, R first, ESC back");key=dv_key();
  if(key==KEY_ESC)break;if(key=='R'||key=='r')at=0;
  if((key==' '||key==KEY_RETURN||key==KEY_DOWN)&&at+304<ds_length)at+=304;
  if((key=='B'||key=='b'||key==KEY_UP)&&at)at-=304;
 }
}
static unsigned char dv_lores(void){
 unsigned int i,at;unsigned char row;int c;
 unsigned char* picture;
 if(ds_kind!=4||ds_aux!=0x0400||ds_length!=1024)return 0;
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
 A->wait_key();
#ifndef PLUGIN_HOST
 *(volatile unsigned char*)0xC051=0;
 *(volatile unsigned char*)0xC00D=0;
#endif
 return 1;
}
void __fastcall__ plugin_entry(const struct A2fcApi* api){
 unsigned char key;
 A=api;
 if(!A->selected->name[0]||!dv_open(A->panels+*A->active)){
  A->strcpy(A->note,"Select a DOS 3.3 file (real disk or DOS-order image).");return;}
 if(!ds_open(A->selected))goto bad;
 A->clrscr();A->message("Direct DOS: T text, H hex, I lo-res, ESC back");
 key=dv_key();
 if(key=='T'||key=='t')dv_text();
 if(key=='H'||key=='h')dv_hex();
 if(key=='I'||key=='i')if(!dv_lores()&&!ds_bad)A->strcpy(A->note,"Prototype image: BIN $0400, exactly 1024 bytes only.");
 if(ds_bad)goto bad;
 if(!dv_close())A->strcpy(A->note,"DOS source close error.");
 A->strcpy(A->reselect,A->selected->name);return;
bad:dv_close();A->strcpy(A->note,"DOS source read/structure error; no file written.");
}
