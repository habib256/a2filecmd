/* MLI parameter blocks, packed by cc65: READ_BLOCK $80 {3, unit, buffer,
 * block}, ON_LINE $C5 {2, unit, buffer}. WRITE_BLOCK $81 is called from one
 * place only, verified() under #ifdef REPAIR: FIXIT never links it. */
struct Blk { unsigned char n, unit; unsigned char* buf; unsigned int block; };
struct Onl { unsigned char n, unit; unsigned char* buf; };
/* The frame of the directory walk, laid out as in volinfo.c. The entry that
 * named this directory -- what DIR_BLOCKS and DIR_EOF have to point at, and
 * where their expected values are read -- is NOT kept here: it is the
 * parent frame's own (block, slot - 1), and its directory block is reread
 * at pop time, which is the read the parent needs next anyway. */
struct Frame {
    unsigned int block, prev, first, count, expected, nblk;
    unsigned char slot;
};

#ifdef FIXIT_HOST
static const struct A2fcApi* A;
#else
/* The service table, copied once to this fixed even address: the direct
 * stubs of fixit.s jump through it without cc65 glue. */
#define A ((const struct A2fcApi*)0x3F9E)
#endif

#ifdef FIXIT_HOST
#define v_mli (A->mli)
#define v_cputs (A->cputs)
#define v_cprintf (A->cprintf)
#define v_sprintf (A->sprintf)
#define v_clrscr (A->clrscr)
#define v_cgetc (A->cgetc)
#define v_gotoxy (A->gotoxy)
#define v_memcpy (A->memcpy)
#define v_memset (A->memset)
#define v_strcpy (A->strcpy)
#define v_strcmp (A->strcmp)
#define v_confirm (A->confirm)
#ifdef REPAIR
#define v_prompt (A->prompt)
#endif
#else
unsigned char __fastcall__ v_mli(unsigned char, void*);
void __fastcall__ v_cputs(const char*);
int __cdecl__ v_cprintf(const char*, ...);
int __cdecl__ v_sprintf(char*, const char*, ...);
void __fastcall__ v_clrscr(void);
char __fastcall__ v_cgetc(void);
void __fastcall__ v_gotoxy(unsigned char, unsigned char);
void* __fastcall__ v_memcpy(void*, const void*, size_t);
void* __fastcall__ v_memset(void*, int, size_t);
char* __fastcall__ v_strcpy(char*, const char*);
int __fastcall__ v_strcmp(const char*, const char*);
unsigned char __fastcall__ v_confirm(const char*);
#ifdef REPAIR
unsigned char __fastcall__ v_prompt(const char*, const char*, unsigned char);
#endif
/* Assembly entry points have no C prologue; variadic calls retain Y.
 * The even fixed table avoids the NMOS indirect-JMP page-wrap bug. */
#endif

/* -- The catalogue of checks ---------------------------------------------
 * The first twenty-four ids, in this order and with this spelling, are
 * those of tools/prodos_check.py: the host oracle and this walker must
 * name a fault identically. The last six are FIXIT's own, in the order of
 * docs/FIXIT.md section 3. */
enum {
    CHK_HDR_STORAGE, CHK_HDR_ENTRY_LEN, CHK_HDR_PER_BLOCK, CHK_HDR_BITMAP,
    CHK_HDR_TOTAL, CHK_DIR_CHAIN, CHK_DIR_LOOP, CHK_DIR_HEADER,
    CHK_DIR_PARENT, CHK_DIR_DEPTH, CHK_ENT_STORAGE, CHK_ENT_NAME,
    CHK_ENT_HEADER_PTR, CHK_ENT_KEY, CHK_FILE_COUNT, CHK_DIR_BLOCKS,
    CHK_DIR_EOF, CHK_FILE_BLOCKS, CHK_FILE_EOF, CHK_IDX_RANGE,
    CHK_FORK_STORAGE, CHK_XLINK, CHK_BM_USED_FREE, CHK_BM_LOST,
    CHK_IO_ERROR, CHK_HDR_NAME, CHK_VOLDIR_SIZE, CHK_ENT_ACCESS,
    CHK_BM_RESERVED, CHK_BM_TAIL,
    CHK_COUNT
};
#ifndef REPAIR
/* The thirty names as one packed string: an array of 30 x 15 bytes cost
 * 450 bytes of RODATA, the walk below 318 plus its walker. */
static const char CHKNAMES[] =
    "HDR_STORAGE\0HDR_ENTRY_LEN\0HDR_PER_BLOCK\0HDR_BITMAP\0"
    "HDR_TOTAL\0DIR_CHAIN\0DIR_LOOP\0DIR_HEADER\0"
    "DIR_PARENT\0DIR_DEPTH\0ENT_STORAGE\0ENT_NAME\0"
    "ENT_HEADER_PTR\0ENT_KEY\0FILE_COUNT\0DIR_BLOCKS\0"
    "DIR_EOF\0FILE_BLOCKS\0FILE_EOF\0IDX_RANGE\0"
    "FORK_STORAGE\0XLINK\0BM_USED_FREE\0BM_LOST\0"
    "IO_ERROR\0HDR_NAME\0VOLDIR_SIZE\0ENT_ACCESS\0"
    "BM_RESERVED\0BM_TAIL";
#else
/* REPAIR names only what it can repair: eleven identifiers instead of
 * thirty, in the order of the plan screen and of the write phase. */
static const char CHKNAMES[] =
    "BM_USED_FREE\0BM_RESERVED\0BM_TAIL\0BM_LOST\0"
    "FILE_COUNT\0DIR_BLOCKS\0FILE_BLOCKS\0DIR_EOF\0"
    "DIR_PARENT\0ENT_HEADER_PTR\0DIR_CHAIN";
/* The check each of them counts, so the plan screen and the second pass
 * read the same counters the walker fills. */
static const unsigned char REPCHK[] = {
    CHK_BM_USED_FREE, CHK_BM_RESERVED, CHK_BM_TAIL, CHK_BM_LOST,
    CHK_FILE_COUNT, CHK_DIR_BLOCKS, CHK_FILE_BLOCKS, CHK_DIR_EOF,
    CHK_DIR_PARENT, CHK_ENT_HEADER_PTR, CHK_DIR_CHAIN
};
static const unsigned char BIT[] = { 1, 2, 4, 8 };
enum {
    REP_BM_USED_FREE, REP_BM_RESERVED, REP_BM_TAIL, REP_BM_LOST,
    REP_FILE_COUNT, REP_DIR_BLOCKS, REP_FILE_BLOCKS, REP_DIR_EOF,
    REP_DIR_PARENT, REP_ENT_HEADER_PTR, REP_DIR_CHAIN, REP_COUNT
};
/* 0 build the plan, 1 apply it, 2 the mandatory second pass. */
enum { MD_PLAN, MD_APPLY, MD_RESCAN };
#endif

/* The name of check `i`, walked from the packed string. */
static const char* chkname(unsigned char i)
{
    const char* p = CHKNAMES;
    while (i) {
        while (*p) ++p;
        ++p; --i;
    }
    return p;
}


