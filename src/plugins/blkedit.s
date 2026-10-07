; Direct service calls through the reserved even API table at $3F9E.
; The editor's own set: BLKVIEW next door keeps a different one, and each
; overlay carries only the thunks it calls.
.segment "CODE"
.export _v_cprintf
_v_cprintf: jmp ($3FD8)
.export _v_cputs
_v_cputs: jmp ($3FDC)
.export _v_cputc
_v_cputc: jmp ($3FDE)
.export _v_gotoxy
_v_gotoxy: jmp ($3FE0)
.export _v_revers
_v_revers: jmp ($3FE2)
.export _v_clrscr
_v_clrscr: jmp ($3FE6)
.export _v_cgetc
_v_cgetc: jmp ($3FE8)
.export _v_message
_v_message: jmp ($3FAE)
.export _v_confirm
_v_confirm: jmp ($3FB0)
.export _v_prompt
_v_prompt: jmp ($3FB2)
.export _v_strcpy
_v_strcpy: jmp ($3FEE)
.export _v_strcmp
_v_strcmp: jmp ($3FF0)

; crc512(p): the CRC-32 of the 512 bytes at p into _crc, low byte first --
; reflected, polynomial $EDB88320, initial value $FFFFFFFF, no final
; inversion (zlib's crc32 of the block, xor $FFFFFFFF). Bit by bit: about
; 0.2 s at 1 MHz, three times per W at most; a table would be 1 KB.
.importzp ptr1, tmp1
.export _crc512, _crc
.segment "BSS"
_crc: .res 4
.segment "CODE"
_crc512:
        sta ptr1
        stx ptr1+1
        lda #$FF
        sta _crc
        sta _crc+1
        sta _crc+2
        sta _crc+3
        ldx #2                  ; two pages
        ldy #0
@byte:  lda (ptr1),y
        eor _crc
        sta _crc
        lda #8
        sta tmp1
@bit:   lsr _crc+3
        ror _crc+2
        ror _crc+1
        ror _crc
        bcc @next
        lda _crc+3
        eor #$ED
        sta _crc+3
        lda _crc+2
        eor #$B8
        sta _crc+2
        lda _crc+1
        eor #$83
        sta _crc+1
        lda _crc
        eor #$20
        sta _crc
@next:  dec tmp1
        bne @bit
        iny
        bne @byte
        inc ptr1+1
        dex
        bne @byte
        rts
