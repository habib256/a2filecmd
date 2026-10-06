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
 *      directory the panel shows must be a directory with the name free in
 *      it and a slot free too.
 *   2. The source is read to its end and counted: the length written is
 *      what the file holds, never what a panel remembered of it.
 *   3. The room is counted before anything moves.
 *   -- the question --
 *   4. The image is read again, and this time ALL of it that matters: every
 *      block its directories and files name must be one the bitmap calls
 *      used (prodos_claims.h), and the panel's directory must be met on the
 *      way as a live one. A bitmap that calls a referenced block free would
 *      have us write over somebody's file, so it gets nothing written.
 *   5. The blocks are chosen, from the bitmap as it reads now. The data
 *      blocks and the index block are written into them, then read back
 *      and compared; the source must end exactly where it was counted to.
 *   6. The bitmap is written: from here the blocks are ours. A bit found
 *      already clear stops it.
 *   7. One directory block, one write: the entry and the file count. From
 *      that instant the name means the file.
 *
 * A cut before 6 changes nothing any file or directory can see -- the
 * blocks written to were free, referenced by nothing (4 proved it) and stay
 * free, and the directory never heard of them. A cut between 6 and 7 loses
 * their space and nothing else; FIXIT finds them, and the message
 * says so rather than calling the work done. None of this is atomic and
 * none of it pretends to be: ProDOS offers no such promise, and no more do
 * we.
 *
 * What it does not do yet, and says so instead of guessing: a file that
 * needs a tree (above 128 KB), a directory with no free slot (extending the
 * chain is a write of its own), and an image whose file is locked, whose
 * 2IMG header says write protected, or which ProDOS will not open for
 * update.
 *
 * What step 4 costs: every directory block and every index block of the
 * image is read through the image FILE, a seek and a read each. Measured
 * under POM2 (65C02 edition, a hard disk with no latency): 90 million
 * cycles -- a minute and a half at 1 MHz -- for a 16 MB image of 765 files
 * (84 directory blocks, 582 index blocks), some 135,000 cycles a block; a
 * floppy image is a second or two. A file under ProDOS cannot exceed
 * 16 MB, so neither can an image. The bitmap is consulted one page at a
 * time, and a volume whose files are scattered across pages rereads them:
 * that case is slower still and was not measured. The activity cell turns
 * at every block and ESC stops the walk with nothing written.
 */
#define UTIL_STUBS
#define IMAGEIO_WRITE
/* Only ever a file: no device path, and with it no unit_of, readblk or
 * writeblk compiled in for branches this overlay can never take. */
#define IMAGEIO_NODEVICE
/* One image, `src`, which imageio.h then declares and addresses directly. */
#define IMAGEIO_ONE

#include "util.h"
#include "imageio.h"
#include "spin.h"
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

/* Two 512-byte buffers of our own, and api->copy_buf: the window is
 * $1B00-$3FFF and four buffers overflowed it by 1638 bytes. Three are
 * enough because no instant needs four:
 *
 *                 dirb               idx              copy_buf (buf, bits)
 *   the walk      a directory block  an index block   a bitmap page
 *   choosing      --                 the blocks       a bitmap page
 *   the data      the read-back      the blocks       the block on its way
 *   the bitmap    the read-back      the blocks       a bitmap page
 *   the entry     the directory      the read-back    --
 *
 * which is why put_verified is told where to read back into. The bitmap
 * page lives in copy_buf: whoever puts anything else there -- the data
 * loop, the counting of the source, a question on screen -- is followed by
 * bm_page = NOPAGE before the bitmap is looked at again. The walk gets the
 * two fixed buffers, whose bytes cc65 can address directly. */
static unsigned char dirb[512], idx[512];
#define bits buf
static FILE* source;
static unsigned int vol_blocks, bm_first, bm_end;   /* bm_end: past the last bitmap page */
static unsigned int bm_page;            /* page held in bits[]; NOPAGE = none */
static unsigned char bm_dirty;
static unsigned char* bm_at;            /* the byte of bits[] holding a block's bit, */
static unsigned char bm_mask;           /* and the bit: set by bm_find */
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
static unsigned int dir_at;             /* the free slot's offset in that block */
/* The source as it was counted: its data blocks (1 to 256) and the bytes
 * in the last of them (0 for an empty file, else 1 to 512). The length is
 * those two and nothing else -- (data_blocks - 1) * 512 + last. */
static unsigned int data_blocks, last, needed;
/* The entry being built. The name goes straight into it and is compared
 * from there. */
static unsigned char ent[0x27], namelen;
#define newname (ent+1)
static unsigned int key;

#define NOPAGE 0xFFFF

