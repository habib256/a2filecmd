/* mdview.c -- read a Markdown or long-line text file, wrapped to 79
 * columns, page by page on a full screen. From the ! menu, on the
 * selected file.
 *
 * The file is streamed 2 KB at a time (fseek/fread) and rendered line by
 * line: CR, LF or CRLF line ends; the high bit stripped when the file is
 * mostly high-bit ASCII (a ProDOS text), else UTF-8, whose C3 xx accented
 * letters become plain letters and any other multibyte sequence a `?`;
 * tabs to the next multiple of 4; word-wrap at the last space before
 * column 79, a hard break when there is none. Markdown: `#` headings in
 * inverse video without their marks; `- `, `* `, `+ ` bullets with a
 * two-column hanging indent; the lines of a ``` fence shown verbatim,
 * truncated at 79; `**` and backticks dropped.
 *
 * Paging both ways: the starts of the last 64 pages seen are kept in a ring in
 * the scratch memory ($3000, 64 pages) -- the file offset of the logical
 * line the page starts in, how many of that line's wrapped rows precede
 * the page, and whether a fence was open -- so a page is always rendered
 * by replaying its first line from its start. Space/Down go forward
 * (the next start is known once a page has been rendered), Up goes back,
 * R restarts at page 1; Escape leaves. Forward reading is unlimited;
 * Up stops at the oldest retained page. Being a big overlay, the core redraws the panels on
 * return.
 *
 * A big overlay under 5,376 bytes: $3000-$3FFF is its scratch memory --
 * the page table (64 x 8 at $3000), the row being built ($3200) and the
 * read buffer (2 KB at $3800). The service table is copied into a static:
 * a call through it costs half of one through api->. */

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
    "Read Markdown or long text, wrapped to 80 columns"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

#define WIDTH     79                       /* columns of text per row */
#define ROW1      1                        /* the first text row; row 0 is the title */
#define LASTROW   21                       /* the last text row; 22 is the status line */
#define MAXPAGES  64
#define VBUFSZ    2048

struct Start { long off; unsigned char skip, fence, r0, r1; };

#define STARTS ((struct Start*)0x3000)     /* 64 x 8 = 512: $3000-$31FF */
#define RB     ((char*)0x3200)             /* the row being built, 80: $3200-$327F */
#define VBUF   ((unsigned char*)0x3800)    /* the read buffer: $3800-$3FFF */

/* BSS: nothing zeroes it; everything below is written before it is read. */
static struct A2fcApi a;                   /* the service table, copied */
static FILE* vf;
static unsigned int vlen, vpos;            /* the window VBUF[0..vlen), read to vpos */
static long vbase;                         /* the file offset of VBUF[0] */
static long line_off;                      /* where the line being rendered starts */
static struct Start next;                  /* where the next page starts */
static unsigned char hibit;                /* 1: a high-bit ASCII text, the bit stripped */
static unsigned char fence, line_fence;    /* inside a ``` fence; the state at line start */
static unsigned char row, skip, rows_done; /* the row being written; rows to skip; rows of this line so far */
static unsigned char inv, indent, rc;      /* inverse (a heading); the hanging indent; the row's length */
static unsigned char done;                 /* the end of the file was reached on this page */

/* Latin-1 $C0-$DF to ASCII; $E0-$FF the same, lower-cased. */
static const char latin[] = "AAAAAAACEEEEIIIIDNOOOOO?OUUUUY?y";

static const char m_pick[] = "Select a text file to read.";
static const char m_open[] = "Open failed.";
static const char m_page[] = "Page %lu%s: Space/Down next, Up back, R start, ESC quits";
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

/* The byte just read goes back: only right after a successful getc_. */
#define unget() (--vpos)

static long tell_(void) { return vbase + vpos; }

static void seek_(long off)
{
    if (off >= vbase && off < vbase + vlen) { vpos = (unsigned int)(off - vbase); return; }
    a.fseek(vf, off, SEEK_SET);
    vbase = off;
    vlen = vpos = 0;
}

/* A byte of text, the high bit stripped in a high-bit ASCII file; -1 at the end. */
static int rd(void)
{
    int c = getc_();
    if (hibit && c >= 0) c &= 0x7F;
    return c;
}

/* Mostly high-bit bytes in the first read: a ProDOS text, not UTF-8. */
static void sniff(void)
{
    unsigned int i, n = 0;
    hibit = 0;
    seek_(0);
    if (getc_() < 0) return;
    for (i = 0; i < vlen; ++i) if (VBUF[i] & 0x80) ++n;
    hibit = n > vlen / 2;
}

/* -- writing ------------------------------------------------------------- */

/* The row RB[0..rc) goes to the screen (or is skipped, at the top of a
 * page); the next row starts with the hanging indent. When the page is
 * full, the next page starts in this very line, after its rows so far. */
