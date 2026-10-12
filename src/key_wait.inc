; Shared interruptible delay. A: positive number of 65536 iterations of
; 11 cycles (~0.72 s at 1 MHz). Returns A=0 on timeout, A=1 on a pending
; keyboard key (left unread); X=0 in both cases.
.macro a2fc_key_wait name
        .export name
name:
        ldx #0
        ldy #0
@loop:
        bit $C000
        bmi @key
        dex
        bne @loop
        dey
        bne @loop
        sec
        sbc #1
        bne @loop
        rts
@key:
        ldx #0
        lda #1
        rts
.endmacro
