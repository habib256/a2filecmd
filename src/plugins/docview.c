/* docview.c -- read an Epistole, Papyrus, HomeWord or Bank Street Writer
 * document laid out as
 * it prints, page by page on a full screen. From Return on a document that
 * says what it is (a leading `_` command or `$FF` code), or the ! menu.
 *
 * Epistole (Version Soft) writes ProDOS text files ($04), seven-bit ASCII
 * with CR ends, and lays them out by commands inside the text: `_` and two
 * letters, then an optional number -- _MG10 left margin, _MD65 right
 * margin, _MI5 indent now, _MA5 indent from the next line, _CE centre the
 * lines until _PC, _CL or _JD, _TD30 a tab stop, _IG/_SG bold on/off,
 * _ID/_IS double width on/off, _SP new page; the rest (justification,
 * condensed, page length...) only concerns the printer. `#NAME]` is a
 * mail-merge variable, `#*NAME=]` one typed at print time, `#:?X]` a
 * calculated value: shown in inverse video without their marks; `#:X=..]`
 * sets a variable and prints nothing.
 *
 * Papyrus (Ediciel) is the French HomeWord (Sierra): DOS 3.3 text files,
 * high-bit ASCII, one $8D per paragraph, and codes between two $FF bytes:
 * $FF $06 $FF centres the next line, $FF $05 $FF starts a page, the
 * others (margins, outline points...) only concern the printer.
 *
 * Bank Street Writer (Broderbund) saves the same high-bit text in a BIN
 * file ($0840 or $63D0 on DOS 3.3, 0 on ProDOS): $8D ends a paragraph,
 * $83 at a line's start centres it, $89 is a tab (4 columns), and the text
 * ends at the first $00 -- what follows is the buffer's leftovers.
 *
 * Both write French with the ISO 646-FR national characters: { e acute,
 * } e grave, | u grave, \ c cedilla, @ a grave, [ degree (n[ is "no"); Epistole types a
 * circumflex as a ^ after its letter, Papyrus as codes $18-$1C (a e i o
 * u; $19 and $1B confirmed on real documents). An Apple IIe with a US
 * character set shows { } | \ @ as themselves: they are shown as the
 * unaccented letter, and A switches to the codes as stored -- right on a
 * machine with the French character set. docs/MANUAL.md, "Read documents".
 *
 * Paging both ways, as MDVIEW does: the starts of the last 16 pages --
 * the offset of the line a page starts in, how many of its rows precede
 * the page, and the layout state at that line -- so that a page is always
 * rendered by replaying its first line. Read-only; a big overlay, code and
 * BSS in $1B00-$3D5F, whose scratch is $3D60-$3FFF: the page table (at
 * $3D60), the copy of the service table ($3E40: a call through it costs
 * half of one through api->), the row and its attributes ($3EB0, $3F00),
 * the state ($3F50), the read buffer (112 bytes at $3F90). A read error
 * ends the page and says so: it is never shown as the end of the document.
 * Offsets are 16 bits: the programs kept their documents in memory, and a
 * file over 64 KB is refused. */

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
    "Read Epistole, Papyrus, HomeWord, Bank Street docs"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

#define WIDTH     79                       /* the widest row */
#define ROW1      1                        /* the first text row; row 0 is the title */
#define LASTROW   21                       /* the last text row; 22 is the status line */
#define MAXPAGES  16                       /* a power of 2: page numbers are masked */
#define NVARS     12                       /* Epistole's variables */
#define VNAME     6                        /* the characters of a name that count */
#define MAXND     8                        /* decimals at most */
#define DEFAULT_ND 2                       /* decimals before any _ND */
#define VBUFSZ    112

/* The layout state a line starts with: margins, indent, bold, for a
 * calculated number its decimals (_ND) and decimal tab (_TD), the printed
 * page's number (1 to 255, where it stays: MAXPG), and whether a page
 * break is due before the next text (so that a line replayed at a screen
 * page's top redoes it) -- a byte of its own: as bit 7 of the number, page
 * 128 was a break nobody asked for. */
struct Layout { unsigned char lm, rm, mi, ma, inv, centre, nd, td, pg, brk; };
#define MAXPG 255
struct Start { unsigned int off, skip; struct Layout lay; };   /* 64 KB at most: offsets in 16 bits */

