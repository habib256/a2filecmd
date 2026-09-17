/* awdata.c -- AppleWorks data bases ($19) and spreadsheets ($1B), read on
 * the screen. From Return or the ! menu, on the selected file.
 *
 * The formats, and the reference this viewer is tested against, are in
 * tools/awdata_ref.py (after CiderPress II's converters and Apple's File
 * Type Notes $19 and $1B).
 *
 * A data base shows one record at a time, a row per category: its name,
 * then the value -- dates and times written out as AppleWorks shows them.
 * Space/Down go to the next record, B/Up back, R to the first; TAB shows
 * categories 23 to 30 when there are more than 22.
 *
 * A spreadsheet shows a row per cell, in the file's order: the cell, then
 * its text, its number, or its formula and the result AppleWorks saved with
 * it. Space/Down, B/Up and R page through them.
 *
 * Numbers are 64-bit doubles: awdata.s converts each to the ROM's 5-byte
 * form and lets Applesoft's FOUT print it, as BASIC would.
 *
 * The file is read through the core's 512-byte buffer, never loaded whole.
 * Records, rows and cells carry their own lengths: `left` counts down what remains
 * of the one being read, so that only a start kept for going back needs a
 * 32-bit offset. Those starts -- each 16th record, or each page of cells,
 * 200 of them -- are kept; going back replays from the nearest one. A data
 * base shows its first 3,200 records, a spreadsheet its first 200 pages.
 *
 * A big overlay: its tables sit after the code, below $4000. Being a big
 * overlay, the core redraws the panels on return. */

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
    "AppleWorks data bases and spreadsheets ($19, $1B)"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

#define LINES     22                    /* text rows 0-21; 22 is the message, 23 the bar */
#define WIDTH     79
#define STEP      16                    /* records between two kept starts */
#define MAXMARKS  200
#define RBSZ      512                   /* api->copy_buf */

struct Mark { unsigned long off; unsigned char skip; };

extern char aw_num[];                   /* awdata.s */
void __fastcall__ aw_fout(const unsigned char* d);

/* BSS: nothing zeroes it; everything below is written before it is read. */
static struct A2fcApi a;
static struct Mark marks[MAXMARKS + 1];
static char names[30 * 21];
static unsigned char* rbuf;
static FILE* f;
static unsigned long size, base;        /* the file's size; the offset of rbuf[0] */
static unsigned int have, at;           /* rbuf[0..have), read up to at */
static unsigned int left;               /* what remains of the record or row */
static unsigned char cleft;             /* ... and of the cell */
static unsigned char eof;
static char line[WIDTH + 1];
static unsigned char pos;               /* the length of line */
static unsigned char ncats, cat0, cut;
static unsigned int nrecs;
static unsigned short row;              /* the spreadsheet row being shown */
static int col;
static unsigned char num[8];

/* -- the reader ---------------------------------------------------------- */

/* The next byte, counted off `left`; 0 once the file has run out. */
static unsigned char getb(void)
{
    --left;
    if (at == have) {
        base += have;
        have = a.fread(rbuf, 1, RBSZ, f);
        at = 0;
        if (!have) { eof = 1; return 0; }
    }
    return rbuf[at++];
}

static unsigned int get16(void)
{
    unsigned char lo = getb();
    return lo | ((unsigned int)getb() << 8);
}

static unsigned char seek(unsigned long off)
{
    base = off; have = at = 0; eof = 0;
    return !a.fseek(f, off, SEEK_SET);
}

/* n bytes on: within the window when they are there. */
static void skipn(unsigned int n)
{
    left -= n;
    if (have - at >= n) at += n;
    else if (!seek(base + at + n)) eof = 1;
}

/* A cell's next byte, or 0 past its end. */
static unsigned char cget(void)
{
    if (!cleft) return 0;
    --cleft;
    return getb();
}

/* A record, a row: its length, checked against the file, into left. 0 at
 * the end, cut saying whether it came before the $FFFF mark. */
