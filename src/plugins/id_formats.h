/* A concrete content/metadata rule owns both the description and reader.
 * A suffix alone is a candidate; the reader still validates the full file. */
static const char* known(const char* label,const char* view){reader=view;return label;}
#include "ps_border_layout.h"
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
 unsigned int k,count,prev;unsigned char c;const unsigned char* q;const unsigned char* line;
 /* n comes from the completed read and id_restore checks n <= fresh EOF. */
 /* OPEN's metadata first, as its classifier had it before any probe. A
  * Movie Maker sheet, or a BIN nearly a page long (8,184-8,199 or
  * 16,376-16,391 bytes; not 816/Paint's $E001-$E002 nor Fantavision's $8400)
  * unless it opens like a DGR pixmap or an Arlequin picture: a coincidence
  * in its first bytes (Graphics Magician, Merlin, code) must not take a
  * picture away from IMAGE. A FOT already goes there from identify(). */
 c=e->type;
 if(c==6){
  k=e->aux;
  if(k==0x1DF0 && !sz.w[1] && sz.w[0]==8720)return known("Movie Maker shape sheet","IMAGE");
  if(k!=0x8400 && k!=0xE001 && k!=0xE002 && !sz.w[1] && memcmp(b,"DGR",3) && (b[2]!='g' || b[3]!='s')){
   count=(sz.w[0]+8)&0xFFF0;
   if(count==8192 || count==16384)return known("Hi-res page","IMAGE");
  }
  /* A Bank Street Writer document: a BIN at $0840 or $63D0 (DOS
   * editions) or 0 (ProDOS), high-bit text throughout the sample; a
   * Merlin source keeps its .S. */
  if((!k || k==0x0840 || k==0x63D0) && !suffix(e->name,".S")){
   /* Walked with a pointer: cc65 2.19 miscompiles b[16-bit] on the
    * page-aligned sample (the pointer's low byte is never written). */
   for(q=b;q<b+n && *q>=128;++q);
   if(n && q==b+n)return known("Bank Street Writer document?","DOCVIEW");
  }
 }
 /* Terrapin Logo procedures: CR-ended text, often a B file at $2000. */
 if((c==4 || c==6) && suffix(e->name,".LOGO"))return known("Terrapin Logo procedures?","TEXT");
 if(e->type==6 && n>=256 && b[0]==0x8D && b[2]>=32 && suffix(e->name,".MW"))return known("Magic Window?","MAGWIN");
 if(!id_dos && (e->type==0xFA || e->type==6) && e->aux>=0x1000 && e->aux<0x4000 && n>=4 && !(word(b+2)&7) && word(b+2)<=4096 && word(b)>0 && sz.l==4UL+word(b)+word(b+2) && strcmp(e->name,"ANIX.EQUATES"))return known("LISA v3?","LISAV3");
 if((e->type==6 || (!id_dos && e->type==0xF5)) && sz.l<=264 &&
    ps_border_layout(e->aux,(unsigned int)sz.l,e->type==0xF5))
  return known("Print Shop border?","PSBORDER");
 if(((e->type==6 && (e->aux==0x6000 || e->aux==0x5FF4)) ||
    (!id_dos && e->type==0xF5 && e->aux==0x1000 && sz.l>=392)) && n>=248 &&
    (!strncmp(e->name,"FONT.",5) || !strcmp(e->name,"UFONT")))
  return known("Print Shop font?","PSFONT");
 if(!id_dos && (e->type==4 || e->type==0x0B || e->type==6) && n>=9 &&
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
 /* Before S-C: a narrow Arlequin picture can pass for one source line. */
 if(!id_dos && (e->type==0xF8 || e->type==6) && n>=4 && b[2]=='g' && b[3]=='s')return known("Arlequin picture","ARLEQUIN");
 /* S-C source: every whole line of the sample is a length, a line number
  * (rising, as the editor keeps them), text and a 0. Only a last line cut
  * by a full 512-byte sample goes unchecked. One line was not enough:
  * Take 1 actors and VCR Companion borders passed for source. */
 if((e->type==0xFA || (!id_dos && e->type==6)) && n>=4){
  /* Pointers, not b[16-bit]: see the Bank Street walk above. */
  line=b;prev=0;
  do{
   c=*line;
   if(line+c>b+n){if(line!=b && n==512)break;goto not_sc;}
   if(c<4 || line[c-1] || (line!=b && word(line+1)<=prev))goto not_sc;
   prev=word(line+1);
   q=line+3;line+=c;
   while(q<line-1){c=*q++;
    if(c>=32 && c<192)continue;
    if(c!=192 || q+1>=line-1 || !q[1] || q[1]>=127)goto not_sc;   /* a run may repeat a control (*SAVE's backspaces) */
    q+=2;
   }
  }while(line<b+n);
  return known("S-C Assembler source","SCASM");
 }
not_sc:
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
  /* A .TEXT name alone: a Pascal text file is a 1,024-byte header and
   * whole 1,024-byte pages, never a TXT, a program or a system file. */
  if(e->type==0x03 || (e->type!=4 && e->type<0xF0 && suffix(e->name,".TEXT") &&
     !(sz.w[0]&1023) && (sz.w[1] || sz.w[0]>=2048)))
   return known("Apple Pascal text?","PASTEXT");
  if(e->type==0x50 && e->aux==0x5445)return known("Teach text","TEACHTXT");
  if(e->type==4 && n && b[0]=='_')return known("Epistole document?","DOCVIEW");
  if(e->type==4 && n && (b[0]==0xFF || b[0]==0xDF))return known("Papyrus/HomeWord?","DOCVIEW");
 }
 if((!id_dos || e->type==4) && (suffix(e->name,".ASM") || suffix(e->name,".S")) && n && b[0]>=128)
  return known("Merlin assembler source?","MERLIN");
 if(n>=4 && (b[0]&127)=='>' && (unsigned char)((b[1]&127)-'A')<26 &&
    (unsigned char)((b[(unsigned char)((b[2]&127)-'A')<26?3:2]&127)-'0')<10)
  return known("VisiCalc worksheet?","VISICALC");
 if(suffix(e->name,".MAC") || suffix(e->name,".PNTG"))return known("MacPaint picture?","MACPAINT");
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