#ifdef PLUGIN_HOST                         /* tools/test_docview.py runs this file on the host */
static struct Start host_starts[MAXPAGES];
static char host_rb[81];
static unsigned char host_ra[81];
static unsigned char host_vbuf[VBUFSZ];
#define STARTS host_starts
#define RB     host_rb
#define RA     host_ra
#define VBUF   host_vbuf
static struct A2fcApi a;                   /* the service table, copied */
#else
/* The scratch, $3D60-$3FFF: the code and BSS end under it (Makefile). */
#define STARTS ((struct Start*)0x3D60)     /* the page table: $3D60-$3E3F */
typedef char starts_fit[0x3E40 - 0x3D60 + 1 - MAXPAGES * sizeof(struct Start)];
#define a      (*(struct A2fcApi*)0x3E40)  /* the service table, copied: $3E40-$3EAF */
typedef char api_copy_fits[0x70 + 1 - sizeof(struct A2fcApi)];
#define RB     ((char*)0x3EB0)             /* the row being built, 80 */
#define RA     ((unsigned char*)0x3F00)    /* its inverse flags, 80 */
#define VBUF   ((unsigned char*)0x3F90)    /* the read buffer: $3F90-$3FFF */
typedef char vbuf_fits[0x4000 - 0x3F90 + 1 - VBUFSZ];
/* libc's ferror links errno and fmisc, 90 bytes: _FILE::f_flags (offset 1,
 * asminc/_file.inc) and its _FERROR bit, as FIND reads them. */
#define ferror(f) (((unsigned char*)(f))[1] & 0x04)
#endif

/* The state, in the scratch at $3F50. Nothing zeroes it; everything is
 * written before it is read. */
struct State {
    struct Start next;                     /* where the next page starts */
    struct Layout lay, line_lay;           /* the state now; at the line's start */
    FILE* vf_;
    unsigned int vlen_, vpos_;             /* the window VBUF[0..vlen), read to vpos */
    unsigned int vbase_;                   /* the file offset of VBUF[0] */
    unsigned int line_off_;                /* where the line being rendered starts */
    unsigned char papyrus_;                /* 1: high-bit Papyrus/HomeWord; 0: Epistole */
    unsigned char raw_;                    /* 1: the ISO 646-FR codes as stored */
    unsigned char row_, rc_, left_;        /* the screen row; the row's length; its left edge */
    unsigned char endmark_;                /* __XX seen: a header or footer ends */
    /* Rows of one paragraph: 16 bits are 65,535 rows, 5 MB of text. */
    unsigned int skip_rows_, rows_done_;
    /* This page: 0 more follows; 1 the end of the file; 2 or 3 a read or
     * a seek failed (bit 1), which ends the page too and is never shown
     * as the end. */
    unsigned char done_;
    /* plugin_entry's: the page shown, the pages known, the oldest, its number */
    unsigned char page_, known_, head_;
    unsigned int first_;
};
#ifdef PLUGIN_HOST
static struct State host_state;
#define ST host_state
#else
#define ST (*(struct State*)0x3F50)
typedef char state_fits[0x3F90 - 0x3F50 + 1 - sizeof(struct State)];   /* below VBUF */
#endif
#define NEXT         ST.next
#define LAY          ST.lay
#define LINE_LAY     ST.line_lay
#define vf           ST.vf_
#define vlen         ST.vlen_
#define vpos         ST.vpos_
#define vbase        ST.vbase_
#define line_off     ST.line_off_
#define papyrus      ST.papyrus_
#define raw          ST.raw_
#define row          ST.row_
#define rc           ST.rc_
#define left         ST.left_
#define endmark      ST.endmark_
#define skip_rows    ST.skip_rows_
#define rows_done    ST.rows_done_
#define done         ST.done_

static const char iso[] = "{e}e|u\\c@a[o";  /* ISO 646-FR pairs: code, plain letter ([ is a degree sign) */
static const char vowels[] = "aeiou";      /* Papyrus $18-$1C */

static const char m_pick[] = "Select a document.";
static const char m_open[] = "Open failed.";
static const char m_big[]  = "Over 64 KB: too long.";
static const char m_page[] = "Page %u%s: Space/Down next, Up back, R start, A accents, ESC quits";
static const char m_end[]  = " (end)";
static const char m_err[]  = " (read error)";
static const char m_nil[]  = "";
static const char* const m_ends[4] = { m_nil, m_end, m_err, m_err };

