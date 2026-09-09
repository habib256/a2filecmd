/*
 * MEMORY SWAP - Video switches (80-column text / full DHGR / mixed DHGR)
 *
 * No screen copy here, and that is the important point: the text never
 * leaves $400-$7FF while we are in graphics. The RLE decoder writes to
 * $2000-$3FFF, the ProDOS I/O buffer lives at $800-$BFF (text page 2), and
 * nothing runs between two key presses. Going back to text is therefore
 * just turning TXTSET back on.
 *
 * The old version saved and restored 2 KB at every switch -- two 1 KB
 * copies, one per bank, the 80-column screen straddling both -- that is
 * ~4000 iterations of a C loop to rewrite the screen with what it already
 * held. That was the slowness of the transitions, and the 2 KB of BSS go
 * away with it (memory is THE constraint of the project, cf. TODO.md).
 */

#include <stdint.h>

/* Apple II soft switches */
#define TXTCLR  (*(volatile uint8_t*)0xC050)  /* Graphics mode */
#define TXTSET  (*(volatile uint8_t*)0xC051)  /* Text mode */
#define MIXCLR  (*(volatile uint8_t*)0xC052)  /* Mixed mode OFF */
#define MIXSET  (*(volatile uint8_t*)0xC053)  /* Mixed mode ON */
#define LOWSCR  (*(volatile uint8_t*)0xC054)  /* Page 1 visible */
#define HISCR   (*(volatile uint8_t*)0xC055)  /* Page 2 visible */
#define LORES   (*(volatile uint8_t*)0xC056)  /* Low-res */
#define HIRES   (*(volatile uint8_t*)0xC057)  /* Hi-res */
#define STORE80ON  (*(volatile uint8_t*)0xC001)
#define STORE80OFF (*(volatile uint8_t*)0xC000)
#define RAMRDOFF   (*(volatile uint8_t*)0xC002)
#define RAMWRTOFF  (*(volatile uint8_t*)0xC004)
#define COL80OFF   (*(volatile uint8_t*)0xC00C)
#define COL80ON    (*(volatile uint8_t*)0xC00D)
#define DHIRESON   (*(volatile uint8_t*)0xC05E)
#define DHIRESOFF  (*(volatile uint8_t*)0xC05F)

static uint8_t current_mode = 0;               /* 0=text, 1=HGR, 2=mixed */

/*
 * Entering graphics: memory routing, then HGR page 1 visible.
 *
 * The four AN3 pulses program the FIFO of the Le Chat Mauve / Video-7
 * observer into COL140: 80COL is its data line, the AN3 edge its clock.
 * They are played ONLY HERE, on entering graphics. Replaying them at every
 * full <-> mixed switch would make the screen flicker for nothing, while
 * the picture is already on air.
 *
 * Double hi-res mode stays active: 80COL interleaves the auxiliary and
 * main planes, AN3/DHIRES selects the 140x192 decoding in sixteen
 * colours.
 */
static void enter_graphics(void) {
    /* 80-column text routes $400-$7FF (and $2000-$3FFF) through auxiliary
     * RAM. Restore main RAM before showing HGR page 1, which is where the
     * decoder wrote. */
    STORE80OFF = 1;
    RAMRDOFF = 1;
    RAMWRTOFF = 1;

    /* The RGB card keeps its own two-bit latch. Two AN3 edges with 80COL=1
     * load 11 = COL140 on Feline / Video-7. The last C05E then re-enables
     * the //e's native DHGR without creating a third edge. Composite
     * ignores this latch; that is why the old sequence looked correct
     * under OpenEmulator but not through Le Chat Mauve. */
    COL80ON = 1;
    DHIRESON = 1; DHIRESOFF = 1;
    DHIRESON = 1; DHIRESOFF = 1;
    DHIRESON = 1;

    HIRES = 1;    /* Hi-res */
    LOWSCR = 1;   /* Page 1 */
    /* No TXTCLR here: the caller turns graphics on, once MIXCLR or MIXSET
     * is set. Turning text off before HIRES is armed makes the text page
     * show up reread as low resolution, and before MIXSET makes the four
     * bottom lines flicker. A few microseconds, but they sometimes land in
     * the displayed frame. */
}

/*
 * Full-screen DHGR
 */
void switch_to_hgr(void) {
    /* Always replay the full sequence. current_mode describes what the
     * game asked for, not necessarily the hardware state left by ProDOS,
     * the 80-column firmware or an overlay. An optimisation based on
     * current_mode could therefore leave the Apple II in plain HGR. */
    enter_graphics();
    MIXCLR = 1;
    TXTCLR = 1;   /* graphics last: the page is ready */
    current_mode = 1;
}

/*
 * DHGR + 4 lines of 80-column text at the bottom
 */
void switch_to_mixed(void) {
    /* Same rule as full screen: first restore a known DHGR page 1, then
     * only open the four text lines. */
    enter_graphics();
    /* The 4 bottom lines read the interleaved text page: without 80COL they
     * would show in 40 columns, that is every other column.
     *
     * And 80STORE, which enter_graphics had just cut, must be PUT BACK: mixed
     * is the only graphics mode in which text is WRITTEN, and the 80-column
     * firmware reaches the auxiliary bank through 80STORE + PAGE2. Without
     * it, half the characters go nowhere and the screen shows two
     * interleaved texts -- the old one in the even columns, the new one in
     * the odd ones. The picture does not move for all that: under 80STORE
     * the hi-res screen stays forced onto page 1 in the main bank. */
    STORE80ON = 1;
    COL80ON = 1;
    DHIRESON = 1;
    MIXSET = 1;
    TXTCLR = 1;   /* graphics last: the page is ready */
    current_mode = 2;
}

/*
 * 80-column text
 */
void switch_to_text(void) {
    /* Nothing to repaint: $400-$7FF has not moved. Put back the routing the
     * 80-column firmware expects for its next writes, turn the 80-column
     * display back on, and make the text visible last. */
    STORE80ON = 1;
    COL80ON = 1;
    DHIRESOFF = 1;
    MIXCLR = 1;
    TXTSET = 1;
    current_mode = 0;
}

/*
 * Utility function: current state
 */
uint8_t get_current_mode(void) {
    return current_mode;
}
