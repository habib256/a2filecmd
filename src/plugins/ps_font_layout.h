/* Shared Print Shop font bounds. The caller supplies the complete header
 * and freshly measured logical EOF. No I/O, source or AUX writes. */
static unsigned int psf_base,psf_data_start;
static unsigned char psf_start,psf_count;
static const unsigned char* psf_header;
static unsigned int ps_font_pointer(unsigned char i){
 return (unsigned int)psf_header[psf_start+(unsigned int)psf_count*2+i]|
        ((unsigned int)psf_header[psf_start+(unsigned int)psf_count*3+i]<<8);
}
static unsigned char ps_font_layout(const unsigned char* h,unsigned int actual,unsigned int aux,unsigned char modern){
 unsigned int p,len;unsigned char i,w,height;
 psf_header=h;
 if(modern){if(aux!=0x1000)return 0;psf_base=0;psf_start=12;psf_count=95;}
 else {if(aux!=0x6000 && aux!=0x5FF4)return 0;psf_base=aux;psf_start=aux==0x6000?0:12;psf_count=59;}
 psf_data_start=psf_start+(unsigned int)psf_count*4;
 if(actual<psf_data_start || actual>16384)return 0;
 if(modern && ((unsigned int)h[6]|((unsigned int)h[7]<<8))!=actual-psf_data_start)return 0;
 /* Space has no bitmap; '@' is an external graphic placeholder. */
 for(i=1;i<psf_count;++i){
  if(i==32)continue;
  w=h[psf_start+i]&127;height=h[psf_start+psf_count+i];p=ps_font_pointer(i);
  if(w>48 || height>64)return 0;
  if(modern){if(p>actual-psf_data_start)return 0;p+=psf_data_start;}
  else if(p<psf_base+psf_data_start)return 0;
  len=((unsigned int)w+7)/8*height;
  if((unsigned long)p+len>(unsigned long)psf_base+actual)return 0;
 }
 return 1;
}
