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
 * : INPUT" out of bytes that hold no space at all.
 *
 * Paging: the starts of the last 64 pages seen are kept in a ring, as
 * MDVIEW does, so Space goes on to the end of any program and B goes back
 * up to 63 pages. A read error stops the page where it hit and the status
 * says "(read error)", never "(end)"; any page drawn again (R, B, a key)
 * reads again, the error flag cleared. */
#include "util.h"

#ifndef PLUGIN_HOST
/* libc's ferror links errno and fmisc, 90 bytes: _FILE::f_flags (offset 1,
 * asminc/_file.inc) and its _FERROR bit, as DOCVIEW and FIND read them. */
#define ferror(f) (((unsigned char*)(f))[1] & 0x04)
/* fread refuses every read once _FERROR is set, and fseek clears only
 * _FEOF/_FPUSHBACK: a page the user asks for again clears it, so one
 * transient error does not blank the rest of the file. */
#define clear_err(f) (((unsigned char*)(f))[1] &= ~0x04)
#endif
#ifndef clear_err
#define clear_err(f) clearerr(f)
#endif

void __fastcall__ plugin_entry(const struct A2fcApi*);

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[40]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
    {0,0,0},
#ifdef APPLESOFT_DOS
    "Direct DOS 3.3 Applesoft listing"
#elif defined(INTEGER_DOS)
    "Direct DOS 3.3 Integer BASIC listing"
#else
    "List an Integer BASIC program ($FA)"
#endif
    };
#pragma rodata-name (pop)

/* The 128 tokens, separated by zeros, in value order. A NAMED array and not
 * a set of literals: cc65 gathers literals differently, and this way the
 * table follows the overlay's own segment. */
#ifdef APPLESOFT_DOS
#include "applesoft_tokens.h"
#else
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

#endif

static const char st_line[] = "%-38.38s page %u%s";
static const char st_end[] = " (end)";
#ifdef INTEGER_DOS
static const char st_malformed[] = " (malformed)";
static const char st_long[] = " (line too long)";
#endif
/* the path shorter: the keys bar starts at column 52 */
static const char st_err[] = "%-29.29s page %u (read error)";
static const char st_keys[] = "SPC Next,B Prev,R First,ESC";
static const char st_num[] = "%u";
#ifdef APPLESOFT_DOS
static const char m_bad[] = "Not an Applesoft program ($FC).";
#else
static const char m_bad[] = "Not an Integer BASIC program ($FA).";
#endif
static const char m_open[] = "Cannot open it.";
static const char m_cut[] = "Program ends in the middle of a line.";
static const char m_err[] = "Read error: the listing stops there.";

#define LINES 22                        /* rows 0 to 21; 22 and 23 are the bars */
#define PAGES 64                        /* a ring: a power of two */

#ifdef INTEGER_DOS
/* BIN/BASIC's 16-bit EOF needs at most 257 logical sectors. Reject any
 * larger allocation, never truncate a chain. Metadata is retired once
 * its map is validated, and the paging ring reuses that space. */
#define A (&a)
#define DS_SECTORS 257
#define DS_DATA_BUFFER buf
#define DS_MLI a.mli
#define DS_SEEK a.fseek
#define frd a.fread
#define fopn a.fopen
#define fcls a.fclose
#include "dos_source.h"
#define starts ds_metadata.pages
#else
static FILE* f;
#endif
/* File offsets are 24-bit in ProDOS: 16 bits wrapped past 64K. */
static unsigned long fpos;              /* the offset of the next byte read */
static unsigned char have, at;
static unsigned char row, col;
static unsigned char space;             /* the last character written was a space */
static unsigned char alnum;             /* ... a letter or a digit */
static unsigned char clipped;           /* a character fell below the last row */
#ifndef INTEGER_DOS
static unsigned long starts[PAGES];     /* where the last pages seen begin, a ring */
#endif
static unsigned char rderr;             /* a read failed (not the end of the file) */

