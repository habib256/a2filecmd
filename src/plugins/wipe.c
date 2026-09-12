/* wipe.c -- zero the free blocks of a volume, or the whole disk.
 *
 * From the ! menu, on a ProDOS volume: the selected entry when the active
 * panel is the volume list ("/VOL", its unit in mdate), or the volume of
 * the active panel's path, whose unit is found with ON_LINE ($C5) on unit
 * 0. An image or a DOS 3.3 disk opened as a directory is refused.
 *
 * Then one key:
 *
 *   F  the FREE blocks only. The volume header (block 2) gives the bitmap
 *      pointer ($27) and the total number of blocks ($29); each bitmap
 *      block covers 4,096 blocks, one bit each, 1 = free, the highest bit
 *      of a byte being the lowest block. Every free block is overwritten
 *      with 512 zeros (WRITE_BLOCK $81): the directory, the bitmap and the
 *      live files are left untouched, only what a deleted file left behind
 *      is erased. A plain confirmation is enough -- nothing readable dies.
 *
 *   W  the WHOLE volume, block 0 to total - 1, directory and bitmap
 *      included: the disk is left unreadable. Destructive, so the word
 *      ERASE has to be typed in full, like DISKIMG; and the volume the
 *      program runs from (the first component of api->cfg_path, matched
 *      against the target by unit and by name) is refused outright.
 *
 * The bar moves every sixteen blocks and ESC stops the wipe where it is.
 *
 * A BIG overlay, and for one reason: F needs two 512-byte buffers at the
 * same time -- the bitmap block being read and the block of zeros being
 * written -- and a small overlay has only api->copy_buf. Rather than
 * re-reading the bitmap between batches of free blocks, the two buffers
 * sit at $3000 and $3200, in the graphics page a big overlay owns and the
 * core rebuilds on return. The file stays well under the 5,376 bytes that
 * keep the code below $3000. Being big, it also gets its panels reread and
 * redrawn by the core on return, so its last words go through api->note,
 * never api->message, and it must not call read_panel itself: that would
 * rebuild the entry tables over these very buffers. */
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Zero the free blocks of a volume, or the whole disk"
};
#pragma rodata-name (pop)

/* The two blocks, in the page the core rebuilds on return. */
#ifndef BM
#define BM   ((unsigned char*)0x3000)      /* one bitmap block */
#define ZERO ((unsigned char*)0x3200)      /* 512 zeros, written over and over */
#endif

#ifndef KBD
#define KBD     (*(volatile unsigned char*)0xC000)
#define KBDSTRB (*(volatile unsigned char*)0xC010)
#endif

/* MLI parameter blocks, packed by cc65: READ_BLOCK $80 / WRITE_BLOCK $81
 * {3, unit, buffer, block}, ON_LINE $C5 {2, unit, buffer}. */
struct Bp { unsigned char n, unit; void* buf; unsigned int block; };
struct Ol { unsigned char n, unit; void* buf; };

/* The volume header, at block 2: storage type $F in the high nibble of
 * the header entry, the bitmap pointer and the total at these offsets. */
#define H_TYPE   0x04
#define H_BITMAP 0x27
#define H_TOTAL  0x29

static const char M_NOTVOL[] = "Not a ProDOS volume.";
static const char M_SELECT[] = "Select a ProDOS volume.";
static const char M_NOVOL[]  = "That volume is not online.";
static const char M_READ[]   = "The volume directory cannot be read.";
static const char M_ASK[]    = "\1Wipe %s: F) the free blocks, W) the WHOLE volume, ESC quits";
static const char M_ASKF[]   = "Zero every free block of %s?";
static const char M_LOST[]   = " EVERYTHING on %s WILL BE LOST. ";
static const char M_ERASE[]  = "Type ERASE to confirm";
static const char M_WORD[]   = "ERASE";
static const char M_BOOT[]   = "That volume holds the running program: choose another.";
static const char M_CANCEL[] = "Nothing was written.";
static const char M_DONE[]   = "%u blocks zeroed on %s%s";
static const char M_STOP[]   = ", stopped by ESC";
static const char M_ERR[]    = ", then ProDOS $%02X";

/* BSS: nothing zeroes it, every field is written before it is read. */
static const struct A2fcApi* A;
static struct Bp bp;
static struct Ol ol;
static char VOL[NAME_LEN + 1];      /* "/TARGET" */
static char BOOT[NAME_LEN + 1];     /* "/BOOTVOLUME", from cfg_path */
static char NM[NAME_LEN + 1];       /* one name of the ON_LINE table */
static char* buf;                   /* api->copy_buf: ON_LINE, then the lines */
static const char* tail;
static unsigned char unit, boot, err, key, whole;
static unsigned int total, bitmap, done, blk;

/* "/VOL": the first component of a ProDOS path. */
static void __fastcall__ first_part(char* dst, const char* path)
{
    unsigned char k;
    for (k = 0; k < NAME_LEN - 1 && path[k] && (k == 0 || path[k] != '/'); ++k) dst[k] = path[k];
    dst[k] = 0;
}

