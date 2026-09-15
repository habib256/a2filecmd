/* Image writes are confined to an exclusively created sibling. The original
 * stays available until the closed copy is verified and safely renamed. */
#define T a
#include "replace.h"
static FILE* image;
static unsigned long image_base;
static unsigned char image_owned;
static unsigned char image_header[64];
#define image_temp a.other_full
static unsigned char image_close(void) {
 unsigned char ok=1;
 if(image && RF(fclose)(image))ok=0;
 image=NULL;return ok;
}
/* Full-image fingerprint across phases, including 2MG metadata. Detect a
 * swapped/changed original before the recoverable rename transaction. */
static unsigned long image_crc;
#include "dosimage_crc.h"
static void image_hash(unsigned int n) {
 unsigned int i;
 for(i=0;i<n;++i)image_crc=(image_crc>>8)^image_crc_table[(unsigned char)(image_crc^buf[i])];
}
static unsigned char image_unchanged(void) {
 unsigned long total=0;unsigned int n;unsigned char ok;
 source=RF(fopen)(other->path,"rb");if(!source)return 0;
 image_crc=0xFFFFFFFFUL;
 do {n=RF(fread)(buf,1,256,source);image_hash(n);total+=n;}
 while(n==256 && total<=0xFFFFFFUL && !stop());
 ok=!ferror(source) && !cancelled && total==rd24((unsigned char*)a.input+9) &&
    image_crc==(rd16((unsigned char*)a.input+5)|((unsigned long)rd16((unsigned char*)a.input+7)<<16));
 if(RF(fclose)(source))ok=0;source=NULL;return ok;
}
static void image_cleanup(void) {
 if(!image_close())note("Image close failed; original kept.");
 if(image_owned)replace_discard(image_temp);
 image_owned=0;
}
static unsigned char image_prepare(void) {
 unsigned int n,m;unsigned char ok=0,first=1;unsigned long total=0;
 image=NULL;image_owned=0;image_base=0;
 if(!RF(strcmp)(a.full,other->path) || getinfo(other->path) ||
    (info.access&0xC3)!=0xC3 || info.storage<1 || info.storage>3)goto bad;
 n=RF(strlen)(other->path);
 if(n!=other->img_len || n>=PATH_LEN)goto bad;
 /* Raw DOS-order images, or a validated DOS-order 2IMG container. */
 if(n>4 && !RF(strcmp)(other->path+n-4,".2MG")) {
  image=RF(fopen)(other->path,"rb");if(!image)goto bad;
  if(RF(fread)(buf,1,64,image)!=64 || ferror(image) || memcmp(buf,"2IMG",4) ||
     rd16(buf+8)!=64 || rd16(buf+10)>1 || rd16(buf+12) || rd16(buf+14) ||
     (buf[19]&0x80) || rd16(buf+20)!=280 || rd16(buf+22) ||
     rd24(buf+28)!=143360UL || buf[31] || buf[27])goto bad;
  image_base=rd24(buf+24);if(image_base<64 || image_base>0xFDFFFFUL)goto bad;
  RF(memcpy)(image_header,buf,64);
  if(!image_close())goto bad;
 } else if(!((n>4 && !RF(strcmp)(other->path+n-4,".DSK")) ||
             (n>3 && !RF(strcmp)(other->path+n-3,".DO"))))goto bad;
 while(n && other->path[n]!='/')--n;
 if(!n || n+10>=PATH_LEN)goto bad;
 if(!image_path())goto bad;
 RF(memcpy)(replace_backup,other->path,n+1);RF(strcpy)(replace_backup+n+1,"A2FC.BAK");
 if(replace_info(replace_backup)!=0x46)goto bad;
 a.sprintf((char*)buf,"Copy %s into %s?",a.selected->name,other->path);
 if(!RF(confirm)((char*)buf))return 0;
 if(newfile(image_temp,info.type,info.aux,1))goto bad;
 image_owned=1;
 image=RF(fopen)(image_temp,"wb");if(!image)goto bad;
 source=RF(fopen)(other->path,"rb");if(!source)goto bad;
 do {
  n=RF(fread)(buf,1,256,source);total+=n;
  if(ferror(source) || stop() || total>0xFFFFFFUL || RF(fwrite)(buf,1,n,image)!=n || ferror(image))goto clone_bad;
 }while(n==256);
 if(total<image_base+143360UL || (!image_base && total!=143360UL))goto clone_bad;
 ok=1;
clone_bad:
 if(RF(fclose)(source))ok=0;source=NULL;
 if(!image_close())ok=0;
 if(!ok)goto bad;
 /* Verify every byte of the closed clone, including container metadata. */
 image_crc=0xFFFFFFFFUL;
 image=RF(fopen)(image_temp,"rb");if(!image)goto bad;
 source=RF(fopen)(other->path,"rb");if(!source)goto bad;
 do {
  n=RF(fread)(buf,1,256,source);image_hash(n);m=RF(fread)(verify,1,256,image);
  if(stop() || n!=m || ferror(source) || ferror(image) || memcmp(buf,verify,n)){ok=0;break;}
  if(first && image_base && (n<64 || memcmp(buf,image_header,64))){ok=0;break;}
  first=0;
 }while(n==256);
 if(RF(fclose)(source))ok=0;source=NULL;
 if(!image_close())ok=0;
 if(!ok)goto bad;
 a.input[1]=image_base;a.input[2]=image_base>>8;a.input[3]=image_base>>16;
 wr16((unsigned char*)a.input+5,image_crc);wr16((unsigned char*)a.input+7,image_crc>>16);
 a.input[9]=total;a.input[10]=total>>8;a.input[11]=total>>16;
 a.input[0]='I';image_owned=0;return 1;
bad:
 note("DOS image refused or copy failed; original kept.");image_cleanup();return 0;
}
static void image_finish(void) {
 unsigned char result;
 if(a.arg=='X') {
  note(a.input[4]==1?"Name exists or DOS catalog inconsistent; original image kept.":
       a.input[4]==2?"DOS image full; original image kept.":"Copy failed; original image kept.");
  replace_discard(image_temp);return;
 }
 if(!image_unchanged()){note("Original image changed or unreadable; A2FC.DOS retained.");return;}
 result=replace_commit(image_temp,other->path);
 /* A pre-check refused (A2FC.BAK present, image locked): nothing was
  * renamed, the original is intact and A2FC.DOS is this run's own copy. */
 if(result==REPLACE_REFUSED){if(replace_discard(image_temp))note("A2FC.BAK exists or image locked: nothing changed.");return;}
 if(result==REPLACE_DONE)note("Copied to DOS 3.3 image; source kept.");
 else note(result==REPLACE_BACKUP?"Copied; old image retained in A2FC.BAK.":
      "Image install failed; keep A2FC.DOS / A2FC.BAK for recovery.");
}
#undef T
