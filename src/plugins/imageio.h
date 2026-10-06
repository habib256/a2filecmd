/* Normalized 512-byte reads, from a ProDOS device or common image containers. */
struct Source { FILE* file; unsigned char unit,kind; unsigned int blocks; unsigned long base; char path[PATH_LEN]; };
static const unsigned char sectors[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};
static unsigned long image_size;
#ifdef IMAGEIO_WRITE
/* cc65 opens "rb" O_RDONLY, so a writer needs "r+b". An image that cannot be
 * opened for update still opens read-only, to be looked at, and
 * source_write refuses it. ProDOS OPENs a LOCKED file for update and fails
 * only its WRITE, so the caller also sets this from the entry's write bit. */
static unsigned char image_readonly;
/* The writers are the overlays with no room to spare. Where util.h gave
 * one its service stubs (UTIL_STUBS), the calls below go through them: a
 * stub call costs a third of a call through the table, and IMGPUT's walk
 * of the image's claims was paid for with the difference. A reader keeps
 * the table calls it was built with, byte for byte. */
#define IMG(name) RF(name)
#else
#define IMG(name) a.name
#endif
#ifdef IMAGEIO_ONE
/* A writer that has one image and calls it `src` says IMAGEIO_ONE (with
 * IMAGEIO_WRITE and IMAGEIO_NODEVICE). What is below then reaches its
 * fields by address instead of through a pointer handed down the C stack:
 * half the bytes of every access, in the three overlays that had none
 * left. The `s` its callers still write is not evaluated. Everybody else
 * gets the pointer, and the code they always had. */
static struct Source src;
#define SRC(field) src.field
#else
#define SRC(field) s->field
#endif
#ifdef IMAGEIO_ONE
/* The image's length, from its entry in the directory that holds it. The
 * path is src's own, so it is cut in two where it stands for the time of
 * the search and joined again: the two copies the general form below makes
 * were eighty-one bytes of BSS. */
