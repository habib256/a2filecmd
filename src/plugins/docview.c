/* docview.c -- read an Epistole, Papyrus or HomeWord document laid out as
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
 * Both write French with the ISO 646-FR national characters: { e acute,
 * } e grave, | u grave, \ c cedilla, @ a grave, [ degree (n[ is "no"); Epistole types a
 * circumflex as a ^ after its letter, Papyrus as codes $18-$1C (a e i o
 * u; $19 and $1B confirmed on real documents). An Apple IIe with a US
 * character set shows { } | \ @ as themselves: they are shown as the
 * unaccented letter, and A switches to the codes as stored -- right on a
 * machine with the French character set. docs/MANUAL.md, "Read documents".
 *
 * Paging both ways, as MDVIEW does: the starts of the last 64 pages --
 * the offset of the line a page starts in, how many of its rows precede
 * the page, and the layout state at that line -- so that a page is always
 * rendered by replaying its first line. Read-only; a big overlay whose
 * scratch is $3000-$3FFF: the page table (64 x 12 at $3000), the copy of
 * the service table ($3300: a call through it costs half of one through
 * api->), the row and its attributes ($3400, $3480), the read buffer
 * (2 KB at $3800). */

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
    "Read Epistole, Papyrus and HomeWord documents"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

#define WIDTH     79                       /* the widest row */
#define ROW1      1                        /* the first text row; row 0 is the title */
#define LASTROW   21                       /* the last text row; 22 is the status line */
#define MAXPAGES  64
#define VBUFSZ    2048

/* The layout state a line starts with: margins, indent, bold. */
struct Layout { unsigned char lm, rm, mi, ma, inv, centre; };
struct Start { long off; unsigned int skip; struct Layout lay; };

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
#define a      (*(struct A2fcApi*)0x3300)  /* the service table, copied: $3300-$33FF */
typedef char api_copy_fits[256 - sizeof(struct A2fcApi)];
#define STARTS ((struct Start*)0x3000)     /* 64 x 12 = 768: $3000-$32FF */
#define RB     ((char*)0x3400)             /* the row being built, 80 */
#define RA     ((unsigned char*)0x3480)    /* its inverse flags, 80 */
#define VBUF   ((unsigned char*)0x3800)    /* the read buffer: $3800-$3FFF */
#endif

/* BSS: nothing zeroes it; everything below is written before it is read. */
static FILE* vf;
static unsigned int vlen, vpos;            /* the window VBUF[0..vlen), read to vpos */
static long vbase;                         /* the file offset of VBUF[0] */
static long line_off;                      /* where the line being rendered starts */
static struct Start next;                  /* where the next page starts */
static struct Layout lay, line_lay;        /* the state now; at the line's start */
static unsigned char papyrus;              /* 1: high-bit Papyrus/HomeWord; 0: Epistole */
static unsigned char raw;                  /* 1: the ISO 646-FR codes as stored */
static unsigned char row, rc, left;        /* the screen row; the row's length; its left edge */
static unsigned char pending_page;         /* a page break seen: a rule row before the next text */
/* Rows of one paragraph: 16 bits are 65,535 rows, 5 MB of text. */
static unsigned int skip, rows_done;
static unsigned char done;                 /* the end of the file was reached on this page */

static const char iso[] = "{e}e|u\\c@a[o";  /* ISO 646-FR pairs: code, plain letter ([ is a degree sign) */
static const char vowels[] = "aeiou";      /* Papyrus $18-$1C */

static const char m_pick[] = "Select a document to read.";
static const char m_open[] = "Open failed.";
static const char m_page[] = "Page %u%s: Space/Down next, Up back, R start, A accents, ESC quits";
static const char m_end[]  = " (end)";
static const char m_nil[]  = "";

/* -- reading ------------------------------------------------------------- */

static int getc_(void)
{
    if (vpos >= vlen) {
        vbase += vlen;
        vpos = 0;
        vlen = a.fread(VBUF, 1, VBUFSZ, vf);
        if (!vlen) return -1;
    }
    return VBUF[vpos++];
}

#define unget() (--vpos)                   /* only right after a successful getc_ */

static long tell_(void) { return vbase + vpos; }

static void seek_(long off)
{
    /* sign-ok: every offset comes from tell_() or is 0, never negative */
    if (off >= vbase && off < vbase + vlen) { vpos = (unsigned int)(off - vbase); return; }
    a.fseek(vf, off, SEEK_SET);
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
    left = lay.lm + lay.mi;
    if (left > WIDTH - 10) left = WIDTH - 10;
    a.memset(RB, ' ', left);
    a.memset(RA, 0, left);
    rc = left;
}

