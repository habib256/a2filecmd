/* Content candidates only: readers validate physical EOF and full structure.
 * Separate detector keeps the 6502 IDENT overlays within their fixed bounds. */
#ifndef PLUGIN_HOST
static const char* known(const char* label,const char* view){reader=view;return label;}
#endif
#include "mv_layout.h"
#include "dg_layout.h"
/* Distinguish renamed DHGR from the existing 280-dot GMAGIC route.
 * Require valid sampled commands, drawing and a coordinate in the right
 * half. Ambiguous narrow pictures retain their existing fallback. */
static unsigned char dpc_content(void){
 unsigned int at=0,x;unsigned char c,t,arg,pen=0,seen=0,wide=0,ended=0;
 if(id_dos || e->type!=6 || e->aux!=0x4000 || sz.l>65535UL)return 0;
 while(at<n){
  c=b[at++];if(ended){if(c)return 0;continue;}if(!c){ended=1;continue;}
  t=c>>4;arg=c&15;
  if(t==2)continue;
  if(t==4){if(arg>7)return 0;continue;}
  if(t==3 || t==5 || t==6){
   if(arg)return 0;if(at==n)break;
   if(t!=6 && (b[at]<32 || b[at]>127))return 0;
   ++at;continue;
  }
  if(t!=1 && t!=8 && t!=10 && t!=12 && t!=14)return 0;
  if(at+2>n)break;x=((unsigned int)arg<<8)|b[at++];c=b[at++];
  if(!dg_point_valid(x,c))return 0;
  if(t==8)pen=1;
  else if(t==10){if(!pen)return 0;seen=1;}
  else if(t==12 || t==14)seen=1;
  if(t!=1 && x>=280)wide=1;
 }
 return seen && wide && (sz.l>n || ended);
}
#include "pcs_layout.h"
/* No magic signature: require all object lengths, a complete first object,
 * every additional complete sampled object, and space for the shortest
 * valid 8192-byte compressed bitmap. The reader checks the remainder. */
static unsigned char pcs_content(void){
 unsigned int at,total,length;unsigned char count,i,j,points;
 if(id_dos || e->type!=6 || e->aux!=0x4000 || n<30 || !b[28])return 0;
 count=b[28];at=29U+count;if(at>n)return 0;total=at;
 for(i=0;i<count;++i){length=b[29U+i];if(length<9)return 0;total+=length;}
 if(sz.l<(unsigned long)total+66)return 0;
 for(i=0;i<count;++i){
  length=b[29U+i];if(at+length>n)return i!=0;
  points=b[at+2];
  if(!pc_object_valid(b[at],b[at+1],points,(unsigned char)length))return 0;
  for(j=0;j<points;++j)if(b[at+3+j]>=154 || b[at+3+points+j]>=192)return 0;
  at+=length;
 }
 return 1;
}
/* A renamed film must have the complete shape table and first bitmap
 * header. Only inspect a second bitmap header if it is in the saved sample.
 * Fresh physical EOF bounds the required remaining commands; the reader
 * still validates all commands and refuses embedded machine code. */
static unsigned char movie_content(void){
 unsigned int length,at;
 if(id_dos || e->type!=6 || (e->aux && e->aux!=0x6000) || n<264 || sz.l>65535UL ||
    b[0]!=1 || word(b+1)!=256 || b[259]!=2)return 0;
 length=word(b+260);
 if(!mv_plane_valid(length,word(b+262)))return 0;
 at=262+length;
 if(sz.l<(unsigned long)at+19)return 0;
 if((unsigned int)(n-5)>=at){
  if(b[at]!=3)return 0;
  length=word(b+at+1);
  if(!mv_plane_valid(length,word(b+at+3)) || sz.l<(unsigned long)at+length+17)return 0;
 }
 return 1;
}
static const char* extra_v1(void){
 unsigned int i;unsigned char t=e->type;
 /* MacBinary has a concrete MacPaint type field. Do not infer a raw
  * picture from a zero version word; the full reader checks every row. */
 if(!id_dos && (t==6 || !t) && n>=128 && !b[0] &&
    !memcmp(b+65,"PNTG",4) && (sz.w[1] || sz.w[0]>=2080))
  return known("MacPaint","MACPAINT");
 /* DOS alternate-B is typeless in the panel. $1800 is the verified
  * v2 editor header; the reader checks raw kind and the complete body. */
 if(id_dos && !t && n>=4 && word(b)==0x1800 && word(b+2)>=2)
  return known("LISA v2 source?","LISAV2");
 if(movie_content() || (id_dos && t==6 && e->aux==0x6000 &&
    suffix(e->name,".MVM") && n>=3 && b[0]==1 && word(b+1)==256))
  return known("Movie Maker preview?","MVMOVIE");
 if(dpc_content() || (t==6 && suffix(e->name,".DPC") && n>=3))return known("Graphics Magician DHGR?","DGMAGI");
 if(pcs_content() || (t==6 && e->aux==0x4000 && suffix(e->name,".PB") && n>=29 && b[28]))return known("PCS static preview?","PCSVW");
 if(!id_dos && (t==0xF4 || t==6) && n>=8 && word(b)==0xE708 && !word(b+2) && word(b+4)==0x10D6 && word(b+6)==1)return known("Multiplan normal 1.06?","MULTPLAN");
 if(!id_dos && t==0xA0 && !e->aux && n)return known("WordPerfect?","WORDPERF");
 if(!id_dos && (t==0xF1 || t==6) && !e->aux && n>=28 && b[0]=='M' && b[1]=='W' &&
    (b[2]==1 || b[2]==4 || b[2]==5) && !b[3] && b[4]==2 &&
    (!b[5] || b[5]==32) && b[26]>0 && b[26]<=120 && !b[27])return known("MouseWrite?","MOUSEWR");
 if(t==6 && n>=20){
  for(i=0;i<10;++i)if(b[i]!=(unsigned char)("AFILER 1.0"[i]|128))break;
  if(i==10)return known("Bank Street Filer?","BSFILER");
 }
 return NULL;
}
