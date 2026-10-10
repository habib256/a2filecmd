/* IDENT: read-only content identification and automatic reader routing,
 * ProDOS and DOS 3.3. IDREAD samples DOS allocation; IDFORMATS handles
 * extended rules and the shared routing table. A closed-source relay keeps
 * each stage inside the guarded overlay window. No AUX or temporary files. */
#include "../a2fc_plugin.h"
#include <string.h>
#include "id_stage.h"
#include "id_context.h"
#ifdef PLUGIN_HOST
#include "id_finish.h"
#endif

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    MEDIA_PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, ID_CPU_TAG,
    "Say what a file is from its content, like file(1)"
};
#pragma rodata-name (pop)

/* BSS: nothing zeroes it; every one of these is written before it is read. */
static const struct A2fcApi* A;
#include "hgr_io.h"
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#pragma optimize(push,off)
#pragma warn(unused-param,push,off)
static int __fastcall__ id_seek(FILE* f,long p,int w) STUB(fseek)
#pragma warn(unused-param,pop)
#pragma optimize(pop)
#else
#define id_seek A->fseek
#endif
static const struct Entry* e;
static struct Entry actual;
static unsigned char id_dos;
static const char* reader;
static unsigned char* b;            /* api->copy_buf: the first 512 bytes, then the message */
static unsigned int n;              /* how many were read */
static FILE* f;
static unsigned char io_failed;
#define DP_READ frd
#define DP_ERROR(f) ferror(f)
#include "../duet_probe.h"
static unsigned char suffix(const char* name, const char* end)
{
    unsigned int n = strlen(name), k = strlen(end);
    return n > k && !strcmp(name+n-k, end);
}

/* The size as two words, copied once: no long compare (cc65 would link its
 * runtime), and no cast of &e->size, which cc65 2.19 compiles as a read at
 * offset 0 of the entry -- the name -- rather than at the member. */
static union { unsigned long l; unsigned int w[2]; } sz;
#define SZ sz.w

static const char* const ends_name[8] = { "no", "CR", "LF", "mixed", "CRLF", "mixed", "mixed", "mixed" };
static const char m_text[] = "Text%s, %s ends%s, %u lines in %u B%s";
static const char s_image[] = "ProDOS disk image, 140K";

/* `m` at the start of the file, the high bits ignored. */
static unsigned char magic(const char* m)
{
    unsigned char i = 0;
    while (m[i]) {
        if ((b[i] & 0x7F) != m[i]) return 0;
        ++i;
    }
    return 1;
}

/* 512 bytes at `pos` of the file (still open) into b; 1 if a ProDOS
 * volume directory header stands at their byte 4 (storage type $F). */
static unsigned char prodos_at(long pos)
{
    if (id_seek(f, pos, SEEK_SET) || frd(b, 1, 512, f) != 512 || ferror(f)) { io_failed = 1; return 0; }
    return b[4] >> 4 == 0xF;
}

/* A tokenised Applesoft line from $0801: link, number, tokens, zero. */
static unsigned char applesoft(void)
{
    unsigned int k;
    unsigned char tok = 0;
    if (n < 6 || b[3] > 0xF9) return 0;           /* the number: 63999 at most */
    for (k = 4; k < n; ++k) {
        if (!b[k]) break;
        if (b[k] & 0x80) tok = 1;
    }
    return tok && k < n && (b[0] | (b[1] << 8)) == 0x0802 + k;
}

/* Validate the complete sample before treating high bytes as UTF-8. A
 * sequence cut by the 512-byte sampling limit is allowed only when the
 * file continues, never at EOF. Reject overlong forms, surrogates and
 * values beyond U+10FFFF. ASCII-only samples retain their old description. */
