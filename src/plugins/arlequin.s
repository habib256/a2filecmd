; arlequin.s -- the decoder of the Arlequin viewer, and the screen around it.
;
; The stream is GLI16.2's (tools/arlequin_ref.py has the format and where it
; was read); a picture is rows of byte columns, each an auxiliary byte then a
; main one, so the two planes are written in ONE pass: the auxiliary byte
; with RAMWRT on for its single store, interrupts off. Only writes move, so
; this code, in the main bank below $2000, keeps running where it is.
; Plain 6502 throughout: the 6502 edition assembles this file too.

        .export _ar_decode, _ar_show, _ar_main_bank, _ar_aux_move
        .export _ar_dry, _ar_win
        .import _ar_read, _ar_buf
        .importzp ptr4
        .segment "CODE"

; unsigned char ar_decode(void): the whole picture, from the start of the
; file just opened. 1 when every byte of it came; 0 when the stream ran out
; first; 2 when the header is no Arlequin header. Nothing is stored in a
; checking pass (_ar_dry). The header also sets where the picture goes:
; centred, on whole groups, and _ar_win says it leaves black around it.
bad:    lda     #2                      ; within a branch of the header checks
        ldx     #0
        rts
_ar_decode:
        lda     #0
        sta     at
        sta     have
        tax
hdr:    jsr     getb
        bcs     bad                     ; shorter than a header
        sta     head,x
        inx
        cpx     #4
        bne     hdr
        lda     head+2
        cmp     #'g'
        bne     bad
        lda     head+3
        cmp     #'s'
        bne     bad
        lda     head                    ; the width: 1 to 20 groups
        beq     bad
        cmp     #21
        bcs     bad
        sta     width
        eor     #20
        sta     _ar_win                 ; nonzero: narrower than the screen
        lda     #20
        sec
        sbc     width
        and     #$FE                    ; whole groups, two columns each
        sta     left
        lda     head+1                  ; the height: 1 to 192 rows
        beq     bad
        cmp     #193
        bcs     bad
        sta     rows
        eor     #192
        ora     _ar_win
        sta     _ar_win
        lda     #192
        sec
        sbc     rows
        lsr     a
        sta     row
        lda     #1
        sta     count
        lda     #0
        sta     last
        lda     #$FF
        sta     mask
rowl:   lda     row
        jsr     setrow
        ldx     left
        lda     width
        asl     a
        sta     cols                    ; two byte columns to a group
coll:   jsr     next
        bcs     fail
        ldy     _ar_dry
        bne     skipa
        php
        sei
        sta     $C005                   ; RAMWRT on: the auxiliary byte
storea: sta     $2000,x                 ; patched: this row
        sta     $C004                   ; RAMWRT off
        plp
skipa:  jsr     next
        bcs     fail
        ldy     _ar_dry
        bne     skipm
storem: sta     $2000,x                 ; patched: this row, the main byte
skipm:  inx
        dec     cols
        bne     coll
        inc     row
        dec     rows
        bne     rowl
        lda     #1
        ldx     #0
        rts
fail:   lda     #0
        tax
        rts

; The next output byte in A, carry clear; carry set once the stream is out.
; X is kept: it is the column.
next:   dec     count
        bne     rot                     ; a run is still going
        lda     #1
        sta     count
nloop:  jsr     getb
        bcs     done
        cmp     #$80
        bcs     lit
        cmp     #0
        bne     run
        lda     mask                    ; $00: colour <-> black and white
        eor     #$80
        sta     mask
        jmp     nloop
run:    pha                             ; the last byte takes bit 7 from bit 6
        lda     last
        and     #$7F
        sta     last
        pla
        cmp     #$40
        bcc     short
        pha
        lda     last
        ora     #$80
        sta     last
        pla
short:  and     #$3F                    ; 0 is 256: the decrement wraps
        sta     count
rot:    lda     last                    ; rotated left, bit 7 into bit 0
        cmp     #$80
        rol     a
lit:    sta     last
        ora     #$80
        and     mask
        clc
done:   rts

; The next stream byte in A, carry clear; carry set at the end. A refill is
; the C of ar_read (arlequin.c), which may use any register and the zero
; page: the column and the buffer pointer are put back after it.
getb:   ldy     at
        cpy     have
        bne     fetch
        stx     savex
        jsr     _ar_read
        ldx     savex
        sta     have
        lda     _ar_buf
        sta     ptr4
        lda     _ar_buf+1
        sta     ptr4+1
        ldy     #0
        sty     at
        lda     have
        bne     fetch
        sec
        rts
fetch:  lda     (ptr4),y
        inc     at
        clc
        rts

; setrow: A = the screen row; both stores patched with its address. A hi-res
; row is $2000 + (y AND 7) * $400 + the text row base of y / 8, which is
; ((y / 8) MOD 8) * $80 + (y / 64) * $28.
setrow: pha
        lsr     a
        lsr     a
        lsr     a
        tay                             ; y / 8
        and     #7
        lsr     a                       ; carry: an odd text row, + $80
        sta     hi
        lda     #0
        bcc     even
        lda     #$80
even:   sta     lo
        tya
        lsr     a
        lsr     a
        lsr     a
        tay                             ; y / 64, 0 to 2
        beq     third
tl:     lda     lo
        clc
        adc     #$28
        sta     lo
        dey
        bne     tl
third:  pla
        and     #7
        asl     a
        asl     a
        clc
        adc     hi
        adc     #$20
        sta     storem+2
.ifdef ARL_TEST
        adc     #$40                    ; sim65 has no auxiliary bank: $6000 up
.endif
        sta     storea+2
        lda     lo
        sta     storea+1
        sta     storem+1
        rts

; void ar_aux_move(void): $2000-$3FFF from the main bank to the auxiliary
; one in a single AUXMOVE ($C311), interrupts off -- the black around a
; picture smaller than the screen, for the auxiliary plane.
_ar_aux_move:
        lda     #$00
        sta     $3C
        sta     $42
        lda     #$20
        sta     $3D
        sta     $43
        lda     #$FF
        sta     $3E
        lda     #$3F
        sta     $3F
        php
        sei
        sec
        jsr     $C311
        plp
        rts

; void ar_show(void): the picture on the air in the Chat Mauve's MIXED mode,
; as EXTASIE shows its own (extasie.s says why each switch): bit 7 of a byte
; chooses sixteen colours or black and white, byte by byte. Without an RGB
; card these are the ordinary double hi-res switches.
_ar_show:
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

; void ar_main_bank(void): $2000-$3FFF on the main bank for reading and
; writing, whatever a picture seen earlier left armed.
_ar_main_bank:
        lda     #0
        sta     $C054                   ; PAGE2 off
        sta     $C000                   ; 80STORE off
        sta     $C002                   ; RAMRD main
        sta     $C004                   ; RAMWRT main
        rts

        .segment "BSS"
_ar_dry: .res 1                         ; 1: a checking pass, nothing stored
_ar_win: .res 1                         ; nonzero: smaller than the screen
head:   .res 4
width:  .res 1                          ; groups of seven cells, 1 to 20
left:   .res 1                          ; the first byte column
count:  .res 1
last:   .res 1
mask:   .res 1
row:    .res 1
rows:   .res 1
cols:   .res 1
at:     .res 1
have:   .res 1
savex:  .res 1
hi:     .res 1
lo:     .res 1
