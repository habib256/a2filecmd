/* Independent streaming decoders, derived from corpus bytes and the Apple
 * Writer manual. Only MAIN buffers/text screen are written. Never execute
 * WPL, includes, printer commands or mail merge. Unknown commands stay visible.
 * MultiScribe fonts/rulers are structural metadata; plain-text approximation. */
#if RT_FORMAT == 9
static void rt_decode(void){
 unsigned char h[14],newer;
 unsigned int i,header;
 int c,end;
 for(i=0;i<9;++i){c=rt_get();if(c<0){rt_invalid();return;}h[i]=c;}
 if(h[0]!=0x80 || h[1]!=0x19 || h[4]!=1 || h[5]){rt_invalid();return;}
 newer=h[6]==0x19 && h[7]==1 && h[8]==0x86;
 if(newer){
  for(i=9;i<14;++i){c=rt_get();if(c<0){rt_invalid();return;}h[i]=c;}
  if(h[9]!=0x19 || h[10]!=10 || h[11]!=1 || h[12]!=20 || h[13]!=20){rt_invalid();return;}
  header=295;
 }else {
  if(h[6]!=0xB1 || h[7]!=0xE2 || h[8]!=2){rt_invalid();return;}
  header=37;
 }
 /* Last header byte closes the first ruler. No text discarded at offset 37. */
 end=-1;while(rt_off<header){end=rt_get();if(end<0){rt_invalid();return;}}
 if(end!=2){rt_invalid();return;}
 while(!rt_cancel && (c=rt_get())>=0){
  if(c==1){
   for(i=0;i<3;++i)if(rt_get()<0){rt_invalid();return;}
   if(rt_get()!=1){rt_invalid();return;}
  }else if(c==2){
   /* A changed ruler contains 27 bytes followed by its closing $02. */
   for(i=0;i<27;++i)if(rt_get()<0){rt_invalid();return;}
   if(rt_get()!=2){rt_invalid();return;}
  }else if(c==3){rt_put(13);}
  else if(c==9){rt_spaces(8-(rt_col&7));}
  else if(c==13 || (c>=32 && c<127)){rt_put(c);}
  else {rt_invalid();return;}
 }
}
#else
static unsigned char wd_line[79],wd_word[79],wd_cmd[79];
static unsigned char wd_len,wd_n,wd_left,wd_right,wd_first,wd_mode,wd_gap;
static signed char wd_para;
static unsigned char wd_start(void){
 int start=wd_left;
 if(wd_first)start+=wd_para;
 if(start<0)start=0;if(start>=wd_right)start=wd_left;
 return (unsigned char)start;
}
static void wd_flush(unsigned char paragraph){
 unsigned char i,start=wd_start(),extra=0;
 if(wd_mode==1)extra=(wd_right-start-wd_len)/2;
 if(wd_mode==2)extra=wd_right-start-wd_len;
 rt_spaces(start+extra);
 for(i=0;i<wd_len && !rt_cancel;++i)rt_put(wd_line[i]);
 rt_put(13);wd_len=wd_gap=0;wd_first=paragraph;
}
static void wd_add(void){
 unsigned char i,width=wd_right-wd_start();
 if(!wd_n)return;
 if(wd_len && wd_len+1+wd_n>width){wd_flush(0);width=wd_right-wd_start();}
 if(wd_len && wd_gap)wd_line[wd_len++]=' ';
 for(i=0;i<wd_n && !rt_cancel;++i){
  if(wd_len==width){wd_flush(0);width=wd_right-wd_start();}
  wd_line[wd_len++]=wd_word[i];
 }
 wd_n=0;wd_gap=1;
}
static void wd_text(unsigned char c){
 if(c==13){wd_add();wd_flush(1);return;}
 if(c==' ' || c==9){wd_add();wd_gap=1;return;}
 if(wd_n==79)wd_add();wd_word[wd_n++]=c;
}
static unsigned char wd_command(unsigned char n){
 unsigned char a,b,i,negative=0;
 int value=0;
 if(n<3 || wd_cmd[0]!='.')return 0;
 a=wd_cmd[1]|32;b=wd_cmd[2]|32;
 if((a=='l'||a=='r'||a=='p') && b=='m'){
  i=3;while(i<n && wd_cmd[i]==' ')++i;
  if(i<n && (wd_cmd[i]=='+'||wd_cmd[i]=='-'))negative=wd_cmd[i++]=='-';
  if(i==n)return 0;
  for(;i<n;++i){if(wd_cmd[i]<'0'||wd_cmd[i]>'9')return 0;
   value=value*10+wd_cmd[i]-'0';if(value>79)return 0;}
  if(negative)value=-value;
  if(a=='p'){wd_para=value;return 1;}
  if(negative)return 0;
  if(a=='l' && value<wd_right){wd_left=value;return 1;}
  if(a=='r' && value>wd_left && value<=79){wd_right=value;return 1;}
  return 0;
 }
 if(n!=3)return 0;
 if(b=='j'){
  if(a=='l'||a=='f')wd_mode=0;
  else if(a=='c')wd_mode=1;else if(a=='r')wd_mode=2;else return 0;
  return 1;
 }
 if(a=='f' && b=='f'){rt_put(13);return 1;}
 return 0;
}
static void rt_decode(void){
 int raw;
 unsigned char c,sol=1,command=0,n=0,i,ended=0,lf=0;
 wd_len=wd_n=wd_left=wd_mode=wd_gap=0;wd_right=79;wd_para=0;wd_first=1;
 while(!rt_cancel && (raw=rt_get())>=0){
  if(ended)continue;
  c=raw&127;
  if(!c){
#ifdef RT_DOS
   if(rt_dos){ended=1;continue;}
#endif
   rt_invalid();return;
  }
  if(c==10 && lf){lf=0;continue;}lf=c==13;
  if(c==10 || c==12)c=13;
  if(c<32 && c!=9 && c!=13){rt_invalid();return;}
  if(sol){command=c=='.';n=0;sol=0;}
  if(command){
   if(c==13){
    if(!wd_command(n)){for(i=0;i<n;++i)wd_text(wd_cmd[i]);wd_text(13);}
    command=0;sol=1;continue;
   }
   if(n<79){wd_cmd[n++]=c;continue;}
   for(i=0;i<n;++i)wd_text(wd_cmd[i]);command=0;
  }
  wd_text(c);if(c==13)sol=1;
 }
 if(!rt_cancel){
  if(command && !wd_command(n))for(i=0;i<n;++i)wd_text(wd_cmd[i]);
  wd_add();if(wd_len)wd_flush(1);
 }
}
#endif
