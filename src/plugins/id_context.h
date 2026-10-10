/* Private, little-endian read-only identification context in other_full. */
static unsigned int word(const unsigned char* p){return (unsigned int)p[0]|((unsigned int)p[1]<<8);}
static void id_context(const struct A2fcApi* a,unsigned int n,unsigned long size,unsigned int aux,unsigned char type){
 unsigned char* m=(unsigned char*)a->other_full;
 m[0]=n;m[1]=n>>8;m[2]=size;m[3]=size>>8;m[4]=size>>16;m[5]=size>>24;
 m[6]=aux;m[7]=aux>>8;m[8]=type;m[40]='I';m[41]='D';m[42]=0;
 m[48]=a->selected->mdate;m[49]=a->selected->mdate>>8;memcpy(m+50,a->selected->name,NAME_LEN);
}
static unsigned char id_restore(const struct A2fcApi* a,struct Entry* e,unsigned int* n){
 unsigned char* m=(unsigned char*)a->other_full;
 if(!m || m[40]!='I' || m[41]!='D' || word(m+48)!=a->selected->mdate || memcmp(m+50,a->selected->name,NAME_LEN))return 0;
 *e=*a->selected;e->type=m[8];e->aux=word(m+6);
 e->size=(unsigned long)word(m+2)|((unsigned long)word(m+4)<<16);*n=word(m);
 return *n<=512 && *n<=e->size && e->type==a->selected->type;
}