#ifndef REPAIR
#define SAMPLES 16
/* A finding that names no entry. A slot is one of the 256 pointers of an
 * index block, so a byte has no value left over for "no slot at all"; the
 * sentinel lives instead in bit 7 of the sample's id, which counts to
 * thirty. A sample is four bytes, 64 in all, and sample[j] is a shift
 * rather than a multiplication by five (docs/FIXIT.md section 4). */
#define NO_SLOT 65535U
#endif
#define NO_SLOT_BIT 0x80
#define MAX_DEPTH 16                /* ProDOS nesting limit, as in volinfo.c */
#define VOLDIR_BLOCKS 4             /* blocks 2, 3, 4 and 5, fixed by ProDOS */
#ifndef REPAIR
struct Sample { unsigned char id; unsigned int block; unsigned char slot; };
#endif

/* The volume header, inside block 2: the header entry starts at +$04. */
#define H_STORAGE  0x04
#define H_ENTRYLEN 0x23             /* +$04 + $1F */
#define H_PERBLOCK 0x24             /* +$04 + $20 */
#define H_FILES    0x25             /* +$04 + $21 */
#define H_BITMAP   0x27             /* +$04 + $23 */
#define H_TOTAL    0x29             /* +$04 + $25 */

static const char M_NOTVOL[]  = "Select a real ProDOS volume.";
static const char M_NOVOL[]   = "Volume not on line.";
static const char M_ONLINE[]  = "ON_LINE failed.";
static const char M_BADHDR[]  = "Invalid volume header: nothing checked.";
static const char M_NOREAD[]  = "Block 2 could not be read: nothing checked.";
static const char M_CLEAN[]   = "This volume is consistent: nothing to repair.";
#ifndef REPAIR
static const char M_FOUND[]   = "%u findings, nothing written: FIXIT only reads.";
static const char M_UNSURE[]  = "Scan incomplete: lost blocks unconfirmed, freeing refused.";
#endif
static const char M_CANCEL[]  = "Scan cancelled: no plan from an incomplete scan.";
static const char M_IOERR[]   = "Read error: this volume was not fully checked.";
/* The loss the core names for the pictures (aux_warning in a2fc.c). */
static const char M_AUXASK[]  = "ALL /RAM files will be LOST. Continue?";
#ifndef REPAIR
static const char M_QCLEAN[]  = "Directories consistent (quick check).";
static const char M_MODES[]   = "Q quick (directories)  F full  ESC back";
/* What the title adds: "" at offset 0, " - QUICK" at offset `quick`. */
static const char M_QUICK[]   = "\0 - QUICK";
#endif
#ifndef REPAIR
static const char M_MORE[]    = "Key: next / ESC: back";
static const char M_TITLE[]   = "FIXIT %s - READ ONLY%s\r\n\r\n";
#else
static const char M_TITLE[]   = "REPAIR %s\r\n\r\n";
#endif
static const char M_SCAN[]    = "Scanning... ESC cancels.\r\n";
#ifndef REPAIR
static const char M_OVER[]    = "more findings than the table holds\r\n";
/* The summary line of the findings screen. P and F belong to the WRITE
 * chantier: no key is offered here that does not exist. */
static const char M_KEYS[]    = "\r\n%u findings.  R rescan  ESC/RETURN back";
static const char M_L0[]      = "%s  %u\r\n";
static const char M_L1[]      = "%s  %u  block %u\r\n";
static const char M_L2[]      = "%s  %u  block %u slot %u\r\n";
#else
static const char M_BOOTVOL[] = "That volume holds the running program: repair it from another boot.";
static const char M_NOPLAN[]  = "Scan incomplete: no repair.";
static const char M_XLINK[]   = "Cross-linked blocks: copy both files to another volume before any repair.";
static const char M_PARTIAL[] = "Broken entries: lost blocks kept.";
/* The refusal M_DIRLATER stood here until increments 13 to 15: the seven
 * directory repairs are applied now, so there is nothing left to defer. */
static const char M_NOTHING[] = "Nothing written.";
static const char M_CHANGED[] = "Disk changed: nothing written.";
static const char M_ASK[]     = "Type FIX to confirm";
static const char M_WORD[]    = "FIX";
static const char M_WRITING[] = "Repairing...\r\n";
static const char M_PLANLN[]  = "Plan: %u corrections over %u blocks. Nothing written yet.\r\n";
static const char M_DONE[]    = "Applied %u of %u blocks; rescan clean: repaired.";
static const char M_LEFT[]    = "Applied %u of %u blocks; rescan still reports %u findings.";
static const char M_NOREST[]  = "Block %u not restored: recover this volume before using it.";
static const char M_LINE[]    = "%s  %u\r\n";
static const char M_RKEYS[]   = "\r\nF fix  ESC back";
#endif

/* BSS: nothing zeroes it, every field is written before it is read. */
static struct Blk io;
static struct Onl onl;
/* One counter per check, then two more cells the one memset of reset()
 * empties with them: `found`, and the byte of `quick` (below). */
static unsigned int counts[CHK_COUNT + 2];
#ifndef REPAIR
static struct Sample sample[SAMPLES];
static unsigned char nsample, overflow;
#endif
static unsigned char complete, failed, cancelled;
#define found counts[CHK_COUNT]     /* every finding, counters summed as they come */
/* The directory block and the slot of the entry being examined: what a
 * finding about that entry has to name. */
static unsigned int curblock;
static unsigned char curslot;
static unsigned char* buf;          /* api->copy_buf: see the two buffers below */
static unsigned int total, bitmap, pages, base, span;
static char volume[NAME_LEN];       /* "/TARGET" */
static char boot[NAME_LEN];         /* "/BOOTVOLUME", from cfg_path */
#ifdef REPAIR
/* One name of the ON_LINE table, built and thrown away before the first
 * block is read: blk is free at that moment and costs no BSS of its own.
 * FIXIT keeps a real buffer, its HDR_NAME check needs one during the walk. */
#define nm ((char*)blk)
#else
static char nm[NAME_LEN];           /* one name of the ON_LINE table */
#endif
static unsigned char unit, isboot;
/* The walker of increment 2: the claim bitmap, the block buffer, the
 * directory stack, the entry being read and the two mini-entries of an
 * extended file, eight bytes each (a type, a key, a length and an eof).
 *
 * THE CLAIM BITMAP, one bit per block the walk reaches. Up to 4 096 blocks
 * it is seen[] itself. Beyond, it lives in the auxiliary bank ($4000-$5FFF,
 * src/plugins/fixit_bits.inc), and the tree is walked ONCE
 * whatever the size of the volume, where the 4 096-block window of 0.8.8
 * walked it once per window -- sixteen times, 69 minutes, on 32 MB. `aux`
 * says which; `granted` that the user agreed to lose the /RAM files the
 * auxiliary bank holds, asked once per run of the overlay. seen[] is not
 * static: the assembly reads and writes it. REPAIR builds a corrected
 * bitmap page in it once the claims of that page have been read. */
unsigned char seen[512];
unsigned char aux;
static unsigned char granted;
/* A quick check (FIXIT only, chosen with the auxiliary bank): the tree of
 * directories and nothing else -- no index block, no key block of an
 * extended file, no bitmap page. REPAIR never offers it: a directory
 * correction written without the file claims could land in a block a
 * file holds as data, which is what refusing XLINK prevents. 1 for a quick
 * check, cleared by reset() with the counters. */
