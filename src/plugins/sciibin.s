; sciibin.s -- CRC-16/XMODEM for sciibin.c, through a table.
;
; void bs_init(void): the 256-entry table (high bytes, low bytes).
; void __fastcall__ bs_crc(const unsigned char* p): 48 bytes at p added to
; bs_sum (low byte first): crc = crc << 8 ^ table[crc >> 8 ^ byte].
; A BinSCII data line is 48 bytes; the header and CRC fields go through C.
; In C, a 12,288-byte segment took seconds; here, a fraction of one.

        .export _bs_init, _bs_crc, _bs_sum
        .importzp ptr1
        .segment "CODE"

_bs_init:
        ldx     #0
build:  lda     #0
        sta     lo
        stx     hi                      ; crc = i << 8
        ldy     #8
shift:  asl     lo
        rol     hi
        bcc     next
        lda     hi
        eor     #$10
        sta     hi
        lda     lo
        eor     #$21
        sta     lo
next:   dey
        bne     shift
        lda     hi
        sta     thi,x
        lda     lo
        sta     tlo,x
        inx
        bne     build
        rts

_bs_crc:
        sta     ptr1
        stx     ptr1+1
        ldy     #0
each:   lda     (ptr1),y
        eor     _bs_sum+1
        tax
        lda     _bs_sum                 ; crc << 8
        eor     thi,x
        sta     _bs_sum+1
        lda     tlo,x
        sta     _bs_sum
        iny
        cpy     #48
        bne     each
        rts

        .segment "BSS"
_bs_sum: .res   2
thi:    .res    256
tlo:    .res    256
lo:     .res    1
hi:     .res    1
