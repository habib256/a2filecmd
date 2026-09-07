; Compatible with the cc65 2.19 apple2enh callmli ABI. Keep its 18-byte
; parameter block in DATA: constructors call ProDOS BEFORE crt0 copies LC.
; BSS overlaps the pending LC load image and would corrupt its instructions.
; The protected $4E/$4F bytes are the monitor's random seed, as in cc65.
        .export callmli, mliparam
        .import __dos_type
        .segment "DATA"
callmli:
        sta command
        stx mliparam
        lda __dos_type
        beq unavailable
        lda $4E
        pha
        lda $4F
        pha
        jsr $BF00
command:
        .byte 0
        .word mliparam
        tax
        pla
        sta $4F
        pla
        sta $4E
        txa
        rts
unavailable:
        lda #1
        sec
        rts
mliparam:
        .res 18, 0