static unsigned char size_of1(void) {
    unsigned char i,found=0;
    for(i=IMG(strlen)(src.path);i && src.path[i]!='/';--i);
    if(!i)return 0;
    src.path[i]=0;
    if(a.dir_open(src.path)) {
        while(!found && a.dir_next())if(!IMG(strcmp)(a.dir_entry->name,src.path+i+1)) {
            image_size=a.dir_entry->size;found=1;
        }
        a.dir_close();
    }
    src.path[i]='/';
    return found;
}
#define size_of(path) size_of1()
#else
static unsigned char size_of(const char* path) {
    unsigned char i; static char dir[PATH_LEN], name[16];
    IMG(strcpy)(dir,path);for(i=IMG(strlen)(dir);i && dir[i]!='/';--i);
    if(!i)return 0;IMG(strcpy)(name,dir+i+1);dir[i]=0;
    if(!a.dir_open(dir))return 0;
    while(a.dir_next())if(!IMG(strcmp)(a.dir_entry->name,name)) {
        image_size=a.dir_entry->size;a.dir_close();return 1;
    }
    a.dir_close();return 0;
}
#endif
/* 0 unknown; 1 ProDOS order; 2 DOS sector order; 3 ProDOS 2MG. */
static unsigned char image_kind(const char* path) {
    unsigned char n=IMG(strlen)(path);
    if(n>4 && !IMG(strcmp)(path+n-4,".2MG"))return 3;
    if((n>4 && !IMG(strcmp)(path+n-4,".DSK")) || (n>3 && !IMG(strcmp)(path+n-3,".DO")))return 2;
    if((n>3 && !IMG(strcmp)(path+n-3,".PO")) || (n>4 && !IMG(strcmp)(path+n-4,".HDV")))return 1;
    return 0;
}
#ifdef IMAGEIO_ONE
#define image_open(s) image_open1()
static unsigned char image_open1(void) {
#else
static unsigned char image_open(struct Source* s) {
#endif
    unsigned char n;unsigned long count;
    SRC(file)=0;SRC(unit)=0;SRC(base)=0;SRC(kind)=0;
    if(!size_of(SRC(path)))return 0;
    n=image_kind(SRC(path));if(!n)return 0;SRC(kind)=n-1;
#ifdef IMAGEIO_WRITE
    image_readonly=0;SRC(file)=IMG(fopen)(SRC(path),"r+b");
    if(!SRC(file)){image_readonly=1;SRC(file)=IMG(fopen)(SRC(path),"rb");}
#else
    SRC(file)=IMG(fopen)(SRC(path),"rb");
#endif
    if(!SRC(file))return 0;
    if(SRC(kind)==2) {
        if(IMG(fread)(buf,1,64,SRC(file))!=64 || rd16(buf)!=0x4932 || rd16(buf+2)!=0x474D ||
           rd16(buf+8)<64 || rd16(buf+12)!=1 || rd16(buf+14) || rd16(buf+22) ||
           rd16(buf+26) || rd16(buf+24)<64)goto fail;
        SRC(base)=rd16(buf+24);SRC(blocks)=rd16(buf+20);
        count=(unsigned long)SRC(blocks)*512;
        if(!SRC(blocks) || count+SRC(base)>image_size || rd24(buf+28)!=count || buf[31])goto fail;
#ifdef IMAGEIO_WRITE
        /* The container's own write protection: bit 31 of its flags, the
         * top bit of header byte 19. Whoever set it said "do not change
         * this disk", and a writer that only looked at the ProDOS file's
         * access wrote into it all the same. */
        if(buf[19]&0x80)image_readonly=1;
#endif
    } else {
        if(image_size&511)goto fail;count=image_size>>9;
        if(!count || count>65535UL || (SRC(kind)==1 && (count&7)))goto fail;
        SRC(blocks)=(unsigned int)count;
    }
    return 1;
fail:IMG(fclose)(SRC(file));SRC(file)=0;return 0;
}
#ifndef IMAGEIO_NODEVICE
static unsigned char volume_open(struct Source* s,unsigned char requested) {
    SRC(file)=0;SRC(unit)=unit_of(SRC(path),requested);
    if(!SRC(unit) || readblk(SRC(unit),2,buf) || (buf[4]>>4)!=15)return 0;
    SRC(blocks)=rd16(buf+41);return SRC(blocks)>=3;
}
#endif
#ifdef IMAGEIO_WRITE
/* A writer reads and writes through one body: the same bounds, the same
 * seek and the same DOS 3.3 order undone, so the block a write lands on is
 * by construction the block its read-back fetches. Two copies of that
 * arithmetic cost the writers four hundred bytes they did not have.
 * source_put says which way the bytes go; source_read and source_write
 * set it and are what everything else calls. */
static unsigned char source_put;
#ifdef IMAGEIO_ONE
#define source_read(s,b,out) (source_put=0,source_rw(b,out))
#define source_write(s,b,in) (source_put=1,source_rw(b,(unsigned char*)(in)))
static unsigned char source_rw(unsigned int b,unsigned char* p) {
#else
#define source_read(s,b,out) (source_put=0,source_rw(s,b,out))
#define source_write(s,b,in) (source_put=1,source_rw(s,b,(unsigned char*)(in)))
static unsigned char source_rw(struct Source* s,unsigned int b,unsigned char* p) {
#endif
    unsigned char half;unsigned int n,got;unsigned long off;
    if(b>=SRC(blocks))return 0;
#ifndef IMAGEIO_NODEVICE
    if(SRC(unit)) {
        if(source_put)return !writeblk(SRC(unit),b,p);
        return !readblk(SRC(unit),b,p);
    }
#endif
    if(source_put && image_readonly)return 0;
    /* cc65's fread and fwrite refuse a stream whose error flag is set, and
     * fseek does not clear it: one failed write would fail every later
     * read and write of the session. Each block starts clean. */
    clearerr(SRC(file));
    for(half=0;half<2;++half) {
        if(SRC(kind)==1) {
            n=256;
            off=((unsigned long)(b>>3)<<12)+((unsigned int)sectors[(b&7)*2+half]<<8);
        } else {
            if(half)break;
            n=512;
            off=SRC(base)+(unsigned long)b*512;
        }
        if(IMG(fseek)(SRC(file),off,SEEK_SET))return 0;
        if(source_put)got=IMG(fwrite)(p,1,n,SRC(file));
        else got=IMG(fread)(p,1,n,SRC(file));
        if(got!=n)return 0;
        p+=256;
    }
    return 1;
}
#else
static unsigned char source_read(struct Source* s,unsigned int b,unsigned char* out) {
    unsigned char half;unsigned long off;
    if(b>=SRC(blocks))return 0;
#ifndef IMAGEIO_NODEVICE
    if(SRC(unit))return !readblk(SRC(unit),b,out);
#endif
    if(SRC(kind)!=1)return !a.fseek(SRC(file),SRC(base)+(unsigned long)b*512,SEEK_SET) && a.fread(out,1,512,SRC(file))==512;
    for(half=0;half<2;++half) {
        off=((unsigned long)(b>>3)<<12)+((unsigned int)sectors[(b&7)*2+half]<<8);
        if(a.fseek(SRC(file),off,SEEK_SET) || a.fread(out+256*half,1,256,SRC(file))!=256)return 0;
    }
    return 1;
}
#endif
#ifdef IMAGEIO_ONE
#define source_close(s) source_close1()
static void source_close1(void) {if(SRC(file))IMG(fclose)(SRC(file));SRC(file)=0;}
#else
static void source_close(struct Source* s) {if(SRC(file))IMG(fclose)(SRC(file));SRC(file)=0;}
#endif
