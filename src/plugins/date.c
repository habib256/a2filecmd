/* date.c -- the system date and time: show it, set it, stamp files with it.
 * A small service-table overlay.
 *
 * From the ! menu. Line 22 shows the ProDOS date and time kept at
 * $BF90-$BF93 ("No date" when the packed date is 0) and whether a clock is
 * present (MACHID $BF98, bit 0: clock:Y or clock:N). Then one key:
 *
 *   S  sets the system date: twelve digits, DD MM YYYY HH MM, read one at a
 *      time with cgetc and echoed as "15/06/2026 14:30" -- the core's
 *      prompt takes the characters of a ProDOS name, not a free run of
 *      digits, so the keys are read here; anything that is not a digit is
 *      ignored (the separators may be typed or not), Escape cancels. The
 *      ranges are checked (1-31, 1-12, 1940-2039, 0-23, 0-59) and the
 *      fields packed the ProDOS way: the day in bits 0-4 of $BF90-$BF91,
 *      the month in bits 5-8, the year in bits 9-15 -- 0-39 is 2000-2039
 *      and 40-99 is 1940-1999 -- then the minute in $BF92, the hour in
 *      $BF93.
 *   F  stamps the tagged files of the active panel (or the entry under the
 *      cursor when nothing is tagged) with the system date, as modification
 *      date: GET_FILE_INFO ($C4) then SET_FILE_INFO ($C3) on
 *      the same parameter block, so the access, the type and the auxtype go
 *      back as they were read. The volume list, a disk image and a DOS 3.3
 *      disk are refused; the ".." of a directory is left to ProDOS, which
 *      refuses that path. Both panels are reread and redrawn -- their dates
 *      changed -- and the count is announced.
 *   Anything else (Escape) leaves, the date still on the message line.
 *
 * No session clock driver is installed at $BF06: the resident has no room
 * left for one. On a machine without a clock the date set here holds until
 * the next boot and stamps every file the program writes from then on;
 * where a clock card is present ProDOS rewrites $BF90-$BF93 at the next MLI
 * call and S only lasts until then.
 *
 * ---- Why this one is written in assembly ----
 *
 * The file AND the BSS have to fit the 1,280-byte window. The same overlay
 * in plain C came out at 1,700 bytes, and 1,475 once the panel walk and the
 * printing were cut down: cc65's own glue is what does not fit. Two costs,
 * measured on this source:
 *
 *  - a service reached through the volname/fixtypes stub (a C function whose
 *    body is `ldy #offset; jmp tramp`) costs 12 bytes for the stub, because
 *    the compiler pushes the register argument in the prologue and emits a
 *    dead epilogue to pop it, plus incsp2/incsp3/incsp6 in the library;
 *  - the sequence around the calls -- reading api->panels, testing a byte,
 *    calling with two arguments -- costs three times what the 6502 needs.
 *
 * So the stubs here have NO parameters (`ldy #offset; jmp apicall`, six
 * bytes, nothing pushed, nothing popped) and everything that calls them is
 * plain 6502 in the compiler's inline assembler, laid out as one small named
 * routine per job. The arguments follow cc65's fastcall all the same: the
 * last one in A/X, the earlier ones pushed with pushax/pusha, so the service
 * sees exactly what a compiled call would give it. No 65C02 opcode: the same
 * source builds the floppy edition. Two habits of the compiler to know: a
 * label whose only reference is a forward `jmp` is dropped (the reference is
 * emitted, the definition is not -- use a branch), and `%v` on a struct
 * gives its address, so a field is `%v+offsetof(...)`. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[22];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, plugin_entry, 0, 0, 0,
    "Set date; stamp files"
};
#pragma rodata-name (pop)

/* The ProDOS global page: $BF90-$BF91 the date, $BF92 the minute, $BF93 the
 * hour, $BF98 the machine identification whose bit 0 says a clock is there. */

/* GET_FILE_INFO $C4 takes 10 parameters, SET_FILE_INFO $C3 the first 7 of
 * the same block (cc65 packs it): the three bytes at storage/blocks are the
 * null field of the second call, and the four at mdate/mtime, with the four
 * at cdate/ctime, are what this overlay writes. */
