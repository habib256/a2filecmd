; fixit_bits.inc -- the claim bitmap of FIXIT and REPAIR (fixit_walk.h).
;
; One bit per block, set when the walk reaches the block, $80 for the first
; block of a byte as in the ProDOS bitmap. A volume of up to 4 096 blocks
; keeps it in seen[], 512 bytes of BSS in the main bank. A bigger one keeps
; all 65 536 bits in the AUXILIARY bank, $4000-$5FFF, and the directory tree
; is walked ONCE: the old walk kept one 4 096-block window in seen[] and
; walked the whole tree again for every window, sixteen times on 32 MB.
;
; Reading the auxiliary bank (RAMRD) also fetches the instructions there, so
; the code from mirror_start to mirror_end is copied to the auxiliary bank at
; its own address by _bit_init, as UNSHRINK does (src/unshrink.s). Writing
; alone (RAMWRT) needs no copy: execution stays in the main bank. The zero
; page and the 6502 stack stay in the main bank throughout (ALTZP is never
; touched), and interrupts are off while the bank is switched.
;
; unsigned char __fastcall__ bit_test(unsigned int b);  the bit of b, 0 if clear
; unsigned char __fastcall__ bit_set(unsigned int b);   the same, then set
; void bit_init(void);                  copy the mirror, clear $4000-$5FFF
;
; _aux (a C variable) chooses the bank for bit_test and bit_set; bit_init is
; only called when it is 1.

RDMAIN  = $C002
RDAUX   = $C003
WRMAIN  = $C004
WRAUX   = $C005
AUXBITS = $40                   ; the auxiliary bitmap starts at $4000

        .importzp ptr1, tmp1, tmp2
        .import _seen, _aux
        .export _bit_test, _bit_set, _bit_init

        .segment "CODE"

; Copy the mirror to the auxiliary bank, then clear the 8 KB of bits there.
; Writes only: the loop runs in the main bank and reads its own bytes.
_bit_init:
        php
        sei
        sta     WRAUX
        ldy     #mirror_end - mirror_start
:       dey
        lda     mirror_start,y
        sta     mirror_start,y
        tya
        bne     :-
        sta     ptr1            ; A = 0: $4000, 32 pages of zeros
        ldx     #AUXBITS
        stx     ptr1+1
        ldx     #$20
:       sta     (ptr1),y
        iny
        bne     :-
        inc     ptr1+1
        dex
        bne     :-
        sta     WRMAIN
        plp
        rts

mirror_start:
; The two entry points share their body: Y = 0 tests, Y = $FF also sets.
; BIT abs swallows the LDY #$FF of the second entry.
_bit_test:
        ldy     #0
        .byte   $2C
_bit_set:
        ldy     #$FF
        sty     tmp2
        sta     ptr1
        and     #7
        tay
        lda     masks,y
        sta     tmp1
        txa                     ; ptr1 = b >> 3, on sixteen bits
        lsr     a
        ror     ptr1
        lsr     a
        ror     ptr1
        lsr     a
        ror     ptr1
        ldy     _aux
        bne     inaux
        tax                     ; b < 4096: 0 or 1
        lda     ptr1
        clc                     ; the last bit shifted out belongs to nobody
        adc     #<_seen
        sta     ptr1
        txa
        adc     #>_seen
        sta     ptr1+1
        bne     op              ; always: seen[] is not in page zero
inaux:  ora     #AUXBITS
        sta     ptr1+1
        php
        sei
        sta     RDAUX           ; from here on, the auxiliary copy executes
        sta     WRAUX
        jsr     op
        sta     RDMAIN
        sta     WRMAIN
        plp
        rts

; The byte is always written back: unchanged for a test, which spares a
; branch and touches only the bitmap.
op:     ldy     #0
        lda     (ptr1),y
        and     tmp1
        tax                     ; the bit before
        lda     tmp2
        and     tmp1
        ora     (ptr1),y
        sta     (ptr1),y
        txa
        ldx     #0
        rts

masks:  .byte   $80, $40, $20, $10, $08, $04, $02, $01
mirror_end:
        .assert mirror_end - mirror_start < 256, error, "FIXIT bit mirror too long"
