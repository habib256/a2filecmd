/* move.c -- move a file or a whole directory WITHOUT copying it: the
 * directory entry is rewritten from one directory into another on the same
 * volume, and not one block of data is touched. A tree of 400 blocks moves
 * in the time it takes to write three blocks.
 *
 * From the ! menu, on the entry under the cursor of the active panel; it
 * goes into the directory the OTHER panel shows.
 *
 * Why not just RENAME. ProDOS 8's RENAME ($C2) is the obvious candidate and
 * it does not work: asked to rename /VOL/A/X to /VOL/B/X it answers $40,
 * invalid pathname syntax. Measured under ProDOS 8 2.4 in the emulator, not
 * assumed. So the entry has to be carried by hand, and that means knowing
 * exactly what points at what:
 *
 *   - an entry's header_pointer (+$25) holds the KEY block of the directory
 *     that contains it -- not the block the entry happens to sit in;
 *   - a subdirectory's own header holds, at +$23, the block that contains
 *     ITS entry (that one IS the block, not the key), at +$25 the entry's
 *     number in that block counting from ONE, and at +$26 the entry length;
 *   - each directory header counts its live entries at +$21.
 *
 * All three were read off a real volume before a line of this was written
 * (/IMG/EXTASIE of the reference disk: entry in block 22 slot 2, key block
 * 2869, header_pointer 22, parent_pointer 22, parent_entry 3).
 *
 * The order of the writes is the one thing that decides what a power cut
 * costs. The target entry is written FIRST and the source entry cleared
 * after: interrupted in between, the file is listed in two directories,
 * which VOLINFO reports as shared blocks and which loses nothing. The other
 * order would leave the blocks allocated and named by nobody -- the file
 * would be gone. Every block written is read back and compared before the
 * move is called done.
 *
 * Two volumes have no entry that can point from one to the other, so there
 * the move is what it has always been: the file is COPIED and the original
 * removed. The copy is read back and compared in full before anything is
 * deleted -- a move that loses the file because the copy came up short is
 * not a move. Only a file: a whole tree across volumes is what the core's V
 * command already walks and copies.
 *
 * What it refuses, and why:
 *
 *   - a directory into its own subtree: the moved branch would name itself
 *     and be lost to the root, exactly what copy_one refuses in the core;
 *   - a name already used in the target directory;
 *   - a FULL volume directory: a subdirectory with no free entry is grown
 *     by a block, but the volume directory's four are fixed and it has no
 *     entry of its own to rewrite;
 *   - anything in the program's own A2FILE directory, or that directory
 *     itself or one of its parents: moving A2FILE.CODE or a .PLG out from
 *     under a running A2FC breaks it, and so does renaming its path;
 *   - a disk that changed while the question was on screen: everything
 *     the move was decided on is read again and compared after the answer;
 *   - a directory that cannot be read, or whose block chain does not end:
 *     a failed read is never taken for a free name or a free entry.
 *
 * One entry per run, the one under the cursor. A big overlay's code covers
 * the panels' entry tables at $2000, so the tags -- which are indexes INTO
 * that table -- can no longer be turned into names. api->selected is the
 * one entry the core copies out for us.
 *
 * A big overlay: the graphics page is its own, the core sets the tags aside,
 * rereads both panels and redraws. The block being rewritten lives in
 * api->copy_buf; the readback needs a second 512 bytes of its own. */
#define UTIL_STUBS
#define UTIL_VOLUME
#define UTIL_WRITE
#define UTIL_API_END ram_format /* MOVE uses cfg_path, no media/AUX services */
#include "util.h"
#include <string.h>

void __fastcall__ plugin_entry(const struct A2fcApi* api);
#define MOVE_DESCRIPTION "Move without copying data"
struct Header {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r[3]; char desc[sizeof MOVE_DESCRIPTION];
};
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    MOVE_DESCRIPTION
};
#pragma rodata-name (pop)

