/* dgrview.c -- double lo-res pictures: a saved screen, or an a2dgrx sprite.
 * From the ! menu, on the selected file.
 *
 * A2FC could show hi-res, double hi-res, their RLE streams, Extasie's $F2
 * and packed FOT, and nothing at all in LO-RES -- the mode that lives in the
 * text page rather than the graphics page. This fills that hole, and it is
 * where a2dgrx (https://github.com/iolo/a2dgrx) draws.
 *
 * A word on a2dgrx, because it decides what this can and cannot do: it is a
 * drawing LIBRARY, not a file format. Its pixmaps are one byte per pixel
 * (low nibble the colour, high nibble a mask, zero meaning transparent),
 * its bitmaps one bit per pixel, its fonts three bytes a glyph -- and none
 * of that carries a header, a signature, a width, a height or a ProDOS
 * type. Its own sprites are `.byte` directives assembled into the program;
 * the repository ships no picture file at all. So nothing in a candidate
 * file says what it is, and this overlay decides by SIZE, with one question
 * asked when size is not enough:
 *
 *   "DGR" $01    A2FC's own header, proposed because no signature for this
 *                 mode exists anywhere: width, height, and a flag saying
 *                 whether the auxiliary half is there. See below.
 *   auxtype $0400 what bmp2dhr writes, the address of the text page, and
 *                 the nearest thing to a convention there is. The file is
 *                 the page as it was saved, screen holes and all: up to
 *                 1,024 bytes is 40 columns in the main half, more is 80
 *                 columns, the auxiliary half first, each half len/2.
 *                 Sizes in the wild are 962, 1,016, 1,922 and pairs of
 *                 1,016 -- so the size is NOT tested for equality.
 *   1,024/2,048   a plain BSAVE of the page, read the same way.
 *   anything else an a2dgrx pixmap. Its width is asked for, since the file
 *                 cannot say, and the height follows from the size.
 *
 * The proposed header, eight bytes, in the shape A2FC's own RLE streams
 * already use ("HGRR", "DHRR"):
 *
 *   0-2  'D' 'G' 'R'
 *   3    version, 1
 *   4    width in pixels, 40 or 80
 *   5    height in pixels, 48 (24 for the top of a mixed screen)
 *   6    flags; bit 0: the auxiliary half is present, and comes first
 *   7    reserved, zero
 *   8..  the picture, rows top to bottom and WITHOUT the screen holes:
 *        height/2 rows of forty bytes for the auxiliary half when bit 0 is
 *        set, then as many for the main half. So 1,928 bytes for 80 x 48
 *        and 968 for 40 x 48 -- and a file that says what it is.
 *
 * The picture lives at $400-$7FF, the TEXT page, not the graphics page: the
 * even columns in the auxiliary bank, the odd ones in the main bank, as in
 * 80-column text, and each byte holds TWO pixels stacked, the low nibble
 * above the high one. That is why the file is staged at $2000 first -- a
 * big overlay owns the graphics page -- and only then moved into the two
 * halves of the text page, which is the screen A2FC was drawing on.
 *
 * The staging area is $3000, NOT $2000: this overlay is loaded at $1B00 and
 * its own code runs past $2000, so staging there overwrote it and the
 * machine landed in the monitor. sdk/plugin.cfg is given a $1500 window
 * (XPLUGINS_SCRATCH in the Makefile) so that ld65 refuses any build whose
 * code or BSS reaches $3000, instead of leaving that to luck.
 *
 * A big overlay for that reason and not for room: what it wrecks is the
 * text screen, and only the core's return path for a big overlay puts the
 * display back to text and redraws both panels. */
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);
struct Header {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r[3]; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = {
    MEDIA_PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    "Lo-res and double lo-res pictures, a2dgrx sprites"
};
#pragma rodata-name (pop)

/* The two halves of the text page and the staging area. The host harness
 * (tools/test_dgrview.py) builds this file for an ordinary machine, where
 * $400 is not a screen and $C05E is not a soft switch: it supplies its own
 * memory and watches which half the writes go to. */
#ifdef PLUGIN_HOST
extern unsigned char host_main[1024], host_aux[1024], host_stage[2049];
extern unsigned char host_bank;             /* 0 main, 1 auxiliary */
extern unsigned char host_shown;            /* show() was reached */
extern unsigned char host_text, host_alt;   /* how show() left the screen */
extern unsigned char host_altchar;          /* RDALTCHAR, read and put back */
#define STAGE host_stage
#define PAGE  (host_bank ? host_aux : host_main)
#else
#define STAGE ((unsigned char*)0x3000)      /* the file, before it is spread out */
#define PAGE  ((unsigned char*)0x0400)      /* the text page: where lo-res lives */
#endif
#define WIDE  80
#define TALL  48
/* Text when at least a quarter of the visible bytes are blanks and blanks
 * outnumber solid bytes (see looks_text). */
#define TEXT_RULE(blank, solid, seen) ((blank) * 4 >= (seen) && (blank) > (solid))

/* BSS: nothing zeroes it; everything below is written before it is read. */
static const struct A2fcApi* A;
static unsigned int len;                    /* what was read */
static unsigned char wide;                  /* 1: double lo-res, 80 columns */
static unsigned char page;                  /* 1: a saved page, which T reads both ways */
static unsigned char text;                  /* 1: shown as text rather than lo-res */
static unsigned char alt;                   /* 1: the alternate character set */

static const char m_pick[] = "Select a lo-res picture or an a2dgrx pixmap.";
static const char m_open[] = "Cannot open it.";
static const char m_big[]  = "Over 2048 bytes: not a lo-res screen or a sprite.";
static const char m_ask[]  = "Pixmap width in pixels (2 hex digits, 01-50)";
static const char m_hdr[]  = "Invalid or truncated DGR picture.";
static const char m_wide[] = "Invalid sprite width or height.";
static const char m_scr[]  = "Lo-res screen, %u x %u.";
static const char m_txt[]  = "Text screen, %u columns. T: lo-res, A: character set.";
static const char m_spr[]  = "a2dgrx pixmap, %u x %u.";

/* The byte row `r` of the text page, 0 to 23: the Apple II's three thirds
 * of eight rows, $80 apart, forty bytes to a row. */
static unsigned int row_of(unsigned char r)
{
    return ((unsigned int)(r & 7) << 7) + (unsigned int)(r >> 3) * 40;
}

/* Which half of the text page the next writes reach. 80STORE must be on for
 * PAGE2 to mean the bank rather than the second screen; HIRES must be OFF,
 * or the routing would take $2000-$3FFF -- where the file is staged -- with
 * it. */
static void bank(unsigned char aux)
{
#ifdef PLUGIN_HOST
    host_bank = aux;
#else
    *(unsigned char*)0xC056 = 0;            /* lo-res: $2000 stays main */
    *(unsigned char*)0xC001 = 0;            /* 80STORE on */
    /* if/else, not *(unsigned char*)(aux ? 0xC055 : 0xC054): cc65 master
     * (the 6502 edition) compiles that cast as a store to address `aux`
     * itself -- zero page $00/$01 -- and never touched PAGE2. */
    if (aux) *(unsigned char*)0xC055 = 0;
    else *(unsigned char*)0xC054 = 0;
#endif
}

/* How many of the forty bytes of row `r` lie within the first `n` bytes of
 * a page saved with its holes: 40, a part of a cut-short row, or none. */
static unsigned char in_row(unsigned char r, unsigned int n)
{
    unsigned int at = row_of(r);
    if (at >= n) return 0;
    n -= at;
    return n < 40 ? (unsigned char)n : 40;
}

/* `n` bytes of a page saved as a BSAVE of $400 brings it back, holes and
 * all, into one half of the text page -- but only its 960 VISIBLE bytes.
 * The eight-byte screen holes after each 120 belong to the cards and the
 * firmware (the 80-column firmware's cursor, the mouse's position, MSLOT at
 * $7F8): the file's leftovers there would be written over live state that
 * nothing shows anyway. A short file simply leaves the bottom of the screen
 * as clear() left it. Walked with pointers: cc65 miscompiles PAGE[i] with a
 * 16-bit i on a page-aligned constant. */
static void half(const unsigned char* src, unsigned char aux, unsigned int n)
{
    unsigned char r, i, k;
    unsigned char* d;
    const unsigned char* s;
    bank(aux);
    for (r = 0; r < 24; ++r) {
        k = in_row(r, n);
        d = PAGE + row_of(r);
        s = src + row_of(r);
        for (i = 0; i < k; ++i) d[i] = s[i];
    }
    bank(0);
}

/* The proposed header's picture: rows of forty bytes with no holes between
 * them, so each row is placed at its own address rather than copied en
 * bloc. Returns what it consumed. */
static unsigned int rows_of(const unsigned char* src, unsigned char aux, unsigned char lines)
{
    unsigned int i, r;
    bank(aux);
    for (r = 0; r < lines; ++r) {
        unsigned int at = row_of((unsigned char)r);
        for (i = 0; i < 40; ++i) PAGE[at + i] = src[(unsigned int)r * 40 + i];
    }
    bank(0);
    return (unsigned int)lines * 40;
}

/* Black, the visible bytes only (see half()): both halves for 80 columns,
 * the main one alone for 40, whose screen never shows the other. */
static void clear(void)
{
    unsigned char b = wide + 1, r, i;
    unsigned char* d;
    while (b--) {
        bank(b);
        for (r = 0; r < 24; ++r) {
            d = PAGE + row_of(r);
            for (i = 0; i < 40; ++i) d[i] = 0;
        }
    }
    bank(0);
}

/* One double lo-res pixel. The even columns are the auxiliary bank's, the
 * odd ones the main bank's; within a byte the low nibble is the upper pixel
 * of the pair and the high nibble the lower. */
static void plot(unsigned char x, unsigned char y, unsigned char c)
{
    unsigned int off = row_of(y >> 1) + (x >> 1);
    unsigned char v;
    bank(!(x & 1));
    v = PAGE[off];
    PAGE[off] = (y & 1) ? ((v & 0x0F) | (c << 4)) : ((v & 0xF0) | c);
    bank(0);
}

/* The picture on the air. 80COL interleaves the two halves and AN3 selects
 * the double decoding; a 40-column screen wants neither. TXTCLR last, once
 * the page is armed. A text page is the same bytes in the same places: only
 * TXTSET and the character set differ, so T re-reads the screen without
 * writing a byte of it. */
static void show(void)
{
#ifdef PLUGIN_HOST
    host_shown = 1;
    host_text = text;
    host_alt = alt;
#else
    *(unsigned char*)0xC000 = 0;            /* 80STORE off: the display is page 1 */
    if (wide) { *(unsigned char*)0xC00D = 0; *(unsigned char*)0xC05E = 0; }
    else { *(unsigned char*)0xC00C = 0; *(unsigned char*)0xC05F = 0; }
    *(unsigned char*)0xC056 = 0;            /* lo-res */
    *(unsigned char*)0xC054 = 0;            /* page 1 */
    *(unsigned char*)0xC052 = 0;            /* mixed off */
    if (alt) *(unsigned char*)0xC00F = 0;   /* ALTCHAR (if/else: see bank()) */
    else *(unsigned char*)0xC00E = 0;
    if (text) *(unsigned char*)0xC051 = 0;  /* TXTSET */
    else *(unsigned char*)0xC050 = 0;
#endif
}

/* An a2dgrx pixmap, centred: one byte a pixel, the colour in the low
 * nibble, the high nibble a mask that leaves the background alone when it
 * is zero. The width has to be asked for -- the file does not carry it. */
static unsigned char pixmap(void)
{
    unsigned int i = 0;
    unsigned char w, h, x, y, x0, y0, b;
    if (!A->prompt(m_ask, 0, 2)) return 0;
    w = (unsigned char)((A->input[0] <= '9' ? A->input[0] - '0' : A->input[0] - 'A' + 10) * 16
                        + (A->input[1] <= '9' ? A->input[1] - '0' : A->input[1] - 'A' + 10));
    if (!w || w > WIDE || len % w || len / w > TALL) { A->strcpy(A->note, m_wide); return 0; }
    h = (unsigned char)(len / w);
    wide = 1;
    clear();
    x0 = (unsigned char)(WIDE - w) >> 1;    /* w <= WIDE and h <= TALL: checked above */
    y0 = (unsigned char)(TALL - h) >> 1;
    for (y = 0; y < h; ++y)
        for (x = 0; x < w; ++x) {
            b = STAGE[i++];
            if (b & 0xF0) plot(x0 + x, y0 + y, b & 0x0F);   /* zero mask: see through */
        }
    A->sprintf(A->note, m_spr, w, h);
    return 1;
}

/* A saved page that reads as TEXT rather than lo-res: the decision for the
 * screens of aux $0400 / 1,024 / 2,048 bytes, whose metadata are the same
 * for both (bmp2dhr's .SLO and a BSAVE of a title screen alike). Counted
 * over the visible bytes of each half read:
 *   blank  a space: $A0 normal, $20 inverse (screens written all in
 *          inverse exist), $E0 (the II+ shows it as a space; a page-2
 *          screen used it) -- in lo-res a black pixel over a grey, blue
 *          or yellow one, pairs pictures seldom hold (not $60: Time
 *          Lord's buildings are full of it);
 *   solid  a byte whose two nibbles are equal -- two pixels of one colour
 *          stacked, what every flat area of a picture is made of, and in
 *          text only a few characters (@ Q " 3 inverse, * ; L ] n normal).
 * Measured 2026-10-04 on 77 distinct real text screens (crack and title
 * screens, BBS and user-group disks, ASCII art) and 45 real lo-res and
 * double lo-res halves: no error. Texts have 33 % blanks or more, pictures
 * 23 % at most (the four text rows of a mixed screen), and the solid bytes
 * exceed the blanks by 27 points at least in every picture, while ASCII
 * art drawn with ';' ($BB, solid) still has more blanks than solids.
 * tools/textscreen_ref.py is the same rule; T turns a wrong guess round. */
static unsigned char looks_text(void)
{
    unsigned int blank = 0, solid = 0, seen = 0, n, h;
    unsigned char r, i, k, b;
    const unsigned char* s;
    h = wide ? len >> 1 : len;
    for (n = 0; n <= wide; ++n) {
        for (r = 0; r < 24; ++r) {
            k = in_row(r, h);
            s = STAGE + (n ? h : 0) + row_of(r);
            seen += k;
            for (i = 0; i < k; ++i) {
                b = s[i];
                if ((b & 0x3F) == 0x20 && b != 0x60) ++blank;
                if ((b >> 4) == (b & 15)) ++solid;
            }
        }
    }
    return TEXT_RULE(blank, solid, seen);
}

void __fastcall__ plugin_entry(const struct A2fcApi* a)
{
    const struct Entry* e = a->selected;
    FILE* in;
    unsigned char k, c, was;

    A = a;
    page = text = alt = 0;
    if (!e->name[0] || e->type == 0x0F || !a->full[0]) { a->strcpy(a->note, m_pick); return; }
    in = a->fopen(a->full, "rb");
    if (!in) { a->strcpy(a->note, m_open); return; }
    len = a->fread(STAGE, 1, 2049, in);      /* one over, to catch what is too big */
    a->fclose(in);
    if (!len || len > 2048) { a->strcpy(a->note, m_big); return; }

    if (len >= 3 && STAGE[0] == 'D' && STAGE[1] == 'G' && STAGE[2] == 'R') {
        unsigned char w, h, lines;
        /* Validate before reading the header or changing either screen bank.
         * Bytes beyond len may still hold another file's data. */
        if (len < 8 || STAGE[3] != 1 || STAGE[6] > 1 || STAGE[7]) {
            a->strcpy(a->note, m_hdr); return;
        }
        w = STAGE[4]; h = STAGE[5]; wide = STAGE[6];
        lines = h >> 1;
        if (w != (wide ? 80 : 40) || !h || h > TALL || (h & 1) ||
            len != 8 + (unsigned int)lines * 40 * (wide + 1)) {
            a->strcpy(a->note, m_hdr); return;
        }
        clear();
        if (wide) {
            unsigned int n = rows_of(STAGE + 8, 1, lines);   /* the auxiliary half */
            rows_of(STAGE + 8 + n, 0, lines);                /* then the main one */
        } else rows_of(STAGE + 8, 0, lines);
        a->sprintf(a->note, m_scr, (unsigned int)w, (unsigned int)h);
    } else if (e->aux == 0x0400 || len == 1024 || len == 2048) {
        page = 1;
        wide = len > 1024;
        clear();
        if (wide) {                          /* two halves: auxiliary one first */
            half(STAGE, 1, len >> 1);
            half(STAGE + (len >> 1), 0, len >> 1);
        } else                               /* forty columns, the main half */
            half(STAGE, 0, len);
        /* The enhanced IIe's 80-column firmware shows the alternate set
         * (MouseText, no flashing); a 40-column screen is the II's own. */
        if (looks_text()) text = 1, alt = wide;
    } else if (!pixmap()) {
        return;                              /* it said why */
    }

#ifdef PLUGIN_HOST
    was = host_altchar;
#else
    was = *(unsigned char*)0xC01E;          /* RDALTCHAR: the panels' set, bit 7 */
#endif
    for (;;) {
        if (page) {
            if (text) a->sprintf(a->note, m_txt, wide ? (unsigned int)WIDE : 40U);
            else a->sprintf(a->note, m_scr, wide ? (unsigned int)WIDE : 40U, (unsigned int)TALL);
        }
        show();
        /* The core's cgetc is the slideshow's (S, and Right by itself);
         * media_key ends on Escape or a neighbour, as media_wait does. */
        for (;;) {
            k = a->cgetc();
            c = k & 0x5F;                   /* either case, Open-Apple or not */
            if (page && c == 'T') { text ^= 1; break; }
            if (text && c == 'A') { alt ^= 1; break; }
            if (a->media_key(k)) goto done;
        }
    }
done:
    /* The panels' character set back: switch_to_text does not touch it. */
#ifdef PLUGIN_HOST
    host_altchar = was;
#else
    if (was & 0x80) *(unsigned char*)0xC00F = 0;
    else *(unsigned char*)0xC00E = 0;
#endif
    a->strcpy(a->reselect, e->name);
}
