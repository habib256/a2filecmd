/* tagpat.c -- tags the files of the active panel by name pattern, type,
 * size or date, the way Copy II Plus selects them.
 *
 * From the ! menu, in a directory panel. A pattern is read on line 22:
 * `=` matches any run of characters (none included), `?` exactly one;
 * a pattern without wildcards is a whole name. After a comma, filters in
 * any order: `Tnn` the ProDOS type in hex, `>n` / `<n` a size in bytes
 * strictly above / below n (decimal, held on 24 bits: 16 MB, the largest
 * a ProDOS file can be), `D` modified today (the mdate equals the system
 * date at $BF90). E.g. `=.TXT,T04`, `=,>2000`, `?.BAS`. Return ends the
 * pattern, ESC cancels, Delete or the left arrow erases. Then one key:
 * T tags the matches, U untags them, X tags the matches and untags
 * everything else (an exact selection). Directories, `..` included, are
 * matched by name and counted among the "(M matched)", but never tagged:
 * the core never tags one either (tag_all skips them) and their `<DIR>`
 * row has no room for the mark. The message line ends with
 * "N tagged (M matched)", "N untagged" after a U.
 *
 * A small overlay: 1,212 bytes of file plus 46 of BSS, in the 1,280-byte
 * window. The same logic in plain C came out at 2,600 bytes with cc65
 * (long arithmetic, pointer indexing, 27 bytes for each call through the
 * table) and a C flow around assembly helpers at 1,700, so the whole body
 * is 6502 assembly in asm() bodies: the header, the entry point and the
 * strings stay C. It runs on the cc65 zero page (ptr1-ptr4, tmp1-tmp4)
 * that the program's own C code already uses, and reaches the table's
 * functions by their offsets in struct A2fcApi (message 16, draw_all 28,
 * sprintf 60, cputs 62, cputc 64, cgetc 74), the panel's fields (count 64,
 * e 74, tags 76; 98 bytes per panel) and the entry's (name 0, type 17,
 * size 23, mdate 27; 29 bytes per entry). sprintf is cdecl: the arguments
 * go on the C stack, Y says how many bytes, and it pops them. Everything
 * is 6502: no 65C02 opcode.
 *
 * Two traps of writing this much assembly inside asm(), both silent until
 * the link, both cost hours:
 *
 *  - a `jsr` or a `jmp` to a label defined FURTHER DOWN in the same
 *    function is compiled as a reference to an external symbol, and the
 *    label, which nothing the code generator can see then refers to, is
 *    dropped from the output: ld65 ends on "Unresolved external 'a_tag'".
 *    Backward jumps are fine, and so are branches in both directions (the
 *    parser knows a branch operand is a code label). `#pragma optimize
 *    (off)`, which is here for the usual reason -- the optimiser would
 *    take a `ldy` before a `jmp` for dead code -- does not help. The cure:
 *    a real function for a forward `jsr` (tagbyte below), and a branch
 *    for a forward `jmp` -- `ora tmp1` before `bne a_store` can never
 *    give zero, tmp1 holding a single bit.
 *  - `#<%v+2` becomes `#<_sym+2` and ca65 reads that as (<_sym)+2: the
 *    high byte took the +2 as well, and the "empty string" of the message
 *    pointed 512 bytes past its NUL. Parenthesise: `#<(%v+2)`. */
#include "../a2fc_plugin.h"

/* Declared without its parameter, and cast into the header: the entry point
 * only wants the pointer in A/X, and a declared parameter costs the six
 * bytes of cc65's pushax/incsp2 around a body that never reads the C stack. */
void __fastcall__ plugin_entry(void);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, (void __fastcall__ (*)(const struct A2fcApi*))plugin_entry, 0, 0, 0,
    "Tag files by pattern (= ?), type, size or date"
};
#pragma rodata-name (pop)

/* The pattern, and afterwards the message built over it: "255 untagged
 * (255 matched)" is 27 bytes, so 28 is the floor. */
#define PAT_MAX 28