/* -- reading ------------------------------------------------------------- */

static int getc_(void)
{
    if (vpos >= vlen) {
        vbase += vlen;
        vpos = 0;
        vlen = a.fread(VBUF, 1, VBUFSZ, vf);
        if (vbase + vlen < vbase) {        /* past 64 KB (a stale size let it open): refused there */
            vlen = 0xFFFF - vbase;
            if (!vlen) done = 2;
        }
        if (!vlen) {                       /* the end -- or an error, never taken for it */
            if (ferror(vf)) done = 2;
            return -1;
        }
    }
    return VBUF[vpos++];
}

#define unget() (--vpos)                   /* only right after a successful getc_ */

static unsigned int tell_(void) { return vbase + vpos; }

static void seek_(unsigned int off)
{
    if (off >= vbase && off < vbase + vlen) { vpos = off - vbase; return; }
    if (a.fseek(vf, (long)off, SEEK_SET)) done = 2;
    vbase = off;
    vlen = vpos = 0;
}

/* A byte, the high bit stripped in a Papyrus document; -1 at the end. The
 * $FF of a code is kept: it is no character. */
static int rd(void)
{
    int c = getc_();
    if (papyrus && c >= 0 && c != 0xFF) c &= 0x7F;
    return c;
}

/* -- writing ------------------------------------------------------------- */

static void pad(void)
{
    left = LAY.lm + LAY.mi;
    if (left > WIDTH - 10) left = WIDTH - 10;
    a.memset(RB, ' ', left);
    a.memset(RA, 0, left);
    rc = left;
}

/* The row RB[0..rc) goes to the screen (or is skipped, at the top of a
 * page), centred between the margins when asked; inverse runs switch the
 * video mode as they go. When the page is full, the next page starts in
 * this very line, after its rows so far -- and nothing more is written,
 * whatever the caller goes on sending (a field of 60 characters between
 * narrow margins, a footer of one long line): a row past the last is
 * dropped here, to be shown by the replay at the next page's top. Row 24
 * and beyond are no screen rows: writing there went into the peripheral
 * cards' screen holes. */
static void emit(void)
{
    unsigned char i, x, now = 0;
    ++rows_done;
    if (skip_rows) --skip_rows;
    else if (row <= LASTROW) {
        i = 0;
        x = 0;
        if (LAY.centre || LINE_LAY.centre) {
            i = x = left;                  /* the text alone, as much room either side: */
            /* half of what the row leaves under the right margin, on eight
             * bits (only when rm > rc: the difference is 1..79) */
            if (LAY.rm > rc) x += (unsigned char)(LAY.rm - rc) >> 1;
        }
        a.gotoxy(x, row);
        for (; i < rc; ++i) {
            if (RA[i] != now) { now = RA[i]; a.revers(now); }
            a.cputc(RB[i]);
        }
        if (now) a.revers(0);
        if (++row > LASTROW) { NEXT.off = line_off; NEXT.skip = rows_done; NEXT.lay = LINE_LAY; }
    }
    pad();
}

/* One character into the row, wrapped at the last space before the right
 * margin. */
static void put_(unsigned char c)
{
    unsigned char i, rm = LAY.rm;
    if (rm > WIDTH) rm = WIDTH;
    if (rm < left + 10) rm = left + 10;
    if (rc >= rm) {
        if (c == ' ') { emit(); return; }
        for (i = rm - 1; i > left && RB[i] != ' '; --i) ;
        /* The tail goes to the next row's left edge (pad): a margin moved
         * in this row (_MG, _MI) can put it past the tail, which pad would
         * then blank and the copy carry beyond the 80 bytes of RB and RA.
         * The row is then cut where it is full, as with no space (also for
         * an edge past pad's clamp at 69: a row that narrow, no matter). */
        if (i > left && (unsigned char)(LAY.lm + LAY.mi) <= i + 1) {   /* break at that space: the tail moves on */
            rm -= i + 1;                   /* now the tail's length (-Cl: a byte less) */
            rc = i;
            emit();
            a.memcpy(RB + rc, RB + i + 1, rm);
            a.memcpy(RA + rc, RA + i + 1, rm);
            rc += rm;
        } else emit();                     /* no space: a hard break */
    }
    RB[rc] = c;                            /* not RB[rc++]: cc65 2.19 increments rc first */
    RA[rc] = LAY.inv;
    ++rc;
}

