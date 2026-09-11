; packfot.s -- the auxiliary half of a packed double hi-res picture.
;
; A service-table overlay reaches the program only through struct A2fcApi,
; which has no bank move: this is the one thing packfot.c cannot write in C.
; RAMRD/RAMWRT cover $0200-$BFFF, so flipping them by hand would send the C
; stack to the auxiliary bank as well; AUXMOVE walks the two banks itself.

        .export _pf_aux_move
        .segment "CODE"

; void pf_aux_move(void): $2000-$3FFF from the main bank to the auxiliary
; one in a single AUXMOVE ($C311) -- the move a2fc_mli.s makes for a raw
; DHGR file, repeated here for a packed one. Interrupts off for its
; duration: an interrupt taken with the banks half switched never comes
; back.
_pf_aux_move:
        lda #$00
        sta $3C                 ; A1 = $2000, the source
        sta $42                 ; A4 = $2000, the destination
        lda #$20
        sta $3D
        sta $43
        lda #$FF                ; A2 = $3FFF, the last source byte
        sta $3E
        lda #$3F
        sta $3F
        php
        sei
        sec                     ; carry set: main to auxiliary
        jsr $C311
        plp
        rts

; void pf_show(unsigned char two): the picture on the air, page 1, full
; screen. The four AN3 edges with 80COL high leave an RGB card (Le Chat
; Mauve, Video-7) on COL140, its power-on state: that latch is clocked by
; the edge whether we want it or not, and 80COL is its data. 80COL then goes
; back off for a plain hi-res, or one more edge arms DHIRES for a double
; one. TXTCLR last, once the page is armed: graphics turned on earlier shows
; the text page reread in low resolution for the length of two writes.
; Written here rather than in C: eleven soft-switch writes cost cc65 four
; bytes each, and the window is 1,280 bytes for everything.
        .export _pf_show, _pf_main_bank
_pf_show:
        tax                     ; A = 0: plain hi-res
        sta $C000               ; 80STORE off
        sta $C00D               ; 80COL on: the latch data
        sta $C05E               ; one edge
        sta $C05F
        sta $C05E               ; two: COL140
        sta $C05F
        cpx #0
        beq @plain
        sta $C05E               ; DHIRES on: double hi-res
        bne @arm                ; always: X is not 0
@plain: sta $C00C               ; 80COL off
@arm:   sta $C057               ; hi-res
        sta $C054               ; page 1
        sta $C052               ; mixed off
        sta $C050               ; graphics
        rts

; void pf_main_bank(void): $2000-$3FFF back on the main bank, whatever a
; picture seen earlier left armed. With HIRES still on, 80STORE would route
; the page to the auxiliary bank and the decoder would write into the wrong
; one.
_pf_main_bank:
        lda #0
        sta $C054               ; PAGE2 off
        sta $C000               ; 80STORE off
        sta $C002               ; RAMRD main
        sta $C004               ; RAMWRT main
        rts
