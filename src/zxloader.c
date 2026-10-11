/* Experimental compressed split-load launcher. All accesses are MAIN:
 * prefix $1000-$1BFF, program $4000-$BEDF, private state below $4000.
 * AUX (including /RAM) is never used. Only a verified, closed image runs. */
#include <stdio.h>
#include <conio.h>
#include <string.h>
extern void set_boot_prefix(void);
static FILE* image;
/* Five aligned ProDOS blocks per refill; linker bounds include this buffer. */
unsigned char zx_buffer[2560];
static unsigned int available, zx_cursor, remaining;
unsigned int zx_refill(void)
{
    unsigned int want;
    if (!remaining) return 0;
    want = remaining > sizeof(zx_buffer) ? sizeof(zx_buffer) : remaining;
    available = fread(zx_buffer, 1, want, image);
    if (available != want || ferror(image)) return 0;
    remaining -= want;
    return available;
}
#ifndef A2FC_ZX02_ASM
static int next_byte(void)
{
    if (zx_cursor == available) {
        if (!zx_refill()) return -1;
        zx_cursor = 0;
    }
    return zx_buffer[zx_cursor++];
}
#define ZX_READ() next_byte()
#ifndef ZX_AT
#define ZX_AT(i) ((unsigned char*)((i) < 0x0C00 ? 0x1000 + (i) : 0x3400 + (i)))
#endif
#include "zx02_stream.h"
#define ZX_INPUT_UNUSED() (zx_cursor != available)
#else
extern unsigned char __fastcall__ zx_decode(unsigned int size, unsigned int crc);
extern unsigned int zx_pos, zx_input_left;
#define ZX_INPUT_UNUSED() zx_input_left
#endif
#ifndef ZX_LAUNCH
#define ZX_LAUNCH() ((void (*)(void))0x4000)()
#endif
static unsigned int word(const unsigned char* p) { return p[0] | ((unsigned int)p[1] << 8); }
int main(void)
{
    static unsigned char h[12], extra, ok;
    unsigned int size;
    videomode(VIDEOMODE_80COL); clrscr();
    cputs("A2 FILE CMD - experimental ZX02 boot\r\nLoading A2FILE.CODE ...");
    set_boot_prefix(); image = fopen("A2FILE/A2FILE.CODE", "rb");
    if (!image) goto failed;
    ok = 0;
    if (fread(h, 1, sizeof(h), image) == sizeof(h) && !ferror(image)
        && (!memcmp(h, "A2Z1", 4) || !memcmp(h, "A2Z2", 4)) && !h[11]
#ifdef A2FC_6502
        && h[10] == 0
#else
        && h[10] == 1
#endif
    ) {
        /* V2 aligns the payload to a ProDOS block. V1 remains readable.
         * Padding is read and checked before any decompression write. */
        if (h[3] == '2') {
            if (fread(zx_buffer, 1, 500, image) != 500 || ferror(image)) goto close_image;
            for (size = 0; size < 500; ++size) if (zx_buffer[size]) goto close_image;
        }
        size = word(h + 4); remaining = word(h + 6);
        if (size > 0x0C00 && size <= 0x8AE0 && remaining) {
            available = zx_cursor = 0;
            ok = zx_decode(size, word(h + 8));
            /* Exact compressed extent, explicit EOF, and clean close. */
            if (remaining || ZX_INPUT_UNUSED() || fread(&extra, 1, 1, image) || ferror(image)) ok = 0;
        }
    }
close_image:
    if (fclose(image)) ok = 0;
    if (ok) { ZX_LAUNCH(); return 0; }
failed:
    cputs("\r\nCompressed image invalid or I/O error.\r\nPress a key to quit.");
    cgetc(); return 1;
}
