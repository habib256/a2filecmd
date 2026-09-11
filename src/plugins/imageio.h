/* Normalized 512-byte reads, from a ProDOS device or common image containers. */
struct Source { FILE* file; unsigned char unit,kind; unsigned int blocks; unsigned long base; char path[PATH_LEN]; };
static const unsigned char sectors[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};
static unsigned long image_size;
static unsigned char size_of(const char* path) {
    unsigned char i; static char dir[PATH_LEN], name[16];
    a.strcpy(dir,path);for(i=a.strlen(dir);i && dir[i]!='/';--i);
    if(!i)return 0;a.strcpy(name,dir+i+1);dir[i]=0;
    if(!a.dir_open(dir))return 0;
    while(a.dir_next())if(!a.strcmp(a.dir_entry->name,name)) {
        image_size=a.dir_entry->size;a.dir_close();return 1;
    }
    a.dir_close();return 0;
}
/* 0 unknown; 1 ProDOS order; 2 DOS sector order; 3 ProDOS 2MG. */
static unsigned char image_kind(const char* path) {
    unsigned char n=a.strlen(path);
    if(n>4 && !a.strcmp(path+n-4,".2MG"))return 3;
    if((n>4 && !a.strcmp(path+n-4,".DSK")) || (n>3 && !a.strcmp(path+n-3,".DO")))return 2;
    if((n>3 && !a.strcmp(path+n-3,".PO")) || (n>4 && !a.strcmp(path+n-4,".HDV")))return 1;
    return 0;
}
static unsigned char image_open(struct Source* s) {
    unsigned char n;unsigned long count;
    s->file=0;s->unit=0;s->base=0;s->kind=0;
    if(!size_of(s->path))return 0;
    n=image_kind(s->path);if(!n)return 0;s->kind=n-1;
    s->file=a.fopen(s->path,"rb");if(!s->file)return 0;
    if(s->kind==2) {
        if(a.fread(buf,1,64,s->file)!=64 || rd16(buf)!=0x4932 || rd16(buf+2)!=0x474D ||
           rd16(buf+8)<64 || rd16(buf+12)!=1 || rd16(buf+14) || rd16(buf+22) ||
           rd16(buf+26) || rd16(buf+24)<64)goto fail;
        s->base=rd16(buf+24);s->blocks=rd16(buf+20);
        count=(unsigned long)s->blocks*512;
        if(!s->blocks || count+s->base>image_size || rd24(buf+28)!=count || buf[31])goto fail;
    } else {
        if(image_size&511)goto fail;count=image_size>>9;
        if(!count || count>65535UL || (s->kind==1 && (count&7)))goto fail;
        s->blocks=(unsigned int)count;
    }
    return 1;
fail:a.fclose(s->file);s->file=0;return 0;
}
static unsigned char volume_open(struct Source* s,unsigned char requested) {
    s->file=0;s->unit=unit_of(s->path,requested);
    if(!s->unit || readblk(s->unit,2,buf) || (buf[4]>>4)!=15)return 0;
    s->blocks=rd16(buf+41);return s->blocks>=3;
}
static unsigned char source_read(struct Source* s,unsigned int b,unsigned char* out) {
    unsigned char half;unsigned long off;
    if(b>=s->blocks)return 0;
    if(s->unit)return !readblk(s->unit,b,out);
    if(s->kind!=1)return !a.fseek(s->file,s->base+(unsigned long)b*512,SEEK_SET) && a.fread(out,1,512,s->file)==512;
    for(half=0;half<2;++half) {
        off=((unsigned long)(b>>3)<<12)+((unsigned int)sectors[(b&7)*2+half]<<8);
        if(a.fseek(s->file,off,SEEK_SET) || a.fread(out+256*half,1,256,s->file)!=256)return 0;
    }
    return 1;
}
#ifdef IMAGEIO_WRITE
/* The mirror of source_read: one normalized 512-byte block back to the
 * device or to the container, the DOS 3.3 order undone the same way. */
static unsigned char source_write(struct Source* s,unsigned int b,const unsigned char* in) {
    unsigned char half;unsigned long off;
    if(b>=s->blocks)return 0;
    if(s->unit)return !writeblk(s->unit,b,in);
    if(s->kind!=1)return !a.fseek(s->file,s->base+(unsigned long)b*512,SEEK_SET) && a.fwrite(in,1,512,s->file)==512;
    for(half=0;half<2;++half) {
        off=((unsigned long)(b>>3)<<12)+((unsigned int)sectors[(b&7)*2+half]<<8);
        if(a.fseek(s->file,off,SEEK_SET) || a.fwrite(in+256*half,1,256,s->file)!=256)return 0;
    }
    return 1;
}
#endif
static void source_close(struct Source* s) {if(s->file)a.fclose(s->file);s->file=0;}