/* BSS is not zeroed: every static below is written before it is read. */
static const struct A2fcApi* A;
static struct Panel* pan;
static char pat[PAT_MAX];               /* the pattern, then its filters after the comma; then the message */
static unsigned char i;                 /* the index into pat, then the entry index */
static unsigned char flags, ftype;      /* the filters: bit 0 type, 1 >, 2 <, 3 today */
static unsigned char lim[6];            /* the > bound then the < bound, 24 bits each, little-endian:
                                         * tmp4 = 2 or 5 indexes the high byte of the one at hand */
static unsigned char* t;                /* its tag byte, and the bit within */
static unsigned char mode, n, matched;

static const char s_vol[]    = "Open a directory.";
static const char s_prompt[] = "Pattern (= ?),Tnn,>n,<n,D: ";
static const char s_bad[]    = "Bad filter";
static const char s_keys[]   = "T Tag  U Untag  X Only  ESC";
static const char s_fmt[]    = "%u %stagged (%u matched)";
static const char s_un[]     = "un";                /* s_un + 2: the empty string */

#pragma optimize (push, off)

/* The table's function at offset Y, into ptr2. */
static void getfn(void)
{
    asm("lda %v", A);
    asm("sta ptr1");
    asm("lda %v+1", A);
    asm("sta ptr1+1");
    asm("lda (ptr1),y");
    asm("sta ptr2");
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta ptr2+1");
}

/* Calls the table's function at offset Y with A/X as its fastcall
 * argument (or as nothing). */
static void call_api(void)
{
    asm("sta tmp1");
    asm("stx tmp2");
    asm("jsr %v", getfn);
    asm("lda tmp1");
    asm("ldx tmp2");
    asm("jmp (ptr2)");
}

/* A jump through ptr2, for sprintf: Y carries its argument bytes. */
static void jump2(void)
{
    asm("jmp (ptr2)");
}

/* message(A/X). */
static void say(void)
{
    asm("ldy #16");
    asm("jmp %v", call_api);
}

/* A key, upper-cased, in A. */
static void getkey(void)
{
    asm("ldy #74");
    asm("jsr %v", call_api);
    asm("cmp #'a'");
    asm("bcc k_done");
    asm("cmp #'z'+1");
    asm("bcs k_done");
    asm("sbc #31");                 /* the carry is clear: 32 */
    asm("k_done:");
}

/* The pattern, on line 22: Return ends (A = 1), ESC gives A = 0, Delete
 * or Left erases, letters are upper-cased. */
static void read_pattern(void)
{
    asm("lda #0");
    asm("sta %v", i);
    asm("r_loop:");
    asm("ldy %v", i);
    asm("lda #0");
    asm("sta %v,y", pat);
    asm("lda #<%v", s_prompt);
    asm("ldx #>%v", s_prompt);
    asm("jsr %v", say);
    asm("lda #<%v", pat);
    asm("ldx #>%v", pat);
    asm("ldy #62");                 /* cputs */
    asm("jsr %v", call_api);
    asm("lda #'_'");
    asm("ldy #64");                 /* cputc */
    asm("jsr %v", call_api);
    asm("jsr %v", getkey);
    asm("cmp #27");
    asm("beq r_esc");
    asm("cmp #13");
    asm("bne r_edit");
    asm("lda %v", i);
    asm("beq r_loop");              /* nothing typed: again */
    asm("lda #1");
    asm("rts");
    asm("r_edit:");
    asm("cmp #127");
    asm("beq r_del");
    asm("cmp #8");
    asm("bne r_char");
    asm("r_del:");
    asm("lda %v", i);
    asm("beq r_loop");
    asm("dec %v", i);
    asm("jmp r_loop");
    asm("r_char:");
    asm("cmp #33");
    asm("bcc r_loop");
    asm("ldy %v", i);
    asm("cpy #%b", PAT_MAX - 1);
    asm("bcs r_loop");
    asm("sta %v,y", pat);
    asm("inc %v", i);
    asm("jmp r_loop");
    asm("r_esc:");
    asm("lda #0");
}

/* Copy II Plus wildcards against the name of the entry at sreg,
 * iteratively: `=` any run, `?` one character. The classic two-pointer
 * walk (ptr1 the pattern, ptr2 the name), backtracking to the last `=`
 * (ptr3, ptr4 the name position after it) when a literal fails. The
 * pattern ends at the zero or at the comma of the filters (a name never
 * holds a comma, so one in the pattern fails as a literal). A = 1 or 0. */
