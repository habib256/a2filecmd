/* pascalw.c -- ProDOS files written INTO an Apple Pascal (UCSD) volume.
 *
 * The mirror of pascal.c, and it wants the same two panels: the image under
 * the cursor of the active panel, a ProDOS directory in the other. That one
 * extracts every file of the volume into the directory; this one puts every
 * file of the directory into the volume, under the same contract -- a name
 * already in the volume is skipped and counted, never overwritten.
 *
 * A UCSD file is one contiguous run of blocks, so there is no bitmap to
 * keep and no index block to build. What there is instead is a rule about
 * where a file may go, and this overlay keeps the strict form of it: **a
 * new file goes after the last block any file uses**, never into a gap left
 * between two of them. The Apple Pascal filer can use those gaps because it
 * knows how to shift the files that follow; shifting files inside someone
 * else's volume is not a thing to do without being asked, so a volume whose
 * free space is all in the middle is refused with the room it has. K(runch
 * in the filer moves it to the end, and then this works.
 *
 * The order per file is the one whose interruption costs nothing:
 *
 *   1. The data blocks, written past the last block in use -- no entry
 *      names them and the volume does not know they exist. Each is read
 *      back and compared against the source a second time.
 *   2. The entry, at index count+1, which is past the file count: a reader
 *      stops at the count, so the entry is not yet a file.
 *   3. The header block, with the count raised by one. That single write is
 *      the instant the file exists.
 *
 * A cut at any point leaves a volume exactly as consistent as it was, with
 * the files put in before it intact. When the entry and the header fall in
 * the same block -- the first nineteen entries -- there is one write and no
 * window at all. None of this is atomic across several files, and it does
 * not pretend to be.
 *
 * What it will not do, and says instead of guessing: an empty file (a UCSD
 * entry must use at least one byte of its last block), a name longer than
 * fifteen characters, a volume whose directory is full, and the image
 * itself if it happens to sit in the directory being copied.
 *
 * The kind it writes is the exact inverse of the kind pascal.c reads: code
 * for $02, text for $03, data for $05, untyped for anything else. A ProDOS
 * TXT file does NOT become a UCSD textfile: that format carries a
 * 1,024-byte header and page padding, and writing one without them would
 * make a file the Pascal system reads as text and no reader could use.
 */
#define UTIL_STUBS
#define UTIL_VOLUME
#define UTIL_WRITE
#define IMAGEIO_WRITE
#define IMAGEIO_NODEVICE

#include "util.h"
#include <string.h>
#include "imageio.h"
#include "pascal_fs.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#ifndef PLUGIN_HOST
#pragma rodata-name(push, "OVLHDR")
#endif
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Apple Pascal volume: put the files opposite into it"
};
#ifndef PLUGIN_HOST
#pragma rodata-name(pop)
#endif

/* One buffer of our own, and copy_buf. The directory block being changed
 * and the read-back of a data write are never wanted at the same instant --
 * a directory write happens with no data block in flight, and a data write
 * has copy_buf to read back into -- so they share `blk`. Two of them
 * overflowed the window by 126 bytes. The source path uses the core's
 * scratch, as DOSIMAGE does. */
static unsigned char work[512];
#define source_path a.other_full
static unsigned char pnamelen;
/* The entry being built -- the name goes straight into it -- and what the
 * directory block held where we are about to write, so a write that lands
 * wrong can be put back. */
static unsigned char newent[ENTRY];
/* What a directory block held where we are about to write, so a write
 * that lands wrong can be put back. */
static unsigned char undo[ENTRY + 2];

static unsigned int tail;               /* first block no file uses */
static unsigned char put, skipped, stopped;
static unsigned int nth;
static FILE* src_file;

/* The UCSD kind for a ProDOS type: the exact inverse of what pascal.c
 * gives, so a file taken out and put back keeps its kind. */
static unsigned char ucsd_kind(unsigned char type)
{
    if (type == 0x02) return 2;
    if (type == 0x03) return 3;
    if (type == 0x05) return 5;
    return 0;
}

/* The block after the last one any file uses, and 0 if the directory does
 * not explain itself. read_dir has already checked the entries are in
 * order, so the last one ends last. */
static unsigned char find_tail(void)
{
    tail = DIR_BLOCK + DIR_BLOCKS;
    if (!count) return 1;
    if (!entry_at(count)) return 0;
    tail = word(ent + 2);
    return tail <= vblocks;
}