static unsigned char utf8(void)
{
    unsigned int i = 0;
    unsigned char c, d, left, seen = 0;
    while (i < n) {
        c = b[i++];
        if (c < 0x80) continue;
        if (c < 0xC2 || c > 0xF4) return 0;
        left = c < 0xE0 ? 1 : c < 0xF0 ? 2 : 3;
        seen = 1;
        while (left) {
            if (i == n) return n == 512 && sz.l > 512;
            d = b[i++];
            if (d < 0x80 || d > 0xBF) return 0;
            if ((c == 0xE0 && d < 0xA0) || (c == 0xED && d >= 0xA0) ||
                (c == 0xF0 && d < 0x90) || (c == 0xF4 && d >= 0x90)) return 0;
            c = 0;                      /* special bounds apply to byte 2 only */
            --left;
        }
    }
    return seen;
}

/* Text, or binary data: the line written at b + 256. */
static const char* text(void)
{
    unsigned int i, lines = 0;
    unsigned char c, k, hi = 0, lo = 0, utf = 0, tabs = 0, pend = 0, ends = 0;
    const char* hb;
    utf = utf8();
    for (i = 0; i < n; ++i) {
        c = b[i];
        /* Valid UTF-8 high bytes are part of a character, not Apple
         * high-bit CR/LF or control bytes. A preceding CR stands alone. */
        if (utf && c >= 0x80) {
            if (pend) { ends |= 1; pend = 0; }
            continue;
        }
        k = c & 0x7F;
        if (c & 0x80) hi = 1; else lo = 1;
        if (k == 13) { ++lines; pend = 1; continue; }
        if (k == 10) {
            if (pend) ends |= 4; else { ends |= 2; ++lines; }
            pend = 0;
            continue;
        }
        if (pend) { ends |= 1; pend = 0; }
        if (k == 9) tabs = 1;
        else if (k < 32 || k == 127) return "Binary data";
    }
    if (pend) ends |= 1;
    hb = utf ? "" : hi ? (lo ? ", high bit mixed" : ", high bit set") : ", high bit clear";
    A->sprintf((char*)b + 256, m_text, utf ? " (UTF-8)" : "", ends_name[ends], hb, lines, n, tabs ? ", tabs" : "");
    return (const char*)b + 256;
}