static void match(void)
{
    asm("lda #<%v", pat);
    asm("sta ptr1");
    asm("lda #>%v", pat);
    asm("sta ptr1+1");
    asm("lda sreg");
    asm("sta ptr2");
    asm("lda sreg+1");
    asm("sta ptr2+1");
    asm("lda #0");
    asm("sta ptr3+1");              /* no `=` seen yet: pat lives above page 0 */
    asm("tay");
    asm("m_loop:");
    asm("lda (ptr2),y");
    asm("beq m_end");
    asm("lda (ptr1),y");
    asm("cmp #'='");
    asm("bne m_lit");
    asm("inc ptr1");                /* star = ++p; back = s */
    asm("bne m_star");
    asm("inc ptr1+1");
    asm("m_star:");
    asm("lda ptr1");
    asm("sta ptr3");
    asm("lda ptr1+1");
    asm("sta ptr3+1");
    asm("lda ptr2");
    asm("sta ptr4");
    asm("lda ptr2+1");
    asm("sta ptr4+1");
    asm("jmp m_loop");
    asm("m_lit:");
    asm("cmp #'?'");
    asm("beq m_adv");
    asm("cmp (ptr2),y");
    asm("beq m_adv");
    asm("lda ptr3+1");              /* a literal failed: back to the last `=`, one name character further */
    asm("beq m_no");
    asm("lda ptr3");
    asm("sta ptr1");
    asm("lda ptr3+1");
    asm("sta ptr1+1");
    asm("inc ptr4");
    asm("bne m_back");
    asm("inc ptr4+1");
    asm("m_back:");
    asm("lda ptr4");
    asm("sta ptr2");
    asm("lda ptr4+1");
    asm("sta ptr2+1");
    asm("jmp m_loop");
    asm("m_adv:");
    asm("inc ptr1");
    asm("bne m_adv2");
    asm("inc ptr1+1");
    asm("m_adv2:");
    asm("inc ptr2");
    asm("bne m_loop");
    asm("inc ptr2+1");
    asm("jmp m_loop");
    asm("m_end:");                  /* the name is done: only `=` may remain before the end or the comma */
    asm("lda (ptr1),y");
    asm("beq m_yes");
    asm("cmp #','");
    asm("beq m_yes");
    asm("cmp #'='");
    asm("bne m_no");
    asm("inc ptr1");
    asm("bne m_end");
    asm("inc ptr1+1");
    asm("jmp m_end");
    asm("m_yes:");
    asm("lda #1");
    asm("rts");
    asm("m_no:");
    asm("lda #0");
}

/* The filters after the pattern's comma, to flags, ftype and lim; A = 0
 * on an unknown one. ptr2 indexes pat. A size is built in the three
 * bytes below lim[tmp4] as lim * 10 + digit: nine additions of a copy
 * (tmp2, tmp3, ptr1), then the digit (tmp1). */