/* A national character as the screen should show it. */
static unsigned char plain(unsigned char c)
{
    unsigned char i;
    if (!raw)
        for (i = 0; i < sizeof iso - 1; i += 2)
            if (c == (unsigned char)iso[i]) return iso[i + 1];
    return c;
}

/* A new page: a rule from margin to margin, if the page has room. */
static void rule(void)
{
    unsigned char i = LAY.rm > WIDTH ? WIDTH : LAY.rm;
    while (rc < i) { RB[rc] = '-'; RA[rc] = 0; ++rc; }
    emit();
}

/* An Epistole command, after its `_`: two letters and a number. Returns 0
 * when the `_` was no command (then it is a character). */
static const char cmds[] = "MGMDMIMACEPCCLJDTDIGIDSGISSPNDDBEN";
static unsigned char inblock = 0;          /* in DATA: nothing zeroes the BSS */
static unsigned char epistole(void)
{
    int c;
    unsigned char k1, k2 = 0, i;
    unsigned int n = 0;
    c = rd();
    if (c == '_') {                        /* __BA, __EA: a block ends; glossary marks */
        for (n = 0; n < 2 && (c = rd()) >= 'A' && c <= 'Z'; ++n) ;
        if (n < 2 && c >= 0) unget();
        endmark = 1;
        return 1;
    }
    if (c < 'A' || c > 'z') { if (c >= 0) unget(); return 0; }
    k1 = c & 0xDF;
    c = rd();
    if (c >= 'A' && c <= 'z') k2 = c & 0xDF; else if (c >= 0) unget();
    while ((c = rd()) >= '0' && c <= '9') n = n * 10 + (c - '0');
    if (c >= 0) unget();
    if (n > WIDTH) n = WIDTH;
    /* A space after a command that opens a row separates it from the text. */
    if (rc == left && rd() != ' ') unget();
    for (i = 0; i < sizeof cmds - 1 && (cmds[i] != k1 || cmds[i + 1] != k2); i += 2) ;
    switch (i >> 1) {
    case 0: LAY.lm = n; goto margin;                   /* MG */
    case 1: LAY.rm = n ? n : WIDTH; goto margin;       /* MD */
    case 2: LAY.mi = n;                                /* MI: now, and from the next line */
    case 3: LAY.ma = n;                                /* MA: from the next line */
    margin: if (rc == left) pad(); break;
    case 4: LAY.centre = 1; break;                     /* CE: centring lasts until */
    case 5: case 6: case 7: LAY.centre = 0; break;     /* PC CL JD: an alignment */
    case 8: LAY.td = n; break;                         /* TD: a decimal tab for numbers, */
                                                       /* from the margin; text stays */
    case 9: case 10: LAY.inv = 1; break;               /* IG ID: bold, wide on */
    case 11: case 12: LAY.inv = 0; break;              /* SG IS: off */
    case 13: LAY.brk = 1; break;                       /* SP: a new page */
    case 14: LAY.nd = n > MAXND ? MAXND : n; break;    /* ND: decimals */
    case 15: case 16:                      /* DB, EN: a footer, a header, shown at the */
        /* page ends (show_def); here, the row it leaves. Its commands are
         * taken as they come, but a _DB or _EN among them opens nothing:
         * the block open goes on to the one __XX that ended them all
         * anyway. Each used to call this function again, two bytes of the
         * processor's stack a level -- 130 of them in a row wrapped page 1
         * over the return addresses. Two levels at most now. */
        if (inblock) break;
        inblock = 1;
        for (endmark = 0; !endmark && (c = rd()) >= 0; )
            if (c == '_' && !epistole()) unget();
        inblock = 0;
    }
    return 1;
}


/* -- Epistole's calculations --------------------------------------------- */
/* #:X=expr] sets a variable, #:?expr] prints a value with _ND decimals, and
 * #*X=] is typed at print time: its value is unknown here, and whatever
 * uses it is shown as written, in inverse video, as a variable is. A
 * variable never set is 0. + - * / ^, comparisons (1 or 0), parentheses,
 * SIN COS TAN ATN LOG EXP SGN ABS SQR INT, a decimal comma or point. The
 * arithmetic is Applesoft's, in the ROM, and the evaluator is docview.s:
 * an error there -- division by zero, overflow, the logarithm of a
 * negative number -- leaves the expression as written, never a wrong
 * number. The values at the top of a page are those of the assignments
 * before it, read again from where the previous page began, or from the
 * start of the file going back. */