struct Gfi {
    unsigned char n; unsigned char* path;
    unsigned char access, type; unsigned int aux;
    unsigned char storage; unsigned int blocks, mdate, mtime, cdate, ctime;
};

static const char m_only[]  = "Open a directory.";
static const char m_bad[]   = "Not a date.";
static const char m_none[]  = "No date";
static const char m_null[]  = "";
static const char m_ask[]   = "DDMMYYYYHHMM: ";
static const char m_clock[] = "  clock:";
static const char m_keys[]  = " S Set date F Stamp ESC";
static const char m_files[] = " files dated";
/* The six pairs of digits read, and what is echoed before each of them. */
static const char sepr[6] = { 0, '/', '/', 0, ' ', ':' };
static const unsigned char ten[10] = { 0, 10, 20, 30, 40, 50, 60, 70, 80, 90 };

/* Nothing here is read before being written at entry. */
static const struct A2fcApi* A;
static struct Panel* P;                 /* the active panel */
static const struct Entry* E;           /* the entry being stamped */
static unsigned char* PATH;             /* api->other_full: a Pascal path, its length first */
static unsigned char* tp;               /* the tag byte of E */
static unsigned char mask;              /* its bit */
static unsigned char i, n, any, done, root, pfs, g, j, acc, pad, u1, u2;
static unsigned char fld[6];            /* day, month, century, year, hour, minute */
static struct Gfi gfi;

#pragma optimize (push, off)            /* the assembler text goes out as written */

/* One service of the table: Y its offset, A/X the last argument, the earlier
 * ones already pushed. Six-byte stubs jump here; nothing is on the C stack
 * that is ours, so nothing has to be taken off it. */
static void apicall(void)
{
    asm("sta tmp1");
    asm("stx tmp2");
    asm("lda %v\n sta ptr1\n lda %v+1\n sta ptr1+1", A, A);
    asm("lda (ptr1),y\n sta jmpvec+1");
    asm("iny");
    asm("lda (ptr1),y\n sta jmpvec+2");
    asm("lda tmp1\n ldx tmp2");
    asm("jmp jmpvec");
}
#define SVC(field) { asm("ldy #%b", offsetof(struct A2fcApi, field)); asm("jmp %v", apicall); }
static void s_msg(void)  SVC(message)       /* A/X: the line */
static void s_outs(void) SVC(cputs)         /* A/X: the string, where the cursor is */
static void s_put(void)  SVC(cputc)         /* A: one character */
static void s_getk(void) SVC(cgetc)         /* returns A */
static void s_read(void) SVC(read_panel)    /* A: 0 or 1 */
static void s_draw(void) SVC(draw_all)
static void s_full(void) SVC(build_full)    /* pushed: out, panel; A/X: the entry */
static void s_mli(void)  SVC(mli)           /* pushed: the command; A/X: the block */

/* A (0-99) in two digits where the cursor is; pad = 0 drops a leading zero. */
static void pr2(void)
{
    asm("ldx #'0'");
    asm("p1: sec");
    asm("sbc #10");
    asm("bcc p2");
    asm("inx");
    asm("bcs p1");                          /* always: the subtraction did not borrow */
    asm("p2: adc #10");                     /* the carry is clear: back to the remainder */
    asm("ora #'0'");
    asm("sta %v", u1);
    asm("cpx #'0'");
    asm("bne p3");
    asm("lda %v", pad);
    asm("beq p4");
    asm("p3: txa");
    asm("jsr %v", s_put);
    asm("p4: lda %v", u1);
    asm("jmp %v", s_put);
}

