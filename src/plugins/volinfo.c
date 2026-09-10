/* Read-only ProDOS allocation audit. A 4096-block window bounds RAM use;
 * larger volumes are walked once per bitmap block. The audit never writes;
 * only an explicit report export creates a file. No recursive C calls.
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
#ifdef VOLINFO_HOST
static const struct A2fcApi* A;
#else
#define A ((const struct A2fcApi*)0x3F9E)
#endif
#include <stddef.h>
#ifdef VOLINFO_HOST
#define v_message (A->message)
#define v_mli (A->mli)
#define v_cputs (A->cputs)
#define v_cputc (A->cputc)
#define v_cprintf (A->cprintf)
#define v_sprintf (A->sprintf)
#define v_clrscr (A->clrscr)
#define v_cgetc (A->cgetc)
#define v_gotoxy (A->gotoxy)
#define v_memcpy (A->memcpy)
#define v_memset (A->memset)
#define v_fopen (A->fopen)
#define v_fread (A->fread)
#define v_fwrite (A->fwrite)
#define v_fclose (A->fclose)
#define v_strcmp (A->strcmp)
#define v_strlen (A->strlen)
#define v_prompt (A->prompt)
#define v_report_error (A->report_error)
#else
void __fastcall__ v_message(const char*);
unsigned char __fastcall__ v_mli(unsigned char, void*);
void __fastcall__ v_cputs(const char*);
void __fastcall__ v_cputc(char);
int __cdecl__ v_cprintf(const char*, ...);
int __cdecl__ v_sprintf(char*, const char*, ...);
void __fastcall__ v_clrscr(void);
char __fastcall__ v_cgetc(void);
void __fastcall__ v_gotoxy(unsigned char,unsigned char);
void* __fastcall__ v_memcpy(void*, const void*, size_t);
void* __fastcall__ v_memset(void*,int,size_t);
FILE* __fastcall__ v_fopen(const char*,const char*);
size_t __fastcall__ v_fread(void*,size_t,size_t,FILE*);
size_t __fastcall__ v_fwrite(const void*,size_t,size_t,FILE*);
int __fastcall__ v_fclose(FILE*);
int __fastcall__ v_strcmp(const char*,const char*);
size_t __fastcall__ v_strlen(const char*);
unsigned char __fastcall__ v_prompt(const char*,const char*,unsigned char);
void __fastcall__ v_report_error(const char*);
/* Assembly entry points have no C prologue; variadic calls retain Y.
 * The even fixed table avoids the NMOS indirect-JMP page-wrap bug. */

#endif
static struct Blk io;
static struct Onl onl;
static unsigned char seen[512], idx[512];
/* A directory block is reloaded after a file uses this buffer. The master
 * index also fits here: reading its children uses the separate idx buffer. */
