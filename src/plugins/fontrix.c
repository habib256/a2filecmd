/* Fontrix fonts: MAIN-only monochrome glyph preview on the text screen.
 * No file writes, AUX graphics or RAM-disk reconstruction. Read and close
 * the complete source, validate ALL glyph pointers against its ACTUAL EOF,
 * then read/close each glyph before showing it. 32-row glyphs combine two
 * bitmap rows per screen row. Reference: CiderPress II Fontrix notes,
 * reverse engineered by Mark Long (Apache-2.0; NOTICE). */
#define DS_SECTORS 81
#include "ps_source.h"
#pragma rodata-name(push,"OVLHDR")
const struct PsHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
 {0,0,0},"Preview Fontrix font glyphs (DOS/ProDOS)"};
#pragma rodata-name(pop)
#define a ps_api
static unsigned char header[384],glyph[128];
static unsigned char first,count,height,index_,width;
static unsigned long actual;
static unsigned int getptr(unsigned char c){
 unsigned int p=32+2*(unsigned int)(c-32);
 return (unsigned int)header[p]|((unsigned int)header[p+1]<<8);
}
static unsigned char load(void){
 unsigned int p,q,len;
 unsigned char c;
 int byte;
 if(!ps_open())return 0;
 actual=0;
 while((byte=ps_get())>=0){
  if(actual<sizeof header)header[(unsigned int)actual]=byte;
  if(++actual>20480UL)break;
 }
 if(!ps_close() || actual<sizeof header || actual>20480UL)return 0;
 if(!((header[24]==0x90 && header[25]==0xF7 && header[26]==0xB2)||
      (header[24]==0x6F && header[25]==0x08 && header[26]==0x4D)))return 0;
 count=header[16];first=header[17];height=header[20];
 if(!count || count>94 || first<33 || (unsigned int)first+count>127 ||
    !height || height>32 || header[18]>1)return 0;
 for(c=first;c<first+count;++c){
  p=getptr(c);q=getptr(c+1);
  if(p<384 || q<p || q>actual)return 0;
  len=q-p;
  if(len%height || len/height>4)return 0;
 }
 return 1;
}
static unsigned char read_glyph(void){
 unsigned int p,len,i;
 int c;
 p=getptr(first+index_);len=getptr(first+index_+1)-p;width=len/height;
 if(!ps_open())return 0;
 if(!ps_seek(p)){ps_close();return 0;}
 for(i=0;i<len;++i){c=ps_get();if(c<0){ps_bad=1;break;}glyph[i]=c;}
 return ps_close();
}

static void show(void){
 unsigned char x,y,k,scale,ink;
 unsigned int p;
 scale=height>20?2:1;
 a.clrscr();a.cprintf("Fontrix: %c ($%02X), glyph %u/%u, %ux%u\r\n",
  first+index_,first+index_,index_+1,count,width*8,height);
 a.message("Left/Up previous, Right/Down/Space next, ESC back");
 for(y=0;y<height;y+=scale){
  a.gotoxy(8,y/scale+1);
  for(x=0;x<width*8;++x){
   ink=0;
   for(k=0;k<scale && y+k<height;++k){
    p=(unsigned int)(y+k)*width+x/8;
    ink|=glyph[p]&(1<<(x&7));
   }
   a.cputc(ink?'*':' ');a.cputc(ink?'*':' ');
  }
 }
}
void __fastcall__ plugin_entry(const struct A2fcApi* api){
 unsigned char key;
 a=*api;
 ps_dos=a.panels!=NULL && a.active!=NULL && a.panels[*a.active].fs==FS_DOS33;
 if((!ps_dos && !a.full[0]) || !a.selected->name[0] || a.selected->type==15){
  a.strcpy(a.note,"Select a Fontrix font.");return;}
 if(!load()){a.strcpy(a.note,"Bad Fontrix font/read/close error.");return;}
 index_=0;
 for(;;){
  if(!read_glyph()){a.strcpy(a.note,"Fontrix read/seek/close error.");break;}
  show();key=a.wait_key();
  if(key==KEY_ESC)break;
  if(key==KEY_LEFT || key==KEY_UP){if(index_)--index_;}
  else if(key==KEY_RIGHT || key==KEY_DOWN || key==' '){if(index_+1<count)++index_;}
 }
 a.strcpy(a.reselect,a.selected->name);
}
