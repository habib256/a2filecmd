/* Read-only verification: tagged files, selection, or raw volume.
 * Small overlay: panel entries and tag indices remain intact.
 * BSS is initialized on every invocation. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void plugin_entry(void);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void (*entry)(void);
    unsigned char r0, r1, r2; char desc[22];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, plugin_entry, 0, 0, 0,
    "Read files or volume"
};
#pragma rodata-name (pop)

#define TABLE 0x1FC2
#define s (*(const struct A2fcApi*)TABLE)
#define SLOT(f) (TABLE + offsetof(struct A2fcApi, f))
int __cdecl__ print(char*,const char*,...);

/* BSS: nothing zeroes it; every field below is written before it is read. */
static const struct Panel* pan;
static const struct Entry* e;      /* the file being read */
static unsigned char* buf;         /* s.copy_buf: the chunk, then the line */
static unsigned int n;             /* the bytes of the chunk */
static unsigned char TG[(MAX_ENTRIES + 7) / 8];   /* the tag bits, copied */
static unsigned char any;          /* verify tags instead of the cursor */
static unsigned char count, cursor, tags, bit, i, did;
static unsigned char errors, aborted;
static struct { unsigned char n, unit; void* buf; unsigned int block; } bp;
static unsigned long done;

void __fastcall__ t_message(const char*);
unsigned char __fastcall__ t_mli(unsigned char, void*);
void __fastcall__ t_fclose(FILE*);
FILE* __fastcall__ t_fopen(const char*,const char*);
unsigned char __fastcall__ t_build_full(char*,const struct Panel*,const struct Entry*);
unsigned int __fastcall__ t_fread(void*,unsigned int,unsigned int,FILE*);

static unsigned char stop(void) {
    if (*(volatile unsigned char*)0xC000 != 155) return 0;
    (void)*(volatile unsigned char*)0xC010; return aborted = 1;
}

/* Count the chunk on 24 bits, the width of a ProDOS EOF. */
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
    ;
}

/* Read the entry to EOF and reject short reads. */
static void verify_file(void)
{
    FILE* f;
    t_message((const char*)e);
    f = t_build_full(s.other_full, pan, e) ? t_fopen(s.other_full, "rb") : 0;
    asm("ldx #3");                    /* done = 0 */
init:
    asm("lda #0");
    asm("sta %v,x", done);
    asm("dex");
    asm("bpl %g", init);
    if (f) {
        for (;;) {
            n = t_fread(buf, 1, 512, f);
            fold();                   /* which counts the chunk in, too */

            if (stop()) break;
            if (n < 512) break;       /* a short chunk, or none: the end */
        }
        t_fclose(f);

    }
    /* Compare the 24-bit byte count with the directory EOF. A short read
     * caused by an I/O error must not be presented as a successful read. */
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
    if (!f && !aborted) ++errors;
    ++did;

}

/* Volume entries carry the driver unit and physical block count. */
static void verify_volume(void)
{
    unsigned int bad = 0;
    t_message((const char*)e);
    bp.n = 3; bp.unit = (unsigned char)(e->mdate << 4); bp.buf = buf;
    for (bp.block = 0; bp.block < e->blocks; ++bp.block) {
        if (stop()) break;
        if (t_mli(0x80, &bp)) ++bad;
    }
    print((char*)buf, "%s: %u blocks read%s, %u bad", (const char*)e,
              bp.block, aborted ? ", interrupted" : "", bad);
    t_message((char*)buf);
}

void plugin_entry(void)
{
    /* The first 62 API bytes; A/X still hold the incoming address. */
    asm("sta ptr1");
    asm("stx ptr1+1");
    asm("ldy #61");
copy:
    asm("lda (ptr1),y");
    asm("sta %w,y", TABLE);
    asm("dey");
    asm("bpl %g", copy);

    pan = s.panels;
    if (*s.active) ++pan;
    buf = s.copy_buf;
    did = errors = aborted = 0;

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
    asm("beq %g", ready);
refuse:
    asm("lda #0");
    asm("sta %v", count);
ready:


    /* The tagged files, or the one under the cursor; directories skipped. */
    i = 0;
    while (i < count && !aborted) {
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
            if (!pan->path[0]) { verify_volume(); return; }
            if (!any || e->type != 0x0F) verify_file();
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
    print((char*)buf, "VERIFY: %s%u read, %u errors%s", "", did, errors,
                        aborted ? ", cancelled" : "");
    t_message((const char*)buf);
}