/* Is `pname` already one of the volume's files? */
static unsigned char name_taken(void)
{
    unsigned char i, k;
    for (i = 1; i <= count; ++i) {
        if (!entry_at(i)) return 1;             /* unreadable: treat as taken */
        if (ent[6] != pnamelen) continue;
        for (k = 0; k < pnamelen; ++k) {
            unsigned char c = ent[7 + k];
            if (c >= 'a' && c <= 'z') c -= 32;
            if (c != newent[7 + k]) break;
        }
        if (k == pnamelen) return 1;
    }
    return 0;
}

/* The new entry goes at index count+1 -- past the file count, so no reader
 * sees it -- and the count is raised afterwards. The order inside is what
 * matters: when the entry straddles two directory blocks, the SECOND half
 * is written first, then the first, and the count last of all. Writing the
 * count with the first half would show a reader a file whose entry is
 * half there. When the entry and the count share block 2, one write does
 * both and there is no window at all. */

/* The file count, in the volume entry -- which starts at byte 0 of block 2.
 * A UCSD directory has no chaining header: the four bytes a ProDOS
 * directory block begins with are not there, and writing the count four
 * bytes along puts it inside the volume name. */
static void set_count(unsigned char* d, unsigned int n)
{
    d[16] = (unsigned char)n;
    d[17] = (unsigned char)(n >> 8);
}

/* A directory block out and read back into copy_buf, which holds nothing
 * while the directory is being changed. */
static unsigned char put_block(unsigned int b)
{
    return source_write(&src, b, work) && source_read(&src, b, buf) &&
           !memcmp(work, buf, 512);
}

/* Patch n bytes of block b at `at`, optionally raising the file count, and
 * read it back. A write that lands WRONG has already destroyed what was
 * there, so the old bytes go back and the block is written again: claiming
 * the volume is whole while a directory block reads as noise would be a
 * lie. 1 written, 0 failed and put back, 2 failed and not put back. */
static unsigned char patch(unsigned int b, unsigned int at,
                           const unsigned char* from, unsigned char n,
                           unsigned char with_count)
{
    if (!source_read(&src, b, work)) return 0;
    RF(memcpy)(undo, work + at, n);
    undo[ENTRY] = work[16];
    undo[ENTRY + 1] = work[17];
    RF(memcpy)(work + at, from, n);
    if (with_count) set_count(work, count + 1);
    if (put_block(b)) return 1;
    RF(memcpy)(work + at, undo, n);
    work[16] = undo[ENTRY];
    work[17] = undo[ENTRY + 1];
    return put_block(b) ? 0 : 2;
}

/* 1 the file exists, 0 nothing changed, 2 the directory needs looking at. */
/* The UCSD date: year in bits 9-15, day in 4-8, month in 0-3 -- where
 * ProDOS keeps year in 9-15, month in 5-8 and day in 0-4. The year sits in
 * the same place in both and both count from 1900, so only the day and the
 * month move. A month of zero means no date at all, which is what an entry
 * written with a zero word carried until now.
 *
 * Byte by byte, not word by word: the same shuffle written on 16-bit
 * values cost 227 bytes of a window that had 364. */
static unsigned char dlo, dhi;
static void set_date(unsigned int prodos)
{
    unsigned char lo = (unsigned char)prodos, hi = (unsigned char)(prodos >> 8);
    dlo = (unsigned char)(((lo & 15) << 4) | ((hi & 1) << 3) | (lo >> 5));
    dhi = (unsigned char)((hi & 0xFE) | ((lo >> 4) & 1));
}

static unsigned char commit(unsigned int first, unsigned int last,
                            unsigned int used, unsigned char kind)
{
    unsigned int off = (unsigned int)(count + 1) * ENTRY;
    unsigned int blk = DIR_BLOCK + (off >> 9), k = off & 511, part;
    unsigned char i, r;
    newent[0] = (unsigned char)first;  newent[1] = (unsigned char)(first >> 8);
    newent[2] = (unsigned char)last;   newent[3] = (unsigned char)(last >> 8);
    newent[4] = kind;
    newent[6] = pnamelen;
    /* the name is already in newent[7..], put there by one() */
    newent[22] = (unsigned char)used;  newent[23] = (unsigned char)(used >> 8);
    newent[24] = dlo;
    newent[25] = dhi;
    part = 512 - k;
    if (part > ENTRY) part = ENTRY;
    if (part < ENTRY) {                         /* the tail of the entry, first */
        r = patch(blk + 1, 0, newent + part, (unsigned char)(ENTRY - part), 0);
        if (r != 1) return r;
    }
    r = patch(blk, k, newent, (unsigned char)part, blk == DIR_BLOCK);
    if (r != 1) return r;
    if (blk != DIR_BLOCK) {                     /* the switch, on its own */
        r = patch(DIR_BLOCK, 0, newent, 0, 1);
        if (r != 1) return r;
    }
    ++count;
    return 1;
}