#define ENTRY_LEN   39
#define PER_BLOCK   13
#define E_HDRPTR    0x25            /* in an entry: the key block of its directory */
#define H_COUNT     0x21            /* in a header: how many live entries */
#define H_PARENT    0x23            /* in a subdirectory header: the block of its entry */
#define H_PARENTNUM 0x25            /* ... the entry's number there, counting from one */
#define H_PARENTLEN 0x26            /* ... and the entry length */
#define H_BITMAP    0x23            /* in the VOLUME header: the first bitmap block */
#define H_TOTAL     0x25            /* ... and how many blocks the volume has */
#define E_BLOCKS    0x13            /* in an entry: blocks used */
#define E_EOF       0x15            /* ... and the length in bytes, three of them */
/* No directory is longer: its header counts 65,535 entries at most, 13 to a
 * block. With the volume's own size, the bound on any walk of a chain, so
 * a chain that loops back on itself ends in a refusal, not a hang. */
#define DIR_MAX     5042

/* BSS: nothing zeroes it; everything below is written before it is read. */
static unsigned char unit;              /* the ProDOS unit of the volume */
static unsigned int volume_blocks;      /* logical volume, not backing-device size */
static unsigned int srckey, dstkey;     /* the two directories, by key block */
static unsigned int dirmax;             /* the longest chain a walk follows */
/* Where the move reads and writes, as examine() found it. */
static struct Plan {
    unsigned int sblk, dblk, subkey, blocks;
    unsigned char sslot, dslot, isdir, room;
} plan;
/* Every block examine() reads goes into a Fletcher sum (two 16-bit halves):
 * one byte changed anywhere in them always changes it. */
static unsigned int sum1, sum2, asked1, asked2;
static unsigned int hit_blk;            /* where locate/free_slot found it */
static unsigned char hit_slot;
static const struct Entry* sel;         /* api->selected */
#ifdef PLUGIN_HOST
static unsigned char ent[ENTRY_LEN];
#else
#define ent ((unsigned char*)0x0E00) /* saved entry, beside scratch at $0C00 */
#endif
/* MOVE opens no files: cross-volume copying belongs to MOVECOPY. The
 * loader has closed its file before entry, so the second ProDOS I/O
 * buffer is available for names, confirmation text, the saved entry and
 * raw readback. scratch occupies $0C00-$0DFF; ent occupies $0E00-$0E26.
 * The first buffer ($0800) remains separate for the bitmap check. */
#ifdef PLUGIN_HOST
static unsigned char scratch[512];
#else
#define scratch ((unsigned char*)0x0C00)
#endif
/* Lookups finish before ent carries the moved entry or scratch is used for
 * write verification. Reuse those buffers for the two lookup names. */
#define seek ((char*)ent)
#define found ((char*)scratch)
static const char m_dirs[]  = "ProDOS directories in both panels.";
static const char m_same[]  = "Both panels: same directory.";
static const char m_btree[] = "\2";   /* a tree across volumes: the core walks it itself, marked or not */
static const char m_prog[]  = "Cannot move the program's A2FILE files.";
static const char m_pick[]  = "Select an entry.";
static const char m_locked[] = "Source is locked.";
static const char m_readonly[] = "Write protected.";
static const char m_self[]  = "Cannot move inside itself.";
static const char m_walk[]  = "The directories cannot be walked.";
static const char m_taken[] = "Other panel already has %s.";
static const char m_gone[]  = "%s is no longer here.";
static const char m_full[]  = "Root full: cannot grow.";
static const char m_grew[]  = "Move %s into %s? Its directory must grow a block.";
static const char m_nogrow[] = "Target directory could not be made longer.";
static const char m_changed[] = "Disk changed: nothing written.";
static const char m_ok[]    = "%s moved: %u block%s untouched, nothing copied.";
static const char m_ask[]   = "Move %s into %s without copying it?";

/* Raw device calls need not reject blocks outside the logical ProDOS
 * volume. Boot blocks are never directory/bitmap storage for MOVE. */
static unsigned char __fastcall__ block_valid(unsigned int b)
{
    return b >= 2 && b < volume_blocks;
}

/* One block into api->copy_buf, added to the sum. */
static unsigned char rd(unsigned int b)
{
    unsigned int i;
    if (!block_valid(b) || readblk(unit, b, buf)) return 0;
    for (i = 0; i < 512; ++i) { sum1 += buf[i]; sum2 += sum1; }
    return 1;
}

/* copy_buf back to block `b`, then read back and compare: a drive that
 * accepts the write and keeps its old contents must not pass for done. */