static void emit(void)
{
    RB[rc] = 0;
    ++rows_done;
    if (skip) --skip;
    else {
        a.gotoxy(0, row);
        if (inv) a.revers(1);
        a.cputs(RB);
        if (inv) a.revers(0);
        if (++row > LASTROW) { next.off = line_off; next.skip = rows_done; next.fence = line_fence; }
    }
    a.memset(RB, ' ', indent);
    rc = indent;
}

/* One character into the row: verbatim in a fence (truncated at the
 * width), otherwise wrapped at the last space before the width. */
static void put_(unsigned char c)
{
    unsigned char i, keep;
    if (rc >= WIDTH) {
        if (fence) return;
        if (c == ' ') { emit(); return; }
        for (i = WIDTH - 1; i > indent && RB[i] != ' '; --i) ;
        if (i > indent) {                  /* break at that space: the tail moves to the next row */
            keep = WIDTH - 1 - i;
            rc = i;
            emit();
            a.memcpy(RB + indent, RB + i + 1, keep);
            rc = indent + keep;
        } else emit();                     /* no space: a hard break */
    }
    RB[rc] = c;                            /* not RB[rc++]: cc65 2.19 increments rc first */
    ++rc;
}

/* One logical line, to its end or to the end of the page. Returns 0 when
 * the file ended before any character was read. */
static unsigned char render_line(void)
{
    int c, c2;
    unsigned char n, first = 1, marker = 0;
    char k;
    line_off = tell_();
    line_fence = fence;
    rows_done = 0; inv = 0; indent = 0; rc = 0;
    for (;;) {
        c = rd();
        if (c < 0) { if (first) return 0; break; }
        if (c == 13) { c2 = rd(); if (c2 != 10 && c2 >= 0) unget(); break; }
        if (c == 10) break;
        if (row > LASTROW) return 1;       /* the page filled: next is set, the line is replayed there */
        if (first) {
            first = 0;
            if (c == '`') {                /* a fence, or backticks to drop */
                n = 1;
                while ((c2 = rd()) == '`') ++n;
                if (c2 >= 0) unget();
                if (n >= 3) { fence ^= 1; marker = 1; }
                continue;
            }
            if (!fence) {
                if (c == '#') {            /* a heading: the marks and one space go */
                    inv = 1;
                    while ((c2 = rd()) == '#') ;
                    if (c2 != ' ' && c2 >= 0) unget();
                    continue;
                }
                if (c == '-' || c == '*' || c == '+') {
                    c2 = rd();
                    if (c2 == ' ') { RB[0] = '-'; RB[1] = ' '; rc = indent = 2; continue; }
                    if (c2 >= 0) unget();
                }
            }
        }
        if (marker) continue;              /* the rest of a fence line: a language tag */
        if (c >= 0x80) {                   /* UTF-8: C3 xx transliterated, the rest a ? */
            k = '?';
            if (c >= 0xC2 && c < 0xF8) {
                n = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : 1;
                c2 = rd();
                if (c2 >= 0x80 && c2 < 0xC0) {
                    if (c == 0xC3) {
                        k = latin[c2 & 0x1F];
                        if (c2 == 0x9F) k = 's';
                        else if (c2 >= 0xA0 && k >= 'A' && k <= 'Z') k += 32;
                    }
                    while (--n) {
                        c2 = rd();
                        if (c2 < 0x80 || c2 >= 0xC0) { if (c2 >= 0) unget(); break; }
                    }
                } else if (c2 >= 0) unget();
            }
            c = k;
        }
        if (c == 9) { do put_(' '); while ((rc & 3) && rc < WIDTH); continue; }
        if (c < 32 || c == 127) continue;
        if (!fence) {
            if (c == '`') continue;
            if (c == '*') { c2 = rd(); if (c2 == '*') continue; if (c2 >= 0) unget(); }
        }
        put_((unsigned char)c);
    }
    if (!marker && (rc > indent || rows_done == 0)) emit();
    next.off = tell_(); next.skip = 0; next.fence = fence;
    return 1;
}

static void render_page(const struct Start* st)
{
    seek_(st->off);
    skip = st->skip;
    fence = st->fence;
    row = ROW1;
    done = 0;
    while (row <= LASTROW)
        if (!render_line()) { done = 1; return; }
    seek_(next.off);                       /* a page that filled on the last line: the end too */
    if (getc_() < 0) done = 1;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    struct Panel* pan;
    unsigned char page = 0, known = 1, head = 0;
    unsigned long first = 1;
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
    sniff();
    STARTS->off = 0; STARTS->skip = 0; STARTS->fence = 0;
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
        if (k == 'r' || k == 'R') {
            page = head = 0; known = 1; first = 1;
            STARTS->off = 0; STARTS->skip = 0; STARTS->fence = 0;
        }
        if ((k == 'b' || k == 'B' || k == KEY_LEFT || k == KEY_UP) && page) --page;
    }
    a.fclose(vf);
    a.note[0] = 0;
}
