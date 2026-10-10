/* Qualified A2CD00 ProDOS profile. Cells are 128 physical bytes, 126
 * payload plus a LE continuation. Fields contain length, x/y and text.
 * Reachable form/record cells are owned once; inactive/free/index areas
 * remain opaque. Complete physical I/O and reachable structural checks
 * precede the first display pass and close. No disk or AUX writes. */
#define PF_CAP 1024
static unsigned char pf_form[PF_CAP],pf_rec[PF_CAP],pf_used[256];
static unsigned int pf_labels[32],pf_cells,pf_have;
static unsigned char pf_nlabels;
static unsigned int pf_word(const unsigned char* p){return (unsigned int)p[0]|((unsigned int)p[1]<<8);}
static unsigned char pf_block(unsigned int cell){
 if(cell>=pf_cells){rt_invalid();return 0;}
 if(rt_api.fseek(rt_file,(unsigned long)cell*128UL,SEEK_SET) ||
    rt_api.fread(rt_api.copy_buf,1,128,rt_file)!=128 || ferror(rt_file)){
  rt_bad=1;return 0;
 }
 return 1;
}
static unsigned char pf_load(unsigned int cell,unsigned char* out){
 unsigned int i;unsigned char bit;
 pf_have=0;
 do{
  if(cell<64 || cell>=pf_cells || pf_have>PF_CAP-126){rt_invalid();return 0;}
  bit=1U<<(cell&7);
  if(pf_used[cell>>3]&bit){rt_invalid();return 0;}
  pf_used[cell>>3]|=bit;
  if(!pf_block(cell))return 0;
  for(i=0;i<126;++i)out[pf_have++]=rt_api.copy_buf[i];
  cell=pf_word(rt_api.copy_buf+126);
 }while(cell);
 return 1;
}
/* Validate a field without hiding unknown controls. $00 terminates each
 * padded field; $04 is its optional alignment byte. $01 introduces a
 * line break and an opaque layout byte (ignored in the text preview). */
static unsigned char pf_value(const unsigned char* p,unsigned int len){
 unsigned int i;unsigned char c;
 if(!len || p[len-1]){rt_invalid();return 0;}
 for(i=0;i<len-1;++i){
  c=p[i];
  if(!c || c==127 || c>=128){rt_invalid();return 0;}
  if(c==4){if(i!=len-2){rt_invalid();return 0;}continue;}
  if(c==1){
   if(i+1>=len-1 || p[i+1]<32 || p[i+1]>=127){rt_invalid();return 0;}
   ++i;
  }
 }
 return 1;
}
static void pf_text(const unsigned char* p,unsigned int len){
 unsigned int i;unsigned char c;
 for(i=0;i<len-1 && !rt_cancel;++i){
  c=p[i];if(c==4)continue;
  if(c==1){rt_put(13);rt_put(' ');rt_put(' ');++i;}
  else if(c<32){rt_put('^');rt_put(c+64);}
  else rt_put(c);
 }
}
static unsigned char pf_fields(unsigned char* p,unsigned char form){
 unsigned int at=12,length,end,i,best;
 unsigned char x,y,j,chosen;
 while(at+2<=pf_have){
  length=pf_word(p+at);
  if(!length){
   for(i=at;i<pf_have;++i)if(p[i]){rt_invalid();return 0;}
   return 1;
  }
  if(length<6 || (length&1) || length>pf_have-at || at+4>pf_have){rt_invalid();return 0;}
  end=at+length;x=p[at+2];y=p[at+3];
  if(x>=80 || y>=128 || !pf_value(p+at+4,length-4)){rt_invalid();return 0;}
  if(form){
   if(pf_nlabels==32){rt_invalid();return 0;}
   for(j=0;j<pf_nlabels;++j){i=pf_labels[j];if(p[i+2]==x && p[i+3]==y){rt_invalid();return 0;}}
   pf_labels[pf_nlabels++]=at;
  }else{
   best=0;chosen=255;
   for(j=0;j<pf_nlabels;++j){
    i=pf_labels[j];
    if(pf_form[i+3]==y && pf_form[i+2]<=x && (chosen==255 || pf_form[i+2]>best)){
     chosen=j;best=pf_form[i+2];
    }
   }
   if(chosen!=255){i=pf_labels[chosen];pf_text(pf_form+i+4,pf_word(pf_form+i)-4);rt_put(' ');}
   else {
    char coord[12];rt_api.sprintf(coord,"[%u,%u] ",(unsigned int)x,(unsigned int)y);
    for(i=0;coord[i];++i)rt_put(coord[i]);
   }
   pf_text(p+at+4,length-4);rt_put(13);
  }
  at=end;if(rt_cancel)return 1;
 }
 rt_invalid();return 0;
}
static unsigned char pf_header(const unsigned char* p){
 return !pf_word(p) && !pf_word(p+2) && pf_word(p+4)==1;
}
static void rt_decode(void){
 unsigned long size=0;
 unsigned int got,form,count,first,last,cur,previous=0,next,id,i;
 char title[32];
 if(rt_api.selected->type!=0x16 || rt_api.selected->aux!=1){rt_invalid();return;}
 /* Actual EOF, no panel-size bounds, and every physical byte read. */
 do{
  got=rt_api.fread(rt_api.copy_buf,1,512,rt_file);
  if(ferror(rt_file)){rt_bad=1;return;}
  size+=got;if(size>262144UL){rt_invalid();return;}
 }while(got);
 if(size<8320UL || (size&511)){rt_invalid();return;}
 pf_cells=(unsigned int)(size>>7);
 if(!pf_block(0))return;
 form=pf_word(rt_api.copy_buf);count=pf_word(rt_api.copy_buf+6);
 first=pf_word(rt_api.copy_buf+8);last=pf_word(rt_api.copy_buf+10);
 if(pf_word(rt_api.copy_buf+2)!=form || pf_word(rt_api.copy_buf+4)!=1 ||
    count>pf_cells-64 || (count?(!first || !last):(first || last))){rt_invalid();return;}
 for(i=0;i<6;++i)if(rt_api.copy_buf[16+i]!="A2CD00"[i]){rt_invalid();return;}
 for(i=0;i<256;++i)pf_used[i]=0;
 pf_nlabels=0;
 if(!pf_load(form,pf_form))return;
 if(!pf_header(pf_form) || pf_word(pf_form+6)!=0xBD98U || pf_word(pf_form+8) || pf_word(pf_form+10) ||
    !pf_fields(pf_form,1) || !pf_nlabels){rt_invalid();return;}
 cur=first;
 for(i=0;i<count && !rt_cancel;++i){
  if(!pf_load(cur,pf_rec))return;
  id=pf_word(pf_rec+6);next=pf_word(pf_rec+10);
  if(!pf_header(pf_rec) || !id || id==0xFFFFU || id==0xBD98U ||
     pf_word(pf_rec+8)!=previous || (i==count-1?(cur!=last || next):!next)){
   rt_invalid();return;
  }
  rt_api.sprintf(title,"Record %u/%u (ID %u)",i+1,count,id);
  {unsigned char j;for(j=0;title[j];++j)rt_put(title[j]);}rt_put(13);
  if(!pf_fields(pf_rec,0))return;
  rt_put(13);previous=cur;cur=next;
 }
 if(!count){
  rt_put('[');rt_put('0');rt_put(']');rt_put(13);
 }
}