/* The message line: the system date, the clock, and the two keys. */
static void show(void)
{
    asm("lda #1\n sta %v", pad);
    asm("lda $BF90\n sta %v\n lda $BF91\n sta %v\n lsr a\n sta %v", u2, j, acc);
    asm("lda #<%v\n ldx #>%v\n jsr %v", m_null, m_null, s_msg);     /* clears line 22 */
    asm("lda %v\n ora %v\n bne sw1", u2, j);                        /* zero date, not year 2000 */
    asm("lda #<%v\n ldx #>%v\n jsr %v", m_none, m_none, s_outs);
    asm("clc\n bcc sw2");
    asm("sw1: lda %v\n and #31\n jsr %v", u2, pr2);                 /* the day */
    asm("lda #'/'\n jsr %v", s_put);
    asm("lda %v\n lsr a\n lsr a\n lsr a\n lsr a\n lsr a\n sta %v", u2, mask);
    asm("lda %v\n and #1\n asl a\n asl a\n asl a\n ora %v", j, mask);
    asm("jsr %v", pr2);                                             /* the month */
    asm("lda #'/'\n jsr %v", s_put);
    asm("ldx #20\n lda %v\n cmp #40\n bcc sw3\n ldx #19", acc);
    asm("sw3: txa\n jsr %v", pr2);                                  /* the century */
    asm("lda %v\n jsr %v", acc, pr2);                               /* the year */
    asm("lda #' '\n jsr %v", s_put);
    asm("lda $BF93\n jsr %v", pr2);                                 /* the hour */
    asm("lda #':'\n jsr %v", s_put);
    asm("lda $BF92\n jsr %v", pr2);                                 /* the minute */
    asm("sw2:");
    asm("lda #<%v\n ldx #>%v\n jsr %v", m_clock, m_clock, s_outs);
    asm("ldx #'N'\n lda $BF98\n and #1\n beq sw4\n ldx #'Y'");
    asm("sw4: txa\n jsr %v", s_put);
    asm("lda #<%v\n ldx #>%v\n jmp %v", m_keys, m_keys, s_outs);
}

/* The twelve digits into fld[], echoed with their separators; A = 0 on
 * Escape. Two at a time, so no field leaves the byte: the tens come from a
 * table, which spares cc65's 16-bit multiplication. */
static void digits(void)
{
    asm("lda #<%v\n ldx #>%v\n jsr %v", m_ask, m_ask, s_msg);   /* the cursor stays after it */
    asm("lda #0\n sta %v", g);
    asm("dg1: ldy %v\n lda %v,y\n beq dg2", g, sepr);
    asm("jsr %v", s_put);
    asm("dg2: lda #0\n sta %v\n lda #2\n sta %v", acc, j);
    asm("dg3: jsr %v", s_getk);
    asm("cmp #%b\n beq dg8", KEY_ESC);
    asm("cmp #'0'\n bcc dg3");
    asm("cmp #$3A\n bcs dg3");
    asm("sta %v\n jsr %v", u1, s_put);
    asm("ldy %v\n lda %v,y\n clc\n adc %v\n sec\n sbc #'0'\n sta %v", acc, ten, u1, acc);
    asm("dec %v\n bne dg3", j);
    asm("ldy %v\n lda %v\n sta %v,y", g, acc, fld);
    asm("inc %v\n lda %v\n cmp #6\n bcc dg1", g, g);
    asm("lda #1\n rts");
    asm("dg8: lda #0");
}

/* PATH, written by build_full from its second byte, made a Pascal string. */
static void pascal(void)
{
    asm("lda %v\n sta ptr1\n lda %v+1\n sta ptr1+1", PATH, PATH);
    asm("ldy #0");
    asm("pl1: iny\n lda (ptr1),y\n bne pl1");
    asm("dey\n tya\n ldy #0\n sta (ptr1),y");
}

/* SET_FILE_INFO writes the modification date; creation stays unchanged. */
static void dates(void)
{
    asm("ldx #3");
    asm("dt1: lda $BF90,x\n sta %v+%b,x\n dex\n bpl dt1",
        gfi, offsetof(struct Gfi, mdate));
}

/* One file: its information read, its modification date replaced, written back;
 * A = 1 once E is stamped. */