static void parse_filters(void)
{
    asm("lda #0");
    asm("sta %v", flags);
    asm("sta ptr2");
    asm("p_skip:");                 /* to the comma, if any */
    asm("ldy ptr2");
    asm("lda %v,y", pat);
    asm("beq p_loop");
    asm("inc ptr2");
    asm("cmp #','");
    asm("bne p_skip");
    asm("p_loop:");
    asm("ldy ptr2");
    asm("inc ptr2");
    asm("lda %v,y", pat);
    asm("bne p_more");
    asm("lda #1");                  /* the end: every filter was known */
    asm("rts");
    asm("p_more:");
    asm("cmp #','");
    asm("beq p_loop");
    asm("cmp #'D'");
    asm("bne p_type");
    asm("lda #8");
    asm("ora %v", flags);
    asm("sta %v", flags);
    asm("jmp p_loop");
    asm("p_type:");
    asm("cmp #'T'");
    asm("bne p_size");
    asm("lda #1");
    asm("ora %v", flags);
    asm("sta %v", flags);
    asm("lda #0");
    asm("sta %v", ftype);
    asm("p_hex:");
    asm("ldy ptr2");
    asm("lda %v,y", pat);
    asm("sec");
    asm("sbc #'0'");
    asm("cmp #10");
    asm("bcc p_hexd");
    asm("sbc #'A'-'0'");
    asm("cmp #6");
    asm("bcs p_loop");              /* not a hex digit: the filter ends */
    asm("adc #10");
    asm("p_hexd:");
    asm("inc ptr2");
    asm("ldy #4");
    asm("p_shift:");
    asm("asl %v", ftype);
    asm("dey");
    asm("bne p_shift");
    asm("ora %v", ftype);
    asm("sta %v", ftype);
    asm("jmp p_hex");
    asm("p_size:");
    asm("ldy #2");                  /* `>`: lim[0..2], bit 1; `<`: lim[3..5], bit 2 */
    asm("ldx #2");
    asm("cmp #'>'");
    asm("beq p_bound");
    asm("ldy #5");
    asm("ldx #4");
    asm("cmp #'<'");
    asm("beq p_bound");
    asm("lda #0");                  /* unknown */
    asm("rts");
    asm("p_bound:");
    asm("sty tmp4");
    asm("txa");
    asm("ora %v", flags);
    asm("sta %v", flags);
    asm("lda #0");
    asm("sta %v-2,y", lim);
    asm("sta %v-1,y", lim);
    asm("sta %v,y", lim);
    asm("p_dec:");
    asm("ldy ptr2");
    asm("lda %v,y", pat);
    asm("sec");
    asm("sbc #'0'");
    asm("cmp #10");
    asm("bcc p_digit");
    asm("jmp p_loop");              /* not a digit: the filter ends */
    asm("p_digit:");
    asm("inc ptr2");
    asm("sta tmp1");
    asm("ldx tmp4");
    asm("lda %v-2,x", lim);         /* the copy */
    asm("sta tmp2");
    asm("lda %v-1,x", lim);
    asm("sta tmp3");
    asm("lda %v,x", lim);
    asm("sta ptr1");
    asm("ldy #9");
    asm("p_mul:");
    asm("clc");
    asm("lda %v-2,x", lim);
    asm("adc tmp2");
    asm("sta %v-2,x", lim);
    asm("lda %v-1,x", lim);
    asm("adc tmp3");
    asm("sta %v-1,x", lim);
    asm("lda %v,x", lim);
    asm("adc ptr1");
    asm("sta %v,x", lim);
    asm("dey");
    asm("bne p_mul");
    asm("clc");                     /* + the digit */
    asm("lda %v-2,x", lim);
    asm("adc tmp1");
    asm("sta %v-2,x", lim);
    asm("bcc p_dec");
    asm("inc %v-1,x", lim);
    asm("bne p_dec");
    asm("inc %v,x", lim);
    asm("jmp p_dec");
}

/* The size of the entry at sreg against the bound whose high byte is
 * lim[tmp4]: A = 1 above, 2 below, 0 equal. */
static void cmp24(void)
{
    asm("lda sreg");
    asm("clc");
    asm("adc #23");
    asm("sta ptr1");
    asm("lda sreg+1");
    asm("adc #0");
    asm("sta ptr1+1");
    asm("ldx tmp4");
    asm("ldy #2");
    asm("c_loop:");
    asm("lda (ptr1),y");
    asm("cmp %v,x", lim);
    asm("bne c_diff");
    asm("dex");
    asm("dey");
    asm("bpl c_loop");
    asm("lda #0");
    asm("rts");
    asm("c_diff:");
    asm("lda #1");
    asm("bcs c_done");
    asm("lda #2");
    asm("c_done:");
}

/* The tag byte of the entry at hand in A, ptr1 on it, Y = 0. A function of
 * its own, not a label inside apply(): a `jsr` or a `jmp` in an asm() body
 * that names a label defined FURTHER DOWN in the same function is compiled
 * as a reference to an external symbol (autoimport), and the label, having
 * no reference the code generator can see, is then dropped -- the link
 * fails on "Unresolved external". Backward jumps and branches (forward or
 * backward) are understood; only the forward jsr/jmp is not. */
