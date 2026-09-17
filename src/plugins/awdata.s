; awdata.s -- AppleWorks numbers printed by Applesoft's FOUT, for awdata.c.
;
; void aw_fout(unsigned char* d): the 8-byte little-endian double at d, as
; BASIC prints it, into aw_num (a zero-ended string, 16 characters at most),
; or "#NUM" when the ROM's numbers cannot hold it (tools/awdata_ref.py:
; mbf() and fout() are the reference).
;
; The ROM's packed number is an exponent byte (0 for zero; the value is
; 0.1mmm... x 2^(exponent - 128)) and four mantissa bytes, the sign in the
; place of the leading 1. A double is 1.fff... x 2^(e - 1023): the exponent
; is e - 894, and the mantissa the leading 1 and the top 31 bits of f, the
; 32nd rounding it.
;
; The ROM is read with the language card switched off ($C082) and put back
; on bank 2 for reading ($C080), the state crt0 leaves; nothing of the
; program in the language card runs in between, and interrupts are off.
; MOVFM ($EAF9) loads the number into FAC, FOUT ($ED34) writes its text at
; $0100. Both use the zero page from $5E up, the cc65 runtime's among it:
; $50-$FF is saved first and put back after. FOUT also counts on $A4 being
; 0, as BASIC leaves it: with another value 0.5 prints as .500592008.
;
; Built with AW_TEST (tools/test_awdata.py), the ROM is not called: aw_num
; gets the packed number in hex between < and >.

        .export _aw_fout, _aw_num
        .importzp ptr1
        .segment "CODE"

MOVFM   = $EAF9
FOUT    = $ED34

_aw_fout:
        sta     ptr1
        stx     ptr1+1
        ; t = 1 f51..f16: 40 bits, big-endian, from d6 (low 4 bits) to d2
        ldy     #6
        lda     (ptr1),y
        and     #$0F
        ora     #$10                    ; the leading 1
        sta     t
        ldx     #1
tcopy:  dey
        lda     (ptr1),y
        sta     t,x
        inx
        cpy     #2
        bne     tcopy
        ldx     #3                      ; the leading 1 to bit 39
shift:  asl     t+4
        rol     t+3
        rol     t+2
        rol     t+1
        rol     t
        dex
        bne     shift
        ; e = (d7 AND $7F) * 16 + d6 / 16, in ehi:elo
        ldy     #7
        lda     (ptr1),y
        sta     sign
        and     #$7F
        pha
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     ehi
        pla
        asl     a
        asl     a
        asl     a
        asl     a
        sta     elo
        dey
        lda     (ptr1),y
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        ora     elo
        sta     elo
        ora     ehi
        beq     zero                    ; e = 0: zero (or too small to show)
        ; the 32nd bit of f rounds (t+4, bit 7)
        lda     t+4
        bpl     exp
        inc     t+3
        bne     exp
        inc     t+2
        bne     exp
        inc     t+1
        bne     exp
        inc     t
        bne     exp
        lda     #$80                    ; 1.111... rounded up is 10.000...
        sta     t
        inc     elo
        bne     exp
        inc     ehi
        ; x = e - 894 must be 1 to 255
exp:    sec
        lda     elo
        sbc     #<894
        sta     mbf
        lda     ehi
        sbc     #>894
        bne     range                   ; below 0, or above 255
        lda     mbf
        beq     range
        lda     t                       ; the sign in place of the leading 1
        asl     a
        asl     sign
        ror     a
        sta     mbf+1
        lda     t+1
        sta     mbf+2
        lda     t+2
        sta     mbf+3
        lda     t+3
        sta     mbf+4
        jmp     rom
range:  ldx     #4
rcopy:  lda     num,x
        sta     _aw_num,x
        dex
        bpl     rcopy
        rts
zero:   ldx     #4                      ; A = 0: FOUT prints 0
zfill:  sta     mbf,x
        dex
        bpl     zfill

.ifdef AW_TEST
rom:    lda     #'<'
        sta     _aw_num
        ldx     #0
        ldy     #1
hex:    lda     mbf,x
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        jsr     digit
        lda     mbf,x
        and     #$0F
        jsr     digit
        inx
        cpx     #5
        bne     hex
        lda     #'>'
        sta     _aw_num,y
        lda     #0
        sta     _aw_num+12
        rts
digit:  cmp     #10
        bcc     isdec
        adc     #6                      ; carry set: 'A' - '0' - 10
isdec:  adc     #'0'
        sta     _aw_num,y
        iny
        rts
.else
rom:    ldx     #0
save:   lda     $50,x
        sta     zp,x
        inx
        cpx     #$B0
        bne     save
        lda     #0                      ; BASIC keeps $A4 at 0; FOUT rounds wrong
        sta     $A4                     ; with anything else there
        lda     #<mbf
        ldy     #>mbf
        php
        sei
        bit     $C082                   ; the ROM
        jsr     MOVFM
        jsr     FOUT
        bit     $C080                   ; the language card, bank 2, read
        plp
        ldy     #0
copy:   lda     $0100,y
        sta     _aw_num,y
        beq     done
        iny
        cpy     #16
        bne     copy
        lda     #0
        sta     _aw_num,y
done:   ldx     #0
back:   lda     zp,x
        sta     $50,x
        inx
        cpx     #$B0
        bne     back
        rts
.endif

        .segment "RODATA"
num:    .asciiz "#NUM"

        .segment "BSS"
t:      .res    5
sign:   .res    1
ehi:    .res    1
elo:    .res    1
mbf:    .res    5
.ifndef AW_TEST
zp:     .res    $B0
.endif
_aw_num: .res   17
