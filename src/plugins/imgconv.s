; imgconv.s -- the DiskCopy 4.2 checksum, for imgconv.c.
;
; void dc_add(const unsigned char* p): the 128 big-endian words of the
; 256 bytes at p added to dc_sum (32 bits, low byte first), the sum rotated
; right by one bit after each word (tools/dc42.py: checksum). imgconv.c
; calls it for each half of a block. In C the 32-bit rotation, 409,600
; times over an 800K disk, would take minutes.

        .export _dc_add, _dc_sum
        .importzp ptr1
        .segment "CODE"

_dc_add:
        sta     ptr1
        stx     ptr1+1
        ldy     #0
word:   lda     (ptr1),y                ; the high byte
        tax
        iny
        lda     (ptr1),y                ; the low byte
        iny
        clc
        adc     _dc_sum
        sta     _dc_sum
        txa
        adc     _dc_sum+1
        sta     _dc_sum+1
        bcc     rotate
        inc     _dc_sum+2
        bne     rotate
        inc     _dc_sum+3
rotate: lsr     _dc_sum+3
        ror     _dc_sum+2
        ror     _dc_sum+1
        ror     _dc_sum
        bcc     next
        lda     _dc_sum+3               ; bit 0 comes back as bit 31
        ora     #$80
        sta     _dc_sum+3
next:   cpy     #0
        bne     word
        rts

        .segment "BSS"
_dc_sum: .res   4
