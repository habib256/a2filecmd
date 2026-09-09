; format_mli.s -- three low-level calls for FORMAT.SYSTEM.
;
;   unsigned char __fastcall__ mli_call(unsigned char cmd, void* parms);
;       Any MLI call; returns the ProDOS error code, 0 if good.
;   unsigned char __fastcall__ driver_call(unsigned char unit, unsigned char cmd, unsigned char lc);
;       Calls the unit's ProDOS block driver (DEVADR table, $BF10) with
;       command cmd (0 STATUS, 3 FORMAT), buffer $6800, block 0;
;       lc != 0 switches language card bank 1 to read/write around the
;       call, as the /RAM driver requires (Hyper-FORMAT).
;       Returns the error code; STATUS leaves the number of blocks in
;       driver_blocks.

        .export _mli_call, _driver_call, _driver_blocks
        .import popa

        .segment "BSS"
_driver_blocks: .res 2

        .segment "DATA"
_mli_call:
        sta mparms
        stx mparms+1
        jsr popa
        sta mcmd
        jsr $BF00
mcmd:   .byte 0
mparms: .word 0
        ldx #0
        rts

_driver_call:
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
        lda #$68
        sta $45                 ; buffer $6800
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
        stx _driver_blocks
        sty _driver_blocks+1
        pha
        lda lcflag
        beq :+
        bit $C082               ; ROM back in, as before the call
:       pla
        plp
        bcs :+
        lda #0
:       ldx #0
        rts
dispatch:
        jmp (vector)
vector: .word 0
lcflag: .byte 0