/* 255 bytes at a time, not 256: `have` and `at` are bytes, and 256 does not
 * fit in one -- cast down, a full read comes back as zero and reads as the
 * end of the file. -1 is the end. */
static int getb(void)
{
#ifdef INTEGER_DOS
    int c=ds_get();if(ds_bad)rderr=1;if(c>=0)++fpos;return c;
#else
    if (at == have) {
        have = (unsigned char)a.fread(buf, 1, 255, f);
        at = 0;
        if (!have) {                    /* the end -- or an error, never taken for it */
            if (ferror(f)) rderr = 1;
            return -1;
        }
    }
    ++fpos;
    return buf[at++];
#endif
}

static void seek(unsigned long off)
{
#ifdef INTEGER_DOS
    if(!ds_seek(off))rderr=1;
#else
    a.fseek(f, (long)off, SEEK_SET);
#endif
    fpos = off;
    have = at = 0;
}

/* One character on the screen, cut at 80 columns and at LINES rows; past that
 * we stop writing but keep reading, so a page always ends on a line boundary
 * the next one can start from. A character that falls off is `clipped`: the
 * next page then starts with that line again. */
static void put(char c)
{
    if (row >= LINES) { if (c != 13) clipped = 1; return; }
    if (c == 13) {
        ++row; col = 0;
        if (row < LINES) a.gotoxy(0, row);
        return;
    }
    if (col == 80) {
        ++row; col = 0;
        if (row >= LINES) { clipped = 1; return; }
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
#ifdef APPLESOFT_DOS
    const char* s = BAS_TOK;
#else
    const char* s = INT_TOK;
#endif
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
#ifdef APPLESOFT_DOS
    int lo, hi, c;
    unsigned int link, v;
    unsigned char quoted=0, literal=0;

    lo=getb();hi=getb();
    if(lo<0 || hi<0)return 2;
    link=(unsigned int)lo|((unsigned int)hi<<8);
    if(!link)return fpos==ds_length ? 0 : 2;
    lo=getb();hi=getb();
    if(lo<0 || hi<0)return 2;
    v=(unsigned int)lo|((unsigned int)hi<<8);
    number(v);put(' ');space=1;
    for(;;){
        c=getb();if(c<0)return 2;
        if(!c)break;
        /* LIST keeps strings, REM and DATA literal. DATA ends at a colon
         * outside quotes. Quotes may end at EOL, as Applesoft permits. */
        if(c=='"' && literal!=2)quoted=!quoted;
        if(c==':' && !quoted && literal==1)literal=0;
        if(c>=0x80 && !quoted && !literal){
            if(c>0xEA)return 2;
            token((unsigned char)(c-0x80));
            if(c==0x83)literal=1;
            if(c==0xB2)literal=2;
        }else{
            c&=0x7F;put((char)(c>=32 && c<127 ? c : '.'));
        }
    }
    /* Follow file order, never pointers from the program. Check the
     * conventional $0801 links with a wide addition before narrowing. */
    if(fpos+0x0801UL>0xFFFFUL || link!=(unsigned int)(fpos+0x0801UL))return 2;
    put(13);return 1;
#else
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
        if (c == 0x01) {
#ifdef INTEGER_DOS
            if(len)return 2;
#endif
            break;
        }           /* the end of the line */
#ifdef INTEGER_DOS
        if (c == 0x29) return 2; /* closing quote without an opening quote */
#endif
        if (c == 0x28 || c == 0x29) {   /* a string, characters throughout */
            put('"');
            while (len-- > 0) {
                c = getb();
                if (c < 0) return 2;
                if (c == 0x29) break;
                put((char)(c & 0x7F));
            }
#ifdef INTEGER_DOS
            if(c!=0x29)return 2;
#endif
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
#ifdef INTEGER_DOS
            if(len<3)return 2; /* two constant bytes and the line terminator */
#endif
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
#ifdef INTEGER_DOS
    if(len || c!=1)return 2;
#endif
    put(13);
    return 1;
#endif
}

/* page: the page shown, counted from the oldest kept (in ring slot head,
 * page number `first`); known: how many are kept; next: where the page
 * after the one shown starts. */
static unsigned char page, known, head;
static unsigned int first;
static unsigned long next;
#define START(p) starts[(unsigned char)(head + (p)) & (PAGES - 1)]

/* Page `page` on the screen, from its start. Returns what the last line()
 * returned: 1 the page is full, 0 the end of the program, 2 a cut record,
 * 3 a read error. Separate from plugin_entry so that the host harness runs
 * THIS. */
static unsigned char listpage(void)
{
    unsigned long last, from;
    unsigned char r;
    from = START(page);
    rderr=0;
#ifndef INTEGER_DOS
    clear_err(f);                       /* an earlier page's error: read again */
#endif
    seek(from);
    a.clrscr();
    row = col = 0; space = 1; clipped = 0;
    if(rderr){next=from;return 3;}
    a.gotoxy(0, 0);
    do { last = fpos; r = line(); } while (r == 1 && row < LINES);
    /* The offset the next page starts from is a line boundary: a page is
     * never re-entered in the middle of a record. It is where this one
     * stopped reading -- or the start of the last line when its tail ran
     * off the bottom, unless that line began the page (it then has the
     * whole screen and there is nowhere else to show it). */
#ifdef INTEGER_DOS
    if(clipped && last==from)r=4; /* never report a clipped long line as complete */
#endif
    if (clipped && last != from) { r = 1; fpos = last; }
    if (rderr) r = 3;
    next = fpos;
    return r;
}

/* Space: the next page, its start recorded; past PAGES pages the oldest
 * kept is dropped. */
static void forward(void)
{
    if (page + 1 < known) { ++page; return; }
    if (known < PAGES) { ++known; ++page; }
    else { head = (head + 1) & (PAGES - 1); ++first; }
    START(page) = next;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Entry* e;
    unsigned char done, ready = 0, last = 0, r;
    char key;

    init(api);
    e = a.selected;
#ifdef INTEGER_DOS
    dv_file=NULL;
#ifdef APPLESOFT_DOS
    if (e->type != 0xFC || pan->fs!=FS_DOS33
#else
    if (e->type != 0xFA || pan->fs!=FS_DOS33
#endif
        || !e->name[0]) { note(m_bad); return; }
    if (!dv_open(pan) || !ds_open(e) || ds_kind!=
#ifdef APPLESOFT_DOS
        2
#else
        1
#endif
        ) {
        dv_close();note("DOS BASIC source read/structure error.");return;
    }
#else
    if (e->type != 0xFA || pan->fs) { note(m_bad); return; }
    f = a.fopen(a.full, "rb");
    if (!f) { note(m_open); return; }
#endif
    for (;;) {
        if (!ready) { starts[0] = 0; page = head = 0; known = 1; first = 1; ready = 1; }
        r = listpage();
        done = r != 1;
        if (done) last = r;
        a.bar_begin();
#ifdef INTEGER_DOS
        a.gotoxy(0,22); /* keep status above the key bar */
#endif
        a.cprintf(r == 3 ? st_err : st_line,
#ifdef INTEGER_DOS
            e->name,
#else
            a.full,
#endif
            first + page, done ?
#ifdef INTEGER_DOS
            r==2 ? st_malformed : r==4 ? st_long :
#endif
            st_end : (const char*)"");
        a.keys_bar(52, st_keys);
        key = a.cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if (key == 'r' || key == 'R') ready = 0;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && !done)
            forward();
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
#ifdef INTEGER_DOS
    if(!dv_close()){note("DOS BASIC source close error.");return;}
#else
    a.fclose(f);
#endif
    a.strcpy(a.reselect, e->name);
    if (last == 2) note(m_cut);
    if (last == 3) note(m_err);
#ifdef INTEGER_DOS
    if(last==4)note("Line listing exceeds one screen page.");
#endif
}
