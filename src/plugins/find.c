/* find.c -- finds files by name pattern, or by a text they contain, in
 * the whole volume of the active panel, and jumps to the one chosen.
 *
 * From the ! menu. A pattern is typed on line 22 (the core's prompt
 * refuses `=` and `?`, so the keys are read here): Copy II Plus wildcards,
 * `=` for any run of characters, `?` for one, upper-cased. A pattern that
 * starts with `"` is a TEXT search: the rest is looked for inside every
 * file of the volume, case-insensitive and high bit ignored, 512 bytes at
 * a time through api->copy_buf with an overlap of the last bytes of the
 * previous read, so a text astride two reads is found too.
 *
 * The volume is the first component of the panel's path ("/VOL"), or the
 * selected volume in the volume list. It is walked breadth-first with one
 * directory open at a time: a queue of directory paths in the scratch
 * area, the current directory read to its end (its subdirectories
 * queued, its files matched), then the next of the queue. In a text
 * search the files cannot be read while the directory is open (both go
 * through copy_buf), so the names of a directory are pooled, the
 * directory closed, and the pool searched; a directory with more files
 * than the pool holds is reread from where the pool stopped.
 *
 * The matches, full paths, are listed on a full screen: up and down to
 * choose, Return sets the active panel on the directory of the chosen
 * file with the cursor on it (the core rereads and redraws after a big
 * overlay), N continues with the next 20 matches, Escape leaves. Escape
 * during the walk aborts it. Traversal state survives each result page. "Nothing
 * found." when there is no match.
 *
 * A big overlay under 5,632 bytes: $3100-$3FFF is its scratch memory --
 * the queue (32 paths of 64), the matches (20 paths of 64) and the name
 * pool (28 names of 16). api->full carries the path being built (and
 * the line being written), api->other_full the directory being read --
 * not a pointer into the queue, which is packed when it fills up. The
 * service table is copied into a static: a call through it costs half
 * of one through api->. */

#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Find files by name pattern or text in the volume"
};
#pragma rodata-name (pop)

#define KBD     (*(volatile unsigned char*)0xC000)
#define KBDSTRB (*(volatile unsigned char*)0xC010)

#define QMAX   32                          /* directories waiting, 64 bytes each */
#define QLEN   64
#define RMAX   20                          /* matches kept, 64 bytes each */
#define RLEN   64
#define PMAX   28                          /* names pooled per directory read, 16 each */
#define PLEN   16
#define PATMAX 32                          /* the pattern, or the text */
#define ROW0   2                           /* the first row of the list */

#ifdef PLUGIN_HOST
static char host_queue[QMAX*QLEN], host_results[RMAX*RLEN], host_pool[PMAX*PLEN];
#define QUEUE host_queue
#define RESULTS host_results
#define POOL host_pool
#else
#define QUEUE   ((char*)0x3100)            /* 32 x 64 = 2048: $3100-$38FF */
#define RESULTS ((char*)0x3900)            /* 20 x 64 = 1280: $3900-$3DFF */
#define POOL    ((char*)0x3E00)            /* 28 x 16 =  448: $3E00-$3FBF */

#endif

/* BSS: nothing zeroes it; everything below is written before it is read. */
static struct A2fcApi a;                   /* the service table, copied */
static struct Panel* pan;
static char* path;                         /* a.full: the path being built, or the line written (80) */
static char* dir;                          /* a.other_full: the directory being read (80) */
static char* root;                         /* a.input: the volume, "/VOL" (17) */
static char pat[PATMAX + 1];               /* the pattern, or the text, upper case */
static unsigned char plen;
static unsigned char text;                 /* 1: a text search */
static unsigned char nres, qhead, qtail;
static unsigned char pool_count, pool_pos, dir_active, ready;
static unsigned int dir_skip;
static unsigned long total;
static unsigned char aborted, cut;         /* cut: queue/path limit or failed open */

static void msg(const char* s) { a.message(s); }

/* Escape pressed? Any other key waiting is dropped. */
static unsigned char abort_key(void)
{
#ifndef PLUGIN_HOST
    if (KBD & 0x80) {
        unsigned char k = KBD & 0x7F;
        KBDSTRB = 0;
        if (k == KEY_ESC) aborted = 1;
    }
#endif
    return aborted;
}

/* Copy II Plus wildcards, without recursion: `=` backtracks to the last
 * one seen. Both strings are upper case. */