#ifdef PLUGIN_HOST
#include "id_formats.h"
#include "id_v1.h"
#endif
#ifdef PLUGIN_HOST
#include "id_routes.h"
#endif
static const char* identify(void)
{
    unsigned char t = e->type, i;
    if (!n) return "Empty file";
    if(!id_dos && t==0x16){
     if(e->aux==1 && n>=22 && !memcmp(b+16,"A2CD00",6))return "PFS:File?";
     if(e->aux==2 && n>=10 && sz.l==1024UL+word(b+8))return "PFS:Write?";
     if(e->aux==4 && n>=34 && !memcmp(b+24,"Plan  \003B00",10))return "PFS:Plan?";
    }
 if(!id_dos && e->type==250 && e->aux>=0x4000 && e->aux<0x6000 && n>=16 && word(b+2)>=16 && word(b+2)<sz.l && b[6]>0 && b[6]<128 && b[7]>=2 && b[7]<128 && b[8]>=3 && b[8]<128)return "LISA 8/16?";

    if (t == 7) return "MGTK font";
    if (suffix(e->name,".FOTO1") || suffix(e->name,".FOTO2")) return "Purplesoft pair";
    if (t == 8 && e->aux == 0x8066) return "LZ4FH HGR";
    if (t == 6 && (e->aux & 0xCFFF) == 0x4800 && (sz.l == 572 || sz.l == 576))
        return "Print Shop clip art";
    if ((t==6 || t==8) && e->aux==0x400 && sz.l<=2048) return "Lo-res / double lo-res";
    if (n>=3 && !memcmp(b,"DGR",3)) return "DGR pixmap";
    if (suffix(e->name,".PT3") || (n>=14 && (!memcmp(b,"ProTracker 3.",13) || !memcmp(b,"Vortex Tracker",14))))
        return "ProTracker 3 music";
    if ((t==0xD5 && e->aux==0xD0E7) || suffix(e->name,".ED") || (t==6 && e->name[0]=='M' && e->name[1]=='.')) {
        unsigned char result;
        if(id_dos)return "Electric Duet? (no DOS reader)";
        if (id_seek(f,0,SEEK_SET)) { io_failed=1; return ""; }
        result=duet_probe(f,b);
        if (result==2) io_failed=1;
        return result==1 ? "Electric Duet compatible song" : "Invalid Electric Duet?";
    }
    if (suffix(e->name,".MD")) return "Markdown text";
    if (magic("NuFile") || magic("NuFX")) return "ShrinkIt (NuFX)";
    if (magic("\x0A\x47\x4C") && b[18] == 2) return "Binary II archive";
    if (magic("2IMG")) return "2IMG disk image";
    if (suffix(e->name,".NIB") && sz.l == 232960L) return "Disk II nibble image";
    if (!id_dos && (suffix(e->name,".PO") || suffix(e->name,".HDV")) && sz.l != 143360L) {
        if (sz.l >= 1536 && prodos_at(1024)) return "ProDOS block image";
        return "Unknown block image";
    }
    if (!id_dos && SZ[1] == 2 && SZ[0] == 0x3000) {          /* 143,360 bytes: a 5.25 image */
        if (prodos_at(1024)) return s_image;
        prodos_at(69632L);                        /* the VTOC, DOS order: track 17 sector 0 */
        if (b[1] == 17 && b[3] == 3) return "DOS 3.3 disk image, 140K";
        if (prodos_at(2816)) return "ProDOS disk image, 140K, DOS order";   /* block 2 = sector 11 */
        return "Disk image, 140K";
    }
    if (t == 0x1A) return "AppleWorks word";
    if (t == 0x19) return "AppleWorks data";
    if (t == 0x1B) return "AppleWorks spreadsheet";
    if (t == 0xFC || applesoft()) return "Applesoft BASIC";
    if (t == 0xFA) return "Integer BASIC";
    if (magic("HGRR")) return "HGR picture, RLE";
    if (magic("DHRR")) return "DHGR picture, RLE";
    /* A FOT is raw or packed, and the auxtype is what says so: $4000 a
     * packed hi-res page, $4001 a packed double hi-res one (PACKFOT reads
     * both), $8066 the LZ4FH compression. Anything else is the load address
     * of a raw page. Saying only "FOT" sent the reader to a viewer that
     * would refuse three quarters of them. */
    if (t == 0x08) {
        if (e->aux == 0x4000) return "Packed HGR";
        if (e->aux == 0x4001) return "Packed DHGR";
        if (e->aux == 0x8066) return "LZ4FH HGR";
    }
    /* Extasie writes its pictures under a type of their own, $F2, and opens
     * them with their own length: a double hi-res page, compressed, for the
     * Le Chat Mauve card (EXTASIE reads them). */
    if (!id_dos && t == 0xF2)
        return SZ[0] == (unsigned long)(unsigned int)(b[0] | (b[1] << 8))
            ? "Extasie (Chat Mauve), packed" : "Extasie (Chat Mauve)";
    /* 816/Paint saves packed by default, as a $06 with an auxtype of its
     * own: $E001 a hi-res page, $E002 a double hi-res one (PAINT816 reads
     * both). Their size is whatever the packing came to, so nothing above
     * claims them and the reader would have called them binary. */
    if (t == 6 && (e->aux == 0xE001 || e->aux == 0xE002))
        return e->aux == 0xE001 ? "816/Paint packed HGR"
                                : "816/Paint packed DHGR";
    if (!SZ[1]) {
        if (SZ[0] == 16384) return "DHGR picture, 16K";
        if (SZ[0] == 8192 || (SZ[0] >= 8184 && SZ[0] < 8192 && t == 6 && e->aux == 0x2000))
            return "HGR picture, 8K";
    }
    if (t == 8) return "Hi-res picture (FOT), raw";
    if (magic("MB1")) return "Mockingboard music (MB1)";
    if (t == 0xFF) return "ProDOS system program";
    if (t == 6 && e->aux)
        for (i = 0; i < 8; ++i) {
            t = b[i];
            if (t == 0x4C || t == 0x20 || t == 0xA9) return "Binary, maybe 6502 code";
        }
    return text();
}

