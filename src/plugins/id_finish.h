/* Detection and routing use the same reader result. DOS eligibility is explicit. */
static void id_finish(const struct A2fcApi* a,const struct Entry* e,const char* what,const char* reader,unsigned char dos){
 unsigned char automatic=a->arg=='O'||a->arg=='I'||a->arg==13;
 if(automatic){
  if(dos){
   if(!strcmp(reader,"BASLIST"))reader="DOSBAS";
   else if(!strcmp(reader,"INTBASIC"))reader="DOSINT";
   else if(!strcmp(reader,"MCS"))reader="DOSMCS";
   else if(!strcmp(reader,"NEWSROOM"))reader="DOSNEWS";
   else if(strcmp(reader,"SCASM") && strcmp(reader,"NEWSPAN") && strcmp(reader,"NEWSPAGE"))reader="DOSVIEW";
  }
  a->strcpy(a->input,reader);return;
 }
 a->sprintf((char*)a->copy_buf,"%s (%lu bytes): %s",e->name,e->size,what);a->copy_buf[79]=0;
 a->strcpy(a->note,(char*)a->copy_buf);
}