#ifdef PLUGIN_HOST                         /* the host tests the layout: nothing is computed */
static unsigned char calc_vars[NVARS * 12];
static unsigned char* fp_zsave;
static unsigned char calc_eval(const char* p) { (void)p; return 0; }
static void calc_assign(const char* p) { (void)p; }
static void calc_forget(const char* p) { (void)p; }
static const char* calc_format(unsigned char nd) { (void)nd; return ""; }
#else
extern unsigned char calc_vars[NVARS * 12];
extern unsigned char* fp_zsave;
unsigned char __fastcall__ calc_eval(const char* p);
void __fastcall__ calc_assign(const char* p);
void __fastcall__ calc_forget(const char* p);
const char* __fastcall__ calc_format(unsigned char nd);
#endif
/* In the service table's copy_buf, 512 bytes no service uses meanwhile:
 * the variables at scan_off, where the page begins, then the field
 * between #: (or #*) and ], then docview.s's copy of the zero page
 * ($50-$FF, 176 bytes) while the ROM computes. */
#define vscan  (a.copy_buf)
#define EBUFSZ 64
#define ebuf   ((char*)a.copy_buf + NVARS * 12)
typedef char copy_buf_fits[512 + 1 - NVARS * 12 - EBUFSZ - 0xB0];
static unsigned int scan_off;

/* The field up to its ], which is taken; a line's end is left for the line. */
static void gather(void)
{
    int c;
    unsigned char n = 0;
    while ((c = rd()) >= 32 && c != ']')   /* Epistole reads 1+2 3 as 1+23 */
        if (c != ' ' && n < EBUFSZ - 1) { ebuf[n] = c; ++n; }
    if (c >= 0 && c < 32) unget();
    ebuf[n] = 0;
}

/* A field after #: or #*, as it is laid out: a #*X=] prints nothing (X
 * is asked for before printing), nor does an assignment. A number goes to
 * the decimal tab, its comma at the tab's column; what cannot be computed
 * is shown as written, in inverse video. */
static void calc_field(char kind)
{
    const char* p = ebuf;
    unsigned char n;
    gather();
    if (kind == '*') { calc_forget(ebuf); return; }
    if (*p != '?') { calc_assign(ebuf); return; }
    if (calc_eval(++p)) {
        p = calc_format(LAY.nd);
        for (n = 0; p[n] && p[n] != ','; ++n) ;
        /* Its comma at the tab's column -- or, when the tab lies beyond
         * the right margin, at the next row's left edge: put_ wraps a
         * blank at the margin and the row starts again at `left`, where
         * padding on towards a column never reached had no end. */
        if (LAY.td > n)
            for (n = left + LAY.td - 1 - n; rc < n; ) {
                put_(' ');
                if (rc == left) break;
            }
        for (; *p; ++p) put_(*p);
        return;
    }
    LAY.inv |= 2;
    for (; *p; ++p) put_(plain((unsigned char)*p));
    LAY.inv &= 1;
}

/* The variables as they are at off, a line's start: the assignments before
 * it, from scan_off on -- or from the start of the file. */
static void calc_to(unsigned int off)
{
    int c;
    if (off < scan_off) { a.memset(vscan, 0, NVARS * 12); scan_off = 0; }
    a.memcpy(calc_vars, vscan, NVARS * 12);
    seek_(scan_off);
    while (tell_() < off && (c = rd()) >= 0) {
        if (c != '#') continue;
        c = rd();
        if (c == ':' || c == '*') {
            gather();
            if (c == '*') calc_forget(ebuf);
            else if (ebuf[0] != '?') calc_assign(ebuf);
        } else if (c >= 0) unget();
    }
    scan_off = off;
    a.memcpy(vscan, calc_vars, NVARS * 12);
}

/* A Papyrus code, after its first $FF: up to the next $FF. $06 centres
 * the line that follows it (the text after the code), $05 starts a page. */
