/* crc.c -- the CRC-32 of the selected file, or of each tagged file, to
 * check a transfer against the other end (zlib.crc32, the CRC of a .zip,
 * of a .gz: polynomial $EDB88320 reflected, initial $FFFFFFFF, final
 * complement).
 *
 * The file is read 512 bytes at a time into api->copy_buf. Eight
 * shift-and-XOR steps fold each byte into the reflected CRC, without a
 * lookup table, keeping both code and BSS inside the small window.
 * One file: its line on the message line, "NAME: CRC-32 $XXXXXXXX, N
 * bytes". Several tagged files: the same line for each on a cleared
 * screen, 20 per page. A key continues; ESC at a page boundary returns
 * to the panels without reading later files. The final page waits for a
 * key before restoring the panels. No empty page at exact multiples of 20.
 *
 * A small overlay is 1,280 bytes, and that window holds the file AND its
 * BSS -- above $2000 are the panels' entry tables, which a small overlay
 * must not touch. cc65 needs help on both counts, so five pieces are
 * plain 6502 in asm(), the same on both processors:
 *
 *  - the fold of a chunk into the CRC: bytewise 6502 shifts avoid the
 *    32-bit C runtime and preserve Y, which walks the input buffer;
 *  - the calls into the service table: cc65 calls a function pointer held
 *    in a variable by pushing it, evaluating the arguments, then fetching
 *    it back (some 30 bytes a call). The services taking arguments get a
 *    thunk: a C function whose body names the service in `off` and joins
 *    `go`, which pops the register argument its prologue pushed and jumps
 *    to the service, the C stack exactly as the service expects it. A
 *    call is then a plain jsr. The offset goes through a static because
 *    an `ldy #n` before a jmp is dropped as dead by the optimiser, and
 *    turning the optimiser off instead leaves the unreachable epilogue of
 *    every thunk in the file;
 *  - the table itself: only its offsets 2 to 73, `panels` to `clrscr`,
 *    are copied (struct Svc), 72 bytes of the window instead of 98, and a
 *    field of it costs three bytes where a field through a pointer costs
 *    a dozen;
 *  - what is wanted of the panel -- how many entries and where, the
 *    cursor, the tag bits, the file system -- read in one pass: through a
 *    pointer in C, cc65 reloads ptr1 before every one of those fields;
 *  - the walk of the entries, 29 bytes apart.
 *
 * `plugin_entry` is declared void(void) so that cc65 emits no prologue at
 * all and A/X still hold the table's address on the first instruction
 * (the header carries only that address; the core calls it fastcall).
 *
 * One loop serves the selection and the tags. Directories are skipped; a
 * panel that is not a ProDOS directory (the volume list, a disk image, a
 * DOS 3.3 disk) has nothing to read. CRC only reads: it writes nothing,
 * anywhere. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void plugin_entry(void);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void (*entry)(void);
    unsigned char r0, r1, r2; char desc[7];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, plugin_entry, 0, 0, 0,
    "CRC-32"
};
#pragma rodata-name (pop)

/* The service table from `panels` (offset 2) to `clrscr` (72): what this
 * overlay copies at entry. The fields it never names are padding, but
 * they are copied all the same -- the thunks reach their service by its
 * offset, and one straight copy is shorter than picking fields out. */
struct Svc {
    struct Panel* panels;                       /*  2 */
    unsigned char* active;                      /*  4 */
    void* p6;                                   /*  6 full */
    char* other_full;                           /*  8 */
    void* p10;                                  /* 10 input */
    unsigned char* copy_buf;                    /* 12 */
    void* p14;                                  /* 14 dir_entry */
    void* p16;                                  /* 16 message, by thunk */
    void* p18[2];                               /* 18 confirm, 20 prompt */
    void (*progress_bar)(const char*, unsigned long, unsigned long);   /* 22 */
    void* p24[2];                               /* 24 keys_bar, 26 bar_begin */
    void (*draw_all)(void);                     /* 28 */
    void* p30[2];                               /* 30 read_panel, 32 report_error */
    char (*wait_key)(void);                     /* 34 */
    void* p36[5];                               /* 36 build_full .. 44 mli */
    void* p46[7];                               /* 46 fopen .. 58 cprintf */
    int (*sprintf)(char*, const char*, ...);    /* 60 */
    void* p62[5];                               /* 62 cputs .. 70 cclearxy */
    void (*clrscr)(void);                       /* 72 */
};
#define SOFF(f) (offsetof(struct A2fcApi, f) - offsetof(struct A2fcApi, panels))

/* The line, with its end: cputs moves to the next row of the list; on
 * the message line the two characters only move the cursor. */
