/* Read-only ProDOS allocation audit. A 4096-block window bounds RAM use;
 * larger volumes are walked once per bitmap block. No recursion or writes.
 * Keep the walker independent of the UI for host corruption fixtures. */
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);
struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char reserved[3]; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    "ProDOS space, fragmentation and allocation audit"
};
#pragma rodata-name (pop)

struct Blk { unsigned char n, unit; unsigned char* buf; unsigned int block; };
struct Onl { unsigned char n, unit; unsigned char* buf; };
struct Frame {
    unsigned int block, prev, first, count, expected, blocks, expectedblocks;
    unsigned char slot;
};
static const struct A2fcApi* A;
static struct Blk io;
static struct Onl onl;
static unsigned char seen[512], idx[512], master[512], dirbuf[512];
static struct Frame stack[16];
static unsigned char entry[39], forks[12];
static unsigned char *buf, depth, failed, incomplete, cancelled;
static unsigned int total, bitmap, base, span, budget, cached;
static unsigned int files, fragmented, lost, shared, usedfree, bad, counts, freeblocks;
static unsigned int fileblocks, lastdata;
static unsigned char frag;
static char volume[17];

static unsigned int word(const unsigned char* p) { return p[0] | ((unsigned int)p[1] << 8); }
static void inc(unsigned int* n) { if (*n != 65535U) ++*n; }
static unsigned char stop(void)
{
#ifndef VOLINFO_HOST
    if (*(volatile unsigned char*)0xC000 == (0x80 | KEY_ESC)) {
        (void)*(volatile unsigned char*)0xC010;
        cancelled = 1;
    }
#endif
    return failed || cancelled;
}
static unsigned char readblock(unsigned int b, unsigned char* dst)
{
    if (stop()) return 0;
    if (b >= total) { if (!base) inc(&bad); incomplete = 1; return 0; }
    io.block = b; io.buf = dst;
    if (A->mli(0x80, &io)) { failed = 1; return 0; }
    return 1;
}
/* Return false for invalid/duplicate blocks in the current window. */
static unsigned char claim(unsigned int b)
{
    unsigned int n;
    unsigned char mask;
    if (b >= total) { if (!base) inc(&bad); incomplete = 1; return 0; }
    if (b < base || b - base >= span) return 1;
    n = b - base; mask = 0x80 >> (n & 7); n >>= 3;
    if (seen[n] & mask) { inc(&shared); return 0; }
    seen[n] |= mask;
    return 1;
}
static void data(unsigned int b)
{
    if (!b) { lastdata = 0; return; } /* sparse file */
    claim(b); inc(&fileblocks);
    if (lastdata && b != lastdata + 1) frag = 1;
    lastdata = b;
}
static void indexblock(unsigned int b)
{
    unsigned int i;
    if (!b) { lastdata = 0; return; }
    claim(b); inc(&fileblocks);
    if (!readblock(b, idx)) return;
    for (i = 0; i < 256; ++i) data(idx[i] | ((unsigned int)idx[i+256] << 8));
}
static void fork(unsigned char kind, unsigned int key)
{
    unsigned int i;
    lastdata = 0;
    if (!key) {
        if (kind > 3) { incomplete = 1; if (!base) inc(&bad); }
        return;
    }
    if (kind == 1) data(key);
    else if (kind == 2) indexblock(key);
    else if (kind == 3) {
        claim(key); inc(&fileblocks);
        if (!readblock(key, master)) return;
        for (i = 0; i < 256 && !stop(); ++i)
            indexblock(master[i] | ((unsigned int)master[i+256] << 8));
    } else { incomplete = 1; if (!base) inc(&bad); }
}
static void file(void)
{
    unsigned int key;
    unsigned char kind;
    kind = entry[0] >> 4; key = word(entry+17);
    if (!key && (entry[21] || entry[22] || entry[23])) {
        incomplete = 1; if (!base) inc(&bad);
    }
    fileblocks = 0; frag = 0;
    if (kind == 5) {
        claim(key); inc(&fileblocks);
        if (!readblock(key, buf)) return;
        A->memcpy(forks, buf, 6); A->memcpy(forks+6, buf+256, 6);
        fork(forks[0], word(forks+1));
        fork(forks[6], word(forks+7));
    } else fork(kind, key);
    if (!base) {
        inc(&files);
        if (frag) inc(&fragmented);
        if (fileblocks != word(entry+19)) inc(&counts);
    }
}
static unsigned char enter(unsigned int key)
{
    unsigned char i;
    if (!key || depth == 16) { incomplete = 1; if (!base) inc(&bad); return 0; }
    for (i = 0; i < depth; ++i)
        if (stack[i].first == key) { incomplete = 1; if (!base) inc(&bad); return 0; }
    stack[depth].block = stack[depth].first = key;
    stack[depth].prev = stack[depth].count = stack[depth].expected = 0;
    stack[depth].blocks = 0;
    stack[depth].expectedblocks = depth ? word(entry+19) : 0;
    stack[depth].slot = 0; ++depth;
    return 1;
}
static void walk(void)
{
    struct Frame* f;
    unsigned int next, key;
    unsigned char kind;
    depth = 0; budget = total; cached = 65535U; enter(2);
    while (depth && !stop()) {
        f = &stack[depth-1];
        if (cached != f->block) {
            if (!readblock(f->block, dirbuf)) { --depth; continue; }
            cached = f->block;
        }
        if (!f->slot) {
            if (!budget || !claim(f->block) || word(dirbuf) != f->prev) {
                incomplete = 1; if (!base) inc(&bad); --depth; continue;
            }
            --budget; ++f->blocks;
            if (f->block == f->first) {
                kind = dirbuf[4] >> 4;
                if (kind != (depth == 1 ? 15 : 14) || dirbuf[35] != 39 || dirbuf[36] != 13) {
                    incomplete = 1; if (!base) inc(&bad); --depth; continue;
                }
                f->expected = word(dirbuf+37); f->slot = 1;
            }
        }
        if (f->slot == 13) {
            next = word(dirbuf+2);
            if (!next) {
                if (!base && (f->count != f->expected ||
                    (depth > 1 && f->blocks != f->expectedblocks))) inc(&counts);
                --depth;
            } else { f->prev = f->block; f->block = next; f->slot = 0; }
            continue;
        }
        A->memcpy(entry, dirbuf+4+39*f->slot, 39); ++f->slot;
        kind = entry[0] >> 4;
        if (!kind) continue;
        inc(&f->count); key = word(entry+17);
        if (kind == 13) enter(key);
        else file();
    }
}
static void audit(void)
{
    unsigned int n;
    unsigned char mask;
    files = fragmented = lost = shared = usedfree = bad = counts = freeblocks = 0;
    failed = incomplete = cancelled = 0; base = 0;
    do {
        span = total - base; if (span > 4096) span = 4096;
        #ifndef VOLINFO_HOST
        A->gotoxy(0, 4); A->cprintf("Blocks %u..%u / %u    ", base, base+span-1, total);
#endif
        A->memset(seen, 0, 512);
        claim(0); claim(1);
        for (n = 0; n < ((total-1)/4096)+1; ++n) claim(bitmap+n);
        walk();
        if (stop() || !readblock(bitmap+(base/4096), buf)) return;
        for (n = 0; n < span; ++n) {
            mask = 0x80 >> (n & 7);
            if (buf[n>>3] & mask) {
                inc(&freeblocks);
                if (seen[n>>3] & mask) inc(&usedfree);
            } else if (!(seen[n>>3] & mask)) inc(&lost);
        }
        if (total - base <= 4096) break;
        base += 4096;
    } while (!stop());
}
/* Bitmap view: one character per block, 80 columns, 16 rows. */
static void map(void)
{
    unsigned int page, n, cache;
    unsigned char row, col, key;
    page = 0;
    do {
        A->clrscr(); A->cprintf("VOLINFO %s - ALLOCATION BITMAP\r\n", volume);
        A->cprintf("First block: %u   . Free   # Used\r\n", page);
        n = page; cache = 65535U;
        for (row = 0; row < 16 && n < total; ++row) {
            A->gotoxy(0, row+3);
            for (col = 0; col < 80 && n < total; ++col, ++n) {
                if (cache != n/4096) {
                    cache = n/4096;
                    if (!readblock(bitmap+cache, buf)) { A->message("Bitmap read failed."); return; }
                }
                A->cputc((buf[(n & 4095)>>3] & (0x80 >> (n & 7))) ? '.' : '#');
            }
        }
        A->gotoxy(0, 22); A->cputs("N Next  P Previous  ESC/RETURN Back");
        key = A->cgetc();
        if ((key == 'n' || key == 'N') && total-page > 1280) page += 1280;
        if ((key == 'p' || key == 'P') && page) page -= 1280;
    } while (key != KEY_ESC && key != KEY_RETURN);
}
void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    struct Panel* pan;
    const char* path;
    unsigned int i;
    unsigned char len, u;
    A = api; buf = A->copy_buf; pan = A->panels + *A->active;
    if (pan->fs) { A->message("Select a real ProDOS volume."); return; }
    path = pan->path[0] ? pan->path : A->selected->name;
    if (*path != '/') { A->message("Select a ProDOS volume."); return; }
    volume[0] = '/';
    for (len = 1; len < 16 && path[len] && path[len] != '/'; ++len) volume[len] = path[len];
    volume[len] = 0;
    onl.n = 2; onl.unit = 0; onl.buf = buf;
    if (A->mli(0xC5, &onl)) { A->message("VOLINFO: ON_LINE failed."); return; }
    u = 0;
    for (i = 0; i < 256; i += 16) {
        /* Equal volume names on two drives: honor the selected unit. */
        if (!pan->path[0] && (buf[i] & 0xF0) != (unsigned char)(A->selected->mdate << 4)) continue;
        if ((buf[i] & 15) != len-1) continue;
        for (u = 1; u < len && buf[i+u] == volume[u]; ++u) ;
        if (u == len) { u = buf[i] & 0xF0; break; }
        u = 0;
    }
    if (!u) { A->message("Volume not on line."); return; }
    io.n = 3; io.unit = u; total = 65535U; base = failed = cancelled = incomplete = 0;
    if (!readblock(2, buf)) { A->message("VOLINFO: cannot read volume header."); return; }
    total = word(buf+41); bitmap = word(buf+39);
    if ((buf[4] >> 4) != 15 || total < 3 || bitmap < 3 || bitmap >= total ||
        ((total-1)/4096)+1 > total-bitmap) {
        A->message("VOLINFO: invalid volume header."); return;
    }
    A->clrscr(); A->cprintf("VOLINFO %s - READ ONLY\r\n\r\nScanning allocation... ESC cancels.\r\n", volume);
    audit();
    do {
    A->clrscr(); A->cprintf("VOLINFO %s - READ ONLY\r\n\r\n", volume);
    if (failed || cancelled) A->cputs("Scan incomplete: read error or cancelled.\r\n");
    else {
        A->cprintf("Blocks: %u   Free: %u   Used: %u\r\nFiles: %u   Fragmented files: %u\r\n\r\n", total, freeblocks, total-freeblocks, files, fragmented);
        A->cprintf("Used but marked free: %u\r\nShared references: %u\r\nInvalid structure/pointers: %u\r\nCount mismatches: %u\r\n", usedfree, shared, bad, counts);
        if (incomplete) A->cputs("Incomplete traversal: lost-block count unavailable.\r\n");
        else A->cprintf("Lost blocks: %u\r\n", lost);
        A->cputs("\r\nFragmentation = nonconsecutive data blocks within a fork.\r\n");
    }
    A->cputs("\r\nM Bitmap  ESC/RETURN Back");
    u = A->cgetc();
    if ((u == 'm' || u == 'M') && !failed && !cancelled) map();
    } while (u != KEY_ESC && u != KEY_RETURN);
}