static void tagbyte(void)
{
    asm("lda %v", t);
    asm("sta ptr1");
    asm("lda %v+1", t);
    asm("sta ptr1+1");
    asm("ldy #0");
    asm("lda (ptr1),y");
}

/* The loop over the entries: sreg is the first entry, tmp2 their number,
 * t their tags, mode and the filters are set; no C runs meanwhile, so
 * the state lives on the zero page (tmp1 the tag bit, tmp3 the index).
 * Counts the matches and the files tagged (n) or untagged. */
static void apply(void)
{
    asm("lda #0");
    asm("sta %v", n);
    asm("sta %v", matched);
    asm("sta tmp3");
    asm("lda #1");
    asm("sta tmp1");
    asm("a_loop:");
    asm("lda tmp3");
    asm("cmp tmp2");
    asm("bcc a_go");
    asm("rts");
    asm("a_go:");
    asm("jsr %v", match);           /* A is 1 or 0, and set the flags */
    asm("beq a_miss");
    asm("lda sreg");
    asm("sta ptr2");
    asm("lda sreg+1");
    asm("sta ptr2+1");
    asm("lda %v", flags);           /* the four filters, shifted out one by one */
    asm("sta ptr3");                /* (match clobbers ptr3, cmp24 and tagbyte do not) */
    asm("lsr ptr3");                /* the type */
    asm("bcc a_gt");
    asm("ldy #17");
    asm("lda (ptr2),y");
    asm("cmp %v", ftype);
    asm("bne a_miss");
    asm("a_gt:");
    asm("lsr ptr3");                /* > */
    asm("bcc a_lt");
    asm("ldy #2");
    asm("sty tmp4");
    asm("jsr %v", cmp24);
    asm("cmp #1");
    asm("bne a_miss");
    asm("a_lt:");
    asm("lsr ptr3");                /* < */
    asm("bcc a_today");
    asm("ldy #5");
    asm("sty tmp4");
    asm("jsr %v", cmp24);
    asm("cmp #2");
    asm("bne a_miss");
    asm("a_today:");
    asm("lsr ptr3");                /* the date */
    asm("bcc a_hit");
    asm("ldy #27");
    asm("lda (ptr2),y");
    asm("cmp $BF90");
    asm("bne a_miss");
    asm("iny");
    asm("lda (ptr2),y");
    asm("cmp $BF91");
    asm("bne a_miss");
    asm("a_hit:");
    asm("inc %v", matched);
    asm("ldy #17");
    asm("lda (ptr2),y");
    asm("cmp #$0F");
    asm("beq a_miss");              /* a directory: matched, never tagged */
    asm("inc %v", n);
    asm("lda %v", mode);
    asm("cmp #'U'");
    asm("beq a_clear");
    asm("jsr %v", tagbyte);
    asm("ora tmp1");
    asm("bne a_store");             /* always: tmp1 is a single bit */
    asm("a_miss:");
    asm("lda %v", mode);
    asm("cmp #'X'");
    asm("bne a_next");
    asm("a_clear:");
    asm("jsr %v", tagbyte);
    asm("ora tmp1");
    asm("eor tmp1");
    asm("a_store:");
    asm("sta (ptr1),y");
    asm("a_next:");
    asm("asl tmp1");
    asm("bne a_same");
    asm("rol tmp1");                /* the carry: bit 0 again, next byte */
    asm("inc %v", t);
    asm("bne a_same");
    asm("inc %v+1", t);
    asm("a_same:");
    asm("lda sreg");
    asm("clc");
    asm("adc #29");
    asm("sta sreg");
    asm("bcc a_inc");
    asm("inc sreg+1");
    asm("a_inc:");
    asm("inc tmp3");
    asm("jmp a_loop");
}

/* The command itself: the panel, the pattern, the filters, the key, the
 * loop, the screen and the message. */