static const char FMT[] = "%s: CRC-32 $%08lX, %lu bytes\r\n";
static const char FMT_ERR[] = "%s: unreadable\r\n";
static const char NONE[] = "Select a file.";
static const char ANYKEY[] = "Any key";

/* BSS: nothing zeroes it; every field below is written before it is read. */
static struct Svc s;               /* the service table, copied */
static const struct Panel* pan;
static const struct Entry* e;      /* the file being read */
static unsigned char* buf;         /* s.copy_buf: the chunk, then the line */
static unsigned int n;             /* the bytes of the chunk */
static unsigned char TG[(MAX_ENTRIES + 7) / 8];   /* the tag bits, copied */
static unsigned char any;          /* files tagged: the list, no progress bar */
static unsigned char count, cursor, tags, bit, i, did, page;
static unsigned char off;          /* the thunks' service (see the head) */
static union { unsigned long l; unsigned char b[4]; } crc;
static unsigned long done;

/* The thunks. `go` is global so that cc65 keeps it. */
void go(void)
{
    asm("ldy %v", off);
    asm("lda %v,y", s);
    asm("sta ptr1");
    asm("lda %v+1,y", s);
    asm("sta ptr1+1");
    asm("jsr popax");
    asm("jmp (ptr1)");
}
#define THUNK(f) { off = SOFF(f); asm("jmp _go"); }
static void __fastcall__ t_message(const char* p) THUNK(message)
static void __fastcall__ t_cputs(const char* p) THUNK(cputs)
static void __fastcall__ t_fclose(FILE* f) THUNK(fclose)
static FILE* __fastcall__ t_fopen(const char* p, const char* m) THUNK(fopen)
static unsigned char __fastcall__ t_build_full(char* p, const struct Panel* q, const struct Entry* r) THUNK(build_full)
static unsigned int __fastcall__ t_fread(void* p, unsigned int sz, unsigned int m, FILE* f) THUNK(fread)

/* The n bytes at buf counted into `done` and folded into the CRC (none:
 * nothing): each xored into the CRC's low byte, then two steps. `done`
 * is counted on 24 bits, the width of a ProDOS file's length; its fourth
 * byte, zeroed with the rest, is there for the %lu of the line. ptr2
 * walks the chunk, ptr3 counts it down. */
static void fold(void)
{
    asm("lda %v", n);
    asm("clc");
    asm("adc %v", done);
    asm("sta %v", done);
    asm("lda %v+1", n);
    asm("adc %v+1", done);
    asm("sta %v+1", done);
    asm("bcc %g", counted);
    asm("inc %v+2", done);
counted:
    asm("lda %v", buf);
    asm("sta ptr2");
    asm("lda %v+1", buf);
    asm("sta ptr2+1");
    asm("lda %v", n);
    asm("sta ptr3");
    asm("ora %v+1", n);
    asm("beq %g", none);
    asm("lda %v+1", n);
    asm("sta ptr3+1");
    asm("ldy #0");
byte:
    asm("lda (ptr2),y");
    asm("eor %v", crc);
    asm("sta %v", crc);
    asm("ldx #8");
bitloop:
    asm("lsr %v+3", crc);
    asm("ror %v+2", crc);
    asm("ror %v+1", crc);
    asm("ror %v", crc);
    asm("bcc %g", nextbit);
    asm("lda %v", crc);
    asm("eor #$20");
    asm("sta %v", crc);
    asm("lda %v+1", crc);
    asm("eor #$83");
    asm("sta %v+1", crc);
    asm("lda %v+2", crc);
    asm("eor #$B8");
    asm("sta %v+2", crc);
    asm("lda %v+3", crc);
    asm("eor #$ED");
    asm("sta %v+3", crc);
nextbit:
    asm("dex");
    asm("bne %g", bitloop);
    asm("iny");
    asm("bne %g", low);
    asm("inc ptr2+1");
low:
    asm("lda ptr3");
    asm("bne %g", nohi);
    asm("dec ptr3+1");
nohi:
    asm("dec ptr3");
    asm("lda ptr3");
    asm("ora ptr3+1");
    asm("bne %g", byte);
none: ;
}

/* Reads the file `e` to its end, folding every byte into crc, and writes
 * its line in buf: the CRC, or that it cannot be read. The name of an
 * entry is its first field, so `e` is that name. */
