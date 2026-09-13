/* ProDOS file -> real DOS 3.3 Disk II. New names only, no source deletion.
 * Audit all live allocations, reserve VTOC first, read back each whole block,
 * compare source again and close it, then publish one catalog entry last.
 * No AUX use. On any failure after reservation, leave sectors allocated:
 * rollback of shared metadata after an uncertain physical write is unsafe. */
#define UTIL_STUBS
#define UTIL_INFO
#define UTIL_VOLUME
#define UTIL_WRITE

#include "util.h"
#include <string.h>
void __fastcall__ plugin_entry(const struct A2fcApi*);
unsigned char __fastcall__ dw_protected(unsigned char unit);
void dw_mainbank(void);
struct Header { unsigned int magic; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[52]; };
#ifndef PLUGIN_HOST
#pragma rodata-name(push,"OVLHDR")
#endif
const struct Header __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},
 "Copy selected ProDOS file to a real DOS 3.3 disk"};
#ifndef PLUGIN_HOST
#pragma rodata-name(pop)
#endif
#ifndef DOS_IMAGE
static const unsigned char order[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};
#endif
static unsigned char vtoc[256], cat[256], ts[256], data[256], seen[70];
#ifdef DOS_IMAGE
static unsigned char verify[256];
#else
static unsigned char verify[512];
#endif
/* A bitmap saves 450 bytes over 260 sector numbers. Ordering is ascending. */
static unsigned char allocation[70];
static unsigned int needed, sectors, lists, length, address;

static unsigned char unit, kind, prefix, slot, catsector, name[30];
static FILE* source;
/* DOS bitmap: sectors 0..7 in the second byte, 8..15 in the first. */
static unsigned char mask(unsigned int s) { return 1U<<(s&7); }
static unsigned int allocated(unsigned int index) {
 unsigned int s;
 for(s=48;s<560;++s)if(allocation[s>>3]&mask(s)) {if(!index)return s;--index;}
 return 560;
}
static unsigned int bitpos(unsigned int s) {return 0x38+(s/16)*4+((s&15)<8);}
static unsigned char free_sector(unsigned int s) {return vtoc[bitpos(s)]&mask(s);}
#ifdef DOS_IMAGE
#include "dosimage_path.h"
static FILE* image;
static unsigned long image_base;

static unsigned char read_sector(unsigned int s,unsigned char* out) {
 return s<560 && !RF(fseek)(image,image_base+(unsigned long)s*256,SEEK_SET) &&
  RF(fread)(out,1,256,image)==256 && !ferror(image);
}
#else
static unsigned char read_sector(unsigned int s,unsigned char* out) {
 unsigned char code=order[s&15];
 if(s>=560 || readblk(unit,(s/16)*8+(code>>1),buf))return 0;
 RF(memcpy)(out,buf+((code&1)?256:0),256);return 1;
}
#endif
/* Read-modify-write preserves the neighbouring DOS sector. Verify all 512
 * bytes, including that neighbour; never retry a failed physical write. */
static unsigned char write_sector(unsigned int s,const unsigned char* in) {
#ifdef DOS_IMAGE
  if(stop() || s>=560 || RF(fseek)(image,image_base+(unsigned long)s*256,SEEK_SET) ||
     RF(fwrite)(in,1,256,image)!=256 || ferror(image))return 0;
  return read_sector(s,verify) && !memcmp(in,verify,256);
#else
 unsigned char code=order[s&15];unsigned int block=(s/16)*8+(code>>1);
 if(stop() || dw_protected(unit) || readblk(unit,block,buf))return 0;
 RF(memcpy)(buf+((code&1)?256:0),in,256);
 RF(memcpy)(verify,buf,512);
 if(writeblk(unit,block,buf) || readblk(unit,block,buf))return 0;
 return !memcmp(buf,verify,512);
#endif
}
static unsigned char claim(unsigned int s) {
 if(s<48 || s>=560 || s/16==17 || free_sector(s) || (seen[s>>3]&mask(s)))return 0;
 seen[s>>3]|=mask(s);return 1;
}
/* Complete catalog and T/S walk, including locked files. Cross-links, loops,
 * live sectors marked free and inconsistent counts forbid all writes. */
