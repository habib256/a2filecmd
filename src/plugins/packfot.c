/* packfot.c -- the PACKED ProDOS graphics files ($08) that the core's own
 * viewer cannot read: auxtype $4000, a hi-res page, and $4001, a double
 * hi-res page. From the ! menu, on the selected entry.
 *
 * The core knows raw pages and its own RLE streams; a $08 used to be
 * claimed as an image on its type alone and then refused with "not an
 * image", which left these files with no viewer at all -- not even the hex
 * one every other unknown type falls back to. Return and I now route the
 * supported packed auxiliary types here, before testing raw-page sizes.
 *
 * The packing is Apple's PackBytes, the one the IIgs uses for its own
 * pictures. One tag byte opens each packet: the low six bits carry a count
 * n (1 to 64), the top two say what to do with it --
 *
 *   0  the next n bytes, as they are;
 *   1  the next byte, n times;
 *   2  the next FOUR bytes, n times (4n bytes out);
 *   3  the next byte, 4n times.
 *
 * The result is the page itself, in address order, so there is no row
 * arithmetic here: the bytes go to $2000 one after another. A packer that
 * drops the tail of the last row is normal (one of the reference files
 * stops one byte short of 8,192); getb reports the end of the stream and
 * the rest of the page is zeroed rather than refused.
 *
 * $4001 holds 16,384 bytes: the auxiliary plane first, then the main one,
 * the order A2FC's raw DHGR files already use. They are ONE stream, not
 * two -- a packet straddles the boundary between them -- so the decoder
 * runs straight through and put() carries the first plane to the auxiliary
 * bank with AUXMOVE (packfot.s) at the moment it crosses. Decoding it
 * through an auxiliary routing of $2000-$3FFF instead would be simpler and
 * wrong: that routing also moves $400-$7FF, where the //c SmartPort
 * firmware keeps its state, and a ProDOS read done under it never comes
 * back (a2fc.c says the same).
 *
 * A BIG overlay, and only for the flag: the code stops before $2000 (the
 * Makefile links it with a $0500 window, so ld65 enforces that) because the
 * picture is about to own $2000-$3FFF. The flag is what makes the core set
 * the tags aside, reread both panels and put the screen back to text on
 * return. Writing to the auxiliary bank costs the ProDOS /RAM volume, which
 * lives there: api->ram_format rebuilds it, as the core does after a raw
 * DHGR, and the note says so. */
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);
void pf_aux_move(void);                 /* packfot.s */
void __fastcall__ pf_show(unsigned char two);
void pf_main_bank(void);

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[34]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUX, plugin_entry,
    {0,0,0}, "Packed $08 pictures ($4000/$4001)" };
#pragma rodata-name (pop)

/* The page the picture goes to. The host harness (tools/test_packfot.py)
 * builds this file for an ordinary machine, where $2000 is not a graphics
 * page: it supplies its own eight kilobytes instead. */
#ifdef PLUGIN_HOST
extern unsigned char host_page[8192];
#define PAGE host_page
#define END  (host_page + 8192)
#else
#define PAGE ((unsigned char*)0x2000)
#define END  ((unsigned char*)0x4000)
#endif

/* BSS: nothing zeroes it; every one of these is written before it is read. */
static const struct A2fcApi* A;
static FILE* in;
static unsigned char have, at, eof;
static unsigned char* dst;              /* the next byte of the picture */
static unsigned char cross;             /* 1: $2000-$3FFF still owes the auxiliary bank */

/* The next byte of the stream, or 0 once it has run out (eof says which):
 * a decoder that never has to test for the end stays short, and a packet
 * cut in two by the end of the file simply finishes on zeros.
 *
 * 255 bytes at a time, not 256: `have` and `at` are bytes, the cheapest
 * arithmetic a 6502 has, and 256 does not fit in one. Cast down, a full
 * read comes back as ZERO -- which getb would read as an end of file at
 * the very first byte, and the picture would decode to nothing at all. */
