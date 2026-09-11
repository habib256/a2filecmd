/* paint816.c -- the packed pictures 816/Paint writes, its own default save
 * format. ProDOS type $06 with auxtype $E001 (a hi-res page) or $E002 (a
 * double hi-res one). From the ! menu, on the selected entry.
 *
 * These are the files a2fc's own viewer cannot claim: a $06 is taken for a
 * picture on its SIZE, and a packed one is any size at all -- the reference
 * picture here is 6,130 bytes for a 16 KB screen -- so they fell through to
 * the hex viewer. 816/Paint is what most Apple II double hi-res art was
 * drawn with, and packed is what it saves unless told otherwise, so this is
 * the format most of that art is actually stored in.
 *
 * Nothing documents it; it was read off twelve chosen-plaintext pairs (the
 * raw pages went on a disk, 816/Paint packed them, the two were compared)
 * and then checked against a real picture, which it reproduces to the byte.
 *
 *   [8 bytes]   double hi-res only: the auxiliary plane's first eight bytes
 *               again -- the stream carries them too, so they are skipped
 *   per plane:  one $FF, then the records below; auxiliary plane first
 *   [trailer]   the Pascal string "816PATT" and 64 bytes of fill patterns,
 *               which a viewer has no use for and never reaches
 *
 * A plane decodes to 7,680 bytes read COLUMN BY COLUMN -- the RIGHTMOST
 * byte column first, rows 0 to 191 down it, then the column to its left --
 * which is why put() below walks row addresses rather than a pointer. The
 * 1,024 bytes of screen holes are not in the stream: they are not on the
 * screen either, so nothing writes them.
 *
 * One tag byte opens each record:
 *
 *   bit 7 clear   a literal run: n = the tag, or the next byte when the tag
 *                 is 0, followed by n bytes copied out as they are;
 *   bit 7 set     a pattern run: n = bits 6-2, or the next byte when those
 *                 are 0; bits 1-0 pick a pattern LENGTH of 1, 2, 4 or 8;
 *                 that many bytes follow and repeat cyclically to make n
 *                 bytes -- so n counts BYTES OUT, not repetitions.
 *
 * A BIG overlay, and its code stops before $2000 (the Makefile links it
 * with a $0500 window so ld65 enforces that) because the picture is about
 * to own $2000-$3FFF. Writing the auxiliary bank costs the ProDOS /RAM
 * volume that lives there; api->ram_format rebuilds it, as the core does
 * after a raw DHGR, and the note says so. */
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);
void p8_aux_move(void);                 /* paint816.s */
void __fastcall__ p8_show(unsigned char two);
void p8_main_bank(void);
void p8_top(void);                      /* the top of a fresh plane */
void __fastcall__ p8_put(unsigned char v);   /* one byte, and one row down */
extern unsigned char p8_col;            /* 39 down to 0, then 255: plane full */

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[34]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
    {0,0,0}, "816/Paint packed picture" };
#pragma rodata-name (pop)

/* BSS: nothing zeroes it; every one of these is written before it is read. */
static const struct A2fcApi* A;
static FILE* in;
static unsigned char have, at;

/* The pattern lengths bits 1-0 of a tag select, less one. They are powers of
 * two, so the length is only ever wanted as a mask: `& len` walks the pattern
 * and `<= len` reads it in, and neither costs a compare against a variable. */
static const unsigned char mask_of[4] = { 0, 1, 3, 7 };

/* The next byte of the stream, or 0 once it has run out: a decoder that
 * never has to test for the end stays short, and a record cut in two by the
 * end of the file simply finishes on zeros. The end needs no flag of its
 * own -- `at` is left where it was, so the next call reads again and gets
 * nothing again, at the price of one fruitless read per byte on a file that
 * really is truncated.
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
        if (!have) return 0;            /* `at` stays 0, so the next call retries */
    }
    return A->copy_buf[at++];
}

