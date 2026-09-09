; format_mli.s -- direct block-driver calls for FORMAT.PLG.
; format_driver_call(unit, command, lc): STATUS (0) or FORMAT (3).
; Buffer $3E00, block 0; STATUS returns its capacity in format_driver_blocks.
; Bank-1 drivers run with interrupts disabled, and return to A2FC's bank 2.

        .export _format_driver_call, _format_driver_blocks
        .import popa
        .segment "FORMATBSS"
_format_driver_blocks: .res 2
        .segment "FORMAT"
_format_driver_call:
        php
        sei
        sta lcflag
        jsr popa
        sta $42                 ; command
        jsr popa
        sta $43                 ; unit DSSS0000
        lsr a
        lsr a
        lsr a
        lsr a
        asl a                   ; index x 2 into DEVADR
        tax
        lda $BF10,x
        sta vector
        lda $BF11,x
        sta vector+1
        lda #$3E
        sta $45                 ; buffer $3E00
        lda #$00
        sta $44
        sta $46
        sta $47                 ; block 0
        lda lcflag
        beq :+
        lda $C08B               ; language card bank 1, read and write
        lda $C08B
:       jsr dispatch
        php
        stx _format_driver_blocks
        sty _format_driver_blocks+1
        pha
        lda lcflag
        beq :+
        bit $C080               ; A2FC language-card bank 2, read-only
:       pla
        plp
        bcs :+
        lda #0
:       plp
        ldx #0
        rts
dispatch:
        jmp (vector)
vector: .word 0
lcflag: .byte 0