/* A key waiting is taken; the strobe leaves its code readable; ESC stops. */
static unsigned char stopped(void)
{
    if (KBD < 128) return 0;
    KBDSTRB = 0;
    return KBD == 27;
}

/* The bar and the ESC test, every sixteen blocks. */
static unsigned char watch(void)
{
    if (blk & 15) return 0;
    A->progress_bar(VOL, blk, total);
    return stopped();
}

/* Block `blk` filled with zeros; 0, or the ProDOS error. */
static unsigned char zero_block(void)
{
    bp.buf = ZERO;
    bp.block = blk;
    return A->mli(0x81, &bp);
}

/* Every block of the volume, block 0 (the boot block) included. */
static void wipe_whole(void)
{
    for (blk = 0; blk < total; ++blk) {
        if (watch()) { err = 0xFF; return; }
        if ((err = zero_block()) != 0) return;
        ++done;
    }
}

/* The free blocks, one bitmap block at a time: 512 bytes, eight blocks a
 * byte, the highest bit the lowest block, 1 = free. `blk` counts the
 * blocks and so gives the offset in the current bitmap block as well as
 * the block number; the loop stops on the total, and a bitmap block is
 * read only when the count reaches it (4,096 blocks each). Bit by bit
 * with a rotating mask, and not blk >> 3 / 0x80 >> (blk & 7): a variable
 * shift is a library call in cc65, on every block of the disk. */
static void wipe_free(void)
{
    unsigned char k = 0, m, bit;
    unsigned int j;
    blk = 0;
    while (blk < total) {
        bp.buf = BM;
        bp.block = bitmap + k;
        ++k;
        if ((err = A->mli(0x80, &bp)) != 0) return;
        for (j = 0; j < 512; ++j) {
            m = BM[j];
            for (bit = 0x80; bit; bit >>= 1) {
                if (blk >= total) return;
                if (watch()) { err = 0xFF; return; }
                if (m & bit) {
                    if ((err = zero_block()) != 0) return;
                    ++done;
                }
                ++blk;
            }
        }
    }
}

/* Never trust a free bit until every live reference has been checked.
 * BM caches allocation bits, ZERO holds a sapling index, copy_buf a directory
 * or tree index. No write occurs during this entire preflight. */