static unsigned char match(const char* s)
{
    const char* p = pat;
    const char* star = 0;
    const char* ss = 0;
    while (*s) {
        if (*p == '?' || *p == *s) { ++p; ++s; }
        else if (*p == '=') { star = p++; ss = s; }
        else if (star) { p = star + 1; s = ++ss; }
        else return 0;
    }
    while (*p == '=') ++p;
    return *p == 0;
}

/* Does the file at `path` contain the text? Reads of 512 bytes into
 * copy_buf, the first plen-1 bytes of the buffer being the tail of the
 * previous read, normalised: high bit off, upper case. */
static unsigned char file_has(void)
{
    unsigned char* buf = a.copy_buf;
    unsigned char keep = plen - 1, i, c;
    unsigned int n, end, j;
    FILE* f = a.fopen(path, "rb");
    if (!f) { cut=1;return 0; }
    n = 0;                                 /* nothing kept yet: the first read starts at 0 */
    for (;;) {
        unsigned char* p = buf + n;
        end = a.fread(p, 1, 512 - n, f);
        if (!end) break;
        for (j = end; j; --j, ++p) {
            c = *p & 0x7F;
            if (c >= 'a' && c <= 'z') c -= 32;
            *p = c;
        }
        end += n;                          /* bytes valid in buf */
        if (end >= plen) {
            for (j = 0; j <= end - plen; ++j) {
                if (buf[j] != (unsigned char)pat[0]) continue;
                for (i = 1; i < plen && buf[j + i] == (unsigned char)pat[i]; ++i) ;
                if (i == plen) { a.fclose(f); return 1; }
            }
        }
        if (end < 512) break;
        for (j = 0; j < keep; ++j) buf[j] = buf[512 - keep + j];
        n = keep;
        if (abort_key()) break;
    }
    a.fclose(f);
    return 0;
}

/* Append the path in a.full; next_page reserves room before calling. */
static void add_result(void)
{
    a.strcpy(RESULTS + nres * RLEN, path);
    ++nres;
}

/* "dir/name" into a.full; 0 if it does not fit. */
static unsigned char join(const char* dir, const char* name)
{
    unsigned char dl = a.strlen(dir), nl = a.strlen(name);
    if (dl + 1 + nl >= PATH_LEN) { cut=1;return 0; }
    a.memcpy(path, dir, dl);
    path[dl] = '/';
    a.strcpy(path + dl + 1, name);
    return 1;
}

/* Queues the directory `dir/name`; the queue is packed first if its
 * consumed head leaves room (nothing points into it: the directory
 * being read is a copy). */
static void enqueue(const char* name)
{
    unsigned char i;
    if (qtail >= QMAX && qhead) {
        for (i = 0; qhead + i < qtail; ++i)
            a.memcpy(QUEUE + i * QLEN, QUEUE + (qhead + i) * QLEN, QLEN);
        qtail -= qhead;
        qhead = 0;
    }
    if (qtail >= QMAX || !join(dir, name) || a.strlen(path) >= QLEN) { cut = 1; return; }
    a.strcpy(QUEUE + qtail * QLEN, path);
    ++qtail;
}

/* Reopen the current directory at its saved entry ordinal. Pool names for
 * both search modes, so the directory is closed before reading file content
 * or showing results. Subdirectories are queued exactly once, including ones
 * after the first pool. Count ALL live entries, using 16 bits rather than 8. */
static void fill_pool(void)
{
    unsigned int seen=0;
    const struct DirEntry* de=a.dir_entry;
    pool_count=pool_pos=0;
    a.sprintf(path,"Searching %s...",dir);msg(path);
    if(!a.dir_open(dir)) { cut=1;dir_active=0;return; }
    while(a.dir_next()) {
        if(abort_key())break;
        if(seen<dir_skip) { ++seen;continue; }
        if(seen==65535U) { cut=1;break; }
        ++seen;
        if(de->type==0x0F)enqueue(de->name);
        else {
            a.strcpy(POOL+pool_count*PLEN,de->name);++pool_count;
            if(pool_count==PMAX) { dir_skip=seen;a.dir_close();return; }
        }
    }
    dir_active=0;a.dir_close();
}

/* Produce one next matching path, retaining the queue, directory position
 * and unconsumed file names between result pages. */
static unsigned char next_result(void)
{
    const char* name;
    while(!abort_key()) {
        if(pool_pos<pool_count) {
            name=POOL+pool_pos*PLEN;++pool_pos;
            if((text || match(name)) && join(dir,name) && (!text || file_has()))return 1;
            continue;
        }
        if(!dir_active) {
            if(qhead==qtail)return 0;
            a.strcpy(dir,QUEUE+qhead*QLEN);++qhead;dir_skip=0;dir_active=1;
        }
        fill_pool();
    }
    return 0;
}