#ifndef REPAIR
#define quick (*(unsigned char*)&counts[CHK_COUNT + 1])
#endif
static unsigned char blk[512];
#ifdef FIXIT_HOST
static unsigned char auxbits[8192];
static unsigned char bit_op(unsigned int b, unsigned char set)
{
    unsigned char* p = (aux ? auxbits : seen) + (b >> 3);
    unsigned char m = 0x80 >> (b & 7), old = *p & m;
    if (set) *p |= m;
    return old;
}
#define bit_test(b) bit_op(b, 0)
#define bit_set(b) bit_op(b, 1)
static void bit_init(void) { v_memset(auxbits, 0, sizeof auxbits); }
#else
unsigned char __fastcall__ bit_test(unsigned int b);
unsigned char __fastcall__ bit_set(unsigned int b);
void bit_init(void);
#endif
static struct Frame stack[MAX_DEPTH];
/* The entry being examined, read straight inside the directory block: the
 * copy of 39 bytes it replaces cost both the bytes and the memcpy. It is
 * only ever read before the entry's own file is walked, which is the first
 * thing that overwrites the block. */
static unsigned char* entry;
static unsigned char forks[16];
static unsigned char depth, partial;
#ifndef REPAIR
static unsigned char row;
#endif
static unsigned int budget, cached, fileblocks;
/* The shape of the volume directory: it is blocks 2, 3, 4, 5 and nothing
 * else. Rather than the first five blocks, the chain keeps what the shape
 * can be judged from -- the first block found where another was expected,
 * the fifth block of a chain that is too long, the last block and the
 * length -- and the shape is judged once the chain has ended where it
 * should: a chain the walk could not follow to its end says nothing
 * about a shape. */
#ifndef REPAIR
static unsigned int rootbad, rootfifth, rootlen, rootlast;
static unsigned char rootdone;
#endif
#ifdef REPAIR
/* What a repair needs, instead of the names and the samples FIXIT keeps.
 * There is NO list of corrections: what the walk computed is what the apply
 * pass writes, and the apply pass walks again. counts[] carries how many of
 * each. The six counters a run starts from zero live in one array so that
 * one v_memset empties them: cc65 addresses zz[k] with a constant k exactly
 * as it addresses a scalar, and six separate stores cost far more. */
static unsigned int zz[6];
#define pgused  zz[0]               /* pages the plan rewrites, with and */
#define pgany   zz[1]               /* without the freeing of BM_LOST */
#define applied zz[2]               /* blocks written and read back */
#define dblocks zz[3]               /* blocks the directory writes cost */
#define corr    zz[4]               /* corrections the plan proposes */
#define blocks  zz[5]               /* and the writes they will cost */
static unsigned char mode, on, hurt;  /* 1 a write failed, 2 unrestored */
/* The few bytes a directory correction writes. Five is the longest one,
 * the +$13..$17 of a subdirectory entry (blocks used and eof, which are
 * contiguous). Putting them in is a SWAP: nv[] comes back holding what the
 * block had, so running the same swap again is the restore. */
static union { unsigned int w; unsigned char b[5]; } nu;
#define nv nu.b
/* The volume header entry as the plan read it: the guard of section 5
 * compares block 2 against these thirty-nine bytes before the first write.
 * It lives in the directory stack, which is empty from the end of a walk to
 * the start of the next one -- and the plan copies it, the guard reads it,
 * both between two walks. Thirty-nine bytes of BSS that do not exist. */
#define hdr ((unsigned char*)stack)
#define HDRLEN 39
static void repair_main(void);
#endif

/* The two 512-byte buffers. `blk` is FIXIT's own: cc65 indexes an array at
 * a known address with one instruction, where `api->copy_buf` is a pointer
 * whose indexing register it rebuilds after every call in between -- and
 * the directory block is what the walk reads most. It holds, in turn, the
 * volume header, a directory block, the master index block of a tree file
 * (which costs the directory block, already read out by then) and the page
 * of the bitmap. `cached` says which directory block is in it, and any
 * other read invalidates it. api->copy_buf keeps what is read once and
 * copied out, or walked with a pointer anyway: the ON_LINE table, the key
 * block of an extended file, one index block. */
#define dirbuf blk
#define master blk

/* The last words of a big overlay go through api->note, never the message
 * line: the core redraws over it. One helper, five call sites. */
static void note(const char* s) { v_strcpy(A->note, s); }

static unsigned int word(const unsigned char* p) { return p[0] | ((unsigned int)p[1] << 8); }
static void inc(unsigned int* n) { if (*n != 65535U) ++*n; }

#ifndef REPAIR
/* A ProDOS name, as tools/prodos_check.py spells it: one to fifteen
 * characters, a letter first, then letters, digits or '.'. `e` points at
 * the entry (or the header), whose length is the low nibble of its first
 * byte; more than fifteen that nibble cannot say. */
static unsigned char valid_name(const unsigned char* e)
{
    unsigned char i, n, c;
    n = e[0] & 15;
    if (!n) return 0;
    for (i = 1; i <= n; ++i) {
        c = e[i];
        if (c >= 'A' && c <= 'Z') continue;
        if (i > 1 && ((c >= '0' && c <= '9') || c == '.')) continue;
        return 0;
    }
    return 1;
}

/* Is this 24-bit eof past what its storage type can address? A seedling
 * holds 512 bytes, a sapling 128 KB; a tree reaches 32 MB, more than the
 * 16 MB a 24-bit eof can even spell, so a tree never overflows. `e` points
 * at the three eof bytes, low first. */
static unsigned char eof_over(unsigned char kind, const unsigned char* e)
{
    if (kind == 1) return e[2] != 0 || word(e) > 512;
    if (kind == 2) return e[2] > 2 || (e[2] == 2 && word(e) != 0);
    return 0;
}
#endif

/* Escape is read at the keyboard and acknowledged by the strobe, as in
 * volinfo.c; a read error stops the pass just the same. The strobe is
 * WRITTEN: cc65 drops a read whose value is thrown away, and the Escape
 * then stayed in the keyboard and closed the findings screen at once. */
static unsigned char stop(void)
{
#ifndef FIXIT_HOST
    if (*(volatile unsigned char*)0xC000 == (0x80 | KEY_ESC)) {
        *(volatile unsigned char*)0xC010 = 0;
        cancelled = 1; complete = 0;
    }
#endif
    return failed || cancelled;
}

/* One finding: the counter always, the {id, block, slot} sample while
 * there is room. Bit 7 of the id says the finding names no entry, so the
 * slot is a byte and a sample four. cc65 2.19 miscompiles an increment
 * inside an index, so nsample is stepped on its own line. */
#ifdef REPAIR
/* REPAIR names no block on a screen: a repair is decided per check. The
 * macros below drop the arguments the call sites still pass -- an unused
 * macro parameter is never even evaluated -- so the walker's text stays the
 * one FIXIT compiles. */