static void crc_file(void)
{
    FILE* f;
    f = t_build_full(s.other_full, pan, e) ? t_fopen(s.other_full, "rb") : 0;
    asm("ldx #3");                    /* crc = $FFFFFFFF, done = 0 */
init:
    asm("lda #$FF");
    asm("sta %v,x", crc);
    asm("lda #0");
    asm("sta %v,x", done);
    asm("dex");
    asm("bpl %g", init);
    if (f) {
        for (;;) {
            n = t_fread(buf, 1, 512, f);
            fold();                   /* which counts the chunk in, too */

            if (n < 512) break;       /* a short chunk, or none: the end */
        }
        t_fclose(f);
        asm("ldx #3");                /* the final complement */
flip:
        asm("lda %v,x", crc);
        asm("eor #$FF");
        asm("sta %v,x", crc);
        asm("dex");
        asm("bpl %g", flip);
    }
    /* Compare the 24-bit byte count with the directory EOF. A short read
     * caused by an I/O error must not be presented as a valid checksum. */
    asm("lda %v", e);
    asm("sta ptr1");
    asm("lda %v+1", e);
    asm("sta ptr1+1");
    asm("ldy #%b", offsetof(struct Entry, size));
    asm("ldx #0");
check:
    asm("lda (ptr1),y");
    asm("cmp %v,x", done);
    asm("bne %g", failed);
    asm("iny");
    asm("inx");
    asm("cpx #3");
    asm("bne %g", check);
    asm("beq %g", checked);
failed:
    asm("lda #0");
    asm("sta %v", f);
    asm("sta %v+1", f);
checked:
    s.sprintf((char*)buf, f ? FMT : FMT_ERR, (const char*)e, crc.l, done);
}

void plugin_entry(void)
{
    /* The table, offsets 2 to 73: A/X still hold its address. */
    asm("sta ptr1");
    asm("stx ptr1+1");
    asm("ldy #%b", offsetof(struct A2fcApi, clrscr) + 1);
    asm("ldx #%b", sizeof s - 1);
copy:
    asm("lda (ptr1),y");
    asm("sta %v,x", s);
    asm("dey");
    asm("dex");
    asm("bpl %g", copy);

    pan = s.panels;
    if (*s.active) ++pan;
    buf = s.copy_buf;
    did = page = 0;

    /* Everything wanted of the panel, in one pass through it: how many
     * entries and where, where the cursor is, the tag bits (ored together
     * into `any`: a list is asked for), and whether it is a ProDOS
     * directory at all -- if not, it is left with no entry to read. */
    asm("lda %v", pan);
    asm("sta ptr1");
    asm("lda %v+1", pan);
    asm("sta ptr1+1");
    asm("ldy #%b", offsetof(struct Panel, count));
    asm("lda (ptr1),y");
    asm("sta %v", count);
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta %v", cursor);
    asm("ldy #%b", offsetof(struct Panel, e));
    asm("lda (ptr1),y");
    asm("sta %v", e);
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta %v+1", e);
    asm("lda #0");
    asm("sta %v", any);
    asm("ldy #%b", offsetof(struct Panel, tags) + sizeof TG - 1);
tag:
    asm("lda (ptr1),y");
    asm("sta %v-%b,y", TG, offsetof(struct Panel, tags));
    asm("ora %v", any);
    asm("sta %v", any);
    asm("dey");
    asm("cpy #%b", offsetof(struct Panel, tags));
    asm("bcs %g", tag);
    asm("ldy #%b", offsetof(struct Panel, fs));
    asm("lda (ptr1),y");              /* 0: real ProDOS */
    asm("bne %g", refuse);
    asm("ldy #0");
    asm("lda (ptr1),y");              /* path[0]: 0 in the volume list */
    asm("bne %g", ready);
refuse:
    asm("lda #0");
    asm("sta %v", count);
ready:
    if (any) s.clrscr();

    /* The tagged files, or the one under the cursor; directories skipped. */
    i = 0;
    while (i < count) {
        if (!(i & 7)) {               /* this entry's tag is bit 0 of `tags` */
            asm("lda %v", i);
            asm("lsr a");
            asm("lsr a");
            asm("lsr a");
            asm("tay");
            asm("lda %v,y", TG);
            asm("sta %v", tags);
        }
        asm("lsr %v", tags);
        asm("lda #0");
        asm("rol a");
        asm("sta %v", bit);
        if (any ? bit : i == cursor) {
            if (e->type != 0x0F) {
                if(any && page==20) {
                    t_message("Key Next/ESC");
                    if(s.wait_key()==KEY_ESC) { s.draw_all();return; }
                    s.clrscr();page=0;
                }
                crc_file();
                did = 1;
                if (any) { t_cputs((char*)buf);++page; }
            }
        }
        asm("inc %v", i);             /* the next entry, 29 bytes on */
        asm("lda #%b", sizeof(struct Entry));
        asm("clc");
        asm("adc %v", e);
        asm("sta %v", e);
        asm("bcc %g", walked);
        asm("inc %v+1", e);
walked: ;
    }
    if (any) {
        t_message(ANYKEY);
        s.wait_key();
        s.draw_all();
        return;
    }
    /* the line of the file (the last one, after the list), or why none */
    t_message(did ? (const char*)buf : NONE);
}