static unsigned char wr(unsigned int b)
{
    if (!block_valid(b)) return 0;
    /* Both commands use the same unit/block. Reuse their input parameter
     * block rather than two generic wrappers; this leaves room for bounds
     * checks without widening the overlay. */
    bio.n=3;bio.unit=unit;bio.buffer=buf;bio.block=b;
    if (RF(mli)(0x81,&bio)) return 0;
    bio.buffer=scratch;
    if (RF(mli)(0x80,&bio)) return 0;
    return !memcmp(buf, scratch, 512);
}

/* The name of entry `k` of the block in copy_buf, into `found`. */
static void name_of(unsigned char k)
{
    unsigned char* e = buf + 4 + (unsigned int)k * ENTRY_LEN;
    unsigned char n = e[0] & 15;
    RF(memcpy)(found, e + 1, n);
    found[n] = 0;
}

/* Walk the directory whose key block is `key` looking for `seek`. 1: found,
 * the block that holds it is left in copy_buf and hit_blk / hit_slot say
 * where it is; 0: not there; 2: a block could not be read or the chain does not end
 * -- never proof that the name is free. Finding a name does not finish
 * the scan: check the whole chain and reject ambiguous duplicate names.
 * Storage types 14 and 15 are headers, never entries. */
static unsigned char locate(unsigned int key)
{
    unsigned int b = key, n = 0, previous = 0;
    unsigned char k, kind, matched = 0;
    while (b) {
        if (++n > dirmax || stop() || !rd(b)) return 2;
        if (rd16(buf) != previous) return 2;
        /* A cached path and a parent entry do not validate this block.
         * Refuse an invalid key header before interpreting fixed-size
         * records, reserving a slot, or rewriting either directory. */
        if (n == 1 && (
            (buf[4] >> 4) != (key == 2 ? 15 : 14) ||
            buf[0x23] != ENTRY_LEN || buf[0x24] != PER_BLOCK)) return 2;
        for (k = 0; k < PER_BLOCK; ++k) {
            kind = buf[4 + (unsigned int)k * ENTRY_LEN] >> 4;
            if (!kind || kind >= 14) continue;
            name_of(k);
            if (!RF(strcmp)(found, seek)) {
                if (matched) return 2;
                matched = 1; hit_blk = b; hit_slot = k;
            }
        }
        previous = b;
        b = rd16(buf + 2);
    }
    if (matched && !rd(hit_blk)) return 2;
    return matched;
}

/* The first free entry of that directory, a deleted one included. Entry 0
 * of the first block is the header and is never free. 1: found, 0: the
 * directory is full, 2: unreadable or endless, as for locate. */
static unsigned char free_slot(unsigned int key)
{
    unsigned int b = key, n = 0, previous = 0;
    unsigned char k, first = 1;
    while (b) {
        if (++n > dirmax || !rd(b)) return 2;
        if (rd16(buf) != previous) return 2;
        for (k = first; k < PER_BLOCK; ++k)
            if (!(buf[4 + (unsigned int)k * ENTRY_LEN] >> 4)) { hit_blk = b; hit_slot = k; return 1; }
        first = 0;
        previous = b;
        b = rd16(buf + 2);
    }
    return 0;
}

/* No files are open in this raw branch. The first ProDOS file I/O buffer
 * is disposable after the overlay loader closes; never use auxiliary RAM. */
#ifdef PLUGIN_HOST
static unsigned char claims_bitmap[512];
#else
#define claims_bitmap ((unsigned char*)0x0800)
#endif
static unsigned int claims_total, claims_map, claims_end, claims_page, claims_budget;
static unsigned char claims_used(unsigned int b)
{
    unsigned int page;
    if (b < 2 || b >= claims_total || (b >= claims_map && b <= claims_end)) return 0;
    page = claims_map + (b >> 12);
    if (page != claims_page) {
        if (readblk(unit, page, claims_bitmap)) return 0;
        claims_page = page;
    }
    return !(claims_bitmap[(b & 4095) >> 3] & (0x80 >> (b & 7)));
}
static unsigned char claims_read(unsigned int b, unsigned char* to)
{
    a.progress_bar(sel->name, claims_total - claims_budget, claims_total);
    return !stop() && claims_budget-- && claims_used(b) && !readblk(unit, b, to);
}
#define CLAIMS_DIR buf
#define CLAIMS_IDX scratch
#define CLAIMS_WORD rd16
#define CLAIMS_BLOCKS claims_total
#define CLAIMS_TARGET dstkey
#include "prodos_claims.h"
static unsigned char allocation_sound(void)
{
    unsigned char i;
    if (!rd(2)) return 0;
    claims_total = rd16(buf + 4 + H_TOTAL);
    claims_map = rd16(buf + 4 + H_BITMAP);
    if (claims_total <= 6 || claims_map < 6 || claims_map >= claims_total ||
        ((claims_total - 1) >> 12) >= claims_total - claims_map) return 0;
    claims_end = claims_map + ((claims_total - 1) >> 12);
    claims_page = 0xFFFF;
    /* Boot and fixed root blocks are reserved even when unreferenced. */
    if (readblk(unit, claims_map, claims_bitmap)) return 0;
    for (i = 0; i < 6; ++i) if (claims_bitmap[0] & (0x80 >> i)) return 0;
    return claims_walk() && claims_met;
}

