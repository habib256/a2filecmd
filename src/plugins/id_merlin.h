/* A tentative content match needs three complete assembly statements.
 * Inspect only IDREAD's immutable MAIN sample; the reader still validates
 * every source sector and close before displaying anything. */
static unsigned char id_assembly(void){
 unsigned int i=0,start,end,p,q,j;
 unsigned char c,count=0;
 static const char ops[]=
  "ADCANDASLBCCBCSBEQBITBMIBNEBPLBRKBVCBVSCLCCLDCLICLVCMPCPXCPY"
  "DECDEXDEYEORINCINXINYJMPJSRLDALDXLDYLSRNOPORAPHAPHPPLAPLPROLROR"
  "RTIRTSSBCSECSEDSEISTASTXSTYTAXTAYTSXTXATXSTYAMACHEXDFBEQUORG";
 while(i<n){
  start=i;
  while(i<n && b[i] && b[i]!=0x8D){
   c=b[i++];if(c!=32 && (c<0xA0 || c>0xFE))return 0;
  }
  if(i==n || !b[i])break;end=i++;
  if(start==end || b[start]==0xAA || b[start]==0xBB)continue;
  p=start;
  /* Column one is the optional label; instructions follow a space. */
  while(p<end && b[p]!=0xA0)++p;
  while(p<end && b[p]==0xA0)++p;
  q=p;while(q<end && b[q]!=0xA0)++q;
  if(q-p==1 && b[p]==0xBD){
   while(q<end && b[q]==0xA0)++q;
   if(q<end && (b[q]==0xA4 || (b[q]>=0xB0 && b[q]<=0xB9)))++count;
  }else if(q-p==3){
   for(j=0;j<sizeof(ops)-1;j+=3)
    if((b[p]&127)==ops[j] && (b[p+1]&127)==ops[j+1] && (b[p+2]&127)==ops[j+2]){++count;break;}
  }
  /* Saturate while continuing to reject invalid bytes later in sample. */
  if(count>3)count=3;
 }
 return count>=3;
}
static const char* merlin_content(void){
 if(e->type==4 && n && b[0]>=128 && id_assembly()){
  reader="MERLIN";return "Merlin assembler source?";
 }
 return NULL;
}