/* One lookahead match in a.full makes N truthful even for exact multiples
 * of 20. choose() only draws the UI and must preserve this borrowed buffer. */
static void next_page(void)
{
    nres=0;
    if(ready) { add_result();ready=0; }
    while(nres<RMAX && next_result())add_result();
    if(nres==RMAX)ready=next_result();
    total+=nres;
}

/* The key loop on line 22: the pattern, echoed as it is typed. Returns 0
 * on Escape, or an empty pattern. */
static unsigned char read_pattern(void)
{
    char k;
    plen = 0;
    for (;;) {
        pat[plen] = 0;
        a.sprintf(path, "Find (= any run, ? one char, \"text): %s_", pat);
        msg(path);
        k = a.cgetc();
        if (k == KEY_ESC) { msg(""); return 0; }
        if (k == KEY_RETURN) { if (plen) return 1; }
        else if (k == KEY_DELETE || k == KEY_LEFT) { if (plen) --plen; }
        else if (k >= ' ' && k <= '~' && plen < PATMAX) {
            if (k >= 'a' && k <= 'z') k -= 32;
            pat[plen++] = k;
        }
    }
}

/* The list of matches, one per row from ROW0, the chosen one in
 * inverse video. Returns the index chosen, or 0xFF on Escape. */
static unsigned char choose(void)
{
    unsigned char sel = 0, i;
    char k;
    a.clrscr();
    a.gotoxy(0, 0);
    a.cprintf("%u match(es) for %s%s in %s", nres, text ? "\"" : "", pat, root);
    a.bar_begin();
    a.keys_bar(0, ready ? "UP/DN Choose,RET Go there,N Next,ESC Leave" : "UP/DN Choose,RET Go there,ESC Leave");
    a.gotoxy(0,22);
    a.cprintf("Results %lu-%lu%s",total-nres+1,total,aborted ? "; aborted" : cut ? "; some paths skipped" : ready ? "; more matches" : "; complete");
    for (;;) {
        for (i = 0; i < nres; ++i) {
            a.gotoxy(0, ROW0 + i);
            a.revers(i == sel);
            a.cprintf("%-79s", RESULTS + i * RLEN);
        }
        a.revers(0);
        k = a.cgetc();
        if (k == KEY_ESC) return 0xFF;
        if (k == KEY_RETURN) return sel;
        if ((k=='N' || k=='n') && ready)return 0xFE;
        if (k == KEY_UP && sel) --sel;
        else if (k == KEY_DOWN && sel + 1 < nres) ++sel;
    }
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char i, sel;
    char* s;
    api->memcpy(&a, api, sizeof a);
    pan = a.panels;
    if (*a.active) ++pan;
    path = a.full;
    dir = a.other_full;
    root = a.input;
    if (pan->fs) { msg("Not in a disk image or a DOS 3.3 disk."); return; }
    /* The volume: the first component of the path, or the selected volume. */
    s = pan->path;
    if (!s[0]) s = a.selected->name;
    if (s[0] != '/') { msg("Select a ProDOS volume first."); return; }
    for (i = 1; s[i] && s[i] != '/' && i < NAME_LEN - 1; ++i) root[i] = s[i];
    root[0] = '/';
    root[i] = 0;
    a.strcpy(QUEUE, root);
    if (!read_pattern()) return;
    text = pat[0] == '"';
    if (text) {
        for (i = 0; i < plen; ++i) pat[i] = pat[i + 1];
        --plen;
        if (!plen) { msg(""); return; }
    }
    nres=0;qhead=0;qtail=1;aborted=cut=0;
    pool_count=pool_pos=dir_active=ready=0;dir_skip=0;total=0;
    next_page();
    if(!nres) { a.strcpy(a.note,aborted ? "Search aborted." : cut ? "Nothing found; some paths skipped." : "Nothing found.");return; }
    for(;;) {
        sel=choose();if(sel!=0xFE)break;
        next_page();
    }
    if (sel != 0xFF) {
        /* The directory of the match into the panel's path, its name reselected. */
        s = RESULTS + sel * RLEN;
        for (i = a.strlen(s); s[i] != '/'; --i) ;
        a.strcpy(a.reselect, s + i + 1);
        s[i] = 0;                          /* a file at the root: "/VOL" */
        if (a.strlen(s) < PATH_LEN) { a.strcpy(pan->path, s); pan->first = 0; }
    }
    a.sprintf(a.note, "%lu match(es)%s.", total, aborted ? ", search aborted"
              : ready ? ", more available" : cut ? ", some paths skipped" : "");
}