/* The row RB[0..rc) goes to the screen (or is skipped, at the top of a
 * page), centred between the margins when asked; inverse runs switch the
 * video mode as they go. When the page is full, the next page starts in
 * this very line, after its rows so far. */
static void emit(void)
{
    unsigned char i, x, now = 0;
    ++rows_done;
    if (skip) --skip;
    else {
        i = 0;
        x = 0;
        if (lay.centre || line_lay.centre) {
            i = left;                      /* the text alone, as much room either side */
            x = rc - left;
            /* sign-ok: only when rm > left + x, so the difference is 1..79 */
            x = lay.rm > left + x ? left + ((lay.rm - left - x) >> 1) : left;
        }
        a.gotoxy(x, row);
        for (; i < rc; ++i) {
            if (RA[i] != now) { now = RA[i]; a.revers(now); }
            a.cputc(RB[i]);
        }
        if (now) a.revers(0);
        if (++row > LASTROW) { next.off = line_off; next.skip = rows_done; next.lay = line_lay; }
    }
    pad();
}

/* One character into the row, wrapped at the last space before the right
 * margin. */
static void put_(unsigned char c)
{
    unsigned char i, keep, rm = lay.rm;
    if (rm > WIDTH) rm = WIDTH;
    if (rm < left + 10) rm = left + 10;
    if (rc >= rm) {
        if (c == ' ') { emit(); return; }
        for (i = rm - 1; i > left && RB[i] != ' '; --i) ;
        if (i > left) {                    /* break at that space: the tail moves on */
            keep = rm - 1 - i;
            rc = i;
            emit();
            a.memcpy(RB + rc, RB + i + 1, keep);
            a.memcpy(RA + rc, RA + i + 1, keep);
            rc += keep;
        } else emit();                     /* no space: a hard break */
    }
    RB[rc] = c;                            /* not RB[rc++]: cc65 2.19 increments rc first */
    RA[rc] = lay.inv;
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
    unsigned char i = lay.rm > WIDTH ? WIDTH : lay.rm;
    if (row > LASTROW) return;
    while (rc < i) { RB[rc] = '-'; RA[rc] = 0; ++rc; }
    emit();
}

/* An Epistole command, after its `_`: two letters and a number. Returns 0
 * when the `_` was no command (then it is a character). */