static void stamp(void)
{
    asm("lda %v\n clc\n adc #1\n tay\n lda %v+1\n adc #0\n tax\n tya", PATH, PATH);
    asm("jsr pushax");                                          /* build_full(PATH + 1, */
    asm("lda %v\n ldx %v+1\n jsr pushax", P, P);                /*            P, */
    asm("lda %v\n ldx %v+1\n jsr %v", E, E, s_full);            /*            E) */
    asm("cmp #0\n bne st1\n rts");                              /* too long a path */
    asm("st1: jsr %v", pascal);
    asm("lda #10\n sta %v", gfi);
    asm("lda #$C4\n jsr pusha\n lda #<%v\n ldx #>%v\n jsr %v", gfi, gfi, s_mli);
    asm("cmp #0\n beq st2\n lda #0\n rts");
    asm("st2: jsr %v", dates);
    asm("lda #7\n sta %v", gfi);                                /* access, type, auxtype as read */
    asm("lda #$C3\n jsr pusha\n lda #<%v\n ldx #>%v\n jsr %v", gfi, gfi, s_mli);
    asm("cmp #0\n beq st3\n lda #0\n rts");
    asm("st3: lda #1");
}

/* The walk over the entries: the tagged ones are stamped, `any` says whether
 * one was, `done` counts those that took the date. */
static void walk(void)
{
    asm("lda #1\n sta %v", mask);
    asm("lda #0\n sta %v\n sta %v\n sta %v", i, done, any);
    asm("wk1: lda %v\n cmp %v\n bcs wk9", i, n);
    asm("lda %v\n sta ptr1\n lda %v+1\n sta ptr1+1", tp, tp);
    asm("ldy #0\n lda (ptr1),y\n and %v\n beq wk3", mask);
    asm("lda #1\n sta %v", any);
    asm("jsr %v\n clc\n adc %v\n sta %v", stamp, done, done);
    asm("wk3: asl %v\n bne wk4", mask);         /* the next tag bit, then the next byte */
    asm("rol %v\n inc %v\n bne wk4\n inc %v+1", mask, tp, tp);
    asm("wk4: lda %v\n clc\n adc #%b\n sta %v\n bcc wk5\n inc %v+1",
        E, sizeof(struct Entry), E, E);
    asm("wk5: inc %v\n jmp wk1", i);
    asm("wk9:");
}

/* "N files dated", N being `done` (140 at most: one panel). */
static void count(void)
{
    asm("lda #0\n sta %v", pad);
    asm("lda %v\n cmp #100\n bcc cn1", done);
    asm("sec\n sbc #100\n sta %v", done);
    asm("lda #'1'\n jsr %v", s_put);            /* 100-140: the hundreds digit is a 1 */
    asm("lda #1\n sta %v", pad);
    asm("cn1: lda %v\n jsr %v", done, pr2);
    asm("lda #<%v\n ldx #>%v\n jmp %v", m_files, m_files, s_outs);
}

/* S: the fields read, checked, and packed into the global page. */
static void set_date(void)
{
    asm("jsr %v\n cmp #0\n bne sd1\n rts", digits);             /* Escape */
    asm("sd1: lda %v+3\n sta %v", fld, acc);                    /* the year, 0-99 */
    asm("lda %v\n beq sd8\n cmp #32\n bcs sd8", fld);           /* the day, 1-31 */
    asm("lda %v+1\n beq sd8\n cmp #13\n bcs sd8", fld);         /* the month, 1-12 */
    asm("lda %v+4\n cmp #24\n bcs sd8", fld);                   /* the hour */
    asm("lda %v+5\n cmp #60\n bcs sd8", fld);                   /* the minute */
    asm("lda %v+2\n cmp #20\n bne sd2", fld);                   /* the century */
    asm("lda %v\n cmp #40\n bcc sd3\n bcs sd8", acc);           /* 20xx: 0-39 */
    asm("sd2: cmp #19\n bne sd8");
    asm("lda %v\n cmp #40\n bcc sd8", acc);                     /* 19xx: 40-99 */
    asm("sd3: lda %v+1\n asl a\n asl a\n asl a\n asl a\n asl a\n ora %v\n sta $BF90", fld, fld);
    asm("lda %v\n asl a\n sta %v", acc, u1);
    asm("lda %v+1\n lsr a\n lsr a\n lsr a\n ora %v\n sta $BF91", fld, u1);
    asm("lda %v+5\n sta $BF92\n lda %v+4\n sta $BF93", fld, fld);
    asm("jmp %v", show);
    asm("sd8: lda #<%v\n ldx #>%v\n jmp %v", m_bad, m_bad, s_msg);
}

