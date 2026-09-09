/* verify.c -- reads every block of a volume, or every byte of a file, and
 * says what could not be read.
 *
 * A volume, when the selection is one -- its name begins with a slash,
 * which only the volume list shows: READ_BLOCK ($80, unit = the entry's
 * mdate << 4) on each block, 0 to total - 1, into api->copy_buf, the bar
 * every sixteen blocks, ESC to stop; a block ProDOS refuses is counted,
 * its number listed as far as the message line holds them, and the read
 * goes on -- "/VOL: 800 blocks read, 0 bad", or "... 3 bad: 17 18 400".
 * Otherwise a file, read to its end 512 bytes at a time, its count checked
 * against the size of the entry: "NAME: 12345 bytes read OK", or "...
 * bytes read, then an error" with the count where it stopped, the offset
 * of the first byte it could not read. A directory reads like a file: its
 * blocks, and the size its entry gives. The verdict goes on the message
 * line.
 *
 * Two things this does not do, for want of room (below): it does not
 * refuse a panel opened on a disk image or a DOS 3.3 disk -- fopen fails
 * on the path and the ProDOS error is reported, which is the truth, just
 * less plainly said -- and it verifies the selection only, not each tagged
 * entry.
 *
 * A small overlay: $1B00-$1FFF, and of those 1,280 bytes the last 62 hold
 * the copy of the service table (below), so the link has 1,218 for code,
 * data and BSS -- the linker only complains past $2000, so check the map
 * (ld65 -m) after any change. cc65 spends twenty-five bytes on each call
 * through a pointer in a table, hence that copy at a constant address:
 * each service is reached through a two-instruction wrapper, a __cdecl__
 * function (its caller pushes all the arguments, cc65 adds no prologue)
 * that pops the last argument back into A/X, as the fastcall callee
 * expects, and jumps through the copy.
 *
 * sprintf is variadic, and cc65 calls a variadic function with the size of
 * its argument list in Y: runtime/enter.s stores that byte on the C stack
 * and runtime/leave.s pops the frame with it. The compiler only writes
 * that LDY when it sees the call is variadic, which a call through a
 * constant address is not -- Y would arrive at 0 (what pushax leaves) and
 * sprintf would return leaving its arguments on the C stack for good, a
 * dozen bytes lost to the program at each call. So each of the three call
 * sites has its own five-byte thunk after the header, LDY #argsize then
 * JMP (the sprintf slot of the table); the sizes are the ones cc65 pushes,
 * two bytes per argument and four for the long -- read them off the
 * generated assembly (the pushes before each JSR callax) if the messages
 * change.
 *
 * The file is counted in 512-byte chunks, in ints; the long the message
 * prints is assembled by hand: the long arithmetic of cc65 would not fit
 * either. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};

/* The copy of the service table, its first COPIED bytes (through sprintf;
 * nothing beyond is used): at the top of the window, at an even address,
 * so that no pointer straddles a page and the 6502's indirect jump reads
 * it right. The linked BSS must end below it: check the map. */
#define COPIED (offsetof(struct A2fcApi, sprintf) + 2)
#define TABLE (0x2000 - COPIED)
#define API ((const struct A2fcApi*)TABLE)
#define SLOT(f) (TABLE + offsetof(struct A2fcApi, f))
#define SERVICE(f) asm("jmp (%w)", SLOT(f))
/* LDY #argsize, JMP (the sprintf slot): see the head of the file. */
#define THUNK(n) 0xA0, (n), 0x6C, (unsigned char)SLOT(sprintf), (unsigned char)(SLOT(sprintf) >> 8)

#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, plugin_entry, 0, 0, 0,
    "Read every block of a volume or file, list bad ones"
};
/* right after the header, at $1B3C, $1B41 and $1B46 */
const unsigned char SPRINTF_THUNKS[15] = { THUNK(14), THUNK(12), THUNK(6) };
#pragma rodata-name (pop)
#define SPRINTF_(i) ((int (*)(char*, const char*, ...))(OVERLAY_WINDOW + sizeof(struct PluginHeader) + 5 * (i)))
#define sprintf_vol  SPRINTF_(0)    /* 7 arguments, 14 bytes */
#define sprintf_file SPRINTF_(1)    /* 5 arguments, the count long: 12 bytes */
#define sprintf_bad  SPRINTF_(2)    /* 3 arguments, 6 bytes */

void __cdecl__ message(const char* s)                          { asm("jsr popax"); SERVICE(message); }
void __cdecl__ report_error(const char* s)                     { asm("jsr popax"); SERVICE(report_error); }
void __cdecl__ progress_bar(const char* s, unsigned long d, unsigned long t) { asm("jsr popeax"); SERVICE(progress_bar); }
unsigned char __cdecl__ mli(unsigned char cmd, void* p)        { asm("jsr popax"); SERVICE(mli); }
FILE* __cdecl__ fopen_(const char* p, const char* m)           { asm("jsr popax"); SERVICE(fopen); }
size_t __cdecl__ fread_(void* b, size_t s, size_t n, FILE* f)  { asm("jsr popax"); SERVICE(fread); }
int __cdecl__ fclose_(FILE* f)                                 { asm("jsr popax"); SERVICE(fclose); }

