/* Print Shop font: BIN has 59 glyphs with absolute pointers; ProDOS F5
 * has a 12-byte prefix, 95 entries and bitmap-relative pointers.
 * Font pixels are MSB-first (verified from original FOEDIT and CiderPress).
 * Pointer/size bounds for ALL glyphs precede display. MAIN only. */
#include "ps_source.h"
#pragma rodata-name(push,"OVLHDR")
const struct PsHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,
 {0,0,0},"Preview Print Shop font glyphs (scrollable)"};
#pragma rodata-name(pop)
static unsigned char head[392],glyph[384];
static unsigned char start,index_,top,width,height,stride,count;
static unsigned int actual,base,data_start,aux;
static unsigned int pointer(unsigned char i){
 return (unsigned int)head[start+(unsigned int)count*2+i]|((unsigned int)head[start+(unsigned int)count*3+i]<<8);
}
static unsigned char validate(void){
 unsigned int n=0,p,len;
 unsigned char i,w,h;
 int c;
 if(!ps_open())return 0;
 aux=ps_aux;base=ps_new?0:aux;
 while((c=ps_get())>=0){if(n<392)head[n]=c;if(++n>16384)break;}
 if(!ps_close())return 0;
 actual=n;
 if(ps_new){if(aux!=0x1000)return 0;start=12;count=95;}
 else {if(base!=0x6000 && base!=0x5FF4)return 0;start=base==0x6000?0:12;count=59;}
 data_start=start+(unsigned int)count*4;
 if(n<data_start || n>16384)return 0;
 if(ps_new && ((unsigned int)head[6]|((unsigned int)head[7]<<8))!=n-data_start)return 0;
 /* Space has no bitmap; '@' is an external graphic placeholder. */
 for(i=1;i<count;++i){
  if(i==32)continue;
  w=head[start+i]&127;h=head[start+count+i];p=pointer(i);
  if(w>48 || h>64)return 0;
  if(ps_new){if(p>actual-data_start)return 0;p+=data_start;}
  else if(p<base+data_start)return 0;
  len=((unsigned int)w+7)/8*h;
  if((unsigned long)p+len>(unsigned long)base+actual)return 0;
 }
 return 1;
}
static unsigned char load_glyph(void){
 unsigned int p,len,i;
 int c;
 width=head[start+index_]&127;height=head[start+count+index_];stride=(width+7)/8;
 p=pointer(index_)-base;if(ps_new)p+=data_start;len=(unsigned int)stride*height;
 if(!ps_open())return 0;
 if(ps_aux!=aux || !ps_seek(p)){ps_close();return 0;}
 for(i=0;i<len;++i){c=ps_get();if(c<0){ps_bad=1;break;}glyph[i]=c;}
 return ps_close();
}
static void show(void){
 unsigned char x,y,ink,scale=width<=32?2:1;
 unsigned int off;
 ps_api.clrscr();ps_api.gotoxy(0,0);
 ps_api.cprintf("Print Shop font: %c ($%02X), %ux%u, rows %u-%u",index_+32,index_+32,width,height,top+1,top+20<height?top+20:height);
 for(y=top;y<height && y<top+20;++y){
  ps_api.gotoxy(4,y-top+1);
  for(x=0;x<width;++x){
   off=(unsigned int)y*stride+x/8;ink=glyph[off]&(0x80>>(x&7));
   ps_api.cputc(ink?'*':' ');if(scale==2)ps_api.cputc(ink?'*':' ');
  }
 }
 ps_api.message("Left/Right glyph, Up/Down scroll, Space next, ESC back");
}
void __fastcall__ plugin_entry(const struct A2fcApi* api){
 unsigned char key;
 if(!ps_select(api))return;
 if(!validate()){
  api->strcpy(api->note,ps_bad?"Print Shop read/open/close error.":"Malformed/unsupported Print Shop font.");return;}
 index_=1;top=0;
 for(;;){
  if(!load_glyph()){api->strcpy(api->note,"Print Shop read/seek/close error.");break;}
  show();key=api->wait_key();if(key==KEY_ESC)break;
  if(key==KEY_LEFT){if(index_>1){--index_;if(index_==32)--index_;top=0;}}
  else if(key==KEY_RIGHT || key==' '){if(index_<count-1){++index_;if(index_==32)++index_;top=0;}}
  else if(key==KEY_DOWN){if(top+20<height)++top;}
  else if(key==KEY_UP && top)--top;
 }
 api->strcpy(api->reselect,api->selected->name);
}
