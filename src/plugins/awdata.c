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
 * A spreadsheet is shown as a sheet: the column letters on the first line,
 * then a row of the file a line, each cell in its own column at the width
 * the header gives it (bytes 4-130). Values sit against the right of their
 * column, labels from the left, and a label wider than its column runs into
 * the next ones until a cell writes over it -- what AppleWorks itself shows,
 * and what makes a sentence typed across a row readable again. A formula
 * cell shows its saved display string or its result. Space/Down and B/Up
 * page through the rows, < and > move a screen of columns, R goes back to
 * the top left. F swaps to the cell-by-cell view -- a cell a line with its
 * formula spelled out -- and back.
 *
 * Numbers are 64-bit doubles: awdata.s converts each to the ROM's 5-byte
 * form and lets Applesoft's FOUT print it, as BASIC would.
 *
 * The file is read through the core's 512-byte buffer, never loaded whole.
 * Records, rows and cells carry their own lengths: `left` counts down what
 * remains of the one being read. The starts kept for going back -- each
 * 64th record, or each page -- are 16-bit offsets, which is what an
 * AppleWorks document can reach; going back replays from the nearest one. A
 * data base reaches its first 2,688 records, a sheet its first 882 rows.
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
#define COLS      127                   /* A to DW, the columns of an AppleWorks sheet */
#define GUTTER    4                     /* the row number down the left of the grid */
#define STEP      64                    /* records between two kept starts */
#define MAXMARKS  42                    /* pages kept: 42 x 21 = 882 rows of a sheet */
#define RBSZ      512                   /* api->copy_buf */

/* Where a page starts, and how many cells of its first row belong to the
 * page before it. The offset is 16 bits: an AppleWorks document lives on
 * its desktop, which holds some 55 KB, and a file that somehow went past
 * 64 KB simply stops being paged there. */
struct Mark { unsigned int off; unsigned char skip; };

extern char aw_num[];                   /* awdata.s */
void __fastcall__ aw_fout(const unsigned char* d);

/* BSS: nothing zeroes it; everything below is written before it is read. */
static struct A2fcApi a;
static struct Mark marks[MAXMARKS + 1];
/* A file is a data base or a sheet, never both: the categories of the one
 * are the column widths and the formula buffer of the other. */
static char names[30 * 21];
#define cw ((unsigned char*)names)      /* a sheet: 127 column widths */
#define SHOWN (names + COLS)            /* ... and the display string of a formula */
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
static unsigned char vcol;              /* the leftmost column on the screen */
static unsigned char formulas;          /* the cell-by-cell view instead of the grid */

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

/* line at (x, y), then emptied. A grid line is the whole width, blanks and
 * all: the screen was cleared, so they cost nothing but the writing. */
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
                if (nrecs / STEP == MAXMARKS || off > 0xFFFFUL) return;
                marks[nrecs / STEP].off = (unsigned int)off;
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
    if ((unsigned int)c > 126) { puts_("#ERR#"); return; }
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

/* The cell of cleft bytes at hand, written where `out` points. Returns 1
 * for a value -- a number, or a formula's result --, which the grid puts at
 * the right of its column as AppleWorks does, 0 for a label.
 *
 * The grid shows what the sheet shows: a formula's saved display string, or
 * its result. The formula itself belongs to the cell-by-cell view (F), the
 * only place where reading `@SUM(A1...A9)` makes sense. */
static unsigned char ss_cell(void)
{
    unsigned char f0, f1, n, k, c;
    char* shown = SHOWN;                /* free while a sheet is open */
    f0 = cget();
    if (!(f0 & 0x80)) {
        if (f0 & 0x20) {                /* a label repeated across its column */
            f1 = awc(cget());
            n = col < COLS ? cw[col] : 8;
            while (n) { put(f1); --n; }
        } else {
            while (cleft) putaw(cget());
        }
        skipn(cleft);
        return 0;
    }
    f1 = cget();
    if (f0 & 0x20) {
        getnum(num);
        putnum(num);
    } else if (f1 & 0x08) {
        /* The display string AppleWorks saved comes first; the cell-by-cell
         * view shows it after the formula. */
        n = cget();
        k = 0;
        while (n-- && cleft) {
            c = awc(cget());
            if (k < WIDTH) shown[k++] = c;
        }
        if (formulas) { formula(); puts_("  = "); }
        for (n = 0; n < k; ++n) put(shown[n]);
    } else {
        getnum(num);                    /* the result; formula() has its own */
        if (formulas) { formula(); puts_("  = "); }
        putnum(num);
    }
    skipn(cleft);
    return 1;
}

