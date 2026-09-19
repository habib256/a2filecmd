/* imgput.c -- a ProDOS file copied INTO the directory a panel has open
 * inside a ProDOS disk image. The image was read-only until now: C extracted
 * files out of it (IMGFS) and nothing ever put one back.
 *
 * From the ! menu, with the file selected in the active panel and the image
 * open in the other -- the same arrangement DOSWRITE uses for a real DOS 3.3
 * disk, and DOSIMAGE/DOSPUT for a DOS 3.3 image.
 *
 * This is a second ProDOS writer, and that is the whole difficulty: ProDOS
 * is not doing the writing, so nothing checks our work. Three structures of
 * the image have to stay consistent with each other -- the volume bitmap,
 * the directory entry, and the file's own index block -- and the order in
 * which they reach the file decides what an interruption costs:
 *
 *   1. The image is explained or nothing is written: block 2 must read as a
 *      volume header, its bitmap must lie inside the volume, and the
 *      directory the panel shows must chain back to it.
 *   2. The room is counted before anything moves. The name must be free in
 *      that directory, and a slot must be free too.
 *   3. The data blocks and the index block are written into blocks the
 *      bitmap still calls free, then read back and compared.
 *   4. The bitmap is written: from here the blocks are ours.
 *   5. One directory block, one write: the entry and the file count. From
 *      that instant the name means the file.
 *
 * A cut before 4 changes nothing at all -- the blocks written to were free
 * and stay free, and the directory never heard of them. A cut between 4 and
 * 5 loses their space and nothing else; FIXIT finds them, and the message
 * says so rather than calling the work done. None of this is atomic and
 * none of it pretends to be: ProDOS offers no such promise, and no more do
 * we.
 *
 * What it does not do yet, and says so instead of guessing: a file that
 * needs a tree (above 128 KB), a directory with no free slot (extending the
 * chain is a write of its own), and an image whose file is locked or which
 * ProDOS will not open for update.
 */
#define UTIL_STUBS
#define IMAGEIO_WRITE
/* Only ever a file: no device path, and with it no unit_of, readblk or
 * writeblk compiled in for branches this overlay can never take. */
#define IMAGEIO_NODEVICE

#include "util.h"
#include "imageio.h"
#include <string.h>

void __fastcall__ plugin_entry(const struct A2fcApi*);

struct Header { unsigned int magic; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[52]; };
#ifndef PLUGIN_HOST
#pragma rodata-name(push,"OVLHDR")
#endif
const struct Header __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},
 "ProDOS image: copy the selected file into it"};
#ifndef PLUGIN_HOST
#pragma rodata-name(pop)
#endif

/* Two 512-byte buffers of our own, and api->copy_buf for the data block on
 * its way in: the window is $1B00-$3FFF and four buffers overflowed it by
 * 1638 bytes. `dirb` doubles as the bitmap page -- the directory and the
 * bitmap are never needed at the same instant -- and the read-back of a
 * write goes into whichever of the two is idle, which is why put_verified
 * is told where to put it. */
static unsigned char dirb[512], idx[512];
#define bits dirb
static struct Source src;
static FILE* source;
static unsigned int vol_blocks, bm_first;
static unsigned int bm_page;            /* page held in bits[]; NOPAGE = none */
static unsigned char bm_dirty;
static unsigned int scan;               /* next block the walk will consider */
/* The first block a file may ever have. Below it lie the boot blocks, the
 * four of the volume directory and the bitmap itself -- and a bitmap that
 * calls any of them free is not a reason to write there. ProDOS trusts the
 * bitmap and would; an image with a damaged one is exactly what FIXIT is
 * for, and handing it a file on top of its own directory destroys the
 * volume outright. Measured: without this, a bitmap marking blocks 1 to 6
 * free made IMGPUT write the file over the directory and the bitmap, and
 * the volume did not read back at all. */
static unsigned int floor_block;
static unsigned int dir_first, dir_blk; /* chain head (the header) and the slot's block */
static unsigned char dir_slot;
static unsigned int data_blocks, needed;
static unsigned long length;
static unsigned char name[16], namelen;
static unsigned int key;

#define NOPAGE 0xFFFF

/* ---- writing a block and reading it back ------------------------------ */
static unsigned char put_verified(unsigned int b,const unsigned char* in,unsigned char* tmp) {
 if(stop() || !source_write(&src,b,in) || !source_read(&src,b,tmp))return 0;
 return !memcmp(tmp,in,512);
}

/* ---- the volume bitmap ------------------------------------------------ */
/* One page at a time: a 65535-block volume has sixteen of them, far past
 * what the window would hold. A page is written back before another is
 * read, so a walk may modify as it goes. */
/* Read back like any other write. A bitmap page that lands wrong is the
 * one failure that turns into a corrupt volume rather than lost space: the
 * entry would name blocks the bitmap calls free, and the next file written
 * would be handed them. The read-back goes into copy_buf, which holds
 * nothing of ours by the time a page is flushed. */