/* One plane: its $FF marker, then records until all 40 columns are full.
 * Returns 0 when the marker is not there -- the one thing in the file that
 * can be checked -- so a file that is not one of these is refused rather
 * than shown as noise.
 *
 * A stream that stops early is padded rather than refused: half a picture is
 * worth more than none. The end needs no flag of its own -- `have` is the
 * length of the last read, and only a read that came back empty leaves it
 * at zero. */
static unsigned char plane(void)
{
    unsigned char tag, n, i, len, b;
    static unsigned char pat[8];

    if (getb() != 0xFF) return 0;   /* a getb past the end returns 0, not $FF */
    p8_top();
    while (!(p8_col & 0x80)) {
        tag = getb();
        if (!have) break;               /* the stream ran out: `have` says so */
        if (tag & 0x80) {
            n = (tag >> 2) & 0x1F;
            if (!n) n = getb();
            len = mask_of[tag & 3];
            /* Through a scalar rather than storing the call's result into
             * the array: cc65 spends fewer bytes that way, and the window is
             * 1,280 bytes for the whole overlay.
             *
             * No `i++` inside either expression. cc65 2.18 compiles
             * `while (i++ != len)` as a test on the INCREMENTED i and
             * `pat[i++ & len]` as `pat[++i & len]`: the reader then swallowed
             * 256 bytes for a one-byte pattern and started it on the wrong
             * one. It decoded correctly on the host, where the same source is
             * built by a different compiler, and only the emulator bench
             * (bench/paint816.py) showed it. */
            i = 0;
            do {
                b = getb();
                pat[i] = b;
                ++i;
            } while (i <= len);
            i = 0;
            while (n--) {
                p8_put(pat[i]);
                i = (i + 1) & len;
            }
        } else {
            n = tag;
            if (!n) n = getb();
            while (n--) p8_put(getb());
        }
    }
    while (!(p8_col & 0x80)) p8_put(0); /* a truncated stream: the rest in zeros */
    return 1;
}

/* The whole file: the prefix a double hi-res one opens with, then its
 * planes. Separate from plugin_entry so that the host harness runs THIS and
 * not a copy of it. */
static unsigned char picture(unsigned char two)
{
    unsigned char i;

    /* A double hi-res file opens with the auxiliary plane's first eight
     * bytes verbatim. The stream holds them as well, so they are read past
     * rather than used. */
    if (two) for (i = 0; i < 8; ++i) getb();
    p8_main_bank();
    /* The screen stays on text while the page is decoded -- the panels are
     * intact in $400-$7FF -- so the picture lights up only once complete,
     * and never column by column. */
    if (!plane()) return 0;
    if (!two) return 1;
    p8_aux_move();
    return plane();
}

static const char m_bad[] = "Not a packed 816/Paint page.";
static const char m_dhr[] = "/RAM rebuilt.";   /* terse: the window is full */

void __fastcall__ plugin_entry(const struct A2fcApi* a)
{
    const struct Entry* e = a->selected;
    unsigned char two, ok;

    A = a;
    /* $E001 is a hi-res page, $E002 a double hi-res one; the high byte alone
     * tells one of these from any other binary. A missing path or an
     * unreadable file falls out of fopen below, which spares a guard. */
    two = (unsigned char)e->aux - 1;
    if (e->type != 0x06 || (e->aux >> 8) != 0xE0 || two > 1) {
        a->strcpy(a->note, m_bad);
        return;
    }
    in = a->fopen(a->full, "rb");
    if (!in) { a->strcpy(a->note, m_bad); return; }
    have = at = 0;
    ok = picture(two);
    a->fclose(in);                      /* one close for both ways out */
    if (!ok) { a->strcpy(a->note, m_bad); return; }

    p8_show(two);
    while (a->cgetc() != KEY_ESC) {}

    a->strcpy(a->reselect, e->name);
    /* The picture was its own answer; the only thing left to say is what a
     * double hi-res cost -- the /RAM volume that shares the auxiliary bank,
     * rebuilt here as the core does after a raw DHGR. */
    if (two && a->ram_format()) a->strcpy(a->note, m_dhr);
}