static unsigned int map_page;
static unsigned int word(const unsigned char* p) { return p[0] | ((unsigned int)p[1] << 8); }
static unsigned char read_at(unsigned int b, unsigned char* dst) {
    bp.block = b; bp.buf = dst; return !A->mli(0x80, &bp);
}
static unsigned char allocated(unsigned int b) {
    unsigned int page;
    if (b >= total) return 0;
    page = bitmap + (b >> 12);
    if (page != map_page) {
        if (!read_at(page, BM)) return 0;
        map_page = page;
    }
    return !(BM[(b & 4095) >> 3] & (0x80 >> (b & 7)));
}
static unsigned char index_safe(unsigned int b) {
    unsigned int i, ref;
    if (!allocated(b) || !read_at(b, ZERO)) return 0;
    for (i = 0; i < 256; ++i) {
        ref = ZERO[i] | ((unsigned int)ZERO[256 + i] << 8);
        if (ref && !allocated(ref)) return 0;
    }
    return 1;
}
static unsigned char file_safe(unsigned char kind, unsigned int b) {
    unsigned int i, ref;
    if (kind > 3 || !kind || !b) return 0; /* extended files: cannot prove safe */
    if (kind == 1) return allocated(b);
    if (kind == 2) return index_safe(b);
    if (!allocated(b) || !read_at(b, A->copy_buf)) return 0;
    for (i = 0; i < 256; ++i) {
        ref = A->copy_buf[i] | ((unsigned int)A->copy_buf[256 + i] << 8);
        if (ref && !index_safe(ref)) return 0;
    }
    return 1;
}
struct WipeFrame { unsigned int block; unsigned char slot; };
static struct WipeFrame walk[16];
static unsigned char free_safe(void) {
    unsigned char depth = 0, kind;
    unsigned int b, visits = 0;
    unsigned char* e;
    map_page = 0xFFFF;
    for (b = 0; b < 3; ++b) if (!allocated(b)) return 0;
    for (b = bitmap; b <= bitmap + ((total - 1) >> 12); ++b)
        if (!allocated(b)) return 0;
    walk[0].block = 2; walk[0].slot = 0;
    for (;;) {
        if (stopped() || !allocated(walk[depth].block) ||
            !read_at(walk[depth].block, A->copy_buf)) return 0;
        if (!walk[depth].slot) {
            if (++visits > total) return 0; /* chained cycles, including empty blocks */
            kind = A->copy_buf[4] >> 4;
            if (kind >= 14) {
                if (A->copy_buf[35] != 39 || A->copy_buf[36] != 13) return 0;
                walk[depth].slot = 1;
            }
        }
        if (walk[depth].slot == 13) {
            b = word(A->copy_buf + 2);
            if (b) { walk[depth].block = b; walk[depth].slot = 0; }
            else { if (!depth) return 1; --depth; }
            continue;
        }
        e = A->copy_buf + 4 + (unsigned int)walk[depth].slot++ * 39;
        kind = e[0] >> 4;
        if (!kind) continue;
        b = word(e + 17);
        if (kind == 13) {
            if (depth == 15 || !b) return 0;
            ++depth; walk[depth].block = b; walk[depth].slot = 0;
        } else if (!file_safe(kind, b)) return 0;
    }
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Panel* pan;
    const struct Entry* e;
    const unsigned char* p;
    unsigned char b, len;

    A = api;
    buf = (char*)api->copy_buf;
    pan = api->panels;
    if (*api->active) ++pan;
    if (pan->fs) { api->strcpy(api->note, M_NOTVOL); return; }

    /* The target volume and its unit: the selection in the volume list
     * (mdate holds the unit byte shifted right four, as read_volumes
     * stores it), or the first component of the panel's path. */
    unit = 0;
    if (pan->path[0]) {
        first_part(VOL, pan->path);
    } else {
        e = api->selected;
        if (e->name[0] != '/' || !e->access) { api->strcpy(api->note, M_SELECT); return; }
        api->strcpy(VOL, e->name);
        unit = (unsigned char)e->mdate << 4;
    }
    first_part(BOOT, api->cfg_path);

    /* One ON_LINE on unit 0 serves twice: the unit of the target when the
     * panel gave a path only, and the unit the program booted from. */
    boot = 0;
    ol.n = 2; ol.unit = 0; ol.buf = buf;
    if (!api->mli(0xC5, &ol)) {
        p = (const unsigned char*)buf;
        for (b = 0; b < 16; ++b, p += 16) {
            if (!*p) break;
            if ((len = *p & 15) == 0) continue;    /* a drive without a volume */
            NM[0] = '/';
            api->memcpy(NM + 1, p + 1, len);
            NM[len + 1] = 0;
            if (!unit && !api->strcmp(NM, VOL)) unit = *p & 0xF0;
            if (!api->strcmp(NM, BOOT)) boot = *p & 0xF0;
        }
    }
    if (!unit) { api->strcpy(api->note, M_NOVOL); return; }

    /* The volume header: the bitmap and the size, from the disk itself. */
    bp.n = 3; bp.unit = unit; bp.buf = BM; bp.block = 2;
    if (api->mli(0x80, &bp)) { api->strcpy(api->note, M_READ); return; }
    if ((BM[H_TYPE] & 0xF0) != 0xF0) { api->strcpy(api->note, M_NOTVOL); return; }
    bitmap = BM[H_BITMAP] | ((unsigned int)BM[H_BITMAP + 1] << 8);
    total  = BM[H_TOTAL]  | ((unsigned int)BM[H_TOTAL + 1] << 8);
    if (!total) { api->strcpy(api->note, M_NOTVOL); return; }

    /* F or W, then the confirmation each deserves. */
    api->sprintf(buf, M_ASK, VOL);
    api->message(buf);
    key = api->cgetc();
    if (key >= 'a') key -= 32;
    whole = key == 'W';
    if (key == 'F') {
        /* Do not interpret boot/header bytes as allocation bits, or begin
         * erasing before discovering a later bitmap page lies off-volume.
         * (total-1)>>12 is pages-1 without a 16-bit rounding overflow. */
        if (bitmap < 3 || bitmap >= total || ((total - 1) >> 12) >= total - bitmap) {
            api->strcpy(api->note, "Invalid volume bitmap."); return;
        }
        api->sprintf(buf, M_ASKF, VOL);
        if (!api->confirm(buf)) { api->strcpy(api->note, M_CANCEL); return; }
    } else if (whole) {
        if (unit == boot || !api->strcmp(VOL, BOOT)) { api->strcpy(api->note, M_BOOT); return; }
        api->gotoxy(0, 20);
        api->revers(1);
        api->cprintf(M_LOST, VOL);
        api->revers(0);
        if (!api->prompt(M_ERASE, 0, 0) || api->strcmp(api->input, M_WORD)) {
            api->strcpy(api->note, M_CANCEL);
            return;
        }
    } else {
        api->strcpy(api->note, M_CANCEL);
        return;
    }

    if (!whole && !free_safe()) {
        api->strcpy(api->note, "Free wipe refused: unreadable/unsafe allocation or cancelled."); return;
    }
    api->memset(ZERO, 0, 512);
    done = 0;
    err = 0;
    if (whole) wipe_whole(); else wipe_free();

    tail = M_WORD + 5;                  /* "" */
    if (err == 0xFF) tail = M_STOP;
    else if (err) { api->sprintf(buf, M_ERR, (unsigned int)err); tail = buf; }
    api->sprintf(api->note, M_DONE, done, VOL, tail);
    /* A big overlay: the core rereads both panels, redraws and writes the
     * note. Calling read_panel here would refill the entry tables over
     * BM and ZERO. */
}