static unsigned int next_len(void)
{
    unsigned int n = get16();
    cut = 1;
    if (eof) return 0;
    if (n == 0xFFFF) { cut = 0; return 0; }
    if (base + at + n > size) return 0;
    left = n;
    return n;
}

/* -- the line being built -------------------------------------------------- */

static void put(char c) { if (pos < WIDTH) line[pos++] = c; }
static void puts_(const char* s) { while (*s) put(*s++); }

/* An AppleWorks character: inverse shown plain, MouseText and controls as ?. */
static char awc(unsigned char c)
{
    if (c < 0x20 || (c >= 0xC0 && c < 0xE0)) return '?';
    if (c < 0x80) return c;
    if (c < 0xA0) return c - 0x40;
    return c - 0x80;
}
static void putaw(unsigned char c) { put(awc(c)); }

static void putu(unsigned int v)
{
    char d[5];
    unsigned char n = 0;
    do d[n++] = '0' + v % 10; while (v /= 10);
    while (n) put(d[--n]);
}

/* line at (x, y), then emptied. */
static void flush(unsigned char x, unsigned char y)
{
    line[pos] = 0;
    a.gotoxy(x, y);
    a.cputs(line);
    pos = 0;
}

/* The double at d, as Applesoft prints it. */
static void putnum(const unsigned char* d)
{
    aw_fout(d);
    puts_(aw_num);
}

/* Eight bytes of the cell into d. */
static void getnum(unsigned char* d)
{
    unsigned char i;
    for (i = 0; i < 8; ++i) d[i] = cget();
}

/* -- the data base ----------------------------------------------------------- */

static const char months[] = "JanFebMarAprMayJunJulAugSepOctNovDec";

static void two(const unsigned char* p) { putaw(p[0]); putaw(p[1]); }

/* A date or time entry of n bytes in num, or plain text. */
static void db_value(unsigned char n)
{
    unsigned char k, *b = num;
    if (n == 6 && b[0] == 0xC0) {
        k = b[3] - 'A';
        if (k > 11) { puts_("#BAD DATE#"); return; }
        if (b[4] == ' ') b[4] = '0';
        if (b[4] != '0' || b[5] != '0') { two(b + 4); put(' '); }
        put(months[k * 3]); put(months[k * 3 + 1]); put(months[k * 3 + 2]);
        if (b[1] != '0' || b[2] != '0') { put(' '); two(b + 1); }
    } else if (n == 4 && b[0] == 0xD4) {
        k = b[1] - 'A';
        if (k > 23 || (unsigned char)(b[2] - '0') > 9 || (unsigned char)(b[3] - '0') > 9) {
            puts_("#BAD TIME#");
            return;
        }
        putu(k % 12 ? k % 12 : 12);
        put(':'); two(b + 2);
        puts_(k < 12 ? " AM" : " PM");
    } else {
        for (k = 0; k < n; ++k) putaw(b[k]);
    }
}

/* The header: the names, and the offset of the first record, or 0. */
static unsigned long db_open(void)
{
    unsigned int i;
    unsigned char n, j, c, reports;
    for (i = 0; i < 35; ++i) getb();
    ncats = getb();
    get16();
    reports = getb();
    if (size < 381 || !ncats || ncats > 30) return 0;
    for (i = 39; i < 357; ++i) getb();
    for (i = 0; i < ncats; ++i) {
        n = getb();
        if (n > 20) return 0;
        for (j = 0; j < 21; ++j) {
            c = getb();
            if (j < n) names[i * 21 + j] = awc(c);
        }
        names[i * 21 + n] = 0;
    }
    if (eof) return 0;
    return 357 + 22UL * ncats + 600UL * reports;
}

/* Every record walked once: the starts kept, the count, and cut when the
 * $FFFF end was not reached. */
static void db_walk(void)
{
    unsigned char first = 1;
    unsigned long off;
    nrecs = 0;
    for (;;) {
        off = base + at;
        if (!next_len()) return;
        if (!first) {
            if (!(nrecs % STEP)) {
                if (nrecs / STEP == MAXMARKS) return;
                marks[nrecs / STEP].off = off;
            }
            ++nrecs;
        }
        first = 0;
        skipn(left);
        if (eof) { cut = 1; return; }
    }
}

