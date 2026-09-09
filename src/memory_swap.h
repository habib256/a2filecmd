/*
 * MEMORY SWAP - Video switches (80-column text / full HGR / mixed HGR)
 */

#ifndef MEMORY_SWAP_H
#define MEMORY_SWAP_H

#include <stdint.h>

/* Video switches. They touch ONLY soft switches: the text screen stays in
 * place at $400-$7FF throughout the time in graphics, so there is nothing
 * to save or restore. See memory_swap.c. */
void switch_to_hgr(void);         /* HGR page 1, full screen */
void switch_to_text(void);        /* 80-column text */
void switch_to_mixed(void);       /* HGR + 4 lines of 80-column text */

/* Utility function */
uint8_t get_current_mode(void);   /* 0=text, 1=HGR, 2=mixed */

#endif /* MEMORY_SWAP_H */