/* F: the tagged entries of the active panel, or the one under the cursor.
 * The fields of the panel are read in one go, then the walk. */
static void stamp_files(void)
{
    asm("lda %v\n sta ptr1\n lda %v+1\n sta ptr1+1", P, P);
    asm("ldy #%b\n lda (ptr1),y\n beq sf8", offsetof(struct Panel, path));    /* the volume list */
    asm("ldy #%b\n lda (ptr1),y\n bne sf8", offsetof(struct Panel, fs));      /* an image, a DOS 3.3 disk */
    asm("ldy #%b\n lda (ptr1),y\n sta %v", offsetof(struct Panel, count), n);
    asm("ldy #%b\n lda (ptr1),y\n sta %v\n iny\n lda (ptr1),y\n sta %v+1",
        offsetof(struct Panel, e), E, E);
    asm("lda %v\n clc\n adc #%b\n sta %v\n lda %v+1\n adc #0\n sta %v+1",
        P, offsetof(struct Panel, tags), tp, P, tp);
    asm("jsr %v", walk);
    asm("lda %v\n bne sf1", any);                               /* nothing tagged: the cursor */
    asm("lda %v\n sta ptr1\n lda %v+1\n sta ptr1+1", A, A);
    asm("ldy #%b\n lda (ptr1),y\n sta %v\n iny\n lda (ptr1),y\n sta %v+1",
        offsetof(struct A2fcApi, selected), E, E);
    asm("jsr %v\n sta %v", stamp, done);
    asm("sf1: lda #0\n jsr %v", s_read);                        /* both panels show dates */
    asm("lda #1\n jsr %v", s_read);
    asm("jsr %v", s_draw);
    asm("lda #<%v\n ldx #>%v\n jsr %v", m_null, m_null, s_msg);
    asm("jmp %v", count);
    asm("sf8: lda #<%v\n ldx #>%v\n jmp %v", m_only, m_only, s_msg);
}

/* The entry point: A/X hold the table (pushax, which the prologue calls,
 * gives them back), then the panel, the borrowed path buffer, the line, and
 * one key. Both branches return through the epilogue, which drops what the
 * prologue pushed. */
void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    asm("sta %v\n stx %v+1", A, A);
    asm("sta ptr1\n stx ptr1+1");
    asm("ldy #%b\n lda (ptr1),y\n sta %v\n iny\n lda (ptr1),y\n sta %v+1",
        offsetof(struct A2fcApi, panels), P, P);
    asm("ldy #%b\n lda (ptr1),y\n sta ptr2\n iny\n lda (ptr1),y\n sta ptr2+1",
        offsetof(struct A2fcApi, active));
    asm("ldy #%b\n lda (ptr1),y\n sta %v\n sta %v+%b",          /* other_full: 81 bytes on loan */
        offsetof(struct A2fcApi, other_full), PATH, gfi, offsetof(struct Gfi, path));
    asm("iny\n lda (ptr1),y\n sta %v+1\n sta %v+%b",
        PATH, gfi, offsetof(struct Gfi, path) + 1);
    asm("ldy #0\n lda (ptr2),y\n beq pe1");
    asm("lda %v\n clc\n adc #%b\n sta %v\n bcc pe1\n inc %v+1",
        P, sizeof(struct Panel), P, P);
    asm("pe1: jsr %v", show);
    asm("jsr %v", s_getk);
    asm("and #$DF\n sta %v", u1);                               /* upper case; Escape stays $1B */
    asm("cmp #'S'\n bne pe2\n jsr %v", set_date);
    asm("pe2: lda %v\n cmp #'F'\n bne pe3\n jsr %v", u1, stamp_files);
    asm("pe3:");
}
#pragma optimize (pop)