static void finding(unsigned char id)
{
    inc(&counts[id]); inc(&found);
}
#define dfinding(id, block, slot) finding(id)
#define vfinding(id) finding(id)
#define bfinding(id, b) finding(id)
#define nfinding(id, b) finding(id)
#define hfinding(id, b) finding(id)
#define efinding(id) finding(id)
#else
static void finding(unsigned char id, unsigned int block, unsigned char slot)
{
    inc(&counts[id & ~NO_SLOT_BIT]); inc(&found);
    if (nsample < SAMPLES) {
        sample[nsample].id = id;
        sample[nsample].block = block;
        sample[nsample].slot = slot;
        ++nsample;
    } else overflow = 1;
}

/* A finding about the directory tree. The tree is walked once, so it is
 * reported once: the name survives from the window walks of 0.8.8. */
#define dfinding finding

/* Five shorthands. Each argument of a call costs cc65 some fifteen bytes at
 * the call site, and these five shapes cover thirty of the thirty-four
 * findings: a fault of the volume header (block 2, slot 0), one that names
 * no entry, one about a directory header (slot 0), one about the entry the
 * walk is looking at, and the bitmap's own. A fault of the tree that names
 * no entry is written like a bitmap one. */
static void vfinding(unsigned char id) { finding(id, 2, 0); }
static void bfinding(unsigned char id, unsigned int b) { finding(id | NO_SLOT_BIT, b, 0); }
#define nfinding bfinding
static void hfinding(unsigned char id, unsigned int b) { finding(id, b, 0); }
static void efinding(unsigned char id) { finding(id, curblock, curslot); }
#endif

/* READ_BLOCK, the only MLI call that ever touches the volume's data. A
 * failure is IO_ERROR and leaves the pass incomplete. */
static unsigned char readblock(unsigned int b, unsigned char* dst)
{
    if (stop()) return 0;
#ifndef FIXIT_HOST
    /* A big volume is minutes of block reads: each turns the resident's
     * activity cell ($06F7, row 21) between / and \ (see spin.h). Here,
     * not in stop(): an even number of stop() calls between two reads
     * would leave the same glyph on the screen. */
    asm("lda #$AF");
    asm("cmp $06F7");
    asm("bne %g", spun);
    asm("lda #$DC");
spun:
    asm("sta $06F7");
#endif
    /* Only a read into blk can lose the cached directory block; a read
     * into api->copy_buf leaves it, which spares a reread per file. */
    if (dst == blk) cached = 65535U;
    io.block = b; io.buf = dst;
    if (v_mli(0x80, &io)) {
        bfinding(CHK_IO_ERROR, b);
        failed = 1; complete = 0;
        return 0;
    }
    return 1;
}

#ifdef REPAIR
/* -- the one write, and the sequence of section 5 around it ---------------
 *
 * THE BUFFERS. There are two 512-byte areas in this window and no third:
 * `blk`, which the walk reads every directory block into, and `buf`
 * (api->copy_buf). `seen` holds the claims of a volume of one bitmap page
 * and is live from the memset of audit() to the page comparison at the end
 * of it, so it can only serve where each byte is already dead -- the
 * corrected bitmap page, each byte written once its eight claims are read,
 * then written to the disk (recours 3 of section 4). The claims of a bigger
 * volume live in the auxiliary bank, and seen[] is free for the page.
 *
 * A directory correction has no such moment: it is written in the middle of
 * the walk. What spares it a third buffer is that a directory correction is
 * two to five bytes. The block stays in `blk` and the patch is SWAPPED into
 * it in place, nv[] coming back loaded with the bytes the block had; blk is
 * then written and the readback goes into `buf`, which holds nothing the
 * walk needs at that point. blk is therefore both what was written and,
 * the same swap done again, the original -- so the restore of section 5 is
 * a write of blk in either case, and the comparison is still the whole 512
 * bytes. The bitmap page follows the same rule, built in `seen` rather than
 * in `buf`: the readback is ALWAYS buf, and verified() has no choice to
 * make. */
static unsigned char verified(unsigned int b, unsigned char* w)
{
    unsigned int i;
    io.block = b; io.buf = w;
    if (v_mli(0x81, &io)) return 0;
    io.block = b; io.buf = buf;
    if (v_mli(0x80, &io)) return 0;
    for (i = 0; i < 512; ++i) if (buf[i] != w[i]) return 0;
    return 1;
}

/* The write failed, the read back failed or the bytes differ: `w` holds the
 * original again, so put it on the disk and prove it. An error may still
 * have reached the medium, so this is tried in every case, as in bootblk.c
 * and the fail: of move.c. If even this fails the block is named and nothing
 * else is attempted -- `failed` stops the walk where it stands. */
static unsigned char restored(unsigned int b, unsigned char* w)
{
    hurt = 1;
    if (verified(b, w)) return 0;
    v_sprintf(A->note, M_NOREST, b);
    hurt = 2; failed = 1;               /* stop() is true: nothing more */
    return 0;
}

/* ONE directory correction, written where the walk computed its value: `n`
 * bytes of nv[] at `p`, a place inside blk, in block b. All seven of them
 * come through here -- the plan pass only counts the block the write will
 * cost, the second pass does nothing. `p` is an address inside blk and
 * stays valid across the reread: blk does not move. */
static void fix(unsigned int b, unsigned char* p, unsigned char n)
{
    unsigned char i, c;

    if (mode != MD_APPLY) { if (!mode) inc(&dblocks); return; }
    /* Escape, a read error, or a block that could not be put back: the
     * walk stops after the correction in hand, never inside one, and a
     * second correction on a block already in blk must not slip past. */
    if (stop()) return;
    if (cached != b) {                  /* walking a file may have taken blk */
        if (!readblock(b, dirbuf)) return;
        cached = b;
    }
    for (i = 0; i < n; ++i) { c = p[i]; p[i] = nv[i]; nv[i] = c; }
    if (verified(b, blk)) { inc(&applied); return; }
    for (i = 0; i < n; ++i) { c = p[i]; p[i] = nv[i]; nv[i] = c; }
    restored(b, blk);
}
#endif

/* What a pass must not inherit from the one before it, and nothing more:
 * `total`, `bitmap` and `pages` are written by header() before anything
 * reads them, `base` and `span` by audit() before the bitmap pages. Ten
 * dead stores paid for the BM_LOST retraction of scan() (docs/FIXIT.md
 * section 4); tools/test_fixit.py fills the whole BSS with $AA before every
 * run to hold that claim. */
static void reset(void)
{
    v_memset(counts, 0, sizeof counts);     /* found and quick too */
#ifndef REPAIR
    nsample = 0; overflow = 0;
#endif
    complete = 1; failed = 0; cancelled = 0;
}

/* "/VOL": the first component of a ProDOS path. */
static void first_part(char* dst, const char* path)
{
    unsigned char k;
    for (k = 0; k < NAME_LEN - 1 && path[k] && (k == 0 || path[k] != '/'); ++k) dst[k] = path[k];
    dst[k] = 0;
}

/* The volume header of block 2, already read into blk. Returns 0 when a
 * refusal-grade fault makes any further check meaningless. */