static void code(void)
{
    int c = rd();
    unsigned char n = 0;
    if (c == 6) LAY.centre = 2;
    if (c == 5) LAY.brk = 1;
    while (c >= 0 && c != 0xFF && ++n < 16) c = rd();
}

/* The footer (DEF_DB, from _DB) or the header (DEF_EN, from _EN) written before
 * `back`, laid out here: Epistole prints the footer at the foot of every
 * page and the header at the top of every page but the first, %$ the
 * page's number. A viewer shows them where it sees a page end: at an _SP
 * break, and the footer at the end of the document. The definition is
 * looked for from the start of the file each time: nothing is kept. */
#define DEF_DB ('D' | 'B' << 8)            /* the two letters, the first in the low byte */
#define DEF_EN ('E' | 'N' << 8)
static void show_def(unsigned int kk)
{
    static struct Layout keep;
    unsigned int back = tell_();
    unsigned char c, n, h;
    keep = LAY;
    seek_(0);
    while (tell_() < back && (c = rd()) != 0xFF)
        if (c == '_' && (unsigned char)(rd() & 0xDF) == (unsigned char)kk
            && (unsigned char)(rd() & 0xDF) == (unsigned char)(kk >> 8)) {
            /* its lines, to its __XX or the screen page's end: the line
             * replayed at the next page's top skips what was shown */
            for (endmark = 0; !endmark && row <= LASTROW; ) {
                pad();
                while ((c = rd()) != 13 && c != 0xFF && !endmark) {
                    if (c == '_' && epistole()) continue;
                    if (c == '%' && rd() == '$') {   /* the page number, 1 to 255: */
                        n = LAY.pg;                  /* its hundreds, its tens (h: 100, */
                        h = 100;                     /* then 10), from the first that */
                        do {                         /* counts, then its units */
                            for (c = '0'; n >= h; n -= h) ++c;
                            if (LAY.pg >= h) put_(c);
                            h -= 90;
                        } while (h == 10);
                        c = n | '0';
                    }
                    put_(plain(c));
                }
                if (c == 0xFF) break;
                if (!endmark || rc > left) emit();   /* not the __XX line's own */
            }
            break;
        }
    LAY = keep;
    seek_(back);
}

/* One logical line, to its end or to the end of the page. Returns 0 when
 * the file ended before any character was read. */
static unsigned char render_line(void)
{
    int c, c2;
    unsigned char first = 1, n;
    line_off = tell_();
    LINE_LAY = LAY;
    rows_done = 0;
    pad();
    for (;;) {
        c = rd();
        if (c <= 0) {                      /* $00: Bank Street Writer's end, read again */
            if (first) return 0;
            if (!c) unget();
            break;
        }
        first = 0;
        if (c == 13) { c2 = rd(); if (c2 != 10 && c2 >= 0) unget(); break; }
        if (c == 10) break;
        if (row > LASTROW) return 1;       /* the page filled: next is set, the line is replayed there */
        if (LAY.brk) {                     /* the footer, the break, the header */
            if (rc > left) emit();
            show_def(DEF_DB);
            rule();
            LAY.brk = 0;
            if (LAY.pg != MAXPG) ++LAY.pg; /* past 255 pages the number stays at 255 */
            show_def(DEF_EN);
            if (row > LASTROW) return 1;
        }
        if (papyrus) {
            if (c == 0xFF) { code(); continue; }
            if (c >= 0x18 && c <= 0x1C) { put_(raw ? '?' : vowels[c - 0x18]); continue; }
            if (c == 3) { LAY.centre = 2; continue; }   /* Bank Street Writer: $83 centres the line */
        } else {
            if (c == '_' && epistole()) continue;
            if (c == '#') {                /* #NAME]: inverse, marks dropped; #: #* calculations */
                c2 = rd();
                if (c2 == ':' || c2 == '*') { calc_field(c2); continue; }
                if (c2 >= 'A') {
                    unget();
                    LAY.inv |= 2;
                    continue;
                }
                if (c2 >= 0) unget();
            }
            if (LAY.inv & 2) {
                if (c == ']') { LAY.inv &= 1; continue; }
            }
            if (c == '^' && !raw && rc > left) continue;   /* a circumflex on the letter before */
            if (c >= 0x80) {               /* a letter set apart (printed wide): inverse */
                n = LAY.inv;
                LAY.inv |= 1;
                put_(plain((unsigned char)c & 0x7F));
                LAY.inv = n;
                continue;
            }
        }
        if (c == 9) { do put_(' '); while ((rc & 3) && rc < WIDTH); continue; }
        if (c < 32 || c == 127) continue;
        put_(plain((unsigned char)c));
    }
    if (rc > left || rows_done == 0) {
        if (row > LASTROW) return 1;
        emit();
    }
    if (LAY.centre == 2) LAY.centre = 0;   /* Papyrus centres one line; Epistole until _PC */
    LAY.inv &= 1;
    LAY.mi = LAY.ma;
    NEXT.off = tell_(); NEXT.skip = 0; NEXT.lay = LAY;
    return 1;
}