/* Record k (0-based) on the screen. */
static void db_show(unsigned int k)
{
    unsigned char c, cat;
    a.clrscr();
    for (cat = cat0; cat < ncats && cat < cat0 + LINES; ++cat) {
        a.gotoxy(0, cat - cat0);
        a.cputs(names + cat * 21);
    }
    if (!seek(marks[k / STEP].off)) return;
    for (c = k % STEP; c; --c) skipn(get16());
    left = get16();
    cat = 0;
    while (left && !eof) {
        c = getb();
        if (c == 0xFF) break;
        if (c && c < 0x80) {
            if (c > left) break;
            if (cat < cat0 || cat >= cat0 + LINES || cat >= ncats) {
                skipn(c);
            } else {
                if (c == 6 || c == 4) {
                    cleft = c;
                    getnum(num);
                    db_value(c);
                } else {
                    while (c--) putaw(getb());
                }
                if (pos > WIDTH - 21) pos = WIDTH - 21;
                flush(21, cat - cat0);
            }
        } else if (c >= 0x81 && c <= 0x9E) {
            cat += c - 0x81;
        } else {
            break;
        }
        ++cat;
    }
}

/* -- the spreadsheet --------------------------------------------------------- */

/* The tokens $C0-$FF, one after another, each ended by a zero. */
static const char tokens[] =
    "@Deg\0@Rad\0@Pi\0@True\0@False\0@Not\0@IsBlank\0@IsNA\0"
    "@IsError\0@Exp\0@Ln\0@Log\0@Cos\0@Sin\0@Tan\0@ACos\0"
    "@ASin\0@ATan2\0@ATan\0@Mod\0@FV\0@PV\0@PMT\0@Term\0"
    "@Rate\0@Round\0@Or\0@And\0@Sum\0@Avg\0@Choose\0@Count\0"
    "@Error\0@IRR\0@If\0@Int\0@Lookup\0@Max\0@Min\0@NA\0"
    "@NPV\0@Sqrt\0@Abs\0\0<>\0>=\0<=\0=\0"
    ">\0<\0,\0^\0)\0-\0+\0/\0"
    "*\0(\0-\0+\0...\0\0\0";

static void putcol(int c)
{
    if (c < 0 || c > 127) { puts_("#ERR#"); return; }
    if (c >= 26) put('@' + c / 26);
    put('A' + c % 26);
}

/* The formula's tokens, to the end of the cell. */
static void formula(void)
{
    unsigned char t, n;
    const char* s;
    unsigned char d[8];
    int dc;
    unsigned short r;                   /* 16 bits, printed signed */
    while (cleft && !eof) {
        t = cget();
        if (t < 0xC0) continue;
        for (s = tokens, n = t - 0xC0; n; --n) while (*s++);
        puts_(s);
        if (t == 0xE0 || t == 0xE7) {
            cget(); cget(); cget();
        } else if (t == 0xFD) {
            getnum(d);
            putnum(d);
        } else if (t == 0xFE) {
            dc = cget();                /* signed: written out, cc65 does not */
            if (dc > 127) dc -= 256;    /* extend a (signed char) cast here */
            r = cget();
            r = row + (r | ((unsigned short)cget() << 8));
            putcol(col + dc);
            if ((short)r < 0) { put('-'); r = -r; }
            putu(r);
        } else if (t == 0xFF) {
            n = cget();
            put('"');
            while (n-- && cleft) putaw(cget());
            put('"');
        }
    }
}

