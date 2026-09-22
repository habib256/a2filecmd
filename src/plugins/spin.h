/* spin.h -- a sign of life for a long phase with no bar to move.
 *
 * spin() turns the resident's activity cell (row 21, column 79 of the MAIN
 * text page, $06F7, where activity_tick draws) between / and \. One store
 * to one text cell: no disk, no AUX, and right with 80STORE on or off, so a
 * picture viewer may call it while it decodes behind the "Loading" screen.
 * Never from a lo-res viewer (DGR): its picture lives in the text page.
 * 15 bytes, 3 per call. On the host, it counts: tools/test_*.py check it. */
#ifndef SPIN_H
#define SPIN_H
#ifdef PLUGIN_HOST
static unsigned long spins;
static void spin(void) { ++spins; }
#else
static void spin(void)
{
    *(volatile unsigned char*)0x6F7 = *(volatile unsigned char*)0x6F7 == 0xAF ? 0xDC : 0xAF;
}
#endif
#endif