static unsigned char header(void)
{
    unsigned char ok = 1;
#ifndef REPAIR
    unsigned char len;
#endif

    if ((blk[H_STORAGE] >> 4) != 15) { vfinding(CHK_HDR_STORAGE); ok = 0; }
#ifndef REPAIR
    if (!valid_name(blk + H_STORAGE)) vfinding(CHK_ENT_NAME);
    /* HDR_NAME, the one check that needs a device: what block 2 calls
     * itself against the name ON_LINE answered for this unit, which is the
     * name `volume` was matched against. The host oracle cannot emit it. */
    len = blk[H_STORAGE] & 15;
    nm[0] = '/';
    v_memcpy(nm + 1, blk + H_STORAGE + 1, len);
    nm[len + 1] = 0;
    if (v_strcmp(nm, volume)) vfinding(CHK_HDR_NAME);
#endif
    if (blk[H_ENTRYLEN] != 39) { vfinding(CHK_HDR_ENTRY_LEN); ok = 0; }
    if (blk[H_PERBLOCK] != 13) { vfinding(CHK_HDR_PER_BLOCK); ok = 0; }

    total = word(blk + H_TOTAL);
    bitmap = word(blk + H_BITMAP);
    /* Blocks 0 and 1 boot, 2 to 5 the volume directory: under six blocks
     * the volume cannot even hold its own root. */
    if (total < 6) { vfinding(CHK_HDR_TOTAL); ok = 0; }
    else {
        /* The last block must exist: a total larger than the medium is a
         * header fault, not a read error of the walk. */
        io.block = total - 1; io.buf = blk;
        if (v_mli(0x80, &io)) { vfinding(CHK_HDR_TOTAL); ok = 0; }
    }
    if (ok) {
        pages = ((total - 1) >> 12) + 1;
        if (bitmap < 3 || bitmap >= total || pages > total - bitmap) {
            vfinding(CHK_HDR_BITMAP);
            complete = 0;
            ok = 0;
        }
    }
    return ok;
}

/* -- the walk ------------------------------------------------------------ */

/* Blocks 0, 1, 2 to 5 and the bitmap pages belong to ProDOS whatever the
 * directory tree says: marked free they are BM_RESERVED, never
 * BM_USED_FREE, and never BM_LOST. */
static unsigned char reserved(unsigned int b)
{
    return b < 2 + VOLDIR_BLOCKS || (b >= bitmap && b - bitmap < pages);
}

/* Was b already reached? The walk uses it as the oracle uses its set of
 * visited directory blocks: a chain that leads back into what we have
 * already seen is a loop, not a longer chain. A block past the end of the
 * volume was never reached. */
static unsigned char claimed(unsigned int b)
{
    return b < total && bit_test(b);
}

/* Record that the walk reached block b, which is on the volume: every
 * caller has checked its range. Reached twice, it is cross-linked. */
static void claim(unsigned int b)
{
    if (bit_set(b)) bfinding(CHK_XLINK, b);
}

static void data(unsigned int b)
{
    if (!b) return;                                 /* a sparse hole */
    claim(b); inc(&fileblocks);
}

/* One index block, its 256 pointers followed; `deep` says it is a master
 * index block, whose pointers are themselves index blocks. cc65 emits some
 * 450 to 600 bytes for a copy of such a loop (docs/MEMORY-BUDGETS.md), so
 * the two levels share this one, each with its own buffer: the master must
 * survive while the index blocks below it are read. The recursion is bounded
 * at two levels and the locals go on the C stack -- the plugins are compiled
 * with -Cl, and a static local would make it wrong. b is in range already. */
#pragma static-locals (push, off)
static void indexwalk(unsigned int b, unsigned char deep)
{
    unsigned char* t;
    unsigned int i, p;
    claim(b); inc(&fileblocks);
    t = deep ? master : buf;
    if (!readblock(b, t)) return;
    for (i = 0; i < 256 && !stop(); ++i) {
        p = t[i] | ((unsigned int)t[i + 256] << 8);
        if (!p) continue;                           /* a sparse hole */
        if (p < 2 || p >= total) {
            dfinding(CHK_IDX_RANGE, b, i); partial = 1; continue;
        }
        if (deep) indexwalk(p, 0);
        else data(p);
    }
}
#pragma static-locals (pop)

/* Seedling, sapling or tree; the key is in range already. */
static void forkwalk(unsigned char kind, unsigned int key)
{
    if (kind == 1) data(key);
    else indexwalk(key, kind == 3);
}

/* One file entry, already copied into entry[] from (curblock, curslot). */
static void file(void)
{
    unsigned int key, used, fkey;
    unsigned char* m;
    unsigned char kind, i, fk;

    kind = entry[0] >> 4; key = word(entry + 17); used = word(entry + 19);
    partial = 0; fileblocks = 0;
    if (kind > 3 && kind != 5) {                    /* 0 never gets here */
        efinding(CHK_ENT_STORAGE);
        return;
    }
    /* The eof is judged before the key, as the oracle does: a file whose
     * key is out of range still declares a length. */
#ifndef REPAIR
    if (kind != 5 && eof_over(kind, entry + 21))
        efinding(CHK_FILE_EOF);
#endif
    if (key < 2 || key >= total) {
        efinding(CHK_ENT_KEY);
        return;
    }
#ifndef REPAIR
    if (quick) return;
#endif
    if (kind == 5) {
        /* The key block of an extended file: two mini-entries of 18 bytes,
         * at +$000 and +$100, each a storage type, a key, a block count and
         * an eof. The first eight bytes are all a check needs. */
        claim(key); inc(&fileblocks);
        if (!readblock(key, buf)) return;
        v_memcpy(forks, buf, 8); v_memcpy(forks + 8, buf + 256, 8);
        m = forks;
        for (i = 0; i < 2; ++i) {
            fk = *m; fkey = word(m + 1);
            if (fk < 1 || fk > 3) {
                dfinding(CHK_FORK_STORAGE, key, i); partial = 1;
            } else {
                /* Each fork carries its own eof at +$5 of its mini-entry:
                 * the $5 entry's own eof is never judged. */
#ifndef REPAIR
                if (eof_over(fk, m + 5)) dfinding(CHK_FILE_EOF, key, i);
#endif
                if (fkey < 2 || fkey >= total) {
                    dfinding(CHK_ENT_KEY, key, i); partial = 1;
                } else forkwalk(fk, fkey);
            }
            m += 8;
        }
    } else forkwalk(kind, key);
    /* A partial entry names its cause, never the arithmetic that follows. */
    if (!partial && fileblocks != used) {
        efinding(CHK_FILE_BLOCKS);
#ifdef REPAIR
        /* Walking the file may have needed blk (a tree's master index), so
         * the directory block is reread unless it is still the one in hand. */
        nu.w = fileblocks;
        fix(curblock, entry + 0x13, 2);
#endif
    }
}

/* Push one directory. The key is in range already. One refusal path for
 * the three ways a directory cannot be entered: cc65 would repeat the
 * whole body of each. */
static unsigned char enter(unsigned int key)
{
    struct Frame* f;
    unsigned char i, id;

    id = CHK_DIR_DEPTH;
    if (depth != MAX_DEPTH) {
        id = CHK_DIR_LOOP;
        for (i = 0; i < depth; ++i) if (stack[i].first == key) break;
        if (i == depth && !claimed(key)) {
            f = &stack[depth];
#ifdef REPAIR
            /* One memset where six stores stood: sixty bytes of REPAIR's
             * window. FIXIT keeps the stores -- its compiled bytes are the
             * oracle of this shared header (docs/FIXIT.md section 4). */
            v_memset(f, 0, sizeof *f);
            f->block = f->first = key;
#else
            f->block = f->first = key;
            f->prev = f->count = f->expected = f->nblk = 0;
            f->slot = 0;
#endif
            ++depth;
            return 1;
        }
    }
    nfinding(id, key); complete = 0;
    return 0;
}