static unsigned char bm_flush(void) {
 if(bm_page!=NOPAGE && bm_dirty) {
  if(!put_verified(bm_first+bm_page,bits,buf))return 0;
  bm_dirty=0;
 }
 return 1;
}
static unsigned char bm_load(unsigned int page) {
 if(bm_page==page)return 1;
 if(!bm_flush())return 0;
 bm_page=NOPAGE;
 if(!source_read(&src,bm_first+page,bits))return 0;
 bm_page=page;return 1;
}
/* The next free block at or after the walk's position, 0 when there is
 * none: block 0 holds the boot code and is never free, so 0 can say it. */
static unsigned int next_free(void) {
 unsigned int b;
 for(b=scan<floor_block?floor_block:scan;b<vol_blocks;++b) {
  if(!bm_load(b>>12))return 0;
  if(bits[(b&0xFFF)>>3] & (0x80>>(b&7))) { scan=b+1; return b; }
 }
 scan=b;return 0;
}
static unsigned char take(unsigned int b) {
 if(!bm_load(b>>12))return 0;
 bits[(b&0xFFF)>>3] &= ~(0x80>>(b&7));
 bm_dirty=1;return 1;
}

/* ---- the directory ---------------------------------------------------- */
/* The chain the panel has open, from its key block. Sets dir_first (the
 * block carrying the header, which every entry points back to), and the
 * first free slot. Returns 0 on a read error, 2 when the name is already
 * there, 3 when no slot is free, 1 when all is well. */
static unsigned char dir_survey(void) {
 unsigned int block=other->dir_key;
 unsigned char guard,k,*p;
 dir_first=block;dir_blk=0;
 for(guard=0;block && guard<255;++guard) {
  if(!source_read(&src,block,dirb))return 0;
  for(k=0,p=dirb+4;k<13;++k,p+=0x27) {
   /* The header of the first block is not a file: skip slot 0 there. */
   if(!guard && !k)continue;
   if(!(*p&0xF0)) {
    if(!dir_blk) { dir_blk=block;dir_slot=k; }
   } else if((*p&0x0F)==namelen && !memcmp(p+1,name,namelen))return 2;
  }
  block=rd16(dirb+2);
 }
 if(!dir_blk)return 3;
 return 1;
}

/* ---- the entry -------------------------------------------------------- */
static void fill_entry(unsigned char* p,unsigned int key) {
 a.memset(p,0,0x27);
 p[0]=(data_blocks>1?0x20:0x10)|namelen;      /* sapling or seedling */
 RF(memcpy)(p+1,name,namelen);
 p[0x10]=a.selected->type;
 wr16(p+0x11,key);
 wr16(p+0x13,needed);
 p[0x15]=(unsigned char)length;
 p[0x16]=(unsigned char)(length>>8);
 p[0x17]=(unsigned char)(length>>16);
 wr16(p+0x18,a.selected->mdate);
 p[0x1E]=a.selected->access;
 wr16(p+0x1F,a.selected->aux);
 wr16(p+0x21,a.selected->mdate);
 wr16(p+0x25,dir_first);
}

/* Block 2 must read as a volume header whose bitmap lies inside it. Read
 * again after the question, so a swapped image is caught before any write. */
