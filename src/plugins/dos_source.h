/* Read-only DOS source: real READ_BLOCK drives and DOS-order images.
 * Caller supplies A, hgr_io stubs, DS_MLI and DS_SEEK. No AUX or writes. */
static FILE* dv_file;
static unsigned char dv_unit;
static unsigned long dv_base;
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
  if(DS_MLI(0x80,parms))return 0;
#ifdef DS_DATA_BUFFER
  if(out!=A->copy_buf||(code&1))
#endif
   memcpy(out,A->copy_buf+(code&1?256:0),256);
 }else{
  if(DS_SEEK(dv_file,dv_base+((unsigned long)((unsigned int)t*16+s)<<8),SEEK_SET)||
     frd(out,1,256,dv_file)!=256||ferror(dv_file))return 0;
 }
 return 1;
}
#include "dos_stream.h"
static unsigned char dv_close(void){
 unsigned char ok=1;if(dv_file && fcls(dv_file))ok=0;dv_file=NULL;return ok;
}
static unsigned char dv_open(const struct Panel* p){
 char path[64];unsigned char n;
 dv_file=NULL;dv_unit=0;dv_base=0;
 if(p->fs!=FS_DOS33)return 0;
 if(!p->img_len){dv_unit=p->dir_key;if(!(dv_unit&0x70)||(dv_unit&15))return 0;return 1;}
 n=p->img_len;if(n>=64)return 0;memcpy(path,p->path,n);path[n]=0;
 dv_file=fopn(path,"rb");if(!dv_file)return 0;
 if(n>4 && !strcmp(path+n-4,".2MG")){
  if(frd(A->copy_buf,1,64,dv_file)!=64||ferror(dv_file)||memcmp(A->copy_buf,"2IMG",4)||
     A->copy_buf[12]||A->copy_buf[13]||A->copy_buf[14]||A->copy_buf[15])goto bad;
  dv_base=(unsigned long)ds_word(A->copy_buf+24)|((unsigned long)ds_word(A->copy_buf+26)<<16);
  if(dv_base<64 || dv_base>0xFC0000UL || ds_word(A->copy_buf+28)!=0x3000 ||
     ds_word(A->copy_buf+30)!=2)goto bad; /* 143360 bytes */
 }
 return 1;
bad:dv_close();return 0;
}
