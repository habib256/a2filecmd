; paint816.s -- the auxiliary half of a packed double hi-res picture.
;
; A service-table overlay reaches the program only through struct A2fcApi,
; which has no bank move: this is the one thing paint816.c cannot write in C.
; RAMRD/RAMWRT cover $0200-$BFFF, so flipping them by hand would send the C
; stack to the auxiliary bank as well; AUXMOVE walks the two banks itself.

        .export _p8_aux_move
        .segment "CODE"

; void pf_aux_move(void): $2000-$3FFF from the main bank to the auxiliary
; one in a single AUXMOVE ($C311) -- the move a2fc_mli.s makes for a raw
; DHGR file, repeated here for a packed one. Interrupts off for its
; duration: an interrupt taken with the banks half switched never comes
; back.
_p8_aux_move:
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
        .export _p8_show, _p8_main_bank
_p8_show:
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
_p8_main_bank:
        lda #0
        sta $C054               ; PAGE2 off
        sta $C000               ; 80STORE off
        sta $C002               ; RAMRD main
        sta $C004               ; RAMWRT main
        rts


; The picture goes down a byte COLUMN, the rightmost one first: 192 rows, then
; one column to the left. Written here rather than in C because a hi-res row
; address is not a pointer that can be stepped: the low three bits of the row
; number are worth $400 each, the next three $80, the top two 40, so moving
; down a row is one of three additions and three counters say which. cc65
; spends 97 bytes on that -- a thirteenth of the whole window -- for something
; that runs 15,360 times on a double hi-res picture.
;
; The store address lives in the STA instruction itself: an absolute,X store
; is the shortest way into a page whose row moves under us, and the column is
; X. Plain 6502 throughout: this file is assembled for the 6502 edition too,
; so no STZ.
        .export _p8_top, _p8_put, _p8_col

; void p8_top(void): the top of the rightmost column, for a fresh plane.
_p8_top:
        lda     #39
        sta     _p8_col
        lda     #0
        sta     _p8_g0
        sta     _p8_g1
        sta     _p8_g2
home:   sta     store+1                 ; and the address back to $2000
        lda     #$20
        sta     store+2
        rts

; void __fastcall__ p8_put(unsigned char v): one byte, and one row down.
_p8_put:
        ldx     _p8_col
        bmi     done                    ; column 0 has gone to 255: plane full
store:  sta     $2000,x                 ; patched: the row this column is on
        inc     _p8_g0
        lda     _p8_g0
        cmp     #8
        bcs     group
        lda     store+2                 ; one row down: + $400
        clc
        adc     #4
        sta     store+2
        rts
group:  lda     #0                      ; the next group of eight rows:
        sta     _p8_g0                  ; + $80 - $1C00
        lda     store+1
        clc
        adc     #$80
        sta     store+1
        lda     store+2
        adc     #$E4                    ; -$1C, with the carry from the low half
        sta     store+2
        inc     _p8_g1
        lda     _p8_g1
        cmp     #8
        bcc     done
        lda     #0                      ; the next third of the screen:
        sta     _p8_g1                  ; + 40 - $400
        lda     store+1
        clc
        adc     #40
        sta     store+1
        lda     store+2
        adc     #$FC                    ; -4, with the carry
        sta     store+2
        inc     _p8_g2
        lda     _p8_g2
        cmp     #3
        bcc     done
        lda     #0                      ; the column is done: one column left,
        sta     _p8_g2                  ; and the address back to the top
        dec     _p8_col
        lda     #0
        beq     home                    ; always: A is 0
done:   rts

        .segment "BSS"
_p8_col: .res 1                         ; 39 down to 0, then 255: the plane is full
_p8_g0:  .res 1                         ; the row number's low three bits
_p8_g1:  .res 1                         ; its next three
_p8_g2:  .res 1                         ; its top two: the third of the screen