/* The line, all spaces, ready for cells to be placed in it. */
static void blank(void)
{
    for (pos = 0; pos < WIDTH; ++pos) line[pos] = ' ';
}

/* Where column c starts on the screen, or 255 when it is not on it. A sheet
 * has 127 columns; a malformed file can claim more, and the walk below
 * counts in bytes. */
static unsigned char colx(int c)
{
    unsigned int x = GUTTER;
    unsigned char i;
    if (c < vcol || c >= COLS) return 255;
    for (i = vcol; i < c; ++i) {
        x += cw[i];
        if (x >= WIDTH) return 255;
    }
    return x >= WIDTH ? 255 : (unsigned char)x;
}

/* A page of the sheet from the start m; the next page's start in *next,
 * 1 when the file ended on this page (cut says how). One walk for the two
 * views: the grid gives a row a line, cells in their columns, and F gives a
 * cell a line with its formula. */
static unsigned char ss_show(const struct Mark* m, struct Mark* next)
{
    unsigned char y, c, n, x, i, d, value, k, skip = m->skip;
    unsigned long off;
    a.clrscr();
    y = 0;
    if (!formulas) {                    /* the column letters over their columns */
        blank();
        for (c = vcol; c < COLS; ++c) {
            x = colx(c);
            if (x == 255) break;
            pos = x;
            putcol(c);
        }
        pos = WIDTH;
        flush(0, y);
        y = 1;
    }
    if (!seek(m->off)) { cut = 1; return 1; }
    for (;;) {
        off = base + at;
        if (next_len() < 2) return 1;   /* the end, or a row too short for its number */
        if (!formulas && y == LINES) {
            if (off > 0xFFFFUL) return 1;
            next->off = (unsigned int)off;
            next->skip = 0;
            return 0;
        }
        row = get16();
        col = 0;
        k = 0;
        if (!formulas) {
            blank();
            pos = 0;
            putu(row);
            pos = WIDTH;
        }
        while (left && !eof) {
            c = getb();
            if (c == 0xFF) break;
            if (c < 0x80) {
                if (!c || c > left) break;
                if (formulas) {
                    if (k >= skip) {
                        if (y == LINES) {
                            if (off > 0xFFFFUL) return 1;
                            next->off = (unsigned int)off;
                            next->skip = k;
                            return 0;
                        }
                        cleft = c;
                        putcol(col);
                        putu(row);
                        while (pos < 7) put(' ');
                        ss_cell();
                        flush(0, y);
                        ++y;
                    } else {
                        skipn(c);
                    }
                    ++k;
                } else {
                    x = colx(col);
                    if (x == 255) {
                        skipn(c);       /* left of the window, or past its right edge */
                    } else {
                        cleft = c;
                        /* The cell owns its column: whatever spilled into it
                         * from the left goes, as it does in AppleWorks. */
                        for (i = 0; i < cw[col] && x + i < WIDTH; ++i) line[x + i] = ' ';
                        pos = x;
                        value = ss_cell();
                        n = pos - x;
                        /* A value goes against the right of its column: what
                         * it wrote moves there, the gap becomes blanks. */
                        if (value && n < cw[col] && x + cw[col] <= WIDTH) {
                            d = cw[col] - n;
                            i = n;
                            while (i) { --i; line[x + d + i] = line[x + i]; }
                            for (i = 0; i < d; ++i) line[x + i] = ' ';
                        }
                        pos = WIDTH;
                    }
                }
            } else {
                col += c - 0x81;
            }
            ++col;
        }
        skip = 0;
        if (!formulas) { flush(0, y); ++y; }
        skipn(left);
        if (eof) { cut = 1; return 1; }
    }
}

