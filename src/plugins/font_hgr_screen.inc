; Shared MAIN-only FONTVIEW screen helpers. Caller supplies offsets.
hv_clear:
        lda     #0
        sta     $C000
        sta     $C002
        sta     $C004
        sta     $C054
        sta     ptr1
        lda     #$20
        sta     ptr1+1
        ldy     #0
        lda     #0
@byte:  sta     (ptr1),y
        iny
        bne     @byte
        inc     ptr1+1
        ldx     ptr1+1
        cpx     #$40
        bne     @byte
        rts

; hv_row: A = the screen row; A/X its address.
hv_row: pha
        and     #7
        asl     a
        asl     a
        ora     #$20
        sta     ptr1+1
        pla
        pha
        and     #$38
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        ora     ptr1+1
        sta     ptr1+1
        pla
        pha
        and     #8
        beq     @even
        lda     #$80
@even:  sta     ptr1
        pla
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        tax
        lda     offsets,x
        clc
        adc     ptr1
        ldx     ptr1+1
        rts

hv_show:
        lda     #0
        sta     $C000
        sta     $C00D
        sta     $C05E
        sta     $C05F
        sta     $C05E
        sta     $C05F
        sta     $C00C
        sta     $C057
        sta     $C054
        sta     $C052
        sta     $C050
        rts