/* The first free block of the volume, marked used. The bitmap is one bit a
 * block, SET meaning free, 4,096 blocks to a bitmap block. Even a damaged
 * bitmap must never offer blocks 0 to 5 or its own pages. Taken
 * before anything points at it: a crash then leaks a block, which VOLINFO
 * reports and FIXIT will mend, where the other order would leave a directory
 * pointing at a block the volume thinks is free. */
static unsigned int alloc_block(void)
{
    unsigned int total, bitmap, end, base, i;

    if (!rd(2)) return 0;
    bitmap = rd16(buf + 4 + H_BITMAP);
    total = rd16(buf + 4 + H_TOTAL);
    /* Bound the whole map before reading any allocation bits. Subtract
     * before adding so a malformed pointer cannot wrap at 16 bits. */
    if (total <= 6 || bitmap < 6 || bitmap >= total ||
        ((total - 1) >> 12) >= total - bitmap) return 0;
    end = bitmap + ((total - 1) >> 12);
    for (base = 0; base < total; base += 4096) {
        if (!rd(bitmap + base / 4096)) return 0;
        for (i = 0; i < 4096 && base + i < total; ++i)
            if (buf[i >> 3] & (0x80 >> (i & 7))) {
                if (base + i < 6 || (base + i >= bitmap && base + i <= end)) return 0;
                buf[i >> 3] &= ~(0x80 >> (i & 7));
                if (!wr(bitmap + base / 4096)) return 0;
                return base + i;
            }
        /* Stop before the final increment: on cc65, $F000 + $1000 wraps
         * to zero and a full volume larger than 61,440 blocks loops forever. */
        if (total - base <= 4096) break;
    }
    return 0;
}

/* One more block on the end of a directory, and its own entry told that it
 * is a block longer. The volume directory cannot grow: its four blocks are
 * fixed and it has no entry of its own to rewrite -- the caller checks that
 * before asking.
 *
 * The block is allocated first, then filled, then linked, then accounted
 * for. A failure can leave an allocated block or outdated parent size;
 * the caller keeps the source if growth fails. Physical block writes are
 * not atomic: a power cut can also damage a link being rewritten. */
static unsigned char grow_dir(unsigned int key)
{
    unsigned int last, next, nb, pblk, blocks, n = 0;
    unsigned char* p;
    unsigned char pslot;

    if (!rd(key)) return 0;
    pblk = rd16(buf + 4 + H_PARENT);
    pslot = buf[4 + H_PARENTNUM];
    if (!pblk || !pslot || pslot > PER_BLOCK ||
        buf[4 + H_PARENTLEN] != ENTRY_LEN) return 0;
    --pslot;                                    /* it is counted from one */

    /* Validate the backlink before allocating or linking anything. A bad
     * parent slot must not rewrite another file, or escape the block buffer. */
    if (!rd(pblk)) return 0;
    p = buf + 4 + (unsigned int)pslot * ENTRY_LEN;
    if ((p[0] >> 4) != 13 || rd16(p + 0x11) != key) return 0;
    /* The parent entry determines the directory length exposed by ProDOS.
     * A stale or malformed size must not hide the newly linked block, wrap
     * its counters, or be used as the basis of an increment. */
    blocks = rd16(p + E_BLOCKS);
    if (!blocks || blocks >= DIR_MAX ||
        rd24(p + E_EOF) != ((unsigned long)blocks << 9)) return 0;
    if (!rd(key)) return 0;

    last = key;                                 /* the end of the chain */
    for (;;) {
        next = rd16(buf + 2);
        if (!next) break;
        if (++n >= dirmax) return 0;            /* a chain that loops */
        if (!rd(next) || rd16(buf) != last) return 0;
        last = next;
    }
    if (blocks != n + 1) return 0;

    if (!allocation_sound()) return 0;
    nb = alloc_block();
    if (!nb) return 0;

    RF(memset)(buf, 0, 512);                    /* every entry free, pointing back */
    wr16(buf, last);
    if (!wr(nb)) return 0;

    if (!rd(last)) return 0;                    /* and the chain points forward */
    wr16(buf + 2, nb);
    if (!wr(last)) return 0;

    if (!rd(pblk)) return 0;                    /* one more block, 512 more bytes */
    p = buf + 4 + (unsigned int)pslot * ENTRY_LEN;
    wr16(p + E_BLOCKS, rd16(p + E_BLOCKS) + 1);
    if ((p[E_EOF + 1] += 2) < 2) ++p[E_EOF + 2];    /* 512 more bytes: 2 in the middle one */
    return wr(pblk);
}