/* The cell of cleft bytes at hand, as one line. */
static void ss_cell(void)
{
    unsigned char f0, f1, n, k, c;
    char shown[WIDTH];
    putcol(col);
    putu(row);
    while (pos < 7) put(' ');
    f0 = cget();
    if (!(f0 & 0x80)) {
        if (f0 & 0x20) {
            f1 = awc(cget());
            for (n = 0; n < 8; ++n) put(f1);
        } else {
            while (cleft) putaw(cget());
        }
    } else {
        f1 = cget();
        if (f0 & 0x20) {
            getnum(num);
            putnum(num);
        } else if (f1 & 0x08) {
            /* The display string AppleWorks saved comes first; it is shown
             * after the formula. */
            n = cget();
            k = 0;
            while (n-- && cleft) {
                c = awc(cget());
                if (k < WIDTH) shown[k++] = c;
            }
            formula();
            puts_("  = ");
            for (n = 0; n < k; ++n) put(shown[n]);
        } else {
            getnum(num);                /* the result; formula() has its own */
            formula();
            puts_("  = ");
            putnum(num);
        }
    }
    skipn(cleft);
}

/* A page of cells from the start m; the next page's start in *next.
 * 1 when the file ended on this page (cut says how). */
static unsigned char ss_page(const struct Mark* m, struct Mark* next)
{
    unsigned char y = 0, c, k, skip = m->skip;
    unsigned long off;
    a.clrscr();
    if (!seek(m->off)) { cut = 1; return 1; }
    for (;;) {
        off = base + at;
        if (next_len() < 2) return 1;   /* the end, or a row too short for its number */
        row = get16();
        col = 0;
        k = 0;
        while (left && !eof) {
            c = getb();
            if (c == 0xFF) break;
            if (c < 0x80) {
                if (!c || c > left) break;
                if (k >= skip) {
                    if (y == LINES) { next->off = off; next->skip = k; return 0; }
                    cleft = c;
                    ss_cell();
                    flush(0, y++);
                } else {
                    skipn(c);
                }
                ++k;
            } else {
                col += c - 0x81;
            }
            ++col;
        }
        skip = 0;
        skipn(left);
        if (eof) { cut = 1; return 1; }
    }
}

/* -- the entry --------------------------------------------------------------- */

static const char k_db[] = "SPC Next,B Prev,R First,TAB More,ESC";
static const char k_ss[] = "SPC Next,B Prev,R First,ESC";

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Entry* e = api->selected;
    unsigned char type = e->type, done = 0;
    unsigned int k = 0, known = 1;
    unsigned long off;
    char key;
    a = *api;
    rbuf = a.copy_buf;
    size = e->size;
    if ((type != 0x19 && type != 0x1B) || !api->full[0] || !(f = a.fopen(api->full, "rb"))) {
        a.strcpy(a.note, "Not an AppleWorks data base or spreadsheet.");
        return;
    }
    base = have = at = pos = eof = cat0 = 0;
    if (type == 0x19) {
        off = db_open();
        if (off && seek(off)) db_walk();
        if (!off || !nrecs) {
            a.fclose(f);
            a.strcpy(a.note, off ? "No record." : "Not an AppleWorks data base.");
            return;
        }
    } else {
        for (k = 0; k < 243; ++k) off = getb();
        marks[0].off = off ? 302 : 300;
        marks[0].skip = 0;
        k = 0;
        if (size < 302) {
            a.fclose(f);
            a.strcpy(a.note, "Not an AppleWorks spreadsheet.");
            return;
        }
    }
    for (;;) {
        if (type == 0x19) db_show(k);
        else {
            done = ss_page(marks + k, marks + k + 1);
            if (!done && known == k + 1 && known < MAXMARKS) ++known;
        }
        a.bar_begin();
        a.cprintf("%s  %s %u", e->name, type == 0x19 ? "record" : "page", k + 1);
        if (type == 0x19) a.cprintf(" of %u%s", nrecs, cut ? " (cut)" : "");
        else if (done) a.cputs(cut ? " (cut)" : " (end)");
        a.keys_bar(44, type == 0x19 ? k_db : k_ss);
        key = a.cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if (key == 'r' || key == 'R') k = 0;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN)
            && k + 1 < (type == 0x19 ? nrecs : known)) ++k;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && k) --k;
        if (key == KEY_TAB && ncats > LINES) cat0 = cat0 ? 0 : LINES;
    }
    a.fclose(f);
}