/* The header of a subdirectory, in its key block: $E, 39, 13. A wrong
 * field is named and the directory is walked all the same, as the oracle
 * does: the entries below it are still worth counting. */
static void subheader(struct Frame* f)
{
    struct Frame* q = f - 1;            /* the frame of the parent directory */

#ifndef REPAIR
    if ((dirbuf[4] >> 4) != 14) hfinding(CHK_DIR_HEADER, f->first);
    if (!valid_name(dirbuf + 4)) hfinding(CHK_ENT_NAME, f->first);
    if (dirbuf[35] != 39) hfinding(CHK_DIR_HEADER, f->first);
    if (dirbuf[36] != 13) hfinding(CHK_DIR_HEADER, f->first);
#endif
    /* The three fields that name the entry this directory hangs from: its
     * parent's key block, its rank there plus one, and the entry length.
     * One DIR_PARENT at most, as the oracle does. The walk pushed this
     * frame right after reading that entry, so the parent frame still
     * holds its block and, one past it, its rank. */
    if (word(dirbuf + 0x27) != q->block || dirbuf[0x29] != q->slot
            || dirbuf[0x2A] != 39) {
        hfinding(CHK_DIR_PARENT, f->first);
#ifdef REPAIR
        /* The three fields go back together: the carrier block, the rank
         * plus one and the entry length, four bytes from +$27. */
        nu.w = q->block; nv[2] = q->slot; nv[3] = 39;
        fix(f->first, dirbuf + 0x27, 4);
#endif
    }
    f->expected = word(dirbuf + 37);
}

/* The entry that named the directory now being popped: the parent frame's
 * own (block, slot - 1), since the walk pushed the child right after
 * reading that entry. Its directory block is reread here -- the read the
 * parent frame needs next anyway, so it costs no extra READ_BLOCK -- and
 * its blocks-used and eof are judged against the chain just walked. The eof
 * of a directory is its block count times 512, compared byte by byte
 * because an entry's eof is 24 bits wide. */
static void subdir_entry(struct Frame* f)
{
    struct Frame* q = f - 1;
    unsigned char* e;
    unsigned int eb;
    unsigned char es;
#ifdef REPAIR
    unsigned char bad = 0;
#endif

    eb = q->block; es = q->slot - 1;
    if (!readblock(eb, dirbuf)) return;
    cached = eb;
    e = dirbuf + 4 + 39 * es;
#ifdef REPAIR
    /* Blocks used and eof are contiguous, +$13..$17, and both are read off
     * the same number: it is spelled once, into the correction, and the two
     * checks are then byte comparisons against it. One patch of five bytes
     * carries both corrections, and a field that was already right keeps its
     * own bytes. blocks x 512 is spelled with byte operations, where a
     * 24-bit shift of a 16-bit count would cost far more. */
    nu.w = f->nblk;
    nv[2] = 0; nv[3] = nv[0] << 1; nv[4] = (nv[0] >> 7) | (nv[1] << 1);
    if (f->nblk != word(e + 19)) {
        dfinding(CHK_DIR_BLOCKS, eb, es);
        bad = 1;
    }
    if (e[21] || e[22] != nv[3] || e[23] != nv[4]) {
        dfinding(CHK_DIR_EOF, eb, es);
        bad = 1;
    }
    if (bad) fix(eb, e + 0x13, 5);
#else
    if (f->nblk != word(e + 19)) dfinding(CHK_DIR_BLOCKS, eb, es);
    if (e[21] || e[22] != (unsigned char)(f->nblk << 1)
              || e[23] != (unsigned char)(f->nblk >> 7))
        dfinding(CHK_DIR_EOF, eb, es);
#endif
}

#ifndef REPAIR
/* One more block of the volume directory chain. */
static void rootchain(unsigned int b)
{
    if (rootlen < VOLDIR_BLOCKS) {
        if (!rootbad && b != 2 + rootlen) rootbad = b;
    } else if (rootlen == VOLDIR_BLOCKS) rootfifth = b;
    rootlast = b; ++rootlen;
}

/* The chain of the volume directory is blocks 2, 3, 4 and 5, in that order.
 * The finding names the first block that does not belong to that shape: the
 * block found where another was expected, or the fifth block of a chain that
 * is too long. One finding at most, and none from a chain that was cut. */
static void voldir_shape(void)
{
    if (!rootdone) return;
    if (rootbad) nfinding(CHK_VOLDIR_SIZE, rootbad);
    else if (rootlen < VOLDIR_BLOCKS) nfinding(CHK_VOLDIR_SIZE, rootlast);
    else if (rootlen > VOLDIR_BLOCKS) nfinding(CHK_VOLDIR_SIZE, rootfifth);
}
#endif

static void walk(void)
{
    struct Frame* f;
    unsigned int next, key;
    unsigned char kind;

    depth = 0; budget = total; cached = 65535U;
#ifndef REPAIR
    rootlen = 0; rootlast = 0; rootbad = 0; rootdone = 0;
#endif
    curblock = 2; curslot = 0;
    enter(2);
    while (depth && !stop()) {
        f = &stack[depth - 1];
        if (cached != f->block) {
            if (!readblock(f->block, dirbuf)) { --depth; continue; }
            cached = f->block;
        }
        if (!f->slot) {
            /* A block entered for the first time. A chain longer than the
             * volume itself can only be a loop: the claims name it first,
             * this is the bound that holds whatever they say. */
            if (!budget) {
                nfinding(CHK_DIR_LOOP, f->block); complete = 0;
                --depth; continue;
            }
            --budget; ++f->nblk;
            claim(f->block);
#ifndef REPAIR
            if (depth == 1) rootchain(f->block);
#endif
            /* A wrong back-pointer is reported and the walk goes on: the
             * forward chain is what holds the directory together. */
            if (word(dirbuf) != f->prev) {
                nfinding(CHK_DIR_CHAIN, f->block);
#ifdef REPAIR
                /* Only the back-pointer is ever rebuilt: the forward chain
                 * is what holds the directory together and is never
                 * invented. */
                nu.w = f->prev; fix(f->block, dirbuf, 2);
#endif
            }
            if (f->block == f->first) {
                if (depth > 1) subheader(f);
                else f->expected = word(dirbuf + H_FILES);
                f->slot = 1;                        /* slot 0 is the header */
            }
        }
        if (f->slot == 13) {
            next = word(dirbuf + 2);
            if (next) {
                kind = CHK_DIR_CHAIN;
                if (claimed(next)) kind = CHK_DIR_LOOP;
                else if (next >= 2 && next < total) {
                    f->prev = f->block; f->block = next; f->slot = 0;
                    continue;
                }
                nfinding(kind, f->block);
                complete = 0;
                --depth; continue;                  /* the chain is cut here */
            }
            /* The chain ended where it should: its counters are meaningful. */
#ifndef REPAIR
            if (depth == 1) rootdone = 1;
#endif
            if (f->count != f->expected) {
                hfinding(CHK_FILE_COUNT, f->first);
#ifdef REPAIR
                /* The count is known only here, at the end of the chain,
                 * and it belongs to the header block: that block is reread
                 * unless it is the one in hand (a one-block directory). */
                nu.w = f->count;
                fix(f->first, dirbuf + H_FILES, 2);
#endif
            }
            if (depth > 1) subdir_entry(f);
            --depth; continue;
        }
        entry = dirbuf + 4 + 39 * f->slot;
        curblock = f->block; curslot = f->slot;
        ++f->slot;
        kind = entry[0] >> 4;
        if (!kind) continue;                        /* a free slot */
        inc(&f->count);
#ifndef REPAIR
        if (!valid_name(entry)) efinding(CHK_ENT_NAME);
#endif
        /* +$25: the key block of the directory that holds this entry. */
        if (word(entry + 0x25) != f->first) {
            efinding(CHK_ENT_HEADER_PTR);
#ifdef REPAIR
            nu.w = f->first;
            fix(f->block, entry + 0x25, 2);
#endif
        }
#ifndef REPAIR
        if (entry[0x1E] & 0x1C) efinding(CHK_ENT_ACCESS);
#endif
        key = word(entry + 17);
        if (kind == 13) {
            if (key < 2 || key >= total) efinding(CHK_ENT_KEY);
            else enter(key);
        } else file();
    }
#ifndef REPAIR
    voldir_shape();
#endif
}