static void run(void)
{
    asm("lda %v", A);
    asm("sta ptr1");
    asm("lda %v+1", A);
    asm("sta ptr1+1");
    asm("ldy #4");                  /* active */
    asm("lda (ptr1),y");
    asm("sta ptr2");
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta ptr2+1");
    asm("ldy #2");                  /* panels */
    asm("lda (ptr1),y");
    asm("sta %v", pan);
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta %v+1", pan);
    asm("ldy #0");
    asm("lda (ptr2),y");
    asm("beq x_pan");
    asm("lda %v", pan);             /* the second panel: 98 bytes further */
    asm("clc");
    asm("adc #98");
    asm("sta %v", pan);
    asm("bcc x_pan");
    asm("inc %v+1", pan);
    asm("x_pan:");
    asm("lda %v", pan);
    asm("sta ptr1");
    asm("lda %v+1", pan);
    asm("sta ptr1+1");
    asm("lda (ptr1),y");            /* path[0]: 0 in the volume list */
    asm("bne x_dir");
    asm("lda #<%v", s_vol);
    asm("ldx #>%v", s_vol);
    asm("jmp %v", say);
    asm("x_dir:");
    asm("jsr %v", read_pattern);
    asm("bne x_filters");
    asm("x_clear:");
    asm("lda #<(%v+2)", s_un);   /* ca65: `<sym+2` is (<sym)+2 -- the parentheses are the point */
    asm("ldx #>(%v+2)", s_un);
    asm("jmp %v", say);
    asm("x_filters:");
    asm("jsr %v", parse_filters);
    asm("bne x_ask");
    asm("lda #<%v", s_bad);
    asm("ldx #>%v", s_bad);
    asm("jmp %v", say);
    asm("x_ask:");
    asm("lda #<%v", s_keys);
    asm("ldx #>%v", s_keys);
    asm("jsr %v", say);
    asm("x_key:");
    asm("jsr %v", getkey);
    asm("cmp #27");
    asm("beq x_clear");
    asm("cmp #'T'");
    asm("beq x_go");
    asm("cmp #'U'");
    asm("beq x_go");
    asm("cmp #'X'");
    asm("bne x_key");
    asm("x_go:");
    asm("sta %v", mode);
    asm("lda %v", pan);
    asm("sta ptr1");
    asm("lda %v+1", pan);
    asm("sta ptr1+1");
    asm("ldy #74");                 /* e, into sreg for apply */
    asm("lda (ptr1),y");
    asm("sta sreg");
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta sreg+1");
    asm("lda ptr1");                /* tags: within the panel, at 76 */
    asm("clc");
    asm("adc #76");
    asm("sta %v", t);
    asm("lda ptr1+1");
    asm("adc #0");
    asm("sta %v+1", t);
    asm("ldy #64");                 /* count, into tmp2 for apply */
    asm("lda (ptr1),y");
    asm("sta tmp2");
    asm("jsr %v", apply);
    asm("ldy #28");                 /* draw_all: the tags show */
    asm("jsr %v", call_api);
    asm("lda #<%v", pat);           /* sprintf(pat, s_fmt, n, "un" or "", matched): the pattern is spent */
    asm("ldx #>%v", pat);
    asm("jsr pushax");
    asm("lda #<%v", s_fmt);
    asm("ldx #>%v", s_fmt);
    asm("jsr pushax");
    asm("lda %v", n);
    asm("ldx #0");
    asm("jsr pushax");
    asm("lda #<%v", s_un);
    asm("ldx #>%v", s_un);
    asm("ldy %v", mode);
    asm("cpy #'U'");
    asm("beq x_un");
    asm("lda #<(%v+2)", s_un);   /* ca65: `<sym+2` is (<sym)+2 -- the parentheses are the point */
    asm("ldx #>(%v+2)", s_un);
    asm("x_un:");
    asm("jsr pushax");
    asm("lda %v", matched);
    asm("ldx #0");
    asm("jsr pushax");
    asm("ldy #60");                 /* sprintf: Y = 10 bytes of arguments, which it pops */
    asm("jsr %v", getfn);
    asm("ldy #10");
    asm("jsr %v", jump2);
    asm("lda #<%v", pat);
    asm("ldx #>%v", pat);
    asm("jmp %v", say);
}

void __fastcall__ plugin_entry(void)
{
    asm("sta %v", A);               /* api, in A/X */
    asm("stx %v+1", A);
    asm("jsr %v", run);
}

#pragma optimize (pop)
