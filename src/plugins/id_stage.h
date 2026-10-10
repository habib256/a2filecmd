/* Private IDENT relay: source/stage closed before loading, sample at $0E00-$0FFF.
 * Only one FILE is open; no AUX, source writes or extracted files. */
#ifdef A2FC_6502
#define ID_CPU_TAG 1
#else
#define ID_CPU_TAG 129
#endif
const unsigned char md_cpu_tag=ID_CPU_TAG;
FILE* md_player;
static unsigned char id_open_stage(const struct A2fcApi* a,const char* name){
 unsigned char n;char* slash;
 n=strlen(a->cfg_path);if(n>=PATH_LEN)return 0;
 memcpy(a->full,a->cfg_path,n+1);slash=strrchr(a->full,'/');
 if(!slash || slash==a->full || (unsigned int)(slash-a->full)+1+strlen(name)>=PATH_LEN)return 0;
 strcpy(slash+1,name);a->dir_close();md_player=a->fopen(a->full,"rb");return md_player!=NULL;
}
#ifdef PLUGIN_HOST
extern unsigned char host_id_sample[512];
#define ID_SAMPLE host_id_sample
#else
#define ID_SAMPLE ((unsigned char*)0x0E00)
#endif
