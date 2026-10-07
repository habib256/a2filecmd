; format_mli.s -- direct block-driver calls for FORMAT.PLG, and the two
; helpers its C code had no room for (online_unit, block_fold).
; format_driver_call(unit, command, lc): STATUS (0) or FORMAT (3).
; Buffer $3E00, block 0; STATUS returns its capacity in format_driver_blocks.
; Bank-1 drivers run with interrupts disabled, and return to A2FC's bank 2.
; tools/test_format_asm.py runs online_unit and block_fold under sim65.

        .export _format_driver_call, _format_driver_blocks, _block_fold, _online_unit
        .import popa, popax
        .importzp ptr1, ptr2, tmp1, tmp2
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
        ; A2FC language-card bank 2, read-only, whatever the driver left:
        ; VDrive's page-3 thunk (DEVADR $0300, so lcflag 0) returns with
        ; ProDOS's bank 1 in, and no MLI exit is there to put ours back.
        bit $C080
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

; unsigned int __fastcall__ block_fold(unsigned int sig);
; For each of the 512 bytes of $3E00: sig = rotate_left(sig, 1) + byte,
; the checksum identify folds its blocks into (format.c).
_block_fold:
        sta tmp1                ; sig, low
        stx tmp2                ; sig, high
        ldy #$00
        sty ptr1
        lda #$3E
        sta ptr1+1
@byte:  lda tmp2
        asl a                   ; C = bit 15
        rol tmp1
        rol tmp2                ; rotated left by one
        lda (ptr1),y
        clc
        adc tmp1
        sta tmp1
        bcc :+
        inc tmp2
:       iny
        bne @byte
        inc ptr1+1
        lda ptr1+1
        cmp #$40
        bne @byte
        lda tmp1
        ldx tmp2
        rts

; unsigned char __fastcall__ online_unit(const char* name, unsigned char skip);
; ON_LINE for all units into $3E00 (16 records of 16 bytes: DSSSLLLL, then
; the name; LLLL = 0 for an error record; a zero byte ends a shorter list).
; Returns the first unit (DSSS0000) other than skip whose volume is the name
; at name -- ended by '/' or by its zero byte -- 0 if none, $FF if the call
; failed: the caller refuses then.
_online_unit:
        sta olskip              ; outside the zero page: a driver may use it
        lda #0                  ; a stale record must not be read as a volume
        tay
:       sta $3E00,y
        iny
        bne :-
        jsr $BF00
        .byte $C5               ; ON_LINE
        .word olparm
        php
        jsr popax               ; name, after the call for the same reason
        sta ptr2
        stx ptr2+1
        plp
        bcs @fail
        lda #$3E
        sta ptr1+1
        ldx #0                  ; X: the record's offset
@rec:   lda $3E00,x
        beq @none               ; the end of the list
        and #$0F
        beq @next               ; an error record
        tay                     ; Y: the name length
        lda (ptr2),y            ; the searched name must end there
        beq :+
        cmp #'/'
        bne @next
:       lda $3E00,x
        and #$F0
        cmp olskip
        beq @next               ; the unit to skip
        stx ptr1
        inc ptr1                ; ptr1: the record's name
        dey
@cmp:   lda (ptr1),y
        cmp (ptr2),y
        bne @next
        dey
        bpl @cmp
        lda $3E00,x             ; found: its unit
        and #$F0
        ldx #0
        rts
@next:  txa
        clc
        adc #16
        tax
        bne @rec                ; 16 records at most
@none:  lda #0
        .byte $2C               ; BIT abs: skips the lda #$FF
@fail:  lda #$FF
        ldx #0
        rts
olparm: .byte 2, 0              ; all units
        .word $3E00
olskip: .byte 0