static const char m_stopped[]="Stopped; image unchanged.";
static const char m_failed[]="Write failed; image unchanged.";
static const char m_source[]="Cannot read the source.";
static const char m_room[]="Not enough free blocks.";
static const char m_damaged[]="Image damaged: nothing written. Run FIXIT.";

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
 * would be handed them. The read-back goes into dirb, which holds
 * nothing of ours while a page is being changed. */
static unsigned char bm_flush(void) {
 if(bm_page!=NOPAGE && bm_dirty) {
  if(!put_verified(bm_first+bm_page,bits,dirb))return 0;
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
/* Where block b's bit is, in bm_at and bm_mask: a set bit is a free block.
 * 0 when b is outside the volume or its page cannot be read -- in which
 * case nobody may conclude anything about b, least of all that it is free. */
static unsigned char bm_find(unsigned int b) {
 if(b>=vol_blocks || !bm_load(b>>12))return 0;
 bm_at=bits+((b&0xFFF)>>3);
 bm_mask=0x80>>(b&7);
 return 1;
}
/* The next free block at or after the walk's position, 0 when there is
 * none: block 0 holds the boot code and is never free, so 0 can say it. */
static unsigned int next_free(void) {
 unsigned int b;
 for(b=scan;bm_find(b);++b)                       /* 0 past the last block */
  if(*bm_at&bm_mask) { scan=b+1; return b; }
 return 0;
}
/* The room, before a single block moves: one walk of the bitmap picks the
 * key block and every data block, and fills the index block with them --
 * so the walk that proves the room is the one that chooses the blocks.
 * Twice: before the question, to refuse without asking, and after it, from
 * the bitmap as it reads then. What the first pass chose is never used. */
static unsigned char reserve(void) {
 unsigned char i=0;
 unsigned int b;
 scan=floor_block;RF(memset)(idx,0,512);
 key=next_free();
 if(!key)return 0;
 if(data_blocks>1) do {
  b=next_free();
  if(!b)return 0;
  idx[i]=(unsigned char)b;(idx+256)[i]=(unsigned char)(b>>8);
  ++i;
 } while(i!=(unsigned char)data_blocks);         /* 256 of them wraps to 0 */
 return 1;
}
/* Data block n of the new file. */
static unsigned int chosen(unsigned char n) {
 return idx[n]|((unsigned int)(idx+256)[n]<<8);
}
/* The key block and every data block out of the bitmap. A bit that is no
 * longer set means the bitmap is not the one the blocks were chosen from:
 * taking it anyway would claim a block somebody else was given. */
static unsigned char take(unsigned int b) {
 if(!bm_find(b) || !(*bm_at&bm_mask))return 0;
 *bm_at^=bm_mask;
 bm_dirty=1;
 return 1;
}
static unsigned char claim(void) {
 unsigned char i=0;
 if(!take(key))return 0;
 if(data_blocks>1) do {
  if(!take(chosen(i)))return 0;
  ++i;
 } while(i!=(unsigned char)data_blocks);
 return 1;
}

/* ---- what the image references ---------------------------------------- */
/* A block a directory or a file may name: past the boot blocks, inside the
 * volume, not one of the bitmap's own pages -- a directory block or a file
 * living where the bitmap is would be rewritten with it -- and marked
 * used. */
static unsigned char marked_used(unsigned int b) {
 return bm_find(b) && !(*bm_at&bm_mask);
}
static unsigned char claims_used(unsigned int b) {
 return b>1 && (b<bm_first || b>=bm_end) && marked_used(b);
}
/* A block the walk reads: a sign of life first, and ESC stops it. */
static unsigned char claims_read(unsigned int b,unsigned char* to) {
 spin();
 return !stop() && claims_used(b) && source_read(&src,b,to);
}
#define CLAIMS_DIR dirb
#define CLAIMS_IDX idx
#define CLAIMS_WORD rd16
#define CLAIMS_BLOCKS vol_blocks
#define CLAIMS_TARGET dir_first
#include "prodos_claims.h"
/* Everything the image names is marked used, the boot blocks and the
 * bitmap's own pages too: only then is a free bit a free block. */
static unsigned char image_sound(void) {
 unsigned int b;
 if(!marked_used(0) || !marked_used(1))return 0;
 for(b=bm_first;b<bm_end;++b)if(!marked_used(b))return 0;
 return claims_walk();
}

/* ---- the directory ---------------------------------------------------- */
/* The chain the panel has open, from its key block. Sets dir_first (the
 * block carrying the header, which every entry points back to), and the
 * first free slot. Returns 0 on a read error or when the key block is not
 * the head of a directory, 2 when the name is already there, 3 when no
 * slot is free, 1 when all is well.
 *
 * The key is the panel's, read when it opened the image. If it no longer
 * names a directory -- measured with the key of a file's data block, all
 * zeros: slot 1 looked free, and the entry and a "file count" were written
 * INTO that file's data -- there is no directory here to add to. */
static unsigned char dir_survey(void) {
 unsigned int block=other->dir_key;
 unsigned char guard,*p;
 dir_first=block;dir_blk=0;
 for(guard=0;block && guard<255;++guard) {
  if(!source_read(&src,block,dirb))return 0;
  p=dirb+4;
  if(!guard) {
   if(*p<0xE0 || rd16(dirb) || dirb[0x23]!=0x27 || dirb[0x24]!=13)return 0;
   p+=0x27;             /* the header of the first block is not a file */
  }
  for(;p!=dirb+4+13*0x27;p+=0x27) {
   if(!(*p&0xF0)) {
    if(!dir_blk) { dir_blk=block;dir_at=p-dirb; }
   } else if((*p&0x0F)==namelen && !memcmp(p+1,newname,namelen))return 2;
  }
  block=rd16(dirb+2);
 }
 if(!dir_blk)return 3;
 return 1;
}

/* ---- the entry -------------------------------------------------------- */
/* Into ent, where the name already is. The length is three bytes: the low
 * one is the low byte of `last` -- 512 times anything ends in a zero byte
 * -- and the other two are the count of 256-byte pages. */
static void fill_entry(void) {
 const struct Entry* e=a.selected;
 ent[0]=(data_blocks>1?0x20:0x10)|namelen;    /* sapling or seedling */
 ent[0x10]=e->type;
 wr16(ent+0x11,key);
 wr16(ent+0x13,needed);
 ent[0x15]=(unsigned char)last;
 wr16(ent+0x16,((data_blocks-1)<<1)+(last>>8));
 wr16(ent+0x18,e->mdate);
 ent[0x1E]=e->access;
 wr16(ent+0x1F,e->aux);
 wr16(ent+0x21,e->mdate);
 wr16(ent+0x25,dir_first);
}

/* The header in dirb counts one more file. */
static void count_up(void) {
 wr16(dirb+4+0x21,rd16(dirb+4+0x21)+1);
}

/* Block 2 must read as a volume header whose bitmap lies inside it. Read
 * again after the question, so a swapped image is caught before any write.
 * A bitmap pointer of 3, 4 or 5 passes here and not for long: those are
 * blocks of the standard volume directory, and the walk refuses a
 * directory block that is one of the bitmap's pages. Whatever page of the
 * bitmap was in hand is forgotten: copy_buf may have been used since. */
static unsigned char header_ok(void) {
 bm_page=NOPAGE;
 if(!source_read(&src,2,dirb) || (dirb[4]>>4)!=15)return 0;
 /* A volume header is not a file entry: its bitmap pointer, total and
  * file count sit at 0x23, 0x25 and 0x21, where a file keeps its auxtype,
  * its modification date and its header pointer. */
 bm_first=rd16(dirb+4+0x23);vol_blocks=rd16(dirb+4+0x25);
 if(vol_blocks>src.blocks || vol_blocks<7 || bm_first<3 || bm_first>=vol_blocks)return 0;
 bm_end=((vol_blocks-1)>>12)+1;                  /* the bitmap's pages, 1 to 16 */
 if(bm_end>vol_blocks-bm_first)return 0;
 bm_end+=bm_first;
 floor_block=bm_end;
 if(floor_block<6)floor_block=6;
 return floor_block<vol_blocks;
}

/* ---- the source ------------------------------------------------------- */
/* What the file holds, counted by reading it to its end. The panel's size
 * is what the directory said when the panel was read, and a file can have
 * been rewritten since -- measured: 512 bytes behind a panel that said 0
 * went in as "Copied" with an EOF of 0, 1024 behind 600 with an EOF of 600,
 * and 900 behind 1000 with an EOF of 1000 and a hundred bytes of zeros
 * nobody wrote. Reading it all first also finds a block that cannot be
 * read before anything is written. Stops one block past the 128 KB a
 * sapling holds: beyond that the answer is already no. */
static unsigned char measure(void) {
 unsigned int n;
 data_blocks=0;last=0;
 source=RF(fopen)(a.full,"rb");
 if(!source)return 0;
 do {
  spin();
  n=RF(fread)(buf,1,512,source);
  if(n) { ++data_blocks;last=n; }
 } while(n==512 && data_blocks<=256 && !stop());
 n=ferror(source) || cancelled;
 if(RF(fclose)(source))n=1;
 source=NULL;
 return !n;
}

/* Everything between the image opened and the image closed. Returns the
 * last word, or 0 when the question was declined and there is none: a
 * `return` is five bytes where a note and a jump to the close were nine,
 * and there are twenty of them. */
static const char* put(void) {
 unsigned int i,b,m;
 unsigned char n;

 if(image_readonly)return "Image is read-only.";

 /* It must read as a ProDOS volume, and its bitmap must lie inside it. */
 if(!header_ok())return "Not a ProDOS image.";

 /* Name taken, no free slot, not a directory, or unreadable: one refusal,
  * because all four mean the same to the caller -- the entry cannot be
  * made here. */
 if(dir_survey()!=1)return "No room for that name in this directory.";

 /* Type, aux, access and date come from the entry the panel already read:
  * a GET_FILE_INFO would say the same and cost its path buffer. The times
  * of day are not in it, so they are written as zero rather than invented.
  * The LENGTH does not come from there: it is counted. */
 if(!measure())return cancelled?m_stopped:m_source;
 if(data_blocks>256)return "Too big: needs a tree file.";
 if(!data_blocks)data_blocks=1;                  /* an empty file still owns one */
 needed=data_blocks;
 if(data_blocks>1)++needed;                      /* and a sapling its index */

 if(!reserve())return m_room;

 a.sprintf(a.note,"Copy %s into the image?",a.selected->name);
 if(!RF(confirm)(a.note))return 0;

 /* The question was on screen a while: the image may have been swapped,
  * or the name taken. Nothing has been written yet, so ask the image
  * again rather than trust what it said before -- and this time ask it
  * everything: no block is chosen until every block the image names has
  * been found marked used. Long on a big image, so it says so. */
 if(!header_ok() || dir_survey()!=1)return "Image changed; nothing done.";
 RF(message)("Checking the image... ESC stops");
 if(!image_sound())return cancelled?m_stopped:m_damaged;
 if(!reserve())return m_room;

 source=RF(fopen)(a.full,"rb");
 if(!source)return m_source;

 /* The data, into blocks the bitmap still calls free and nothing names: a
  * cut here leaves every file and directory of the image exactly as it
  * was. copy_buf carries the data from now on, so the bitmap page it held
  * is gone. Each block is asked for by its exact size: a source that gives
  * less, or has a byte left after the last one, is not the file that was
  * counted. */
 bm_page=NOPAGE;
 for(i=0;i<data_blocks;++i) {
  /* up to 256 blocks, each written then read back */
  a.progress_bar(a.selected->name,i,data_blocks);
  b=key;
  if(data_blocks>1)b=chosen((unsigned char)i);
  RF(memset)(buf,0,512);
  m=512;
  if(i+1==data_blocks)m=last;
  if(m && RF(fread)(buf,1,m,source)!=m)break;
  if(!put_verified(b,buf,dirb))return cancelled?m_stopped:m_failed;
 }
 if(i<data_blocks || RF(fread)(dirb,1,1,source) || ferror(source))
  return "Source changed; nothing added to the image.";
 if(data_blocks>1 && !put_verified(key,idx,dirb))return m_failed;

 /* From here the blocks are ours. A cut now costs their space, no more,
  * and the message says so instead of calling the work done. */
 bm_page=NOPAGE;bm_dirty=0;
 if(!claim() || !bm_flush())return "Bitmap write failed; run FIXIT.";

 /* One directory block, one write: the entry and, when it lives there,
  * the file count. From that instant the name means the file. The slot is
  * looked at once more: it must still be free. */
 fill_entry();
 n=0;
 if(source_read(&src,dir_blk,dirb) && !(dirb[dir_at]&0xF0)) {
  RF(memcpy)(dirb+dir_at,ent,0x27);
  if(dir_blk==dir_first)count_up();
  if(put_verified(dir_blk,dirb,idx)) {
   n=1;
   if(dir_blk!=dir_first) {
    n=0;
    if(source_read(&src,dir_first,dirb)) {
     count_up();
     n=put_verified(dir_first,dirb,idx);
    }
   }
  }
 }
 if(n)return "Copied into the image; source kept.";
 return "Copied; entry unfinished: run FIXIT.";
}

void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 unsigned char n;
 const char* m;

 init(api);source=NULL;bm_page=NOPAGE;bm_dirty=0;src.file=0;
 if(pan->fs || !a.full[0] || !a.selected->name[0] || a.selected->type==0x0F ||
    other->fs!=FS_IMG || !other->img_len) {
  note("ProDOS file here, ProDOS image opposite.");return;
 }
 namelen=RF(strlen)(a.selected->name);
 if(!namelen || namelen>15) { note("Bad name.");return; }
 RF(memset)(ent,0,0x27);
 RF(memcpy)(newname,a.selected->name,namelen);

 /* The image, by the path the other panel is mounted on. */
 n=other->img_len;
 RF(memcpy)(src.path,other->path,n);src.path[n]=0;
 if(!image_open(&src)) { note("Cannot open the image.");return; }
 m=put();
 if(m)note(m);
 if(source)RF(fclose)(source);
 source_close(&src);
}