/* One ProDOS file into the volume. 1 done, 0 stopped for good. */
static unsigned char one(const char* name, unsigned char type, unsigned long size)
{
    unsigned int blocks, used, b, n, first;
    unsigned char i;

    /* The date comes straight from the entry the walk is standing on: a
     * fifth parameter went on the stack and cost the window fifty bytes. */
    set_date(a.dir_entry->mdate);
    pnamelen = (unsigned char)RF(strlen)(name);
    if (!pnamelen || pnamelen > 15 || !size) { ++skipped; return 1; }
    a.memset(newent, 0, ENTRY);
    RF(memcpy)(newent + 7, name, pnamelen);
    if (name_taken()) { ++skipped; return 1; }

    blocks = (unsigned int)((size + 511) >> 9);
    used = (unsigned int)(size & 511);
    if (!used) used = 512;
    if (count >= MAX_FILES) { note("The volume directory is full."); return 0; }
    if (tail + blocks > vblocks) { note("No room after the last file."); return 0; }

    if (!join(source_path, other->path, name)) { ++skipped; return 1; }
    src_file = RF(fopen)(source_path, "rb");
    if (!src_file) { note("Cannot read a file opposite."); return 0; }
    first = tail;
    for (b = 0; b < blocks; ++b) {
        n = (b + 1 == blocks) ? used : 512;
        a.memset(buf, 0, 512);
        if (RF(fread)(buf, 1, n, src_file) != n) { note("Cannot read a file opposite."); goto bad; }
        if (stop()) { note("Stopped; the volume is whole."); goto bad; }
        if (!source_write(&src, first + b, buf) || !source_read(&src, first + b, work) ||
            memcmp(buf, work, 512)) { note("Write failed; the volume is whole."); goto bad; }
        a.progress_bar(name, b, blocks);
    }
    RF(fclose)(src_file); src_file = 0;
    /* Nothing above this line is visible to a reader: the blocks are past
     * the last file and the entry does not exist yet. */
    i = commit(first, first + blocks, used, ucsd_kind(type));
    if (i != 1) {
        note(i == 2 ? "Directory write failed; check the volume."
                    : "Write failed; the volume is whole.");
        return 0;
    }
    tail = first + blocks;
    ++put;
    return 1;
bad:
    if (src_file) { RF(fclose)(src_file); src_file = 0; }
    return 0;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    init(api);
    put = skipped = stopped = 0; src_file = 0; src.file = 0;
    if (pan->fs || !a.full[0] || !a.selected->name[0] || a.selected->type == 0x0F) {
        note("Select a disk image; ProDOS folder opposite.");
        return;
    }
    if (!other->path[0] || other->fs) {
        note("Other panel: open a ProDOS directory.");
        return;
    }
    RF(strcpy)(src.path, a.full);
    if (!image_open(&src)) { note("Not a disk image this can open."); return; }
    if (image_readonly) { note("The image is read-only."); goto done; }
    if (!read_dir() || !find_tail()) { note("Not an Apple Pascal volume."); goto done; }

    a.sprintf(a.note, "Put the files opposite into %s?", a.selected->name);
    if (!RF(confirm)(a.note)) goto done;
    /* The image may have been swapped while the question waited. */
    if (!read_dir() || !find_tail()) { note("Image changed; nothing done."); goto done; }

    /* One entry per pass, the directory closed before the file is opened.
     * Leaving it open makes three files open at once -- the image, the
     * directory and the source -- and ProDOS runs out of buffers: the very
     * first source refused to open. */
    for (nth = 0; ; ++nth) {
        unsigned int k;
        if (!a.dir_open(other->path)) { note("Cannot read the other panel."); goto done; }
        for (k = 0; k <= nth; ++k) if (!a.dir_next()) break;
        a.dir_close();
        if (k <= nth) break;                                  /* past the end */
        if (a.dir_entry->type == 0x0F) continue;              /* a directory */
        if (!join(source_path, other->path, a.dir_entry->name) ||
            !a.strcmp(source_path, a.full)) { ++skipped; continue; }   /* the image itself */
        if (!one(a.dir_entry->name, a.dir_entry->type, a.dir_entry->size)) { stopped = 1; break; }
    }
    if (stopped) goto done;
    a.sprintf(a.note, "%u put, %u skipped (name taken or empty).", put, skipped);
done:
    if (src_file) RF(fclose)(src_file);
    source_close(&src);
}