#define dirbuf buf
#define master buf
static unsigned char listing, row, role;
static FILE* reportfile;
static unsigned char reporterror;
static struct { unsigned char n; char* path; unsigned char access,type;
    unsigned int aux; unsigned char storage; unsigned int date,time; } create;
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
    if (dst == buf) cached = 65535U;
    io.block = b; io.buf = dst;
    if (v_mli(0x80, &io)) { failed = 1; return 0; }
    return 1;
}
/* Listing is streamed: no size limit and no extra block table in RAM. */
static void listed(unsigned int b)
{
    unsigned int n;
    if (stop()) return;
    n = v_sprintf(A->other_full, "%c %5u ($%04X)%s\r\n", role, b, b,
                   b >= total ? " INVALID" : "");
    if (reportfile) {
        if (v_fwrite(A->other_full, 1, n, reportfile) != n) { reporterror = 1; cancelled = 1; }
    } else {
        v_cputs(A->other_full);
        if (++row == 18) {
            v_message("Key: next blocks / ESC: back");
            if (v_cgetc() == KEY_ESC) cancelled = 1;
            v_clrscr(); row = 0;
        }
    }
}
/* Return false for invalid/duplicate blocks in the current window. */
static unsigned char claim(unsigned int b)
{
    unsigned int n;
    unsigned char mask;
    if (listing) { listed(b); return b < total; }
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
    role = 'D'; claim(b); inc(&fileblocks);
    if (lastdata && b != lastdata + 1) frag = 1;
    lastdata = b;
}
static void indexblock(unsigned int b)
{
    unsigned int i;
    if (!b) { lastdata = 0; return; }
    role = 'I'; claim(b); inc(&fileblocks);
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
        role = 'M'; claim(key); inc(&fileblocks);
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
        role = 'E'; claim(key); inc(&fileblocks);
        if (!readblock(key, buf)) return;
        v_memcpy(forks, buf, 6); v_memcpy(forks+6, buf+256, 6);
        fork(forks[0], word(forks+1));
        fork(forks[6], word(forks+7));
    } else fork(kind, key);
    if (!base && !listing) {
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
        v_memcpy(entry, dirbuf+4+39*f->slot, 39); ++f->slot;
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
    listing = 0;
    files = fragmented = lost = shared = usedfree = bad = counts = freeblocks = 0;
    failed = incomplete = cancelled = 0; base = 0;
    do {
        span = total - base; if (span > 4096) span = 4096;
        #ifndef VOLINFO_HOST
        v_gotoxy(0, 4); v_cprintf("Blocks %u..%u / %u    ", base, base+span-1, total);
#endif
        v_memset(seen, 0, 512);
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
        v_clrscr(); v_cprintf("VOLINFO %s - ALLOCATION BITMAP\r\n", volume);
        v_cprintf("First block: %u   . Free   # Used\r\n", page);
        n = page; cache = 65535U;
        for (row = 0; row < 16 && n < total; ++row) {
            v_gotoxy(0, row+3);
            for (col = 0; col < 80 && n < total; ++col, ++n) {
                if (cache != n/4096) {
                    cache = n/4096;
                    if (!readblock(bitmap+cache, buf)) { v_message("Bitmap read failed."); return; }
                }
                v_cputc((buf[(n & 4095)>>3] & (0x80 >> (n & 7))) ? '.' : '#');
            }
        }
        v_gotoxy(0, 22); v_cputs("N Next  P Previous  ESC/RETURN Back");
        key = v_cgetc();
        if ((key == 'n' || key == 'N') && total-page > 1280) page += 1280;
        if ((key == 'p' || key == 'P') && page) page -= 1280;
    } while (key != KEY_ESC && key != KEY_RETURN);
}
/* Find the selected entry by name; BIG overlays overwrite panel tables. */
static unsigned char selected_file(void)
{
    FILE* f;
    unsigned char j, len, found = 0;
    struct Panel* p = A->panels + *A->active;
    if (!p->path[0] || !A->selected->name[0] || A->selected->type == 15) return 0;
    f = v_fopen(p->path, "rb");
    if (!f) { failed = 1; return 0; }
    while (!found && !stop() && v_fread(buf, 1, 512, f) == 512) {
        for (j = 0; j < 13; ++j) {
            v_memcpy(entry, buf+4+39*j, 39);
            len = entry[0] & 15;
            if (!(entry[0] >> 4) || !len) continue;
            entry[1+len] = 0;
            if (!v_strcmp((char*)entry+1, A->selected->name)) { found = 1; break; }
        }
    }
    if (v_fclose(f) || (!found && !cancelled)) failed = 1;
    return found;
}
static void file_list(void)
{
    if (!selected_file()) { v_message("Select a file."); return; }
    listing = 1; row = 0;
    v_clrscr(); v_cputs("FILE BLOCKS: D Data  I Index  M Master  E Extended\r\n");
    file(); listing = 0;
    v_message(failed ? "Block read failed." : "End of block list. Key to return.");
    if (!cancelled) v_cgetc();
    cancelled = 0;
}
/* The report describes the scan above, before the new report is allocated. */
static void summary(void)
{
    v_sprintf((char*)buf,
        "VOLINFO %s\r\nBlocks: %u   Free: %u   Used: %u\r\n"
        "Files: %u   Fragmented files: %u\r\n"
        "Used but marked free: %u\r\nShared references: %u\r\n"
        "Invalid structure/pointers: %u\r\nCount mismatches: %u\r\n"
        "Lost blocks%s: %u\r\n%s\r\n", volume, total, freeblocks, total-freeblocks,
        files, fragmented, usedfree, shared, bad, counts,
        failed || cancelled || incomplete ? " (unconfirmed)" : "", lost,
        failed || cancelled ? "Scan incomplete: read error or cancelled." :
        incomplete ? "Incomplete traversal: lost-block count unavailable." : "Scan complete.");
}
static void export_report(void)
{
    struct Panel* p = A->panels + !*A->active;
    unsigned int n;
    if (p->fs || !p->path[0]) {
        v_message("Open destination in other panel."); v_cgetc(); return;
    }
    if (!v_prompt("Report name (other panel)", "VOLINFO.TXT", 0)) return;
    if (v_strlen(p->path)+v_strlen(A->input)+2 > PATH_LEN) return;
    v_sprintf(A->other_full, "%s/%s", p->path, A->input);
    n = v_strlen(A->other_full);
    A->full[0] = n; v_memcpy(A->full+1, A->other_full, n+1);
    create.n = 7; create.path = A->full; create.access = 0xC3; create.type = 4;
    create.aux = create.date = create.time = 0; create.storage = 1;
    if (v_mli(0xC0, &create)) { v_message("Cannot create report (name in use?)."); v_cgetc(); return; }
    *A->filetype = 4; *A->auxtype = 0;
    reportfile = v_fopen(A->other_full, "wb");
    if (!reportfile) { v_report_error("Report"); return; }
    summary(); n = v_strlen((char*)buf);
    reporterror = v_fwrite(buf, 1, n, reportfile) != n;
    if (!reporterror && !failed && !cancelled) {
      if (selected_file()) {
        n = v_sprintf(A->other_full, "FILE %s: D data I index M master E extended\r\n", A->selected->name);
        if (v_fwrite(A->other_full, 1, n, reportfile) != n) reporterror = 1;
        else {
            listing = 1; file(); listing = 0;
        }
      }
      if (failed || cancelled) reporterror = 1;
    }
    if (!reporterror && v_fwrite("END REPORT\r\n", 1, 12, reportfile) != 12) reporterror = 1;
    if (v_fclose(reportfile)) reporterror = 1;
    reportfile = 0;
    v_message(reporterror ? "Partial report (error/cancelled)." : "Report saved in other panel.");
    v_cgetc();
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    struct Panel* pan;
    const char* path;
    unsigned int i;
    unsigned char len, u;
    listing = 0; reportfile = 0;
#ifdef VOLINFO_HOST
    A = api;
#else
    api->memcpy((void*)A, api, sizeof *A);
#endif
    buf = A->copy_buf; pan = A->panels + *A->active;
    if (pan->fs) { v_message("Select a real ProDOS volume."); return; }
    path = pan->path[0] ? pan->path : A->selected->name;
    if (*path != '/') { v_message("Select a ProDOS volume."); return; }
    volume[0] = '/';
    for (len = 1; len < 16 && path[len] && path[len] != '/'; ++len) volume[len] = path[len];
    volume[len] = 0;
    onl.n = 2; onl.unit = 0; onl.buf = buf;
    if (v_mli(0xC5, &onl)) { v_message("VOLINFO: ON_LINE failed."); return; }
    u = 0;
    for (i = 0; i < 256; i += 16) {
        /* Equal volume names on two drives: honor the selected unit. */
        if (!pan->path[0] && (buf[i] & 0xF0) != (unsigned char)(A->selected->mdate << 4)) continue;
        if ((buf[i] & 15) != len-1) continue;
        for (u = 1; u < len && buf[i+u] == volume[u]; ++u) ;
        if (u == len) { u = buf[i] & 0xF0; break; }
        u = 0;
    }
    if (!u) { v_message("Volume not on line."); return; }
    io.n = 3; io.unit = u; total = 65535U; base = failed = cancelled = incomplete = 0;
    if (!readblock(2, buf)) { v_message("Header read failed."); return; }
    total = word(buf+41); bitmap = word(buf+39);
    if ((buf[4] >> 4) != 15 || total < 3 || bitmap < 3 || bitmap >= total ||
        ((total-1)/4096)+1 > total-bitmap) {
        v_message("Invalid volume header."); return;
    }
    v_clrscr(); v_cprintf("VOLINFO %s - READ ONLY\r\n\r\nScanning allocation... ESC cancels.\r\n", volume);
    audit();
    do {
    v_clrscr(); summary(); v_cputs((char*)buf);
    v_cputs("\r\nM Bitmap  F File blocks  E Export  ESC/RETURN Back");
    u = v_cgetc();
    if ((u == 'f' || u == 'F') && !failed && !cancelled) file_list();
    if (u == 'e' || u == 'E') export_report();
    if ((u == 'm' || u == 'M') && !failed && !cancelled) map();
    } while (u != KEY_ESC && u != KEY_RETURN);
}
