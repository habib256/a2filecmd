/* txtconv.c -- convert the selected text file: line endings (CR, LF, CRLF),
 * the high bit (off or on), tabs to spaces, UTF-8 accents to plain ASCII.
 * In place (through TXTCONV.TMP in the same directory, then an MLI RENAME)
 * or to the same name in the other panel. Streams 256 bytes at a time
 * through api->copy_buf: the input in the first half, the output in the
 * second; the state (a CR waiting for its LF, a UTF-8 lead byte, the
 * column) is kept across chunks.
 *
 * A big overlay, for want of room: cc65 spends 25 to 30 bytes on each call
 * through a function pointer, and the thirty-odd service calls plus the
 * converter come to some 2.5 KB of code, twice the small window. The
 * service table is copied into T, a static, which makes each use of it a
 * little shorter than a pointer dereference. Being big, the core re-reads
 * and redraws both panels on return (clrscr included): every word for the
 * user goes through api->note, and the cursor through api->reselect --
 * message() and report_error() would be wiped before being seen. */
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
    "Convert text: CR/LF/CRLF, high bit, tabs, accents"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

/* Nothing zeroes the BSS: every one of these is written before it is read. */
static struct A2fcApi T;
static FILE* out;
static unsigned char* obuf;             /* copy_buf + 256 */
static unsigned int olen;
static unsigned long nin, nout;
static unsigned char mode, prev, col, pend, lead, fail;
static struct { unsigned char count; unsigned char* old; unsigned char* new_; } rp;
static struct {
    unsigned char count; unsigned char* path; unsigned char access, type;
    unsigned int aux; unsigned char storage; unsigned int date, time;
} cp;
/* GET_FILE_INFO writes fifteen result bytes after the Pascal-path pointer. */
static struct { unsigned char count; unsigned char* path; unsigned char result[15]; } ip;

/* Latin-1 $C0-$DF to ASCII; $E0-$FF the same, lower-cased. */
static const char latin[] = "AAAAAAACEEEEIIIIDNOOOOO?OUUUUY?y";

static const char keys_msg[]  = "To C)R L)F D)CRLF, H)igh bit off S)et, T)abs A)ccents, ESC ";
static const char m_pick[]    = "Select a file to convert.";
static const char m_other[]   = "Other panel: same directory, or not ProDOS.";
static const char m_inplace[] = "In place? (N = to the other panel)";
static const char m_over[]    = "Overwrite it in the other panel?";
static const char m_rename[]  = "Rename: ProDOS $%02X, result left as TXTCONV.TMP";
static const char m_done[]    = "Converted %lu bytes -> %lu bytes";
static const char m_fail[]    = "%s failed.";
static const char m_temp[]    = "TXTCONV.TMP already exists: rename or remove it first.";
static const char m_exists[]  = "Destination already exists.";
static const char f_tmp[]     = "%s/TXTCONV.TMP";
static const char f_other[]   = "%s/%s";

static void flush(void)
{
    if (olen && T.fwrite(obuf, 1, olen, out) != olen) fail = 1;
    nout += olen;
    olen = 0;
}

static void put(unsigned char c)
{
    obuf[olen++] = c;
    if (olen == 256) flush();
}

static void eol(unsigned char hb)
{
    if (mode != 'L') put(13 | hb);
    if (mode != 'C') put(10 | hb);
}

static void convert(unsigned char c)
{
    unsigned char k = c & 0x7F, hb = c & 0x80, x;
    switch (mode) {
    case 'H': put(k); break;
    case 'S': put(c | 0x80); break;
    case 'T':
        if (k == 9) { do put(' ' | hb); while (++col & 7); }
        else { put(c); col = (k == 13 || k == 10) ? 0 : col + 1; }
        break;
    case 'A':
        /* A broken sequence must not swallow the next ASCII character or
         * a new lead byte. Finish it, then process this byte normally. */
        if (pend && (c & 0xC0) != 0x80) { put('?'); pend = 0; }
        if (pend) {                                 /* inside a multi-byte sequence */
            --pend;
            if (lead == 0xC3) {
                x = latin[c & 0x1F];
                if (c == 0x9F) x = 's';             /* sharp s */
                else if (c >= 0xA0 && x >= 'A' && x <= 'Z') x += 32;
                put(x);
            } else if (!pend) put('?');
        }
        else if (c < 0x80) put(c);
        else if (c >= 0xC0 && c < 0xF8) { lead = c; pend = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : 1; }
        else put('?');
        break;
    default:                                        /* C, L, D */
        if (k == 13) eol(hb);
        else if (k == 10) { if (prev != 13) eol(hb); }   /* the LF of a CRLF: already done */
        else put(c);
        prev = k;
    }
}

