/* A concrete content/metadata rule owns both the description and reader.
 * A suffix alone is a candidate; the reader still validates the full file. */
static const char* known(const char* label,const char* view){reader=view;return label;}
#include "ps_border_layout.h"
/* Read fixed sample offsets in a separate call. cc65 2.19 can reuse a
 * stale ptr1 across branches/calls when the sample is fixed at $0E00. */
static unsigned char __fastcall__ sample_byte(unsigned char offset){return b[offset];}
/* Same eight-byte discriminator as OPEN's album classifier. Full structural
 * validation still belongs to GMAGIC; the description remains a candidate. */
static unsigned char gm_candidate(void){
 static const unsigned char limits[]={0,2,8,1,8,1,1,0,2,0,2,0,2,0,2,0};
 unsigned char at=0,top=0,start=0,command,end;
 end=n<8?(unsigned char)n:8;
 if(!end || sample_byte(0)<0x20 || sample_byte(0)>=0xB0 || (sample_byte(0)&0x10))return 0;
 while(at<end){
  if(!b[at])return top>=10 && (top!=10 || start);
  command=b[at]>>4;
  if((b[at]&15)>=limits[command])return 0;
  if(command>top)top=command;if(command==8)start=1;
  at+=1+(limits[command]&3);
 }
 return end==8 && memcmp(b,b+3,3);
}
/* Keep this walk in its own function. cc65 2.19 can reuse ptr1 across
 * suffix() calls in extra(), although strcmp has overwritten that pointer.
 * A standalone walk initializes its pointer before inspecting the sample. */
