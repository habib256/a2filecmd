/* Content candidates only: readers validate physical EOF and full structure.
 * Separate detector keeps the 6502 IDENT overlays within their fixed bounds. */
#ifndef PLUGIN_HOST
static const char* known(const char* label,const char* view){reader=view;return label;}
#endif
static const char* extra_v1(void){
 unsigned int i;
 if(e->type==6 && e->aux==0x6000 && suffix(e->name,".MVM") && n>=3 && b[0]==1 && word(b+1)==256)return known("Movie Maker preview?","MVMOVIE");
 if(e->type==6 && suffix(e->name,".DPC") && n>=3)return known("Graphics Magician DHGR?","DGMAGI");
 if(e->type==6 && e->aux==0x4000 && suffix(e->name,".PB") && n>=29 && b[28])return known("PCS static preview?","PCSVW");
 if(!id_dos && e->type==0xF4 && n>=8 && word(b)==0xE708 && !word(b+2) && word(b+4)==0x10D6 && word(b+6)==1)return known("Multiplan normal 1.06?","MULTPLAN");
 if(!id_dos && e->type==0xA0 && !e->aux && n)return known("WordPerfect?","WORDPERF");
 if(!id_dos && e->type==0xF1 && !e->aux && n>=28 && b[0]=='M' && b[1]=='W' &&
    (b[2]==1 || b[2]==4 || b[2]==5) && !b[3] && b[4]==2 &&
    b[26]>0 && b[26]<=120 && !b[27])return known("MouseWrite?","MOUSEWR");
 if(e->type==6 && n>=20){
  for(i=0;i<10;++i)if(b[i]!=(unsigned char)("AFILER 1.0"[i]|128))break;
  if(i==10)return known("Bank Street Filer?","BSFILER");
 }
 return NULL;
}
