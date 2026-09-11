/* intbasic.c -- listing an Integer BASIC program, ProDOS type $FA. From the
 * ! menu, on the selected entry.
 *
 * BASLIST serves the $FC, Applesoft, and nothing served the $FA: it fell to
 * the hex viewer or to the text reader, both of which show its tokens as the
 * control characters they are. Integer BASIC is what the Apple II shipped
 * with in 1977 and what Woz's own Breakout is written in.
 *
 * The file is a chain of line records, no header and no end marker beyond
 * the file's length:
 *
 *   [len][number lo][number hi][ ... ][$01]
 *
 * `len` counts the whole record, its own byte included, so the next line
 * starts `len` bytes on. Inside a line:
 *
 *   $00-$7F   a token, from the table below -- 128 of them, several values
 *             sharing one text, which is how the tokeniser records which
 *             form of a comma or a THEN was typed;
 *   $80-$FF   a character of a name or a number, ASCII with the high bit
 *             set;
 *   $B0-$B9   AND not following a letter or a digit: the leading digit of a
 *             CONSTANT, whose sixteen-bit value is the next two bytes. The
 *             test matters -- the 1 of A1 is a $B1 too.
 *
 * A string ($28 to its closing $29) and the tail of a REM ($5D to the end of
 * the line) are characters throughout, digits included: reading a $B5 there
 * as a constant swallowed two bytes of text and turned "WITH 5 BALLS" into
 * "WITH 49824ALLS".
 *
 * The spacing is the interpreter's own: LIST puts a space before a keyword
 * that begins with a letter and after one that ends with a letter, and none
 * around the punctuation and the operators. That is what makes ": GR : PRINT
 * : INPUT" out of bytes that hold no space at all. */
#include "util.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[40]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
    {0,0,0}, "List an Integer BASIC program ($FA)" };
#pragma rodata-name (pop)

/* The 128 tokens, separated by zeros, in value order. A NAMED array and not
 * a set of literals: cc65 gathers literals differently, and this way the
 * table follows the overlay's own segment. */
static const char INT_TOK[] =
    "HIMEM:\0\0_\0:\0LOAD\0SAVE\0CON\0RUN\0RUN\0DEL\0,\0NEW\0CLR\0AUTO\0,\0MAN\0"
    "HIMEM:\0LOMEM:\0+\0-\0*\0/\0=\0#\0>=\0>\0<=\0<>\0<\0AND\0OR\0MOD\0"
    "^\0+\0(\0,\0THEN\0THEN\0,\0,\0\"\0\"\0(\0!\0!\0(\0PEEK\0RND\0"
    "SGN\0ABS\0PDL\0RNDX\0(\0+\0-\0NOT\0(\0=\0#\0LEN(\0ASC(\0SCRN(\0,\0(\0"
    "$\0$\0(\0,\0,\0;\0;\0;\0,\0,\0,\0TEXT\0GR\0CALL\0DIM\0DIM\0"
    "TAB\0END\0INPUT\0INPUT\0INPUT\0FOR\0=\0TO\0STEP\0NEXT\0,\0RETURN\0GOSUB\0"
    "REM\0LET\0GOTO\0IF\0PRINT\0PRINT\0PRINT\0POKE\0,\0COLOR=\0PLOT\0,\0HLIN\0"
    ",\0AT\0VLIN\0,\0AT\0VTAB\0=\0=\0)\0)\0LIST\0,\0LIST\0POP\0"
    "NODSP\0NODSP\0NOTRACE\0DSP\0DSP\0TRACE\0PR#\0IN#";

static const char st_line[] = "%-38.38s page %u%s";
static const char st_end[] = " (end)";
static const char st_keys[] = "SPC Next,B Prev,R First,ESC";
static const char st_num[] = "%u";
static const char m_bad[] = "Not an Integer BASIC program ($FA).";
static const char m_open[] = "Cannot open it.";
static const char m_cut[] = "Program ends in the middle of a line.";

#define LINES 22                        /* rows 0 to 21; 22 and 23 are the bars */
#define PAGES 40

static FILE* f;
static unsigned int fpos;               /* the offset of the next byte read */
static unsigned char have, at;
static unsigned char row, col;
static unsigned char space;             /* the last character written was a space */
static unsigned char alnum;             /* ... a letter or a digit */
static unsigned int starts[PAGES];      /* where each page seen so far begins */

/* 255 bytes at a time, not 256: `have` and `at` are bytes, and 256 does not
 * fit in one -- cast down, a full read comes back as zero and reads as the
 * end of the file. -1 is the end. */