#define KBD (*(volatile unsigned char*)0xC000)
#define KBDSTRB (*(volatile unsigned char*)0xC010)
#define BUF ((char*)API->copy_buf)      /* the block read, then the message */
#define BAD ((char*)API->other_full)    /* the other panel's path, free: the bad blocks */
#define BAD_LEN 40                      /* of its 81 bytes, what the message line holds */

/* READ_BLOCK's parameter block: cc65 packs it without padding. */
struct BlockParms { unsigned char n, unit; void* buf; unsigned int block; };

static const char NOTHING[] = "Nothing to verify.";

/* BSS: nothing zeroes it; every field below is written before it is read. */
static const void* tmp;            /* what the copy loops read from */
static unsigned char blen;         /* what is written in BAD */
static struct Entry ent;           /* the selected entry, copied: absolute addresses */
static union {
    struct BlockParms bp;          /* the volume: READ_BLOCK's parameters */
    struct {                       /* the file: what was read, 512-byte chunks then bytes, */
        unsigned int chunks, last; /* and chunks * 512 + last as the long the message prints */
        unsigned long bytes;
    } f;
} u;

/* Every block of the selected volume, whose mdate holds its DSSS byte >> 4.
 * A block ProDOS refuses is counted and its number listed, and the read
 * goes on. */
static void verify_volume(void)
{
    unsigned int blk = 0, left = ent.blocks, nbad = 0;
    BAD[0] = 0;
    blen = 0;
    u.bp.n = 3;
    u.bp.unit = (unsigned char)(ent.mdate << 4);
    u.bp.buf = BUF;
    for (; left; --left, ++blk) {
        if (!(blk & 15)) {
            progress_bar(ent.name, blk, ent.blocks);
            /* a key waiting is taken; the strobe leaves its code readable; ESC stops */
            if (KBD >= 128) { KBDSTRB = 0; if (KBD == 27) break; }
        }
        u.bp.block = blk;
        if (mli(0x80, &u.bp)) {
            ++nbad;
            if (blen < BAD_LEN) blen += sprintf_bad(BAD + blen, " %u", blk);
        }
    }
    sprintf_vol(BUF, "%s: %u blocks read%s, %u bad%s", ent.name, blk,
                left ? ", interrupted" : "", nbad, BAD);
    message(BUF);
}

/* Reads the selected file to its end, 512 bytes at a time. */
static void verify_file(void)
{
    FILE* f;
    const char* how;
    /* access = 0 is the mark the core puts on a DOS 3.3 disk offered in the
     * volume list: it is not a ProDOS file and has no path to open. */
    if (!ent.access) { message(NOTHING); return; }
    f = fopen_(API->full, "rb");             /* the path of the selection ("" if too long) */
    if (!f) { report_error(ent.name); return; }
    u.f.chunks = 0;
    while ((u.f.last = fread_(BUF, 1, 512, f)) == 512) ++u.f.chunks;
    fclose_(f);
    /* bytes = chunks * 512 + last (last < 512: nothing to carry) */
    asm("lda %v+2", u);   asm("sta %v+4", u);                                    /* last.lo */
    asm("lda %v", u);     asm("asl a"); asm("ora %v+3", u); asm("sta %v+5", u);  /* chunks.lo << 1 | last.hi */
    asm("lda %v+1", u);   asm("rol a"); asm("sta %v+6", u);
    asm("lda #0");        asm("rol a"); asm("sta %v+7", u);
    /* read entirely: as many bytes as the entry says (a short read is an error) */
    how = ", then an error";
    asm("ldy #3");
same:
    asm("lda %v+4,y", u);
    asm("cmp %v+%w,y", ent, offsetof(struct Entry, size));
    asm("bne %g", done);
    asm("dey");
    asm("bpl %g", same);
    how = " OK";
done:
    sprintf_file(BUF, "%s: %lu bytes read%s", ent.name, u.f.bytes, how);
    message(BUF);
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    /* the table, COPIED bytes to TABLE, and the selected entry, 29 bytes:
     * one pointer setup for the two, api in ptr1 and api->selected in ptr2 */
    tmp = api;
    asm("lda %v", tmp); asm("sta ptr1"); asm("lda %v+1", tmp); asm("sta ptr1+1");
    asm("ldy #%b", offsetof(struct A2fcApi, selected) + 1);
    asm("lda (ptr1),y"); asm("sta ptr2+1"); asm("dey");
    asm("lda (ptr1),y"); asm("sta ptr2");
    asm("ldy #%b", sizeof(struct Entry) - 1);
copy:
    asm("lda (ptr2),y"); asm("sta %v,y", ent); asm("dey"); asm("bpl %g", copy);
    asm("ldy #%b", COPIED - 1);
copy2:
    asm("lda (ptr1),y"); asm("sta %w,y", TABLE); asm("dey"); asm("bpl %g", copy2);

    if (!ent.name[0]) message(NOTHING);
    else if (ent.name[0] == '/') verify_volume();
    else verify_file();
}