unsigned char __fastcall__ md_entrypoint(const struct A2fcApi* api)
{
    const struct Panel* pan=api->panels+*api->active;
    const char* what;unsigned char automatic;unsigned char* m=(unsigned char*)api->other_full;
    A=api;e=api->selected;b=api->copy_buf;sz.l=e->size;reader=NULL;io_failed=0;f=NULL;
    automatic=api->arg=='O'||api->arg=='I'||api->arg==13;
    if(automatic)api->input[0]=0;
    id_dos=pan->fs==FS_DOS33;
    if(!e->name[0] || e->type==15 || !pan->path[0] || (pan->fs && !id_dos)){
        scpy(A->note,"Select a file in ProDOS or DOS 3.3.");return 0;
    }
    scpy(A->reselect,e->name);
#ifndef PLUGIN_HOST
    A->dir_close();
    if(id_restore(api,&actual,&n)){
        e=&actual;sz.l=e->size;b=ID_SAMPLE;
        if(m[42]!=1)goto extra_stage;
        m[40]=m[41]=0;
        if(!id_dos){
            if(!A->build_full(A->full,pan,A->selected))goto failed;
            f=fopn(A->full,"rb");if(!f)goto failed;
        }
    }else if(id_dos){
        if(id_open_stage(api,"IDREAD.PLG"))return 1;
        goto failed;
    }else{
        f=fopn(A->full,"rb");if(!f)goto failed;
        n=frd(b,1,512,f);if(ferror(f))io_failed=1;
        if(n<512)A->memset(b+n,0,512-n);
        memcpy(ID_SAMPLE,b,512);
        {unsigned int got=n;unsigned long total=n;
         while(got && !io_failed){got=frd(b,1,512,f);total+=got;if(ferror(f))io_failed=1;}
         actual=*e;actual.size=total;e=&actual;sz.l=total;}
        if(fcls(f))io_failed=1;f=NULL;
        if(io_failed)goto failed;
        id_context(api,n,sz.l,e->aux,e->type);
extra_stage:
        if(id_open_stage(api,"IDV1.PLG"))return 1;
        goto failed;
    }
    what=identify();
#else
    if(id_dos){
        if(!id_restore(api,&actual,&n))goto failed;
        e=&actual;sz.l=e->size;b=ID_SAMPLE;m[40]=m[41]=0;
    }else{
        f=fopn(A->full,"rb");if(!f)goto failed;
        if(id_seek(f,0,SEEK_END))io_failed=1;
        {long size=ftell(f);if(size<0)io_failed=1;else {actual=*e;actual.size=(unsigned long)size;e=&actual;sz.l=e->size;}}
        if(id_seek(f,0,SEEK_SET))io_failed=1;
        n=frd(b,1,512,f);if(ferror(f))io_failed=1;
        if(n<512)A->memset(b+n,0,512-n);
    }
    what=extra_v1();if(!what)what=extra();if(!what)what=identify();
#endif
#ifdef PLUGIN_HOST
    if(!reader)route(what);
#endif
    if(f){if(ferror(f))io_failed=1;if(fcls(f))io_failed=1;f=NULL;}
    if(io_failed)goto failed;
#ifdef PLUGIN_HOST
    id_finish(api,e,what,reader,id_dos);return 0;
#else
    /* The old literal belongs to this overlay. Preserve a bounded label
     * before handing classification/routing to the format stage. */
    {unsigned char j=0;while(j<127 && what[j]){ID_SAMPLE[j]=what[j];++j;}ID_SAMPLE[j]=0;}
    id_context(api,n,sz.l,e->aux,e->type);m[42]=2;
    if(id_open_stage(api,"IDFORMATS.PLG"))return 1;
    goto failed;
#endif
failed:
    if(m)m[40]=m[41]=0;
    if(f)fcls(f);
    scpy(A->note,"Cannot identify: read/seek/close/stage error.");return 0;
}
#ifdef PLUGIN_HOST
void __fastcall__ plugin_entry(const struct A2fcApi* api){md_entrypoint(api);}
#endif
