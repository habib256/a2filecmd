; Shared FONTVIEW HRCG glyph: g = glyph index, ptr3 = its eight rows.
; Writes only MAIN HGR, preserves ptr3. fr starts at zero.
grow:   lda     g                       ; row (g / 16) * 10 + r
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     t
        asl     a
        asl     a
        adc     t
        asl     a
        adc     fr
        jsr     hv_row
        sta     ptr1
        stx     ptr1+1
        ldy     fr
        lda     (ptr3),y
        pha
        lda     g                       ; byte 4 + (g % 16) * 2
        and     #15
        asl     a
        adc     #4
        tay
        pla
        sta     (ptr1),y
        inc     fr
        lda     fr
        cmp     #8
        bne     grow