static int getb(void)
{
    if (at == have) {
        have = (unsigned char)a.fread(buf, 1, 255, f);
        at = 0;
        if (!have) return -1;
    }
    ++fpos;
    return buf[at++];
}

static void seek(unsigned int off)
{
    a.fseek(f, (long)off, SEEK_SET);
    fpos = off;
    have = at = 0;
}

/* One character on the screen, cut at 80 columns and at LINES rows; past that
 * we stop writing but keep reading, so a page always ends on a line boundary
 * the next one can start from. */
static void put(char c)
{
    if (row >= LINES) return;
    if (c == 13) {
        ++row; col = 0;
        if (row < LINES) a.gotoxy(0, row);
        return;
    }
    if (col == 80) {
        ++row; col = 0;
        if (row >= LINES) return;
        a.gotoxy(0, row);
    }
    a.cputc(c);
    ++col;
    space = c == ' ';
}

static void puts_(const char* s) { while (*s) put(*s++); }

static unsigned char letter(char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); }

/* A token, with the interpreter's spacing around it. */
static void token(unsigned char n)
{
    const char* s = INT_TOK;
    const char* e;

    while (n--) { while (*s) ++s; ++s; }
    if (!*s) return;                    /* $01, the end of a line: nothing to show */
    if (letter(*s) && !space) put(' ');
    for (e = s; *e; ++e) {}
    puts_(s);
    if (letter(e[-1])) put(' ');
    alnum = 0;
}

static void number(unsigned int v)
{
    char t[7];

    a.sprintf(t, st_num, v);
    puts_(t);
    alnum = 1;
}

/* One line record, from its length byte. Returns 0 at the end of the file and
 * 2 on a record that runs past it -- a truncated program is said to be one
 * rather than listed as if it were whole. */
static unsigned char line(void)
{
    int len, c, n;
    unsigned int v;

    len = getb();
    if (len < 0) return 0;
    if (len < 4) return 2;
    n = getb();
    c = getb();
    if (c < 0) return 2;
    number((unsigned int)n | ((unsigned int)c << 8));
    put(' ');
    space = 1;
    alnum = 0;
    len -= 3;
    while (len-- > 0) {
        c = getb();
        if (c < 0) return 2;
        if (c == 0x01) break;           /* the end of the line */
        if (c == 0x28 || c == 0x29) {   /* a string, characters throughout */
            put('"');
            while (len-- > 0) {
                c = getb();
                if (c < 0) return 2;
                if (c == 0x29) break;
                put((char)(c & 0x7F));
            }
            put('"');
            alnum = 0;
        } else if (c == 0x5D) {         /* REM, characters to the end of the line */
            token(0x5D);
            while (len-- > 0) {
                c = getb();
                if (c < 0) return 2;
                if (c == 0x01) break;
                put((char)(c & 0x7F));
            }
            break;
        } else if (c >= 0xB0 && c <= 0xB9 && !alnum) {
            v = (unsigned int)getb();   /* a constant: its value is the next two */
            c = getb();
            if (c < 0) return 2;
            v |= (unsigned int)c << 8;
            len -= 2;
            number(v);
        } else if (c & 0x80) {
            c &= 0x7F;
            put((char)c);
            alnum = letter((char)c) || (c >= '0' && c <= '9');
        } else {
            token((unsigned char)c);
        }
    }
    put(13);
    return 1;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Entry* e;
    unsigned char page = 0, known = 1, done, cut = 0, r;
    char key;

    init(api);
    e = a.selected;
    if (e->type != 0xFA || pan->fs) { note(m_bad); return; }
    f = a.fopen(a.full, "rb");
    if (!f) { note(m_open); return; }
    starts[0] = 0;
    for (;;) {
        seek(starts[page]);
        a.clrscr();
        row = col = 0; space = 1; done = 0;
        a.gotoxy(0, 0);
        while (row < LINES) {
            r = line();
            if (r != 1) { done = 1; cut = r == 2; break; }
        }
        /* The offset the next page starts from is where this one stopped
         * reading, which is a line boundary: a page is never re-entered in
         * the middle of a record. */
        if (!done && page + 1 < PAGES && known == page + 1) {
            starts[page + 1] = fpos;
            known = page + 2;
        }
        a.bar_begin();
        a.cprintf(st_line, a.full, page + 1, done ? st_end : (const char*)"");
        a.keys_bar(52, st_keys);
        key = a.cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if (key == 'r' || key == 'R') page = 0;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN)
            && !done && page + 1 < known) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    a.fclose(f);
    a.strcpy(a.reselect, e->name);
    if (cut) note(m_cut);
}
