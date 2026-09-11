; extasie.s -- the parts of the Extasie viewer that C cannot write, or cannot
; write small enough.
;
; A service-table overlay reaches the program only through struct A2fcApi,
; which has no bank move; and the window below $2000 is 1,280 bytes for the
; whole overlay, which the picture geometry alone would eat a tenth of in
; cc65. Plain 6502 throughout: this file is assembled for the 6502 edition
; too, so no STZ.

        .export _ex_aux_move, _ex_show, _ex_main_bank
        .export _ex_top, _ex_put, _ex_col
        .segment "CODE"

; void ex_aux_move(void): $2000-$3FFF from the main bank to the auxiliary
; one in a single AUXMOVE ($C311). Interrupts off for its duration: an
; interrupt taken with the banks half switched never comes back.
_ex_aux_move:
        lda     #$00
        sta     $3C                     ; A1 = $2000, the source
        sta     $42                     ; A4 = $2000, the destination
        lda     #$20
        sta     $3D
        sta     $43
        lda     #$FF                    ; A2 = $3FFF, the last source byte
        sta     $3E
        lda     #$3F
        sta     $3F
        php
        sei
        sec                             ; carry set: main to auxiliary
        jsr     $C311
        plp
        rts

; void ex_show(void): the picture on the air in the Chat Mauve's MIXED mode,
; the one Extasie draws in -- 560 dots in black and white and 140 cells of
; sixteen colours, chosen per byte, which is what the format is for.
;
; The card holds a two-bit shift register clocked by the $C05E -> $C05F edge,
; its data being 80COL (US 4,631,692). Pushing 0 then 1 leaves it on 01,
; MIXED; 1 then 1 would be COL140, the power-on state the rest of the program
; restores. $C05E is then written once more, alone, to arm DHIRES: with no
; $C05F after it there is no edge, so the latch keeps what it was given.
; 80COL stays ON, as double hi-res needs. Without an RGB card these writes
; are the ordinary double hi-res switches and the picture comes out in the
; machine's own colours.
_ex_show:
        lda     #0
        sta     $C000                   ; 80STORE off
        sta     $C00C                   ; 80COL off: the latch data, 0
        sta     $C05E
        sta     $C05F                   ; one edge
        sta     $C00D                   ; 80COL on: the data, 1
        sta     $C05E
        sta     $C05F                   ; two: the latch is 01, MIXED
        sta     $C05E                   ; DHIRES on, and no edge with it
        sta     $C057                   ; hi-res
        sta     $C054                   ; page 1
        sta     $C052                   ; mixed text off
        sta     $C050                   ; graphics
        rts

; void ex_main_bank(void): $2000-$3FFF back on the main bank, whatever a
; picture seen earlier left armed. With HIRES still on, 80STORE would route
; the page to the auxiliary bank and the decoder would fill the wrong one.
_ex_main_bank:
        lda     #0
        sta     $C054                   ; PAGE2 off
        sta     $C000                   ; 80STORE off
        sta     $C002                   ; RAMRD main
        sta     $C004                   ; RAMWRT main
        rts

; The picture goes down a byte COLUMN, the leftmost first: 192 rows, then one
; column to the right, forty of them to a plane. A hi-res row address is not
; a pointer that can be stepped -- the low three bits of the row number are
; worth $400 each, the next three $80, the top two 40 -- so moving down a row
; is one of three additions and three counters say which. The store address
; lives in the STA instruction itself: an absolute,X store is the shortest
; way into a page whose row moves under us, and the column is X.
;
; The two planes are ONE stream: a record may in principle run from the last
; column of the auxiliary plane into the first of the main one, so the plane
; changes here, inside the write, and not between two passes in C. _ex_col
; only reaches 40 when the whole picture is in.
;
; void ex_top(void): the top of the leftmost column of the auxiliary plane.
_ex_top:
        lda     #0
        sta     _ex_col
        sta     _ex_plane
        sta     _ex_g0
        sta     _ex_g1
        sta     _ex_g2
home:   sta     store+1                 ; and the address back to $2000
        lda     #$20
        sta     store+2
        rts

; void __fastcall__ ex_put(unsigned char v): one byte, and one row down.
_ex_put:
        ldx     _ex_col
        cpx     #40
        bcs     done                    ; the fortieth column is past: plane full
store:  sta     $2000,x                 ; patched: the row this column is on
        inc     _ex_g0
        lda     _ex_g0
        cmp     #8
        bcs     group
        lda     store+2                 ; one row down: + $400
        clc
        adc     #4
        sta     store+2
        rts
group:  lda     #0                      ; the next group of eight rows:
        sta     _ex_g0                  ; + $80 - $1C00
        lda     store+1
        clc
        adc     #$80
        sta     store+1
        lda     store+2
        adc     #$E4                    ; -$1C, with the carry from the low half
        sta     store+2
        inc     _ex_g1
        lda     _ex_g1
        cmp     #8
        bcc     done
        lda     #0                      ; the next third of the screen:
        sta     _ex_g1                  ; + 40 - $400
        lda     store+1
        clc
        adc     #40
        sta     store+1
        lda     store+2
        adc     #$FC                    ; -4, with the carry
        sta     store+2
        inc     _ex_g2
        lda     _ex_g2
        cmp     #3
        bcc     done
        lda     #0                      ; the column is done: one column right,
        sta     _ex_g2                  ; and the address back to the top
        inc     _ex_col
        lda     _ex_col
        cmp     #40
        bcc     back                    ; still inside this plane
        ldx     _ex_plane
        bne     back                    ; the main plane is full: _ex_col stays 40
        inc     _ex_plane               ; the auxiliary plane is: hand it over
        jsr     _ex_aux_move
        lda     #0
        sta     _ex_col
back:   lda     #0
        jmp     home                    ; the address back to the top of the page
done:   rts

        .segment "BSS"
_ex_col: .res 1                         ; 0 to 39, then 40: the plane is full
_ex_g0:  .res 1                         ; the row number's low three bits
_ex_g1:  .res 1                         ; its next three
_ex_g2:  .res 1                         ; its top two: the third of the screen
_ex_plane: .res 1                       ; 0 the auxiliary plane, 1 the main one