#ifdef REPAIR
/* May a lost block be given back to the bitmap? Section 5: only when the
 * pass is complete, no block is cross-linked and no entry was abandoned
 * half walked -- the blocks nobody claims may be the tail of the broken
 * entry, which RESCUE and UNDELETE can still read. Asked once when the
 * plan is built, and again at every page of the apply pass: the disk may
 * have changed, and a second walk that no longer agrees writes nothing. */
static unsigned char freeing_ok(void)
{
    return complete && !counts[CHK_XLINK] && !counts[CHK_ENT_KEY]
        && !counts[CHK_ENT_STORAGE] && !counts[CHK_IDX_RANGE]
        && !counts[CHK_FORK_STORAGE];
}

/* One bitmap page against the claims of the walk -- the same loop for the
 * three passes, because cc65 writes 450 to 600 bytes for a copy of one
 * (docs/MEMORY-BUDGETS.md). The plan pass reports a finding per wrong bit
 * and remembers which checks the page carries; the apply pass flips
 * exactly those bits and writes the page once. Every correction of
 * section 5 is one bit the wrong way round -- a block that is reached,
 * reserved or past the end of the volume must not be marked free, one
 * nobody claims must be -- so an exclusive or is the whole of it. The
 * corrected page is DERIVED here, never read from a list. */
static unsigned char bitmap_page(void)
{
    unsigned int n, i, b;
    unsigned char mask, resv, fb, sb, nb, id, hit, changed;

    /* A walk that did not finish knows nothing about what is free, and a
     * second walk that no longer allows freeing writes nothing either. */
    if (mode == MD_APPLY && (!complete || ((on & 8) && !freeing_ok()))) return 0;
    hit = 0; changed = 0; n = 0;
    for (i = 0; i < 512; ++i) {
        fb = blk[i]; nb = fb;
        for (mask = 0x80; mask; mask >>= 1) {
            id = 255;
            if (n >= span) {
                if (fb & mask) id = REP_BM_TAIL;
            } else {
                b = base + n;
                resv = reserved(b);
                sb = bit_test(b);
                if (fb & mask) {
                    if (resv) id = REP_BM_RESERVED;
                    else if (sb) id = REP_BM_USED_FREE;
                } else if (!resv && !sb && complete) id = REP_BM_LOST;
            }
            if (id != 255) {
                hit |= BIT[id];
                if (mode != MD_APPLY) bfinding(REPCHK[id], base + n);
                else if (on & BIT[id]) { nb ^= mask; changed = 1; }
            }
            ++n;
        }
        /* In the main bank this is the byte whose bits were just read. */
        if (mode == MD_APPLY) seen[i] = nb;
    }
    if (mode == MD_APPLY) {
        if (!changed) return 1;
        /* The page is built in buf, blk still holds it as the disk has it,
         * and seen is dead now that the page is derived: the readback goes
         * there and the restore is a write of blk. */
        b = bitmap + (base >> 12);
        if (verified(b, seen)) { inc(&applied); return 1; }
        return restored(b, blk);
    }
    if (hit & 7) inc(&pgused);
    if (hit) inc(&pgany);
    return 1;
}
#endif

/* The whole volume: the tree once, then the bitmap one page -- 4 096
 * blocks -- at a time. A quick check stops after the tree. */
static void audit(void)
{
    unsigned int n;
#ifndef REPAIR
    unsigned int i, b;
    unsigned char mask, resv, fb, sb;
#endif

    base = 0;
    v_memset(seen, 0, 512);
    if (aux) bit_init();
    claim(0); claim(1);
    for (n = 0; n < pages; ++n) claim(bitmap + n);
    walk();
#ifndef REPAIR
    if (quick) return;
#endif
    do {
        span = total - base; if (span > 4096) span = 4096;
        if (stop() || !readblock(bitmap + (base >> 12), blk)) return;
#ifdef REPAIR
        if (!bitmap_page()) return;
#else
        /* The whole page, not just its span: past the last block of the
         * volume the padding of the last bitmap page must be zero, which
         * is BM_TAIL. Every other page is full, so its tail is empty.
         * A byte of the bitmap and its eight bits, the claim of each block
         * asked of the bitmap wherever it lives. */
        n = 0; b = base;
        for (i = 0; i < 512; ++i) {
            fb = blk[i];
            for (mask = 0x80; mask; mask >>= 1) {
                if (n >= span) {
                    if (fb & mask) bfinding(CHK_BM_TAIL, b);
                } else {
                    resv = reserved(b);
                    sb = bit_test(b);
                    if (fb & mask) {                /* bit set: free */
                        if (resv) bfinding(CHK_BM_RESERVED, b);
                        else if (sb) bfinding(CHK_BM_USED_FREE, b);
                    } else if (!resv && !sb && complete) {
                        bfinding(CHK_BM_LOST, b);
                    }
                }
                ++n; ++b;
            }
        }
#endif
        if (total - base <= 4096) break;
        base += 4096;
    } while (!stop());
}

/* -- the findings screen -------------------------------------------------- */

#ifndef REPAIR
/* 18 lines a page, as docs/FIXIT.md section 6 asks. 0: Escape was hit. */
static unsigned char nextline(void)
{
    unsigned char k;
    ++row;
    if (row < 18) return 1;
    row = 0;
    v_cputs(M_MORE);
    k = v_cgetc();
    v_clrscr();
    return k != KEY_ESC;
}

#endif

/* The title line, rewritten by every pass: the volume it is working on. */
static void title(void)
{
    v_clrscr();
#ifdef REPAIR
    v_cprintf(M_TITLE, volume);
#else
    v_cprintf(M_TITLE, volume, M_QUICK + quick);
#endif
}

#ifndef REPAIR