/* The first column of the screen that starts at v. */
static unsigned char next_from(unsigned char v)
{
    unsigned int x = GUTTER;
    while (v < COLS && x < WIDTH) { x += cw[v]; ++v; }
    return v;
}

/* One screen to the right, or back to the left. The screens are the ones a
 * walk from column A gives, so going back lands on the window one came
 * from, whatever the widths on the way. */
static void scroll(unsigned char right)
{
    unsigned char c, prev = 0;
    if (right) {
        c = next_from(vcol);
        if (c < COLS) vcol = c;
        return;
    }
    for (c = next_from(0); c < vcol; c = next_from(c)) {
        if (c <= prev) break;
        prev = c;
    }
    vcol = prev;
}

/* -- the entry --------------------------------------------------------------- */

static const char k_db[] = "SPC Next,B Prev,R First,TAB More,ESC";
static const char k_ss[] = "SPC Page,B Back,<> Cols,F Cells,ESC";
static const char k_sf[] = "SPC Page,B Back,F Grid,ESC";

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Entry* e = api->selected;
    unsigned char type = e->type, done = 0;
    unsigned int k = 0, known = 1, last;
    unsigned long off;
    unsigned char grid;
    char key;
    a = *api;
    rbuf = a.copy_buf;
    size = e->size;
    if ((type != 0x19 && type != 0x1B) || !api->full[0] || !(f = a.fopen(api->full, "rb"))) {
        a.strcpy(a.note, "Not an AppleWorks data base or sheet.");
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
        if (size < 302) {
            a.fclose(f);
            a.strcpy(a.note, "Not an AppleWorks spreadsheet.");
            return;
        }
        /* The header is the first read: 127 column widths at bytes 4-130,
         * and at 242 the version byte that says whether the rows start at
         * 300 or 302. A column of no width would stack its cell on the next
         * one, so it is shown at the default nine. */
        getb();
        for (k = 0; k < COLS; ++k) cw[k] = rbuf[4 + k] ? rbuf[4 + k] : 9;
        marks[0].off = rbuf[242] ? 302 : 300;
        marks[0].skip = 0;
        k = 0;
        vcol = 0;
        formulas = 0;
    }
    for (;;) {
        if (type == 0x19) db_show(k);
        else {
            done = ss_show(marks + k, marks + k + 1);
            if (!done && known == k + 1 && known < MAXMARKS) ++known;
        }
        a.bar_begin();
        a.cprintf("%s  %s %u", e->name, type == 0x19 ? "record" : "page", k + 1);
        if (type == 0x19) a.cprintf(" of %u%s", nrecs, cut ? " (cut)" : "");
        else if (done) a.cputs(cut ? " (cut)" : " (end)");
        a.keys_bar(44, type == 0x19 ? k_db : formulas ? k_sf : k_ss);
        key = a.cgetc();
        /* In the grid the horizontal arrows and <> walk the columns: what a
         * sheet pages through is its rows. The cell-by-cell view and the
         * data base keep them for paging. */
        grid = type == 0x1B && !formulas;
        last = type == 0x19 ? nrecs : known;
        if (key == KEY_ESC || (key | 0x20) == 'q') break;
        if ((key | 0x20) == 'r') { k = 0; vcol = 0; }
        if ((key == ' ' || key == KEY_RETURN || key == KEY_DOWN
             || (!grid && key == KEY_RIGHT)) && k + 1 < last) ++k;
        if (((key | 0x20) == 'b' || key == KEY_UP
             || (!grid && key == KEY_LEFT)) && k) --k;
        if (grid && (key == KEY_RIGHT || key == '>')) scroll(1);
        if (grid && (key == KEY_LEFT || key == '<')) scroll(0);
        if (type == 0x1B && (key | 0x20) == 'f') {
            formulas = !formulas;       /* the marks belong to one view or the other */
            k = 0;
            known = 1;
            marks[0].skip = 0;
        }
        if (key == KEY_TAB && ncats > LINES) cat0 = cat0 ? 0 : LINES;
    }
    a.fclose(f);
}