static void render_page(const struct Start* st)
{
    done = 0;                              /* before the seek, which may fail */
    if (!papyrus) calc_to(st->off);
    seek_(st->off);
    skip_rows = st->skip;
    LAY = st->lay;
    row = ROW1;
    while (row <= LASTROW)
        if (!render_line()) {
            done |= 1;
            show_def(DEF_DB);
            if (row > LASTROW) done &= 2;  /* the footer goes on over the page */
            return;
        }
    seek_(NEXT.off);                       /* a page that filled on the last line: the end too */
    if (rd() <= 0) done |= 1;
}

/* The kind, from the first bytes: mostly high-bit, a Papyrus document. */
static void sniff(void)
{
    unsigned int i, n = 0;
    seek_(0);
    getc_();
    for (i = 0; i < vlen; ++i) if (VBUF[i] & 0x80) ++n;
    papyrus = n > vlen / 2;
    seek_(0);
}

static void first_page(void)
{
    STARTS->off = 0; STARTS->skip = 0;
    a.memset(&STARTS->lay, 0, sizeof STARTS->lay);
    STARTS->lay.rm = WIDTH;
    STARTS->lay.nd = DEFAULT_ND;
    STARTS->lay.pg = 1;
    a.memset(vscan, 0, NVARS * 12);      /* the variables start again */
    scan_off = 0;
}

/* The page shown, in the page table. */
static struct Start* slot(void)
{
    return STARTS + ((ST.head_ + ST.page_) & (MAXPAGES - 1));
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
#define page  ST.page_
#define known ST.known_
#define head  ST.head_
#define first ST.first_
    struct Panel* pan;
    char k, l;
    api->memcpy(&a, api, sizeof a);
    pan = a.panels + *a.active;
    if (!a.selected->name[0] || a.selected->type == 0x0F || !a.full[0] || !pan->path[0] || pan->fs) {
        a.strcpy(a.note, m_pick);
        return;
    }
    /* cc65 2.19 drops the member's offset from ((unsigned*)&p->size)[1]:
     * the size's high bytes, one by one. */
    if (a.selected->size >= 0x10000UL) { a.strcpy(a.note, m_big); return; }
    vf = a.fopen(a.full, "rb");
    if (!vf) { a.strcpy(a.note, m_open); return; }
    vbase = 0; vlen = vpos = 0;
    raw = page = head = 0;
    known = first = 1;
    fp_zsave = a.copy_buf + NVARS * 12 + EBUFSZ;
    sniff();
    first_page();
    for (;;) {
        a.clrscr();
        a.revers(1);
        a.cprintf("%-79.79s", a.full);
        a.revers(0);
        render_page(slot());
        a.gotoxy(0, 22);
        a.cprintf(m_page, first + page, m_ends[done]);
        k = a.cgetc();
        l = k | 0x20;                      /* a letter in lower case */
        if (k == KEY_ESC || l == 'q') break;
        if ((k == ' ' || k == KEY_RETURN || k == KEY_RIGHT || k == KEY_DOWN) && !done) {
            if (page + 1 < known) ++page;
            else {
                if (known < MAXPAGES) { ++known; ++page; }
                else { head = (head + 1) & (MAXPAGES - 1); ++first; }
                a.memcpy(slot(), &NEXT, sizeof NEXT);
            }
        }
        if (l == 'a') raw ^= 1;
        if (l == 'r') { page = head = 0; known = first = 1; first_page(); }
        if ((l == 'b' || k == KEY_LEFT || k == KEY_UP) && page) --page;
    }
    a.fclose(vf);
    a.note[0] = 0;
}
#undef page
#undef known
#undef head
#undef first