static unsigned char epistole(void)
{
    int c;
    unsigned char k1, k2 = 0;
    unsigned int n = 0;
    c = rd();
    if (c == '_') {                        /* __BA, __EA: a block ends; glossary marks */
        for (n = 0; n < 2 && (c = rd()) >= 'A' && c <= 'Z'; ++n) ;
        if (n < 2 && c >= 0) unget();
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
    if (k1 == 'M') {
        if (k2 == 'G') lay.lm = n;
        else if (k2 == 'D') lay.rm = n ? n : WIDTH;
        else if (k2 == 'I') { lay.mi = lay.ma = n; if (rc == left) pad(); }
        else if (k2 == 'A') lay.ma = n;
        if (rc == left) pad();
    } else if (k1 == 'C' && k2 == 'E') lay.centre = 1;
    else if ((k1 == 'P' && k2 == 'C') || (k1 == 'C' && k2 == 'L') || (k1 == 'J' && k2 == 'D'))
        lay.centre = 0;                    /* centring lasts until an alignment */
    else if (k1 == 'T' && k2 == 'D')       /* a tab stop, from the margin */
        while (rc < left + n && rc < WIDTH) { RB[rc] = ' '; RA[rc] = 0; ++rc; }
    else if (k1 == 'I' && (k2 == 'G' || k2 == 'D')) lay.inv = 1;
    else if (k1 == 'S' && k2 == 'G') lay.inv = 0;
    else if (k1 == 'I' && k2 == 'S') lay.inv = 0;
    else if (k1 == 'S' && k2 == 'P') pending_page = 1;
    return 1;
}

/* A Papyrus code, after its first $FF: up to the next $FF. $06 centres
 * the line that follows it (the text after the code), $05 starts a page. */
static void code(void)
{
    int c = rd();
    unsigned char n = 0;
    if (c == 6) lay.centre = 2;
    if (c == 5) pending_page = 1;
    while (c >= 0 && c != 0xFF && ++n < 16) c = rd();
}

/* One logical line, to its end or to the end of the page. Returns 0 when
 * the file ended before any character was read. */
static unsigned char render_line(void)
{
    int c, c2;
    unsigned char first = 1;
    line_off = tell_();
    line_lay = lay;
    rows_done = 0;
    pad();
    for (;;) {
        c = rd();
        if (c < 0) { if (first) return 0; break; }
        first = 0;
        if (c == 13) { c2 = rd(); if (c2 != 10 && c2 >= 0) unget(); break; }
        if (c == 10) break;
        if (row > LASTROW) return 1;       /* the page filled: next is set, the line is replayed there */
        if (pending_page) {
            pending_page = 0;
            if (rc > left) emit();
            rule();
            if (row > LASTROW) return 1;
        }
        if (papyrus) {
            if (c == 0xFF) { code(); continue; }
            if (c >= 0x18 && c <= 0x1C) { put_(raw ? '?' : vowels[c - 0x18]); continue; }
        } else {
            if (c == '_' && epistole()) continue;
            if (c == '#') {                /* #NAME], #*NAME=], #:?calc]: inverse, marks dropped */
                c2 = rd();
                if (c2 == ':') {           /* #:X=1] sets a variable: nothing printed */
                    c2 = rd();
                    if (c2 != '?') {
                        while (c2 >= 32 && c2 != ']') c2 = rd();
                        continue;
                    }
                    lay.inv |= 2;
                    continue;
                }
                if (c2 >= 'A' || c2 == '*') {
                    if (c2 != '*') unget();
                    lay.inv |= 2;
                    continue;
                }
                if (c2 >= 0) unget();
            }
            if (lay.inv & 2) {
                if (c == ']') { lay.inv &= 1; continue; }
                if (c == '=') continue;    /* #*M1=]: the name to be typed */
            }
            if (c == '^' && !raw && rc > left) continue;   /* a circumflex on the letter before */
        }
        if (c == 9) { do put_(' '); while ((rc & 3) && rc < WIDTH); continue; }
        if (c < 32 || c == 127) continue;
        put_(plain((unsigned char)c));
    }
    if (rc > left || rows_done == 0) {
        if (row > LASTROW) return 1;
        emit();
    }
    if (lay.centre == 2) lay.centre = 0;   /* Papyrus centres one line; Epistole until _PC */
    lay.inv &= 1;
    lay.mi = lay.ma;
    next.off = tell_(); next.skip = 0; next.lay = lay;
    return 1;
}

static void render_page(const struct Start* st)
{
    seek_(st->off);
    skip = st->skip;
    lay = st->lay;
    pending_page = 0;
    row = ROW1;
    done = 0;
    while (row <= LASTROW)
        if (!render_line()) { done = 1; return; }
    seek_(next.off);                       /* a page that filled on the last line: the end too */
    if (getc_() < 0) done = 1;
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
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    struct Panel* pan;
    unsigned char page = 0, known = 1, head = 0;
    unsigned int first = 1;
    char k;
    api->memcpy(&a, api, sizeof a);
    pan = a.panels + *a.active;
    if (!a.selected->name[0] || a.selected->type == 0x0F || !a.full[0] || !pan->path[0] || pan->fs) {
        a.strcpy(a.note, m_pick);
        return;
    }
    vf = a.fopen(a.full, "rb");
    if (!vf) { a.strcpy(a.note, m_open); return; }
    vbase = 0; vlen = vpos = 0;
    raw = 0;
    sniff();
    first_page();
    for (;;) {
        a.clrscr();
        a.revers(1);
        a.cprintf("%-79.79s", a.full);
        a.revers(0);
        render_page(STARTS + ((head + page) & (MAXPAGES - 1)));
        a.gotoxy(0, 22);
        a.cprintf(m_page, first + page, done ? m_end : m_nil);
        k = a.cgetc();
        if (k == KEY_ESC || k == 'q' || k == 'Q') break;
        if ((k == ' ' || k == KEY_RETURN || k == KEY_RIGHT || k == KEY_DOWN) && !done) {
            if (page + 1 < known) ++page;
            else {
                if (known < MAXPAGES) { ++known; ++page; }
                else { head = (head + 1) & (MAXPAGES - 1); ++first; }
                a.memcpy(STARTS + ((head + page) & (MAXPAGES - 1)), &next, sizeof next);
            }
        }
        if (k == 'a' || k == 'A') raw ^= 1;
        if (k == 'r' || k == 'R') { page = head = 0; known = 1; first = 1; first_page(); }
        if ((k == 'b' || k == 'B' || k == KEY_LEFT || k == KEY_UP) && page) --page;
    }
    a.fclose(vf);
    a.note[0] = 0;
}