/* One line per check with a non-zero counter: id, counter, first block, and
 * the slot when the finding names an entry. 0: Escape was hit while paging,
 * which leaves FIXIT. */
static unsigned char findings_screen(void)
{
    unsigned char i, j, got;
    unsigned int block, slot;

    title();
    row = 0;                            /* the title is above the count */
    for (i = 0; i < CHK_COUNT; ++i) {
        if (!counts[i]) continue;
        got = 0; block = 0; slot = NO_SLOT;
        for (j = 0; j < nsample; ++j)
            if ((sample[j].id & ~NO_SLOT_BIT) == i) {
                block = sample[j].block; got = 1;
                if (!(sample[j].id & NO_SLOT_BIT)) slot = sample[j].slot;
                break;
            }
        /* One call site, three formats: a variadic call carries the size
         * of what it pushed, and a format that reads fewer arguments
         * leaves the rest untouched. Three call sites cost far more. */
        v_cprintf(!got ? M_L0 : slot == NO_SLOT ? M_L1 : M_L2,
                  chkname(i), counts[i], block, slot);
        if (!nextline()) return 0;
    }
    if (overflow) { v_cputs(M_OVER); if (!nextline()) return 0; }
    v_cprintf(M_KEYS, found);
    return 1;
}
#endif

/* A volume the auxiliary bank has to serve. FIXIT asks at every pass how
 * deep to look, Q or F, so that R can follow a quick check with a full one;
 * the question on the /RAM files comes once per run of the overlay. 0:
 * Escape, or the /RAM files kept. */
static unsigned char bigvol(void)
{
#ifndef REPAIR
    unsigned char k;
#endif

    /* Slot 3, drive 2 is where ProDOS puts /RAM, and where a bigger RAM
     * disk living in the auxiliary bank replaces it: the claims would be
     * written over the very blocks being checked. */
    if (unit == 0xB0) return 0;
#ifndef REPAIR
    title();
    v_cputs(M_MODES);
    for (;;) {
        k = v_cgetc() & 0xDF;           /* upper case; Escape stays $1B */
        if (k == KEY_ESC) return 0;
        if (k == 'F') break;
        if (k == 'Q') { quick = 1; break; }
    }
#endif
    if (!granted) granted = v_confirm(M_AUXASK);
    return granted;
}

/* One pass over the volume: block 2, the header revalidated, the audit.
 * R comes back through here because the disk may have been swapped, so
 * nothing of the previous pass is believed -- reset() empties the counters
 * and the sample table. 2: block 2 unreadable, 0: header refused, 3: the
 * auxiliary bank refused, which a volume of more than 4 096 blocks -- more
 * than one bitmap page -- needs; the pass then counts as cancelled. */
static unsigned char scan(void)
{
    reset();
    if (!readblock(2, blk)) return 2;
    if (!header()) return 0;
    aux = pages - 1;
    if (aux && !bigvol()) { cancelled = 1; return 3; }
    title(); v_cputs(M_SCAN);
    audit();
    /* Completeness is a property of the whole pass, and a page of the
     * bitmap compared before an Escape has already named its BM_LOST: a cut
     * takes back every BM_LOST already recorded, not only the ones after
     * it. The sample slots they used are not given back (docs/FIXIT.md
     * section 4). */
    if (!complete) { found -= counts[CHK_BM_LOST]; counts[CHK_BM_LOST] = 0; }
    return 1;
}

/* The last words, on line 22 once the core has redrawn the panels. A local
 * pointer walked down the chain costs more than the six call sites: cc65
 * compiles -Cl locals into BSS and stores a pointer in two instructions. */
#ifndef REPAIR
/* What the last scan() answered. A static rather than an argument: cc65
 * then ends each branch below with a jump to note() instead of a call
 * followed by the pop of the argument. */
static unsigned char state;
static void verdict(void)
{
    if (state == 2) note(M_NOREAD);
    else if (!state) note(M_BADHDR);
    else if (cancelled) note(M_CANCEL);
    else if (failed) note(M_IOERR);
    else if (!complete) note(M_UNSURE);
    else if (!found) note(quick ? M_QCLEAN : M_CLEAN);
    else v_sprintf(A->note, M_FOUND, found);
}
#endif

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    struct Panel* pan;
    const char* path;
    unsigned char* e;
    unsigned char i, len, bootunit;

#ifdef FIXIT_HOST
    A = api;
#else
    /* Up to cfg_path: the fields after it would land on the resident at
     * $4000, and are read through `api`. */
    api->memcpy((void*)A, api, offsetof(struct A2fcApi, ram_format));
#endif
    buf = A->copy_buf;
    granted = 0;
    reset();

    /* A real ProDOS volume only: an image or a DOS 3.3 disk opened as a
     * directory has no block layout FIXIT could check. The three ways of
     * not being one share their refusal: an empty name says it. */
    pan = A->panels + *A->active;
    path = pan->path[0] ? pan->path : A->selected->name;
    volume[1] = 0;
    if (!pan->fs && *path == '/') first_part(volume, path);
    if (!volume[1]) { note(M_NOTVOL); return; }
    first_part(boot, A->cfg_path);

    /* One ON_LINE on unit 0 serves twice: the unit of the target when the
     * panel gave a path only, and the unit the program booted from. */
    onl.n = 2; onl.unit = 0; onl.buf = buf;
    if (v_mli(0xC5, &onl)) { note(M_ONLINE); return; }
    unit = 0; bootunit = 0;
    e = buf;
    for (i = 0; i < 16; ++i) {
        len = *e & 15;
        if (len) {                          /* else a drive without a volume */
            nm[0] = '/';
            v_memcpy(nm + 1, e + 1, len);
            nm[len + 1] = 0;
            if (!bootunit && !v_strcmp(nm, boot)) bootunit = *e & 0xF0;
            if (!unit && !v_strcmp(nm, volume)) {
                /* Equal names on two drives: honor the selected unit. */
                if (pan->path[0]
                        || (*e & 0xF0) == (unsigned char)(A->selected->mdate << 4))
                    unit = *e & 0xF0;
            }
        }
        e += 16;
    }
    if (!unit) { note(M_NOVOL); return; }
    /* Remembered by name AND by unit for the WRITE chantier, which refuses
     * to repair the volume the running program is read from. Reading it is
     * allowed: this increment only reads. */
    isboot = (bootunit && bootunit == unit) || !v_strcmp(volume, boot);

    io.n = 3; io.unit = unit;
#ifndef REPAIR
    /* The findings screen, then its keys: R scans again (the user may have
     * changed the disk, so the header is read and judged again), ESC or
     * RETURN leaves, and any other key only redraws the list. */
    state = scan();
    while (state != 3) {
        if (!findings_screen()) break;
        len = v_cgetc();
        if (len == KEY_ESC || len == KEY_RETURN) break;
        if (len == 'r' || len == 'R') state = scan();
    }
    verdict();
#else
    repair_main();
#endif
    /* The auxiliary bank was written: /RAM is rebuilt empty, as the core
     * does on return from a picture, or its next write returns anything. */
    if (granted) api->ram_format();
    /* A big overlay: the core rereads both panels, redraws and writes the
     * note. No read_panel, no draw_all, and nothing written to the disk. */
}