static unsigned char getb(void)
{
    if (at == have) {
        have = (unsigned char)A->fread(A->copy_buf, 1, 255, in);
        at = 0;
        if (!have) { eof = 1; return 0; }
    }
    return A->copy_buf[at++];
}

/* One byte of the picture. The end of the page is what bounds the writes,
 * so a corrupt packet cannot run past $3FFF -- and no separate counter is
 * kept for it, which matters in a loop that runs sixteen thousand times.
 * Filling it once with a double hi-res still to finish hands that plane to
 * the auxiliary bank and starts the main one over the same addresses. */
static void put(unsigned char v)
{
    if (dst == END) {
        if (!cross) return;
        pf_aux_move();
        cross = 0;
        dst = PAGE;
    }
    *dst++ = v;
}

/* The whole picture: 8,192 bytes at $2000, or 16,384 across the two banks
 * when `two`. Returns 0 if the stream held nothing at all; a stream that
 * stops early -- one of the reference pictures ends a byte short -- fills
 * the rest with zeros rather than being refused. Every count stays on a
 * byte: a packet is 64 items at most, and the two four-at-a-time forms are
 * written as four puts rather than a count of 256. */
static unsigned char decode(unsigned char two)
{
    unsigned char tag, n, q0, q1, q2, q3;
    dst = PAGE;
    cross = two;
    while (dst != END || cross) {
        tag = getb();
        if (eof) break;                             /* a tag read past the end is not a tag */
        n = (tag & 0x3F) + 1;
        /* The tag compared whole, not `tag >> 6` in a switch: the shift and
         * the dispatch cost more than three branches, and the window has no
         * room to spare. */
        if (tag < 0x40) {                           /* n bytes, as they are */
            while (n--) put(getb());
        } else if (tag < 0x80) {                    /* one byte, n times */
            tag = getb();
            while (n--) put(tag);
        } else if (tag < 0xC0) {                    /* four bytes, n times */
            q0 = getb(); q1 = getb(); q2 = getb(); q3 = getb();
            while (n--) { put(q0); put(q1); put(q2); put(q3); }
        } else {                                    /* one byte, 4 x n times */
            tag = getb();
            while (n--) { put(tag); put(tag); put(tag); put(tag); }
        }
    }
    if (dst == PAGE && cross == two) return 0;
    while (dst != END || cross) put(0);
    return 1;
}

static const char m_bad[]  = "Not a packed $08 picture.";
static const char m_dhr[]  = "Double hi-res; /RAM rebuilt.";

void __fastcall__ plugin_entry(const struct A2fcApi* a)
{
    const struct Entry* e = a->selected;
    unsigned char two;

    A = a;
    /* The high byte alone tells a packed picture from a raw one; the low
     * byte is 0 for hi-res, 1 for double. A missing path or an unreadable
     * file falls out of fopen below, which spares a guard here. */
    two = (unsigned char)e->aux;
    if (e->type != 0x08 || (e->aux >> 8) != 0x40 || two > 1) {
        a->strcpy(a->note, m_bad);
        return;
    }
    in = a->fopen(a->full, "rb");
    if (!in) { a->strcpy(a->note, m_bad); return; }
    have = at = eof = 0;
    pf_main_bank();

    /* The screen stays on text while the page is decoded -- the panels are
     * intact in $400-$7FF -- so the picture lights up only once complete,
     * and never band by band. */
    if (!decode(two)) { a->fclose(in); a->strcpy(a->note, m_bad); return; }
    a->fclose(in);

    pf_show(two);
    a->media_wait();

    /* The auxiliary plane is memory the ProDOS /RAM volume uses: once
     * written to, the volume is inconsistent and the next write to it would
     * return anything at all. Rebuilt from scratch through its own driver,
     * as the core does on return from a raw DHGR, and said so. */
    a->strcpy(a->reselect, e->name);
    /* The picture was its own answer; the only thing left to say is what a
     * double hi-res cost, the /RAM volume that shares the auxiliary bank. */
    if (two && a->ram_format()) a->strcpy(a->note, m_dhr);
}
