/* A concrete content/metadata rule owns both the description and reader.
 * A suffix alone is a candidate; the reader still validates the full file. */
static const char* known(const char* label,const char* view){reader=view;return label;}
/* Same eight-byte discriminator as OPEN's album classifier. Full structural
 * validation still belongs to GMAGIC; the description remains a candidate. */
static unsigned char gm_candidate(void){
 static const unsigned char limits[]={0,2,8,1,8,1,1,0,2,0,2,0,2,0,2,0};
 unsigned char at=0,top=0,start=0,command,end;
 end=n<8?(unsigned char)n:8;
 if(!end || b[0]<0x20 || b[0]>=0xB0 || (b[0]&0x10))return 0;
 while(at<end){
  if(!b[at])return top>=10 && (top!=10 || start);
  command=b[at]>>4;
  if((b[at]&15)>=limits[command])return 0;
  if(command>top)top=command;if(command==8)start=1;
  at+=1+(limits[command]&3);
 }
 return end==8 && memcmp(b,b+3,3);
}
static const char* extra(void){
 unsigned int k,count;unsigned char c;
 if(e->type==6 && n>=256 && sz.l>=256 && b[0]==0x8D && b[2]>=32 && suffix(e->name,".MW"))return known("Magic Window?","MAGWIN");
 if(!id_dos && e->type==0xFA && e->aux>=0x1000 && e->aux<0x4000 && n>=4 && !(word(b+2)&7) && word(b+2)<=4096 && word(b)>0 && sz.l==4UL+word(b)+word(b+2) && strcmp(e->name,"ANIX.EQUATES"))return known("LISA v3?","LISAV3");
 if(((e->type==6 && (e->aux&0xCFFF)==0x4800 && (sz.l==144 || sz.l==148)) ||
    (!id_dos && e->type==0xF5 && e->aux==0x2000 && sz.l==264)) &&
    !strncmp(e->name,"BORD.",5))return known("Print Shop border?","PSBORDER");
 if(((e->type==6 && (e->aux==0x6000 || e->aux==0x5FF4)) ||
    (!id_dos && e->type==0xF5 && e->aux==0x1000 && sz.l>=392)) && n>=248 && sz.l>=248 &&
    (!strncmp(e->name,"FONT.",5) || !strcmp(e->name,"UFONT")))
  return known("Print Shop font?","PSFONT");
 if(!id_dos && (e->type==4 || e->type==0x0B) && n>=9 &&
    b[0]==0x80 && b[1]==0x19 && b[4]==1 && !b[5] &&
    ((b[6]==0xB1 && b[7]==0xE2 && b[8]==2) ||
     (n>=14 && b[6]==0x19 && b[7]==1 && b[8]==0x86 && b[9]==0x19 && b[10]==10 && b[11]==1 && b[12]==20 && b[13]==20)))
  return known("MultiScribe?","MULTISCR");
 if(e->type==4 && n>=4 && (b[0]&127)=='.'){
  c=(b[1]&127)|32;k=(b[2]&127)|32;
  if((c=='l' && (k=='m'||k=='j')) || (c=='r' && (k=='m'||k=='j')) ||
     (c=='p' && k=='m') || (c=='c' && k=='j') || (c=='f' && (k=='j'||k=='f')))
   return known("Apple Writer layout?","APPLEWR");
 }
 if(e->type==0xFA && n>=4 && b[0]>=4 && b[0]<=n && !b[b[0]-1]){
  k=3;while(k<(unsigned int)b[0]-1U){c=b[k++];
   if(c>=32 && c<192)continue;
   if(c!=192 || k+1>=(unsigned int)b[0]-1U || b[k+1]<32 || b[k+1]>=127)return NULL;
   k+=2;
  }
  return known("S-C Assembler source","SCASM");
 }
 if(e->type==6 && e->aux==0x4000 && e->name[2]=='.'){
  if((e->name[0]=='P'&&e->name[1]=='H')||(e->name[0]=='B'&&e->name[1]=='N'))
   return known("Newsroom photo","NEWSROOM");
  if(e->name[0]=='P'&&e->name[1]=='N')return known("Newsroom panel","NEWSPAN");
 }
 if(e->type==6 && e->aux==0x98A5 && !strncmp(e->name,"PG.",3))return known("Newsroom page layout","NEWSPAGE");
 if(n>=128 && e->type==6 && !b[122] && !b[123] && b[124]==0x41 && b[125]==0x74 && b[126]<4)
  return known("MCS editor score?","MCS");
 if(e->type==6 && sz.l==2304 && n>=4){
  count=0;for(k=0;k+1<n;k+=2){
   if(!(b[k]>>1)&&!b[k+1])break;
   if(b[k]>=128 || !(b[k+1]&63)){count=0;break;}++count;
  }
  if(count)return known("MCS export?","MCS");
 }
 if(n>=27 && ((b[24]==0x90 && b[25]==0xF7 && b[26]==0xB2)||
    (b[24]==0x6F && b[25]==8 && b[26]==0x4D)))return known("Fontrix font","FONTRIX");
 if(!id_dos){
  if(e->type==6 && gm_candidate())return known("Graphics Magician picture?","GMAGIC");
  if(e->type==0xF4 && n>=4 && word(b+2)>=2)return known("LISA v2 source?","LISAV2");
  if(e->type==0x03 || suffix(e->name,".TEXT"))return known("Apple Pascal text?","PASTEXT");
  if(e->type==0x50 && e->aux==0x5445)return known("Teach text","TEACHTXT");
  if(e->type==0xF8 && n>=4 && b[2]=='g' && b[3]=='s')return known("Arlequin picture","ARLEQUIN");
  if(e->type==4 && n && b[0]=='_')return known("Epistole document?","DOCVIEW");
  if(e->type==4 && n && (b[0]==0xFF || b[0]==0xDF))return known("Papyrus/HomeWord?","DOCVIEW");
  if((suffix(e->name,".ASM") || suffix(e->name,".S")) && n && b[0]>=128)
   return known("Merlin assembler source?","MERLIN");
 }
 if(n>=4 && (b[0]&127)=='>' && b[1]>='A' && b[1]<='Z' && b[2]>='0' && b[2]<='9')
  return known("VisiCalc worksheet?","VISICALC");
 if(suffix(e->name,".MAC"))return known("MacPaint picture?","MACPAINT");
 if(suffix(e->name,".AS") || (e->type==0xE0 && e->aux==1))return known("AppleSingle wrapper","UNWRAP");
 if(suffix(e->name,".BSC") || suffix(e->name,".BSQ"))return known("BinSCII wrapper","SCIIBIN");
 if(suffix(e->name,".QQ") || suffix(e->name,".ACU") || (n>=2 && b[0]==0x76 && b[1]==0xFF))return known("Squeezed data?","UNSQ");
 if(suffix(e->name,".SHAPE"))return known("Apple II shape table?","SHAPES");
 if(suffix(e->name,".BA3") || e->type==9)return known("Business BASIC","BASLIST");
 if(e->type==6 && (suffix(e->name,".SET")||suffix(e->name,".FONT")) && (sz.l==768||sz.l==1024))return known("HRCG hi-res font","FONTVIEW");
 if(!id_dos && e->type==6 && e->aux==0x8400 && sz.l>512 && sz.l<=9216)return known("Fantavision movie","RUN");
 if(e->type==6 && !strncmp(e->name,"MV.",3) && (e->aux==0x8029||!e->aux))return known("Take 1 movie?","RUN");
 return NULL;
}