static unsigned char header_ok(void) {
 if(!source_read(&src,2,dirb) || (dirb[4]>>4)!=15)return 0;
 bm_page=NOPAGE;
 /* A volume header is not a file entry: its bitmap pointer, total and
  * file count sit at 0x23, 0x25 and 0x21, where a file keeps its auxtype,
  * its modification date and its header pointer. */
 bm_first=rd16(dirb+4+0x23);vol_blocks=rd16(dirb+4+0x25);
 if(!(vol_blocks<=src.blocks && vol_blocks>=7 && bm_first>=3 && bm_first<vol_blocks &&
      (unsigned int)((vol_blocks-1)>>12)+1<=vol_blocks-bm_first))return 0;
 floor_block=bm_first+(unsigned int)((vol_blocks-1)>>12)+1;
 if(floor_block<6)floor_block=6;
 return floor_block<vol_blocks;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 unsigned int i,b;
 unsigned char n;
 unsigned char* p;

 init(api);source=NULL;bm_page=NOPAGE;bm_dirty=0;src.file=0;
 if(pan->fs || !a.full[0] || !a.selected->name[0] || a.selected->type==0x0F ||
    other->fs!=FS_IMG || !other->img_len) {
  note("ProDOS file here, ProDOS image opposite.");return;
 }
 namelen=RF(strlen)(a.selected->name);
 if(!namelen || namelen>15) { note("Bad name.");return; }
 RF(memcpy)(name,a.selected->name,namelen);
 /* Type, aux, access and date come from the entry the panel already read:
  * a GET_FILE_INFO would say the same and cost its path buffer. The times
  * of day are not in it, so they are written as zero rather than invented. */
 length=a.selected->size;
 data_blocks=(unsigned int)((length+511)>>9);
 if(!data_blocks)data_blocks=1;                  /* an empty file still owns one */
 if(data_blocks>256) { note("Too big: needs a tree file.");return; }
 needed=data_blocks+(data_blocks>1?1:0);

 /* The image, by the path the other panel is mounted on. */
 n=other->img_len;
 RF(memcpy)(src.path,other->path,n);src.path[n]=0;
 if(!image_open(&src)) { note("Cannot open the image.");return; }
 if(image_readonly) { note("Image is read-only.");goto done; }

 /* It must read as a ProDOS volume, and its bitmap must lie inside it. */
 if(!header_ok()) { note("Not a ProDOS image.");goto done; }

 n=dir_survey();
 /* Name taken, no free slot, or unreadable: one refusal, because all
  * three mean the same to the caller -- the entry cannot be made here. */
 if(n!=1) { note("No room for that name in this directory.");goto done; }

 /* The room, before a single block moves: one walk of the bitmap reserves
  * the key block and every data block, and fills the index block with them
  * -- so the walk that proves the room is the one that chooses the blocks,
  * and the bitmap is not read again until it is written. */
 scan=floor_block;a.memset(idx,0,512);
 key=next_free();
 if(!key) { note("Not enough free blocks.");goto done; }
 for(i=0;i<data_blocks && data_blocks>1;++i) {
  b=next_free();
  if(!b) { note("Not enough free blocks.");goto done; }
  idx[i]=(unsigned char)b;idx[256+i]=(unsigned char)(b>>8);
 }

 a.sprintf(a.note,"Copy %s into the image?",a.selected->name);
 if(!RF(confirm)(a.note))goto done;

 /* The question was on screen a while: the image may have been swapped,
  * or the name taken. Nothing has been written yet, so ask the image
  * again rather than trust what it said before. */
 if(!header_ok() || dir_survey()!=1) { note("Image changed; nothing done.");goto done; }

 source=RF(fopen)(a.full,"rb");
 if(!source) { note("Cannot read the source.");goto done; }

 /* The data, into blocks the bitmap still calls free: a cut here leaves
  * the image exactly as it was. dirb is the read-back from now on, so the
  * bitmap page it held is gone. */
 bm_page=NOPAGE;
 for(i=0;i<data_blocks;++i) {
  b=(data_blocks>1)?(idx[i]|((unsigned int)idx[256+i]<<8)):key;
  a.memset(buf,0,512);
  n=(RF(fread)(buf,1,512,source)==512);
  if(i+1<data_blocks && !n) { note("Source is shorter than its entry.");goto done; }
  if(!put_verified(b,buf,dirb)) { note(cancelled?"Stopped; image unchanged.":
                                      "Write failed; image unchanged.");goto done; }
 }
 if(RF(fread)(&n,1,1,source)) { note("Source grew while copying.");goto done; }
 RF(fclose)(source);source=NULL;
 if(data_blocks>1 && !put_verified(key,idx,dirb)) {
  note("Write failed; image unchanged.");goto done;
 }

 /* From here the blocks are ours. A cut now costs their space, no more,
  * and the message says so instead of calling the work done. */
 bm_page=NOPAGE;bm_dirty=0;
 n=take(key);
 for(i=0;i<data_blocks && data_blocks>1 && n;++i)
  n=take(idx[i]|((unsigned int)idx[256+i]<<8));
 if(!n || !bm_flush()) { note("Bitmap write failed; run FIXIT.");goto done; }

 /* One directory block, one write: the entry and, when it lives there,
  * the file count. From that instant the name means the file. */
 /* dirb is about to stop being the bitmap page: say so, or a later
  * bm_load would hand out directory bytes as a bitmap. */
 bm_page=NOPAGE;
 if(!source_read(&src,dir_blk,dirb)) { note("Copied; entry unfinished: run FIXIT.");goto done; }
 p=dirb+4+dir_slot*0x27;
 if(*p&0xF0) { note("Copied; entry unfinished: run FIXIT.");goto done; }
 fill_entry(p,key);
 if(dir_blk==dir_first)wr16(dirb+4+0x21,rd16(dirb+4+0x21)+1);
 if(!put_verified(dir_blk,dirb,idx)) { note("Copied; entry unfinished: run FIXIT.");goto done; }
 if(dir_blk!=dir_first) {
  if(!source_read(&src,dir_first,dirb)) { note("Copied; entry unfinished: run FIXIT.");goto done; }
  wr16(dirb+4+0x21,rd16(dirb+4+0x21)+1);
  if(!put_verified(dir_first,dirb,idx)) { note("Copied; entry unfinished: run FIXIT.");goto done; }
 }
 note("Copied into the image; source kept.");

done:
 if(source)RF(fclose)(source);
 source_close(&src);
}
