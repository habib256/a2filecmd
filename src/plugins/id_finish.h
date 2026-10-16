/* Detection and routing use the same reader result. DOS eligibility is explicit. */
static void id_finish(const struct A2fcApi* a,const struct Entry* e,const char* what,const char* reader,unsigned char dos){
 /* A DOS 3.3 file: its own reader (pairs: found, used; 0 = the same),
  * DOSVIEW for any other. */
 static const char* const dos_readers[]={"BASLIST","DOSBAS","INTBASIC","DOSINT","FONTVIEW","DOSFONT",
  "MCS","DOSMCS","NEWSROOM","DOSNEWS","PRINTSHOP",0,"FONTRIX",0,"MAGWIN",0,"PSBORDER",0,"PSFONT",0,
  "APPLEWR",0,"SCASM",0,"MERLIN",0,"LISAV2",0,"NEWSPAN",0,"NEWSPAGE",0};
 unsigned char i;
 unsigned char automatic=a->arg=='O'||a->arg=='I'||a->arg==13;
 if(automatic){
  if(dos){
   for(i=0;i<sizeof dos_readers/sizeof dos_readers[0];i+=2)
    if(!strcmp(reader,dos_readers[i]))break;
   if(i==sizeof dos_readers/sizeof dos_readers[0])reader="DOSVIEW";
   else if(dos_readers[i+1])reader=dos_readers[i+1];
  }
  a->strcpy(a->input,reader);return;
 }
 a->sprintf((char*)a->copy_buf,"%s (%lu bytes): %s",e->name,e->size,what);a->copy_buf[79]=0;
 a->strcpy(a->note,(char*)a->copy_buf);
}