/* The key block of `path`, walked from the volume directory: the first
 * component is the volume, whose directory is block 2, and each one after
 * it is an entry to step into. 0 if any of it is missing. */
static unsigned int key_of(const char* path)
{
    unsigned int b = 2;
    unsigned char i, n;
    unsigned char* entry;
    if (path[0] != '/') return 0;
    for (i = 1; path[i] && path[i] != '/'; ++i) ;
    while (path[i]) {
        ++i;                                    /* past the slash */
        for (n = 0; path[i] && path[i] != '/'; ++i)
            if (n < NAME_LEN - 1) seek[n++] = path[i];
        seek[n] = 0;
        if (!n) break;                          /* a trailing slash */
        if (locate(b) != 1) return 0;
        entry = buf + 4 + (unsigned int)hit_slot * ENTRY_LEN;
        /* A cached panel path does not guarantee this entry is still a
         * directory. Never walk a file's data/index blocks as directory records. */
        if ((entry[0] >> 4) != 13) return 0;
        /* Only the final component is about to be written. Ancestors
         * traversed for lookup need not grant directory write access. */
        if ((!path[i] || !path[i + 1]) && !(entry[30] & 0x02)) return 0;
        b = rd16(entry + 0x11);                  /* the directory's key block */
        if (!b) return 0;
    }
    return b;
}

/* Add `delta` to the live-entry count in a directory's header. */
static unsigned char count_add(unsigned int key, unsigned int delta)
{
    if (!rd(key)) return 0;
    wr16(buf + 4 + H_COUNT, rd16(buf + 4 + H_COUNT) + delta);
    return wr(key);
}

/* `p` as a whole-component prefix of `q`: the index in q just past it
 * (q[i] is 0 or '/'), or 0 if it is not one. `p` is never empty. */
static unsigned char prefix(const char* p, const char* q)
{
    unsigned char i;
    for (i = 0; p[i] && p[i] == q[i]; ++i) ;
    return !p[i] && (!q[i] || q[i] == '/') ? i : 0;
}

/* Where is `path` from the directory the program keeps itself in?
 * api->cfg_path is "/VOL/A2FILE/A2FILE.CFG", so that directory is cfg_path
 * up to its last slash. 1: that directory; 2: one of its parents, the
 * volume root included; 0: neither. Moving A2FILE.CODE or a .PLG out from
 * under a running A2FC, or the directory that holds them, is not something
 * to find out about afterwards -- but the volume root is only a parent: its
 * other entries may come and go. */
static unsigned char program_dir(const char* path)
{
    unsigned char i = prefix(path, a.cfg_path);
    if (!i || !a.cfg_path[i]) return 0;
    for (++i; a.cfg_path[i] && a.cfg_path[i] != '/'; ++i) ;
    return a.cfg_path[i] ? 2 : 1;
}

/* Everything the move is decided on, read from the disk into `plan` and
 * `ent`, every block of it summed. 0 if the move may go ahead, otherwise
 * the refusal (written with the entry's name). */
