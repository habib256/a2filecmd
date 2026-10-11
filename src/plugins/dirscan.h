/* Bounded directory iteration, with one cached block and no open handle
 * across calls. Position includes deleted entries, so no 255-entry limit.
 * Reads only directories in main RAM. Reject stream errors before caching
 * or exposing entries to callers such as SYNC, which can replace files. */
static unsigned char dirbuf[512], raw[39];
static char cachedpath[PATH_LEN];
static unsigned int cachedblock;
static void dir_reset(void){cachedpath[0]=0;}
static unsigned char dir_begin(const char* path,unsigned int* blocks) {
    FILE* f;
    if(getinfo(path) || (info.storage!=13 && info.storage!=15))return 0;
    *blocks=info.blocks;
    if(info.storage==15) {
        /* GET_FILE_INFO on a volume returns all allocated blocks, not
         * the root directory length. Count its linked blocks instead;
         * roots need not be four blocks. Keep the allocation as a bound.
         * https://prodos8.com/docs/techref/calls-to-the-mli/#445---get_file_info-c4 */
        f=a.fopen(path,"rb");if(!f)return 0;
        *blocks=0;
        do {
            if(stop() || *blocks==info.blocks || a.fread(buf,1,512,f)!=512 || ferror(f)) {
                a.fclose(f);return 0;
            }
            ++*blocks;
        } while(rd16(buf+2));
        if(a.fclose(f))return 0;
    }
    return *blocks!=0;
}
/* 1 entry, 0 end, 2 malformed/unreadable. */
static unsigned char dir_next(const char* path,unsigned int blocks,unsigned long* pos) {
    unsigned int b;unsigned char slot,n,c;FILE* f;
    while(*pos<(unsigned long)blocks*13) {
        b=(unsigned int)(*pos/13);slot=(unsigned char)(*pos%13);++*pos;
        if(!b && !slot)continue;
        if(a.strcmp(cachedpath,path)||cachedblock!=b) {
            f=a.fopen(path,"rb");if(!f)return 2;
            if(a.fseek(f,(unsigned long)b*512,SEEK_SET)||a.fread(dirbuf,1,512,f)!=512||ferror(f)){a.fclose(f);return 2;}
            if(a.fclose(f))return 2;
            if(!b && ((dirbuf[4]>>4)<14 || dirbuf[35]!=39 || dirbuf[36]!=13))return 2;
            a.strcpy(cachedpath,path);cachedblock=b;
        }
        a.memcpy(raw,dirbuf+4+39*slot,39);
        n=raw[0]&15;if(!(raw[0]>>4))continue;
        if(!n || (raw[0]>>4)>13)return 2;
        /* Raw directory bytes are not trusted path components. A slash,
         * NUL or dot-leading name could change the path built by a caller
         * (SYNC writes it). ProDOS names start with A-Z, then use A-Z,
         * digits or dots; case flags are separate from these name bytes. */
        if(raw[1]<'A' || raw[1]>'Z')return 2;
        do {
            c=raw[n];
            if((c<'A' || c>'Z') && (c<'0' || c>'9') && c!='.')return 2;
        }while(--n);
        return 1;
    }
    return 0;
}
static void rawname(char* name){unsigned char n=raw[0]&15;a.memcpy(name,raw+1,n);name[n]=0;}
