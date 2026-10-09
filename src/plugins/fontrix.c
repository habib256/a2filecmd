/* Fontrix fonts: MAIN-only monochrome glyph preview on the text screen.
 * No file writes, AUX graphics or RAM-disk reconstruction. Read and close
 * the complete source, validate ALL glyph pointers against its ACTUAL EOF,
 * then read/close each glyph before showing it. 32-row glyphs combine two
 * bitmap rows per screen row. Reference: CiderPress II Fontrix notes,
 * reverse engineered by Mark Long (Apache-2.0; NOTICE). */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[50];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
 {0,0,0},"Preview Fontrix font glyphs (monochrome text)"};
#pragma rodata-name(pop)
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
static struct A2fcApi a;
static unsigned char header[384],glyph[128];
static unsigned char first,count,height,index_,width;
static unsigned long actual;
static unsigned int getptr(unsigned char c){
 unsigned int p=32+2*(unsigned int)(c-32);
 return (unsigned int)header[p]|((unsigned int)header[p+1]<<8);
}
static unsigned char load(void){
 FILE* f;
 unsigned int n,p,q,len;
 unsigned char c,bad=0;
 f=a.fopen(a.full,"rb");if(!f)return 0;
 actual=a.fread(header,1,sizeof header,f);
 if(actual!=sizeof header || ferror(f))bad=1;
 do{
  n=a.fread(a.copy_buf,1,512,f);actual+=n;
  if(ferror(f) || actual>20480UL)bad=1;
 }while(n && !bad);
 if(a.fclose(f))bad=1;
 if(bad)return 0;
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
 FILE* f;
 unsigned int p,len;
 unsigned char bad;
 p=getptr(first+index_);len=getptr(first+index_+1)-p;width=len/height;
 f=a.fopen(a.full,"rb");if(!f)return 0;
 bad=a.fseek(f,(long)p,SEEK_SET)!=0;
 if(!bad && (a.fread(glyph,1,len,f)!=len || ferror(f)))bad=1;
 if(a.fclose(f))bad=1;
 return !bad;
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
 if(!a.full[0] || !a.selected->name[0] || a.selected->type==15){
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