static const char* examine(void)
{
    unsigned char k;

    sum1 = sum2 = 0;
    /* Only the fixed header is read before its logical bound is known.
     * Reset on every examination: overlay BSS and prior media are stale. */
    volume_blocks = 0xFFFF;
    if (!rd(2) || (buf[4] >> 4) != 15) return m_walk;
    /* WRITE_BLOCK bypasses ProDOS access checks. Both directory entries,
     * their counts and any growth bitmap belong to this volume. Check its
     * fresh header before asking, and again after the user answers. */
    if (!(buf[0x22] & 0x02)) return m_readonly;
    dirmax = volume_blocks = rd16(buf + 4 + H_TOTAL);
    if (dirmax > DIR_MAX) dirmax = DIR_MAX;

    srckey = key_of(pan->path);
    dstkey = key_of(other->path);
    if (!srckey || !dstkey || srckey == dstkey) return m_walk;
    /* Parent entries and key headers both carry directory access. Refuse
     * either protected copy, including inconsistent metadata, before any
     * raw entry/count update or destination bitmap allocation. */
    if (!rd(srckey)) return m_walk;
    if (!(buf[0x22] & 0x02)) return m_readonly;
    if (!rd(dstkey)) return m_walk;
    if (!(buf[0x22] & 0x02)) return m_readonly;

    RF(strcpy)(seek, sel->name);
    k = locate(dstkey);
    if (k == 1) return m_taken;
    if (k) return m_walk;
    k = locate(srckey);
    if (k == 2) return m_walk;
    if (!k) return m_gone;
    plan.sblk = hit_blk; plan.sslot = hit_slot;
    RF(memcpy)(ent, buf + 4 + (unsigned int)hit_slot * ENTRY_LEN, ENTRY_LEN);
    /* Raw directory writes bypass ProDOS DESTROY's access check. Use the
     * freshly read entry, not a possibly stale panel access flag. */
    if (!(ent[30] & 0x80)) return m_locked;
    k = ent[0] >> 4;
    plan.isdir = k == 13;
    plan.subkey = rd16(ent + 0x11);
    plan.blocks = rd16(ent + 0x13);
    if (!plan.isdir && (k < 1 || k > 3)) return m_walk;
    if (plan.isdir && (!rd(plan.subkey) || (buf[4] >> 4) != 14 ||
        rd16(buf + 4 + H_PARENT) != plan.sblk || buf[4 + H_PARENTNUM] != plan.sslot + 1 ||
        buf[4 + H_PARENTLEN] != ENTRY_LEN)) return m_walk;
    if (plan.isdir && (!(ent[30] & 0x02) || !(buf[0x22] & 0x02))) return m_readonly;
    /* A target with no free entry is grown by a block -- but only after the
     * user has said yes, and never the volume directory, whose four blocks
     * are fixed and which has no entry of its own to rewrite. */
    plan.room = free_slot(dstkey);
    plan.dblk = hit_blk; plan.dslot = hit_slot;
    if (plan.room == 2) return m_walk;
    if (!plan.room && dstkey == 2) return m_full;
    return 0;
}


