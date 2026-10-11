/* Bounded forward ZX02 reader (default Elias polarity, initial offset 1).
 * Algorithm: Daniel Serpell's ZX02, https://github.com/dmsc/zx02.
 * Input, output and back references are checked before every access.
 * ZX_READ() returns a byte or -1; ZX_AT(index) maps split-load MAIN RAM.
 * No allocation, auxiliary RAM, disk writes or executable callbacks. */
#include <stdint.h>
static uint16_t zx_pos, zx_size, zx_crc;
static unsigned char zx_bits, zx_extra, zx_bad;
static unsigned char zx_byte(void)
{
    int c = ZX_READ();
    if (c < 0) { zx_bad = 1; return 0; }
    return (unsigned char)c;
}
static unsigned char zx_bit(void)
{
    unsigned char b;
    if (zx_extra) { b = zx_extra & 1; zx_extra = 0; return b; }
    if (zx_bits == 0x80) { b = zx_byte(); zx_bits = (b << 1) | 1; return b >> 7; }
    b = zx_bits >> 7; zx_bits <<= 1; return b;
}
static unsigned int zx_elias(void)
{
    unsigned int v = 1;
    while (zx_bit()) {
        if (v >= 256 || zx_bad) { zx_bad = 1; return 0; }
        v = (v << 1) | zx_bit();
        if (v > 256) { zx_bad = 1; return 0; }
    }
    return v;
}
static void zx_put(unsigned char c)
{
    static const unsigned int table[16] = {
        0x0000,0x1021,0x2042,0x3063,0x4084,0x50A5,0x60C6,0x70E7,
        0x8108,0x9129,0xA14A,0xB16B,0xC18C,0xD1AD,0xE1CE,0xF1EF
    };
    if (zx_bad || zx_pos >= zx_size) { zx_bad = 1; return; }
    *ZX_AT(zx_pos) = c; ++zx_pos;
    zx_crc ^= (unsigned int)c << 8;
    zx_crc = (uint16_t)(zx_crc << 4) ^ table[zx_crc >> 12];
    zx_crc = (uint16_t)(zx_crc << 4) ^ table[zx_crc >> 12];
}
static unsigned char zx_decode(unsigned int size, unsigned int crc)
{
    unsigned int n, distance = 1;
    unsigned char state = 0, c;
    zx_pos = 0; zx_size = size; zx_crc = 0xFFFF;
    zx_bits = 0x80; zx_extra = zx_bad = 0;
    for (;;) {
        if (state == 0) {
            n = zx_elias();
            if (zx_bad || !n || n > zx_size - zx_pos) return 0;
            do { c = zx_byte(); zx_put(c); } while (--n && !zx_bad);
        } else {
            if (state == 2) {
                n = zx_elias();
                if (zx_bad) return 0;
                if (n == 256) return zx_pos == zx_size && zx_crc == crc;
                c = zx_byte(); zx_extra = 2 | (c & 1);
                distance = ((n - 1) << 7) + (c >> 1) + 1;
            }
            n = zx_elias();
            if (state == 2) { ++n; if (n > 256) n &= 255; }
            if (zx_bad || !n || distance > zx_pos || n > zx_size - zx_pos) return 0;
            do { c = *ZX_AT(zx_pos - distance); zx_put(c); } while (--n && !zx_bad);
        }
        if (zx_bad) return 0;
        state = zx_bit() ? 2 : (state == 0 ? 1 : 0);
    }
}
