/* Normal v1.06: 666-byte saved workspace, row-major 16-bit pool offsets,
 * then a variable cell pool. Byte zero of the pool is reserved. Each cell
 * has LE formula length, type/format byte, byte value length, value and
 * formula tokens. All pointers must name fully validated record starts.
 * Unused disk-sector padding can contain stale bytes; read it, never show
 * it as sheet data. Formula bytes remain visible, cached values are read
 * without executing expressions. Signature excludes the MP.* code modules. */
static unsigned char mp_header[666],mp_starts[1024];
static const unsigned char mp_bits[8]={1,2,4,8,16,32,64,128};
static unsigned int mp_pool,mp_length,mp_grid;
static unsigned int mp_word(const unsigned char* p){return (unsigned int)p[0]|((unsigned int)p[1]<<8);}
static unsigned char mp_seek(unsigned int off){
 if(rt_api.fseek(rt_file,(long)off,SEEK_SET)){rt_bad=1;return 0;}
 rt_pos=rt_len=0;rt_off=off;return 1;
}
static void mp_text(const char* s){while(*s && !rt_cancel)rt_put(*s++);}
static unsigned char mp_number(const unsigned char* v,unsigned char show){
 unsigned char digits[14],i,last=0,any=0;int point,exp;
 for(i=0;i<7;++i){
  if((v[i+1]&15)>9 || (v[i+1]>>4)>9){rt_invalid();return 0;}
  digits[i*2]=v[i+1]>>4;digits[i*2+1]=v[i+1]&15;
 }
 for(i=0;i<14;++i)if(digits[i]){any=1;last=i+1;}
 if(!any){if(show)rt_put('0');return 1;}
 exp=(int)(v[0]&127)-64;
 if(exp<-63 || exp>63 || !digits[0]){rt_invalid();return 0;}
 if(!show)return 1;
 if(v[0]&128)rt_put('-');
 if(exp>14 || exp<-6){
  rt_put('0'+digits[0]);if(last>1){rt_put('.');for(i=1;i<last;++i)rt_put('0'+digits[i]);}
  {char e[8];rt_api.sprintf(e,"E%d",exp-1);mp_text(e);}return 1;
 }
 if(exp<=0){rt_put('0');rt_put('.');for(point=exp;point<0;++point)rt_put('0');for(i=0;i<last;++i)rt_put('0'+digits[i]);}
 else {
  for(point=0;point<exp;++point)rt_put('0'+(point<14?digits[point]:0));
  if(last>exp){rt_put('.');for(i=exp;i<last;++i)rt_put('0'+digits[i]);}
 }
 return 1;
}
static unsigned char mp_cell(unsigned int offset,unsigned char show){
 unsigned int formula,i,total;unsigned char type,len,v[8];int raw;
 if(offset>=mp_length || !mp_seek(mp_pool+offset))return 0;
 raw=rt_get();if(raw<0){rt_invalid();return 0;}formula=raw;
 raw=rt_get();if(raw<0){rt_invalid();return 0;}formula|=(unsigned int)raw<<8;
 type=rt_get();raw=rt_get();if(raw<0){rt_invalid();return 0;}len=raw;
 if((type&0xB8) || !len || (unsigned long)offset+4+len+formula>mp_length){rt_invalid();return 0;}
 total=4+len+formula;
 if(type&64){
  for(i=0;i<len;++i){raw=rt_get();if(raw<32 || raw>=127){rt_invalid();return 0;}if(show)rt_put(raw);}
 }else{
  if(len!=8){rt_invalid();return 0;}
  for(i=0;i<8;++i){raw=rt_get();if(raw<0){rt_invalid();return 0;}v[i]=raw;}
  if(!mp_number(v,show))return 0;
 }
 if(formula && show)mp_text(" [formula tokens:");
 for(i=0;i<formula;++i){raw=rt_get();if(raw<0){rt_invalid();return 0;}
  if(show){rt_put(' ');rt_put("0123456789ABCDEF"[raw>>4]);rt_put("0123456789ABCDEF"[raw&15]);}}
 if(formula && show)rt_put(']');
 return 1;
}
static void rt_decode(void){
 unsigned int i,rows,cols,cells,offset,next,r,c;unsigned long size;int raw;
 char label[20];
 if(rt_api.selected->type!=0xF4){rt_invalid();return;}
 for(i=0;i<666;++i){raw=rt_get();if(raw<0){rt_invalid();return;}mp_header[i]=raw;}
 while(rt_get()>=0)if(rt_off>65535UL){rt_invalid();return;}
 if(rt_bad)return;size=rt_off;
 if(mp_header[0]!=8 || mp_header[1]!=0xE7 || mp_word(mp_header+2) ||
    mp_word(mp_header+4)!=0x10D6 || mp_word(mp_header+6)!=1){rt_invalid();return;}
 rows=mp_word(mp_header+628)+1;cols=mp_word(mp_header+630)+1;
 if(!rows || rows>255 || !cols || cols>63 || (unsigned long)rows*cols>4096UL){rt_invalid();return;}
 cells=rows*cols;mp_grid=mp_word(mp_header+652);mp_length=mp_word(mp_header+658);
 if(mp_grid!=cells*2 || mp_word(mp_header+654)!=mp_grid || mp_word(mp_header+656)!=mp_grid ||
    !mp_length || mp_length>8192 || mp_word(mp_header+660)!=mp_grid+mp_length ||
    mp_word(mp_header+662)!=mp_grid+mp_length || mp_word(mp_header+664)!=mp_grid+mp_length+1){rt_invalid();return;}
 mp_pool=666+mp_grid;
 if((unsigned long)mp_pool+mp_length>size){rt_invalid();return;}
 for(i=0;i<1024;++i)mp_starts[i]=0;
 offset=1;
 while(offset<mp_length){
  mp_starts[offset>>3]|=mp_bits[offset&7];
  if(!mp_cell(offset,0))return;
  next=rt_off-mp_pool;if(next<=offset){rt_invalid();return;}offset=next;
 }
 if(offset!=mp_length){rt_invalid();return;}
 for(r=1,i=0;r<=rows && !rt_cancel;++r){
  for(c=1;c<=cols && !rt_cancel;++c,++i){
   if(!mp_seek(666+i*2))return;
   raw=rt_get();if(raw<0){rt_invalid();return;}offset=raw;
   raw=rt_get();if(raw<0){rt_invalid();return;}offset|=(unsigned int)raw<<8;
   if(!offset)continue;
   if(offset>=mp_length || !(mp_starts[offset>>3]&mp_bits[offset&7])){rt_invalid();return;}
   rt_api.sprintf(label,"R%uC%u = ",r,c);mp_text(label);
   if(!mp_cell(offset,1))return;rt_put(13);
  }
 }
 if(cells==1 && mp_length==1){mp_text("Empty worksheet");rt_put(13);}
}