static unsigned char audit(void) {
 unsigned char c,next,j,k,t,s;unsigned int cats=0,cur,count,want;
 catsector=0;a.memset(seen,0,sizeof seen);
 if(!read_sector(272,vtoc) || vtoc[3]<1 || vtoc[3]>3 || vtoc[1]!=17 ||
    !vtoc[2] || vtoc[2]>15 || vtoc[0x27]!=122 || vtoc[0x34]!=35 ||
    vtoc[0x35]!=16 || rd16(vtoc+0x36)!=256)return 0;
 /* Reserve boot tracks and the entire catalog track even on a dubious bitmap. */
 for(cur=0;cur<560;++cur)if((cur<48 || cur/16==17) && free_sector(cur))return 0;
 c=vtoc[2];
 while(c) {
  if(c>15 || (cats&(1U<<c)) || !read_sector(272+c,cat))return 0;
  cats|=1U<<c;
  if(cat[1] && cat[1]!=17)return 0;
  next=cat[2];if(!cat[1] && next)return 0;
  for(j=0;j<7;++j) {
   unsigned char* e=cat+11+j*35;
   if(!e[0] || e[0]==255) {if(!catsector){catsector=c;slot=j;}continue;}
   if(!memcmp(e+3,name,30))return 0;
   t=e[0];s=e[1];want=rd16(e+33);count=0;
   while(t) {
    cur=(unsigned int)t*16+s;
    if(s>=16 || !claim(cur) || !read_sector(cur,ts))return 0;
    ++count;t=ts[1];s=ts[2];if(!t && s)return 0;
    for(k=0;k<122;++k) {
     unsigned char dt=ts[12+2*k],ds=ts[13+2*k];
     if(!dt){if(ds)return 0;continue;}
     if(ds>=16 || !claim((unsigned int)dt*16+ds))return 0;
     ++count;
    }
   }
   if(count!=want)return 0;
  }
  c=next;
 }
 return catsector!=0;
}
static unsigned char source_length(void) {
 unsigned int n;unsigned long total=0;
 source=RF(fopen)(a.full,"rb");if(!source)return 0;
 do {n=RF(fread)(data,1,256,source);total+=n;}while(n==256 && total<=65535UL && !stop());
 n=ferror(source) || total>65535UL || cancelled;
 if(RF(fclose)(source))n=1;source=NULL;
 length=(unsigned int)total;return !n;
}
/* Produce the exact DOS byte stream, with its native BIN/BASIC prefix. */
static unsigned char chunk(unsigned int index,unsigned int* left) {
 unsigned int off=0,n;
 a.memset(data,0,256);
 if(!index && prefix) {
  if(prefix==4){wr16(data,address);off=2;}
  wr16(data+off,length);off+=2;
 }
 n=*left>256-off?256-off:*left;
 if(RF(fread)(data+off,1,n,source)!=n || ferror(source))return 0;
 *left-=n;return 1;
}
static unsigned char end_source(unsigned int left) {
 unsigned char ok=!left && !RF(fread)(data,1,1,source) && !ferror(source);
 if(RF(fclose)(source))ok=0;source=NULL;return ok;
}
static unsigned char verify_source(void);
static unsigned char lists_io(unsigned char writing) {
 unsigned int i,j,cur;
 for(i=0;i<lists;++i) {
  a.memset(data,0,256);
  if(i+1<lists){cur=allocated(i+1);data[1]=cur/16;data[2]=cur&15;}
  wr16(data+5,i*122);
  for(j=0;j<122 && i*122+j<sectors;++j) {
   cur=allocated(lists+i*122+j);data[12+2*j]=cur/16;data[13+2*j]=cur&15;
  }
  #ifdef DOS_IMAGE
  if(!writing) {if(!read_sector(allocated(i),ts) || memcmp(ts,data,256))return 0;}
  else
#endif
  if(!write_sector(allocated(i),data))return 0;
 }
 return 1;
}
static unsigned char transfer(void) {
 unsigned int i,left=length;unsigned char ok;
 source=RF(fopen)(a.full,"rb");if(!source)return 0;
 for(i=0;i<sectors;++i) {
  if(!chunk(i,&left) || !write_sector(allocated(lists+i),data))goto bad;
  a.progress_bar(a.selected->name,i,sectors);
 }
 if(!end_source(left))return 0;
 if(!lists_io(1))return 0;
 return verify_source();
bad:
 ok=RF(fclose)(source);source=NULL;(void)ok;return 0;
}
static unsigned char verify_source(void) {
 unsigned int i,left=length;unsigned char ok;
 source=RF(fopen)(a.full,"rb");if(!source)return 0;
 for(i=0;i<sectors;++i) {
  if(stop() || !chunk(i,&left) || !read_sector(allocated(lists+i),ts) || memcmp(data,ts,256))goto bad;
 }
 return end_source(left);
bad:
 ok=RF(fclose)(source);source=NULL;(void)ok;return 0;
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 unsigned int i,n;unsigned char* e;
 init(api);source=NULL;
#ifdef DOS_IMAGE
 image=NULL;a.input[0]='X';a.input[4]=0;
#endif
 if(a.arg==1 || a.arg=='V'){note("DOS 3.3: use C to copy; source is kept.");return;}
 if(pan->fs || !a.full[0] || !a.selected->name[0] || other->fs!=FS_DOS33
 ) {
  note("Select a ProDOS file; open a real DOS 3.3 disk opposite.");return;
 }
#ifndef DOS_IMAGE
 if(other->img_len){note("Use C to prepare a DOS image copy.");return;}
 unit=(unsigned char)other->dir_key;
 n=unit_of(a.full,0);
 if(!(unit&0x70) || (unit&15) || !n || n==unit) {
  note("Cannot identify separate source and DOS drives.");return;
 }
 dw_mainbank();
 if(dw_protected(unit)){note("DOS 3.3 disk is write-protected.");return;}
#else
 if(!other->img_len || a.arg!='I'){note("Use C to prepare a DOS image copy.");return;}
#endif
 if(getinfo(a.full) || info.storage<1 || info.storage>3 || !(info.access&1)) {
  note("Cannot read source metadata.");return;
 }
 address=info.aux;prefix=0;
 switch(info.type) {
 case 4:kind=0;break;
 case 6:kind=4;prefix=4;break;
 case 0xFC:kind=2;prefix=2;break;
 case 0xFA:kind=1;prefix=2;break;
 default:note("DOS 3.3 copy supports TXT, BIN, BAS and INT files.");return;
 }
 a.memset(name,0xA0,30);
 for(i=0;a.selected->name[i] && i<15;++i)name[i]=a.selected->name[i]|0x80;
 if(!source_length()) {note("Cannot read source.");return;}
#ifdef DOS_IMAGE
 {
  if(!image_path())return;
  image_base=rd24((unsigned char*)a.input+1);
  image=RF(fopen)(image_temp,"r+b");if(!image){note("Cannot open reserved DOS image copy.");return;}
 }
#endif
 if(!audit()) {
#ifdef DOS_IMAGE
 a.input[4]=1;
#endif
 note("Copy refused: name collision or DOS disk consistency.");goto done;}
 sectors=((unsigned long)length+prefix+255)/256;
 lists=(sectors+121)/122;if(!lists)lists=1;
 needed=sectors+lists;n=0;
 a.memset(allocation,0,sizeof allocation);
 for(i=48;i<560 && n<needed;++i)if(i/16!=17 && free_sector(i)){allocation[i>>3]|=mask(i);++n;}
 if(n!=needed){
#ifdef DOS_IMAGE
 a.input[4]=2;
#endif
 note("DOS 3.3 disk full; nothing written.");goto done;}
#ifndef DOS_IMAGE
 a.sprintf((char*)data,"Copy %s to DOS 3.3 S%u,D%u?",a.selected->name,(unit>>4)&7,(unit>>7)+1);
 if(!RF(confirm)((char*)data))return;
#endif
 /* Refuse a swap/change while the confirmation was on screen. */
 if(!read_sector(272,ts) || memcmp(ts,vtoc,256) || !audit() ||
    !read_sector(272+catsector,cat))goto refused;
 e=cat+11+slot*35;if(e[0] && e[0]!=255)goto refused;
 for(i=0;i<needed;++i)vtoc[bitpos(allocated(i))]&=~mask(allocated(i));
 if(!write_sector(272,vtoc) || !transfer())goto failed;
 /* Preserve the complete catalog sector and reject late metadata changes. */
 if(!read_sector(272+catsector,ts) || memcmp(ts,cat,256) ||
    !read_sector(272,ts) || memcmp(ts,vtoc,256))goto failed;
 e[0]=allocated(0)/16;e[1]=allocated(0)&15;e[2]=kind;
 RF(memcpy)(e+3,name,30);wr16(e+33,needed);
 if(!write_sector(272+catsector,cat))goto failed;
#ifdef DOS_IMAGE
 {
  n=RF(fclose)(image);image=NULL;if(n)goto failed;
  image=RF(fopen)(image_temp,"rb");if(!image)goto failed;
  if(!read_sector(272,ts) || memcmp(ts,vtoc,256) ||
     !read_sector(272+catsector,ts) || memcmp(ts,cat,256) || !lists_io(0) || !verify_source())goto failed;
  n=RF(fclose)(image);image=NULL;if(n)goto failed;
  a.input[0]='F';
 }
#endif
#ifdef DOS_IMAGE
 note("DOS image verified; installing copy.");
#else
 note("Copied to DOS 3.3; source kept.");
#endif
 goto done;
refused:note("DOS 3.3 disk changed; nothing written.");goto done;
failed:note("Copy stopped; source kept. Check DOS disk; space may stay reserved.");
done:
#ifdef DOS_IMAGE
 if(image){n=RF(fclose)(image);image=NULL;if(n)a.input[0]='X';}
#endif
 return;
}