static unsigned char vc_candidate(void){
 const unsigned char* q=b;unsigned char c;
 if((*q++&127)!='>')return 0;
 c=(*q++&127)-'A';if(c>=26)return 0;
 c=*q++&127;if((unsigned char)(c-'A')<26)c=*q&127;
 return (unsigned char)(c-'0')<10;
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
  /* A named FOTO pair must reach PURPLE's complete pair validation,
   * rather than showing just one plane as a generic 8K picture. */
  if(k!=0x8400 && k!=0xE001 && k!=0xE002 && !sz.w[1] &&
     !suffix(e->name,".FOTO1") && !suffix(e->name,".FOTO2") &&
     memcmp(b,"DGR",3) && (sample_byte(2)!='g' || sample_byte(3)!='s')){
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
 if(e->type==6 && n>=256 && sample_byte(0)==0x8D && sample_byte(2)>=32 && suffix(e->name,".MW"))return known("Magic Window?","MAGWIN");
 /* Claim INT-typed LISA sources before IDV1's second visit can offer RUN.
  * The reader validates the complete symbol table and token stream. */
 if(!id_dos && e->type==250 && e->aux>=0x4000 && e->aux<0x6000 && n>=16 &&
    word(b+2)>=16 && word(b+2)<sz.l && sample_byte(6)>0 && sample_byte(6)<128 &&
    sample_byte(7)>=2 && sample_byte(7)<128 && sample_byte(8)>=3 && sample_byte(8)<128)
  return known("LISA 8/16?","LISAV4");
 if(!id_dos && (e->type==0xFA || e->type==6) && e->aux>=0x1000 && e->aux<0x4000 && n>=4 && !(word(b+2)&7) && word(b+2)<=4096 && word(b)>0 && sz.l==4UL+word(b)+word(b+2) && strcmp(e->name,"ANIX.EQUATES"))return known("LISA v3?","LISAV3");
 if((e->type==6 || (!id_dos && e->type==0xF5)) && sz.l<=264 &&
    ps_border_layout(e->aux,(unsigned int)sz.l,e->type==0xF5))
  return known("Print Shop border?","PSBORDER");
 if(((e->type==6 && (e->aux==0x6000 || e->aux==0x5FF4)) ||
    (!id_dos && e->type==0xF5 && e->aux==0x1000 && sz.l>=392)) && n>=248 &&
    (!strncmp(e->name,"FONT.",5) || !strcmp(e->name,"UFONT")))
  return known("Print Shop font?","PSFONT");
 if(!id_dos && (e->type==4 || e->type==0x0B || e->type==6) && n>=9 &&
    sample_byte(0)==0x80 && sample_byte(1)==0x19 && sample_byte(4)==1 && !sample_byte(5) &&
    ((sample_byte(6)==0xB1 && sample_byte(7)==0xE2 && sample_byte(8)==2) ||
     (n>=14 && sample_byte(6)==0x19 && sample_byte(7)==1 && sample_byte(8)==0x86 && sample_byte(9)==0x19 && sample_byte(10)==10 && sample_byte(11)==1 && sample_byte(12)==20 && sample_byte(13)==20)))
  return known("MultiScribe?","MULTISCR");
 if(e->type==4 && n>=4 && (sample_byte(0)&127)=='.'){
  c=(sample_byte(1)&127)|32;k=(sample_byte(2)&127)|32;
  if((c=='l' && (k=='m'||k=='j')) || (c=='r' && (k=='m'||k=='j')) ||
     (c=='p' && k=='m') || (c=='c' && k=='j') || (c=='f' && (k=='j'||k=='f')))
   return known("Apple Writer layout?","APPLEWR");
 }
 /* Before S-C: a narrow Arlequin picture can pass for one source line. */
 if(!id_dos && (e->type==0xF8 || e->type==6) && n>=4 && sample_byte(2)=='g' && sample_byte(3)=='s')return known("Arlequin picture","ARLEQUIN");
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
 if(n>=128 && e->type==6 && !sample_byte(122) && !sample_byte(123) && sample_byte(124)==0x41 && sample_byte(125)==0x74 && sample_byte(126)<4)
  return known("MCS editor score?","MCS");
 if(e->type==6 && sz.l==2304 && n>=4){
  count=0;for(k=0;k+1<n;k+=2){
   if(!(b[k]>>1)&&!b[k+1])break;
   if(b[k]>=128 || !(b[k+1]&63)){count=0;break;}++count;
  }
  if(count)return known("MCS export?","MCS");
 }
 if(n>=27 && ((sample_byte(24)==0x90 && sample_byte(25)==0xF7 && sample_byte(26)==0xB2)||
    (sample_byte(24)==0x6F && sample_byte(25)==8 && sample_byte(26)==0x4D)))return known("Fontrix font","FONTRIX");
 if(!id_dos){
  if(e->type==6 && gm_candidate())return known("Graphics Magician picture?","GMAGIC");
  if(e->type==0xF4 && n>=4 && word(b+2)>=2)return known("LISA v2 source?","LISAV2");
  /* A .TEXT name alone: a Pascal text file is a 1,024-byte header and
   * whole 1,024-byte pages, never a TXT, a program or a system file. */
  if(e->type==0x03 || (e->type!=4 && e->type<0xF0 && suffix(e->name,".TEXT") &&
     !(sz.w[0]&1023) && (sz.w[1] || sz.w[0]>=2048)))
   return known("Apple Pascal text?","PASTEXT");
  if(e->type==0x50 && e->aux==0x5445)return known("Teach text","TEACHTXT");
  if(e->type==4 && n && sample_byte(0)=='_')return known("Epistole document?","DOCVIEW");
  if(e->type==4 && n && (sample_byte(0)==0xFF || sample_byte(0)==0xDF))return known("Papyrus/HomeWord?","DOCVIEW");
 }
 if((!id_dos || e->type==4) && (suffix(e->name,".ASM") || suffix(e->name,".S")) && n && sample_byte(0)>=128)
  return known("Merlin assembler source?","MERLIN");
 if(n>=4 && vc_candidate())
  return known("VisiCalc worksheet?","VISICALC");
 if(suffix(e->name,".MAC") || suffix(e->name,".PNTG"))return known("MacPaint picture?","MACPAINT");
 if(suffix(e->name,".AS") || (e->type==0xE0 && e->aux==1))return known("AppleSingle wrapper","UNWRAP");
 if(suffix(e->name,".BSC") || suffix(e->name,".BSQ"))return known("BinSCII wrapper","SCIIBIN");
 if(suffix(e->name,".QQ") || suffix(e->name,".ACU") || (n>=2 && sample_byte(0)==0x76 && sample_byte(1)==0xFF))return known("Squeezed data?","UNSQ");
 if(suffix(e->name,".SHAPE"))return known("Apple II shape table?","SHAPES");
 if(suffix(e->name,".BA3") || e->type==9)return known("Business BASIC","BASLIST");
 if(e->type==6 && (suffix(e->name,".SET")||suffix(e->name,".FONT")) && (sz.l==768||sz.l==1024))return known("HRCG hi-res font","FONTVIEW");
 if(!id_dos && e->type==6 && e->aux==0x8400 && sz.l>512 && sz.l<=9216)return known("Fantavision movie","RUN");
 if(e->type==6 && !strncmp(e->name,"MV.",3) && (e->aux==0x8029||!e->aux))return known("Take 1 movie?","RUN");
 return NULL;
}
