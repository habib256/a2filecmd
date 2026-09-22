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
#ifdef DOS_IMAGE
/* Internal phase: DOSIMAGE reports the final result from input[0]/input[4]. */
#define note(s) ((void)0)
#endif
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
static unsigned char vtoc[256], cat[256], ts[256], data[256], seen[70];
#ifdef DOS_IMAGE
static unsigned char verify[256];
#else
static unsigned char verify[256];
#endif
/* A bitmap saves 450 bytes over 260 sector numbers. Ordering is ascending. */
static unsigned char allocation[70];
static unsigned int needed, sectors, lists, length, address;

static unsigned char unit, kind, prefix, slot, catsector, name[30];
static FILE* source;
#ifdef DOS_IMAGE
#include "dosimage_path.h"
static FILE* image;
static unsigned long image_base;
#endif
/* The volume itself -- sector I/O, the bitmap and the audit -- is shared
 * with DOS33W (dos33_fs.h), and so is the copy engine below it: the two
 * overlays write the same files to the same disks. */
#include "dos33_fs.h"
#include "dos33_copy.h"

#ifdef DOS_IMAGE
/* New sectors and metadata were verified above. Everything else, including
 * the container and existing files, must still match the original exactly. */
static unsigned char verify_preserved(void) {
 unsigned long pos=0,relative;unsigned int n,m,i,s;unsigned char ok=0;
 if(RF(fseek)(image,0,SEEK_SET))return 0;
 source=RF(fopen)(other->path,"rb");if(!source)return 0;
 do {
  /* 140 KB twice more, compared byte by byte: the bar, from 0 */
  a.progress_bar("Checking image",pos,rd24((unsigned char*)a.input+9));
  n=RF(fread)(buf,1,256,source);m=RF(fread)(verify,1,256,image);
  if(n!=m || ferror(source) || ferror(image) || stop())goto done;
  for(i=0;i<n;++i)if(buf[i]!=verify[i]) {
   relative=pos+i-image_base;
   if(relative>=143360UL)goto done;
   s=relative>>8;
   if(s!=272 && s!=272+catsector && !(allocation[s>>3]&mask(s)))goto done;
  }
  pos+=n;
 }while(n==256 && pos<=0xFFFFFFUL);
 ok=pos==rd24((unsigned char*)a.input+9);
done:
 if(RF(fclose)(source))ok=0;source=NULL;return ok;
}
#endif
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
 n=dw_protected(unit);
 if(n){note(n==1?"Target is not a standard Disk II.":"DOS 3.3 disk is write-protected.");return;}
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
 reserve();
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
     !read_sector(272+catsector,ts) || memcmp(ts,cat,256) || !lists_io(0) ||
     !verify_source() || !verify_preserved())goto failed;
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