static void pascal(unsigned char* p, const char* s)
{
    unsigned char n = T.strlen(s);
    p[0] = n;
    T.memcpy(p + 1, s, n);
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Panel* pan;
    const struct Panel* oth;
    const struct Entry* e;
    char* target;
    unsigned char* p;
    FILE* in;
    const char* what;
    unsigned int n, i;
    unsigned char inplace, k, replace = 0;

    api->memcpy(&T, api, sizeof T);
    pan = T.panels;
    oth = pan + 1;
    if (*T.active) { pan = oth; oth = T.panels; }
    e = T.selected;
    target = T.other_full;
    if (!e->name[0] || e->type == 0x0F || !pan->path[0] || pan->fs) { T.strcpy(T.note, m_pick); return; }
    T.message(keys_msg);
    for (;;) {
        k = T.cgetc();
        if (k == KEY_ESC) return;
        if (k >= 'a') k -= 32;
        if (k == 'C' || k == 'L' || k == 'D' || k == 'H' || k == 'S' || k == 'T' || k == 'A') break;
    }
    mode = k;
    inplace = T.confirm(m_inplace);
    if (inplace) T.sprintf(target, f_tmp, pan->path);
    else {
        if (!oth->path[0] || oth->fs || !T.strcmp(oth->path, pan->path)) { T.strcpy(T.note, m_other); return; }
        T.sprintf(target, f_other, oth->path, e->name);
        pascal(T.copy_buf, target);
        ip.count = 10; ip.path = T.copy_buf;
        k = T.mli(0xC4, &ip);
        if (!k) {
            if (!T.confirm(m_over)) return;
            replace = 1;
        } else if (k != 0x46) {
            T.strcpy(T.note, "Destination check failed."); return;
        }
    }
    what = "Open";
    in = T.fopen(T.full, "rb");
    if (!in) goto err;
    *T.filetype = e->type;
    *T.auxtype = e->aux;
    what = "Create";
    if (inplace || !replace) {
        /* A leftover may be the only recoverable result of an earlier
         * failed rename, or even the selected source. Never overwrite it. */
        pascal(T.copy_buf, target);
        cp.count = 7; cp.path = T.copy_buf; cp.access = 0xC3;
        cp.type = e->type; cp.aux = e->aux; cp.storage = 1;
        cp.date = cp.time = 0;
        k = T.mli(0xC0, &cp);
        if (k) {
            T.fclose(in);
            if (k == 0x47) {
                T.strcpy(T.note, inplace ? m_temp : m_exists); return;
            }
            goto err;
        }
    } else T.remove(target);                       /* confirmed replacement */
    out = T.fopen(target, "wb");
    if (!out) { T.fclose(in); goto errrm; }
    what = "Write";
    obuf = T.copy_buf + 256;
    olen = 0; nin = 0; nout = 0;
    prev = 0; col = 0; pend = 0; fail = 0;
    for (;;) {
        T.progress_bar(e->name, nin, e->size);
        n = T.fread(T.copy_buf, 1, 256, in);
        nin += n;
        for (p = T.copy_buf, i = n; i; --i) convert(*p++);
        if (n < 256) break;
    }
    if (mode == 'A' && pend) put('?');             /* incomplete sequence at EOF */
    flush();
    /* fread returns short on errors as well as EOF. Without ferror in the
     * service API, require the panel's full byte count before replacing
     * the source; a stale size also leaves the original intact. */
    if (nin != e->size) { fail = 1; what = "Read"; }
    T.fclose(in);
    if (T.fclose(out)) fail = 1;
    if (fail) goto errrm;
    if (inplace) {
        /* the original goes, TXTCONV.TMP takes its name: MLI RENAME ($C2) on two Pascal strings */
        what = "Delete";
        if (T.remove(T.full)) goto errrm;
        pascal(T.copy_buf, target);
        pascal(T.copy_buf + 128, T.full);
        rp.count = 2; rp.old = T.copy_buf; rp.new_ = T.copy_buf + 128;
        k = T.mli(0xC2, &rp);
        if (k) { T.sprintf(T.note, m_rename, k); return; }
    }
    T.strcpy(T.reselect, e->name);
    T.sprintf(T.note, m_done, nin, nout);        /* the core re-reads and redraws, then writes it */
    return;
errrm:
    T.remove(target);
err:
    T.sprintf(T.note, m_fail, what);                /* report_error's line would not survive the redraw */
}