void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char restored;
    unsigned int src_count, dst_count;
    const char* why;

    init(api);
    sel = a.selected;

    if (pan->fs || other->fs || !pan->path[0] || !other->path[0]) { note(m_dirs); return; }
    if (!RF(strcmp)(pan->path, other->path)) { note(m_same); return; }
    if (program_dir(pan->path) == 1 || program_dir(other->path) == 1) { note(m_prog); return; }
    if (!sel->name[0] || (sel->name[0] == '.' && sel->name[1] == '.')) { note(m_pick); return; }
    if (!a.full[0]) { note(m_pick); return; }
    if (program_dir(a.full)) { note(m_prog); return; }
    /* The other panel is the entry itself or under it: moving a directory
     * there would cut it off from the root, as copy_one refuses in the core. */
    if (prefix(a.full, other->path)) { note(m_self); return; }

    /* The same volume, compared by UNIT: two names can be the same drive.
     * Anything else has to be copied -- no entry points across a volume. */
    unit = unit_of(pan->path, 0);
    if (!unit || unit != unit_of(other->path, 0)) {
        if (sel->type == 0x0F) note(m_btree);
        else note("\3"); /* resident loads MOVECOPY before refreshing panels */
        return;
    }

    why = examine();
    if (!why && a.arg != 'B') {
        asked1 = sum1; asked2 = sum2;
        a.sprintf((char*)scratch, plan.room ? m_ask : m_grew, sel->name, other->path);
        if (!RF(confirm)((char*)scratch)) { note(""); return; }
        /* The same guard as DOSWRITE's: a floppy swapped, or a directory
         * changed, while the question was on screen must not receive block
         * numbers read from the disk that was there before. Everything is
         * read again; the writes below use this second reading, and only if
         * every block of it matches the first -- the volume header in
         * block 2 included, so another disk in the drive does not pass. A
         * sum, not a copy: MOVE has no room for one. It misses no single
         * changed byte; several changes cancelling out is left to a chance
         * of about one in 2^32. */
        why = examine();
        if (!why && (sum1 != asked1 || sum2 != asked2)) why = m_changed;
    }
    if (why) { a.sprintf(a.note, why, sel->name); return; }

    if (!rd(srckey)) { note(m_walk); return; }
    src_count = rd16(buf + 4 + H_COUNT);
    if (!rd(dstkey)) { note(m_walk); return; }
    dst_count = rd16(buf + 4 + H_COUNT);
    /* Raw writes must not wrap the live-entry counters. Check before even
     * growing the destination: that already writes its bitmap and links. */
    if (!src_count || dst_count == 0xFFFF) { note(m_walk); return; }

    if (!plan.room) {
        if (!grow_dir(dstkey) || free_slot(dstkey) != 1) { note(m_nogrow); return; }
        plan.dblk = hit_blk; plan.dslot = hit_slot;
    }

    /* 1. The entry into the target directory, its header pointer put right.
     *    This one first: interrupted after it, the file is in two places,
     *    which is recoverable; the other way round it would be in none. */
    wr16(ent + E_HDRPTR, dstkey);
    if (!rd(plan.dblk)) { goto fail; }
    RF(memcpy)(buf + 4 + (unsigned int)plan.dslot * ENTRY_LEN, ent, ENTRY_LEN);
    if (!wr(plan.dblk)) { goto fail; }

    /* 2. A moved subdirectory says where its own entry now lives. */
    if (plan.isdir) {
        if (!rd(plan.subkey)) { goto fail; }
        wr16(buf + 4 + H_PARENT, plan.dblk);
        buf[4 + H_PARENTNUM] = plan.dslot + 1;           /* counted from one */
        buf[4 + H_PARENTLEN] = ENTRY_LEN;
        if (!wr(plan.subkey)) { goto fail; }
    }

    /* 3. The old entry goes. Storage type 0 is what DESTROY leaves. */
    if (!rd(plan.sblk)) { goto fail; }
    buf[4 + (unsigned int)plan.sslot * ENTRY_LEN] = 0;
    if (!wr(plan.sblk)) { goto fail; }

    /* 4. Both counts. */
    if (!count_add(srckey, 0xFFFF)) { goto fail; }
    if (!count_add(dstkey, 1)) { goto fail; }

    RF(strcpy)(a.reselect, sel->name);
    a.sprintf(a.note, m_ok, sel->name, plan.blocks, plan.blocks == 1 ? "" : "s");
    return;
fail:
    /* A reported I/O failure may have committed its write. Restore the
     * source FIRST, then its backlink, then remove the duplicate entry.
     * Never destroy the destination if restoring the source failed. */
    restored = 0;
    wr16(ent + E_HDRPTR, srckey);
    if (rd(plan.sblk)) {
        RF(memcpy)(buf + 4 + (unsigned int)plan.sslot * ENTRY_LEN, ent, ENTRY_LEN);
        restored = wr(plan.sblk);
    }
    if (restored && plan.isdir) {
        restored = rd(plan.subkey);
        if (restored) {
            wr16(buf + 4 + H_PARENT, plan.sblk);
            buf[4 + H_PARENTNUM] = plan.sslot + 1;
            restored = wr(plan.subkey);
        }
    }
    if (restored && rd(plan.dblk)) {
        buf[4 + (unsigned int)plan.dslot * ENTRY_LEN] = 0;
        restored = wr(plan.dblk);
    } else restored = 0;
    if (restored && rd(srckey)) { wr16(buf + 4 + H_COUNT, src_count); restored = wr(srckey); }
    else restored = 0;
    if (restored && rd(dstkey)) { wr16(buf + 4 + H_COUNT, dst_count); restored = wr(dstkey); }
    else restored = 0;
    if (restored) note("Move failed; original restored.");
    else note("Move incomplete: delete neither entry; run VOLINFO.");
}
