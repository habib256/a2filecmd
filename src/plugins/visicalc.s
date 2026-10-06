; visicalc.s -- the VISICALC overlay: VisiCalc worksheets (/SS files),
; recalculated once as VisiCalc does on loading them and shown as it shows
; them (docs/VISICALC-FORMAT.md; tools/visicalc_ref.py is the reference,
; tools/test_visicalc.py and bench/visicalc.py hold this to it). All of it
; is here; visicalc.c gives the header and the services' offsets.
;
; In four pieces (sdk/visicalc.cfg): the CODE stays at $1B00; VCA reads the
; file (pass 1 counts, pass 2 fills the cell table), VCB recalculates, VCC
; shows -- three phases that take turns in the swap area, VCB and VCC read
; from A2FILE/VISICALC.BIN. The cell table holds the value cells only, 8
; bytes each (row, packed value), column after column: in MAIN after the
; BSS, or in AUX $4000-$BEFF with the user's consent (tread/twrite & co).
; Labels, formats and formulas are read again from the file when needed;
; rowlo/rowhi say where each row's lines start (VisiCalc writes the rows in
; descending order). Read-only: no file is written.
;
; Numbers are VisiCalc's own: decimal, a mantissa of six base-100 digits
; (one BCD byte each, the first non-zero) and an exponent e, the value being
; 0.m0m1..m5 (base 100) x 100^e, with -32 <= e <= 31. Every operation is
; truncated to those six bytes; a result out of range is ERROR. This is
; what makes 1/3*3 read .999999999999 and 1E12+1-1E12 read 0, as VisiCalc
; shows them (tools/visicalc_ref.py, docs/VISICALC-FORMAT.md).
;
; A value at work is unpacked, 9 bytes: type (0 a number, then ERROR, NA,
; TRUE, FALSE, EMPTY -- a blank cell or a label read by a formula), sign
; ($00 or $80), exponent + 64, six mantissa bytes. Zero is a mantissa
; starting with 0. A value kept in the cell table is packed in 7 bytes: a
; header ($40 + type for the others; for a number its sign and e + 32 in
; six bits), then the mantissa.
;
; Decimal mode is only ever on between php/sei/sed and plp, interrupts off:
; an interrupt handler run with D set would compute wrongly.

        .export _vc_acc, _vc_arg, _vc_out, _vc_parse, _vc_format, _vc_pack, _vc_unpack
        .export _vc_add, _vc_sub, _vc_mul, _vc_div, _vc_cmp, _vc_int
        .importzp ptr1, ptr2, ptr3, ptr4, tmp1, tmp2, tmp3, tmp4, sreg
        .macpack longbranch

T_NUM   = 0
T_ERROR = 1
T_NA    = 2
T_TRUE  = 3
T_FALSE = 4
T_EMPTY = 5

; the fields of an unpacked value
VT      = 0
VS      = 1
VE      = 2
VM      = 3

; Each phase starts with the link's identity: VISICALC.BIN from another
; build is refused (its code would call this one's at the wrong places).
        .import __CODE_SIZE__, __VCA_SIZE__, __VCB_SIZE__, __VCC_SIZE__
        .import VC_KEEP, VC_SWAP
VC_ID   = __CODE_SIZE__ ^ (__VCA_SIZE__ * 3) ^ (__VCB_SIZE__ * 5) ^ (__VCC_SIZE__ * 7)
SWAPAT  = $1B00 + VC_KEEP
        .segment "VCB"
        .word   VC_ID
        .segment "VCC"
        .word   VC_ID

        .segment "BSS"
_vc_acc: .res   9
_vc_arg: .res   9
_vc_out: .res   80              ; a formatted cell, zero-ended
wide:   .res    14              ; products, remainders, quotients
wide2:  .res    7
digits: .res    14              ; the significant digits of a number
ndig:   .res    1               ; how many
xexp:   .res    1               ; the decimal exponent, signed: d0.d1.. x 10^X
qd:     .res    14              ; a quotient's digits
nrnd:   .res    1
carried: .res   1
cnt:    .res    1
sgn:    .res    1               ; 1 when a minus is written
room:   .res    1               ; n: the characters a number may take
outn:   .res    1               ; the length written in out
fmtc:   .res    1
lit_int: .res   1               ; literal parsing: integer digits, zeros after
lit_frz: .res   1               ; the point, a point seen, significant seen
lit_pt: .res    1
lit_sig: .res   1
lit_ex: .res    1
lit_exs: .res   1
fieldw: .res    1
emitx:  .res    1


; -- moving values --------------------------------------------------------------

; ACC <-> ARG, ARG = ACC (resident: the recalculation phase has no room
; left)
        .segment "CODE"
acc2arg: ldx    #8
@l:     lda     _vc_acc,x
        sta     _vc_arg,x
        dex
        bpl     @l
        rts
swap:   ldx     #8
@l:     lda     _vc_acc,x
        ldy     _vc_arg,x
        sta     _vc_arg,x
        tya
        sta     _vc_acc,x
        dex
        bpl     @l
        rts
; strcpy(api->note, A/X) and back to the core, from wherever the overlay
; is (the stack as plugin_entry found it). After the auxiliary bank was
; used, /RAM is rebuilt and the note says so: ram_format overwrites MAIN
; $2000-$21FF, so this comes first in the overlay, below $2000, and its
; argument is pushed before.
leave:  sta     ptr1
        stx     ptr1+1
        ldx     entsp
        txs
        ldy     #0                      ; the note into vc_out (it may be
@c:     lda     (ptr1),y                ; vc_out already)
        sta     _vc_out,y
        beq     @e
        iny
        bne     @c
@e:     lda     auxed
        beq     @go
        ldx     #0                      ; ... and /RAM rebuilt
@a:     lda     m_ram,x
        sta     _vc_out,y
        beq     @go
        inx
        iny
        bne     @a
@go:    lda     notep
        ldx     notep+1
        jsr     pushax
        lda     auxed
        beq     :+
        jsr     J_RAMFMT
:       lda     #<_vc_out
        ldx     #>_vc_out
        jmp     J_STRCPY


; ACC = ERROR, NA... (A)
settype:
        sta     _vc_acc+VT
        rts

seterror:
        lda     #T_ERROR
        bne     settype

; ACC = 0
setzero:
        lda     #0
        ldx     #8
@l:     sta     _vc_acc,x
        dex
        bpl     @l
        lda     #64
        sta     _vc_acc+VE
        rts

; -- the table's bytes ----------------------------------------------------------------
; The cell table is in the main bank, or in the auxiliary one when it does
; not fit (tables: a 128 KB machine, the user's consent when /RAM holds
; files). Every access to it goes through these: A = (ptrN),y, or
; (ptrN),y = A, with the bank switched around the access alone, interrupts
; off. Reading the auxiliary bank switches the processor's reads too: the
; instructions that follow are fetched from it, so taux copies this block
; there, at the same addresses. In the main bank the switches are made
; harmless (tmain: BIT instead of STA). N and Z follow A after a read.
tblock:
trd1:   php
        sei
        sta     $C003                   ; RAMRD: auxiliary
        lda     (ptr1),y
        sta     $C002                   ; RAMRD: main
        plp
        ora     #0
        rts
trd3:   php
        sei
        sta     $C003
        lda     (ptr3),y
        sta     $C002
        plp
        ora     #0
        rts
trd4:   php
        sei
        sta     $C003
        lda     (ptr4),y
        sta     $C002
        plp
        ora     #0
        rts
twr1:   php
        sei
        sta     $C005                   ; RAMWRT: auxiliary
        sta     (ptr1),y
        sta     $C004                   ; RAMWRT: main
        plp
        rts
twr3:   php
        sei
        sta     $C005
        sta     (ptr3),y
        sta     $C004
        plp
        rts
twr4:   php
        sei
        sta     $C005
        sta     (ptr4),y
        sta     $C004
        plp
        rts
TBLOCK  = * - tblock

        .segment "VCA"
; The table in the main bank: each STA $C00x of the block becomes BIT.
tmain:  ldx     #TBLOCK - 3
@l:     lda     tblock,x
        cmp     #$8D
        bne     @n
        lda     tblock+2,x
        cmp     #$C0
        bne     @n
        lda     #$2C
        sta     tblock,x
@n:     dex
        bpl     @l
        rts

; The table in the auxiliary bank: the block copied there, where it is.
taux:   php
        sei
        sta     $C005
        ldx     #TBLOCK - 1
@l:     lda     tblock,x
        sta     tblock,x
        dex
        bpl     @l
        sta     $C004
        plp
        rts
        .segment "CODE"

; void __fastcall__ vc_pack(unsigned char* dst): ACC, packed, at dst.
_vc_pack:
        sta     ptr1
        stx     ptr1+1
        lda     _vc_acc+VT
        beq     @num
        ora     #$40
        bne     @hdr
@num:   lda     _vc_acc+VM
        beq     @hdr                    ; zero: header 0
        lda     _vc_acc+VE
        sec
        sbc     #32                     ; e + 32
        and     #$3F
        ora     _vc_acc+VS
@hdr:   ldy     #0
        jsr     twr1
@m:     lda     _vc_acc+VM,y
        iny
        jsr     twr1
        cpy     #6
        bne     @m
        rts

; void __fastcall__ vc_unpack(const unsigned char* src): ACC = the value.
_vc_unpack:
        sta     ptr1
        stx     ptr1+1
unpack: ldy     #6
@m:     jsr     trd1
        sta     _vc_acc+VM-1,y
        dey
        bne     @m
        jsr     trd1
        tax
        and     #$80
        sta     _vc_acc+VS
        txa
        and     #$40
        beq     @num
        txa
        and     #$3F
        sta     _vc_acc+VT
        rts
@num:   sty     _vc_acc+VT
        txa
        and     #$3F
        clc
        adc     #32                     ; e + 32 + 32
        sta     _vc_acc+VE
        rts
        .segment "VCB"

; -- arithmetic ---------------------------------------------------------------

; Magnitudes: carry set when |ACC| >= |ARG| (exponent, then mantissa).
magcmp: lda     _vc_acc+VE
        cmp     _vc_arg+VE
        bne     @r
        ldx     #0
@l:     lda     _vc_acc+VM,x
        cmp     _vc_arg+VM,x
        bne     @r
        inx
        cpx     #6
        bne     @l
@r:     rts

; ACC = ACC - ARG, ACC = ACC + ARG: numbers. ERROR when out of range.
_vc_sub:
        lda     _vc_arg+VS
        eor     #$80
        sta     _vc_arg+VS
_vc_add:
        lda     _vc_arg+VM
        beq     @done                   ; + 0
        lda     _vc_acc+VM
        bne     @both
        jmp     swap                    ; 0 + ARG
@both:  jsr     magcmp
        bcs     @big
        jsr     swap                    ; ACC: the larger magnitude
@big:   lda     _vc_acc+VE
        sec
        sbc     _vc_arg+VE              ; the shift, in bytes
        cmp     #6
        bcs     @done                   ; ARG truncated away
        tax                             ; wide[0..5] = ARG, x bytes right
        ldy     #0
@z:     txa
        beq     @c
        lda     #0
        sta     wide,y
        iny
        dex
        bpl     @z                      ; always
@c:     cpy     #6
        beq     @aligned
        lda     _vc_arg+VM,x
        sta     wide,y
        inx
        iny
        bne     @c                      ; always
@aligned:
        php
        sei
        sed
        lda     _vc_acc+VS
        cmp     _vc_arg+VS
        bne     @minus
        ldx     #5
        clc
@add:   lda     _vc_acc+VM,x
        adc     wide,x
        sta     _vc_acc+VM,x
        dex
        bpl     @add
        ror     tmp1                    ; the carry, past plp
        plp
        bit     tmp1
        bpl     @done
        jsr     shr1                    ; carry out: one more digit pair
        lda     #1
        sta     _vc_acc+VM
        inc     _vc_acc+VE
        jmp     inrange
@minus: ldx     #5
        sec
@sbc:   lda     _vc_acc+VM,x
        sbc     wide,x
        sta     _vc_acc+VM,x
        dex
        bpl     @sbc
        plp
        jmp     normal
@done:  rts

; ACC's mantissa one byte right, the last one dropped.
shr1:   ldx     #5
@l:     lda     _vc_acc+VM-1,x
        sta     _vc_acc+VM,x
        dex
        bne     @l
        rts

; Leading zero bytes out, the exponent down; zero stays zero.
normal: ldx     #5
@z:     lda     _vc_acc+VM,x
        bne     @nz
        dex
        bpl     @z
        jmp     setzero
@nz:    lda     _vc_acc+VM
        bne     inrange
        ldx     #0
@l:     lda     _vc_acc+VM+1,x
        sta     _vc_acc+VM,x
        inx
        cpx     #5
        bne     @l
        lda     #0
        sta     _vc_acc+VM+5
        dec     _vc_acc+VE
        jmp     @nz
; The exponent within -32..31 (stored 32..95), else ERROR.
inrange: lda     _vc_acc+VE
        cmp     #32
        bcc     @bad
        cmp     #96
        bcc     @ok
@bad:   jmp     seterror
@ok:    rts

; ACC = ACC * ARG: the twelve-byte product of the mantissas, its first six
; non-zero bytes kept.
_vc_mul:
        lda     _vc_acc+VM
        jeq     @r                      ; 0 * x
        lda     _vc_arg+VM
        bne     @go
        jmp     setzero
@go:    jsr     signs
        lda     _vc_acc+VE
        clc
        adc     _vc_arg+VE
        sec
        sbc     #64
        sta     _vc_acc+VE
        ldx     #13
        lda     #0
@clr:   sta     wide,x
        dex
        bpl     @clr
        lda     #0
        sta     cnt                     ; the digit of ARG, 0..11
@digit: jsr     wshl4                   ; wide *= 10
        lda     cnt
        lsr     a
        tax
        lda     _vc_arg+VM,x
        bcs     @lo
        lsr     a
        lsr     a
        lsr     a
        lsr     a
@lo:    and     #$0F
        beq     @next
        sta     tmp2
@rep:   php                             ; wide[6..11] += ACC, carry upward
        sei
        sed
        ldx     #5
        clc
@ad:    lda     wide+6,x
        adc     _vc_acc+VM,x
        sta     wide+6,x
        dex
        bpl     @ad
        ldx     #5
@cy:    lda     wide,x
        adc     #0
        sta     wide,x
        dex
        bpl     @cy
        plp
        dec     tmp2
        bne     @rep
@next:  inc     cnt
        lda     cnt
        cmp     #12
        bne     @digit
        ldx     #0                      ; the product's first non-zero byte
        lda     wide
        bne     @take
        inx
        dec     _vc_acc+VE
@take:  ldy     #0
@tk:    lda     wide,x
        sta     _vc_acc+VM,y
        inx
        iny
        cpy     #6
        bne     @tk
        jmp     inrange
@r:     rts

; The result's sign, from both.
signs:  lda     _vc_acc+VS
        eor     _vc_arg+VS
        sta     _vc_acc+VS
        rts

; wide[0..11] * 10: one nibble left.
wshl4:  ldx     #11
        ldy     #12
; Y bytes of wide ending at wide[X], one nibble left. (No rol abs,x: sim65
; 2.18, which the tests run, decodes it wrong.)
shl4:   lda     #0
        sta     tmp3                    ; the nibble carried in
@l:     lda     wide,x
        pha
        asl     a
        asl     a
        asl     a
        asl     a
        ora     tmp3
        sta     wide,x
        pla
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     tmp3
        dex
        dey
        bne     @l
        rts

; ACC = ACC / ARG: fourteen quotient digits by subtraction, the remainder
; against ten times the divisor; the first six non-zero bytes kept.
_vc_div:
        lda     _vc_arg+VM
        bne     @nz
        jmp     seterror                ; / 0
@nz:    lda     _vc_acc+VM
        bne     @go
        rts                             ; 0 / x
@go:    jsr     signs
        lda     _vc_acc+VE
        sec
        sbc     _vc_arg+VE
        clc
        adc     #64
        sta     _vc_acc+VE
        ; wide[0..6]: the remainder, ACC's mantissa behind a zero byte;
        ; wide2[0..6]: ten times ARG's (one nibble left, behind a zero byte)
        lda     #0
        sta     wide
        sta     wide2
        ldx     #5
@cp:    lda     _vc_acc+VM,x
        sta     wide+1,x
        lda     _vc_arg+VM,x
        sta     wide2+1,x
        dex
        bpl     @cp
        ldx     #20                     ; wide2 = wide + 14
        ldy     #7
        jsr     shl4
        lda     #0
        sta     cnt
@digit: lda     #0
        sta     tmp2                    ; the quotient digit
@try:   ldx     #0                      ; the remainder against D': a
@cmp:   lda     wide,x                  ; binary compare of BCD bytes orders
        cmp     wide2,x                 ; them right, and needs no decimal
        bne     @dcd                    ; flag (sim65 2.18 gets those wrong)
        inx
        cpx     #7
        bne     @cmp
@dcd:   bcc     @done                   ; it does not go
        php
        sei
        sed
        ldx     #6
        sec
@sb:    lda     wide,x
        sbc     wide2,x
        sta     wide,x
        dex
        bpl     @sb
        plp
        inc     tmp2
        bne     @try                    ; always
@done:  lda     cnt                     ; the digit into qd[cnt]
        tax
        lda     tmp2
        sta     qd,x
        ldx     #6                      ; remainder * 10
        ldy     #7
        jsr     shl4
        inc     cnt
        lda     cnt
        cmp     #14
        bne     @digit
        ldx     #0                      ; digits two by two into bytes
        lda     qd
        ora     qd+1
        bne     @pk
        ldx     #2                      ; the first pair zero: start one later
        dec     _vc_acc+VE
@pk:    inc     _vc_acc+VE
        ldy     #0
@pb:    lda     qd,x
        asl     a
        asl     a
        asl     a
        asl     a
        ora     qd+1,x
        sta     _vc_acc+VM,y
        inx
        inx
        iny
        cpy     #6
        bne     @pb
        jmp     inrange

; signed char __fastcall__ vc_cmp(void): -1, 0 or 1 as ACC <, =, > ARG.
_vc_cmp:
        lda     _vc_acc+VM
        bne     @a
        lda     _vc_arg+VM              ; ACC is 0
        beq     @eq
        lda     _vc_arg+VS
        bmi     @gt
        bpl     @lt
@a:     lda     _vc_arg+VM
        bne     @b
        lda     _vc_acc+VS              ; ARG is 0
        bmi     @lt
        bpl     @gt
@b:     lda     _vc_acc+VS
        cmp     _vc_arg+VS
        beq     @same
        lda     _vc_acc+VS
        bmi     @lt
        bpl     @gt
@same:  jsr     magcmp
        beq     @eq
        ror     a                       ; bit 7: |ACC| > |ARG|
        eor     _vc_acc+VS              ; flipped for two negatives
        bmi     @gt
@lt:    lda     #$FF
        tax
        rts
@eq:    lda     #0
        tax
        rts
@gt:    lda     #1
        ldx     #0
        rts

; ACC = INT(ACC), toward zero.
_vc_int:
        lda     _vc_acc+VM
        beq     @r
        lda     _vc_acc+VE
        sec
        sbc     #64                     ; e
        beq     @zero
        bmi     @zero
        cmp     #6
        bcs     @r
        tax
        lda     #0
@z:     sta     _vc_acc+VM,x
        inx
        cpx     #6
        bne     @z
@r:     rts
@zero:  jmp     setzero
        .segment "CODE"

; -- number literals --------------------------------------------------------------

; unsigned char __fastcall__ vc_parse(const char* s): the number literal at
; s -- digits, an optional point, an optional E and signed exponent -- into
; ACC (ERROR when out of range); the characters it took, 0 if none.
_vc_parse:
        sta     ptr1
        stx     ptr1+1
        jsr     parse
        tya
        ldx     #0
        rts

; The same at ptr1: Y = the length, 0 when there is no number.
parse:  lda     #0
        sta     _vc_acc+VT
        sta     _vc_acc+VS
        sta     ndig
        sta     lit_int
        sta     lit_frz
        sta     lit_pt
        sta     lit_sig
        sta     tmp1                    ; a digit seen
        tay
@ch:    lda     (ptr1),y
        cmp     #'.'
        bne     @dg
        lda     lit_pt
        bne     @end
        inc     lit_pt
        iny
        bne     @ch
@dg:    sec
        sbc     #'0'
        cmp     #10
        bcs     @end
        sta     tmp2
        sta     tmp1                    ; non-zero is enough... and for "0":
        inc     tmp1
        iny
        lda     lit_sig
        bne     @sig
        lda     tmp2
        bne     @first
        lda     lit_pt                  ; a leading zero
        beq     @ch
        inc     lit_frz
        bne     @ch
        dec     lit_frz                 ; (255 at most)
        bne     @ch
@first: inc     lit_sig
@sig:   ldx     ndig
        cpx     #14
        bcs     @skip
        lda     tmp2
        sta     digits,x
        inc     ndig
@skip:  lda     lit_pt
        bne     @ch
        inc     lit_int
        bne     @ch
        dec     lit_int
        bne     @ch
@end:   lda     tmp1
        bne     @num
        ldy     #0                      ; no digit: not a number
        rts
@num:   lda     #0                      ; the exponent
        sta     lit_ex
        sta     lit_exs
        lda     (ptr1),y
        cmp     #'E'
        bne     @val
        sty     tmp3                    ; where to come back if no digit follows
        iny
        lda     (ptr1),y
        cmp     #'-'
        bne     @plus
        inc     lit_exs
        bne     @esg
@plus:  cmp     #'+'
        bne     @ed
@esg:   iny
@ed:    ldx     #0                      ; digits of the exponent
@el:    lda     (ptr1),y
        sec
        sbc     #'0'
        cmp     #10
        bcs     @ee
        sta     tmp2
        lda     lit_ex                  ; lit_ex*10 + digit, 100 at most
        cmp     #10
        bcs     @big
        asl     a
        sta     tmp4
        asl     a
        asl     a
        adc     tmp4
        adc     tmp2
        sta     lit_ex
        inx
        iny
        bne     @el
@big:   lda     #100
        sta     lit_ex
        inx
        iny
        bne     @el
@ee:    txa
        bne     @val
        ldy     tmp3                    ; "E" alone is not the number's
@val:   sty     tmp3                    ; the length, kept
        lda     ndig
        bne     @nz
        jsr     setzero
        ldy     tmp3
        rts
@nz:    lda     lit_ex
        cmp     #100
        bcs     @err
        lda     lit_int                 ; X = int - 1, or -zeros - 1
        cmp     #100
        bcs     @err
        lda     lit_frz
        cmp     #100
        bcs     @err
        lda     lit_int
        beq     @frac
        sec
        sbc     #1
        jmp     @xs
@frac:  lda     #$FF
        sec
        sbc     lit_frz                 ; -1 - zeros
@xs:    ldx     lit_exs
        bne     @xneg
        clc
        adc     lit_ex
        jmp     @xr
@xneg:  sec
        sbc     lit_ex
@xr:    bvs     @err                    ; beyond -128..127: far out of range
        sta     xexp
        ; X within -66..61, else out of range
        bmi     @neg
        cmp     #62
        bcs     @err
        bcc     @pack
@neg:   cmp     #<-66
        bcc     @err
@pack:  jsr     packdig
        ldy     tmp3
        rts
@err:   jsr     seterror
        ldy     tmp3
        rts

; ACC = digits[0..ndig) at the decimal exponent xexp: aligned on pairs (a
; leading 0 when X is even), the first twelve digits taken.
packdig:
        lda     xexp
        cmp     #$80                    ; e = floor(X / 2) + 1
        ror     a
        clc
        adc     #65
        sta     _vc_acc+VE
        ldx     #0                      ; X even: start one digit early
        lda     xexp
        lsr     a
        bcs     @odd
        dex
@odd:   ldy     #0
@b:     jsr     dg                      ; high nibble
        asl     a
        asl     a
        asl     a
        asl     a
        sta     tmp2
        inx
        jsr     dg
        ora     tmp2
        sta     _vc_acc+VM,y
        inx
        iny
        cpy     #6
        bne     @b
        rts
; digits[x], or 0 out of 0..ndig-1
dg:     cpx     ndig
        bcs     @z                      ; (x = $FF too)
        lda     digits,x
        rts
@z:     lda     #0
        rts

; -- display ------------------------------------------------------------------------

; ACC's significant digits into digits/ndig (trailing zeros dropped), its
; decimal exponent into xexp: |ACC| = d0.d1d2... x 10^X.
unpackdig:
        ldx     #0
        ldy     #0
@b:     lda     _vc_acc+VM,y
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     digits,x
        inx
        lda     _vc_acc+VM,y
        and     #$0F
        sta     digits,x
        inx
        iny
        cpy     #6
        bne     @b
        lda     _vc_acc+VE              ; X = 2e - 1, or 2e - 2 and one digit less
        sec
        sbc     #64
        asl     a
        sta     xexp
        dec     xexp
        lda     digits
        bne     @strip
        dec     xexp
        ldx     #0                      ; the digits one place left
@sl:    lda     digits+1,x
        sta     digits,x
        inx
        cpx     #11
        bne     @sl
        lda     #0
        sta     digits+11
@strip: ldx     #12
@t:     dex
        bmi     @n
        lda     digits,x
        beq     @t
@n:     inx
        stx     ndig
        rts
        .segment "VCC"

; digits rounded half up to their first A digits (A signed): rnd/nrnd, and
; carried = 1 when the rounding made one more leading digit (999 -> 1000).
round:  sta     nrnd
        lda     #0
        sta     carried
        lda     nrnd
        bmi     @none                   ; nothing kept, nothing carried
        tax
        cpx     ndig
        bcc     @cut
        ldx     #0                      ; all of them, then zeros
@all:   cpx     nrnd
        beq     @r
        jsr     dg
        sta     rnd,x
        inx
        bne     @all
@cut:   ldx     #0
@c:     cpx     nrnd
        beq     @up
        lda     digits,x
        sta     rnd,x
        inx
        bne     @c
@up:    lda     digits,x                ; the first digit dropped
        cmp     #5
        bcc     @r
@inc:   dex
        bmi     @over
        lda     rnd,x
        clc
        adc     #1
        sta     rnd,x
        cmp     #10
        bcc     @r
        lda     #0
        sta     rnd,x
        beq     @inc
@over:  ldx     nrnd                    ; all nines: a 1 in front
@sh:    dex
        bmi     @one
        lda     rnd,x
        sta     rnd+1,x
        jmp     @sh
@one:   lda     #1
        sta     rnd
        inc     nrnd
        sta     carried
@r:     rts
@none:  lda     #0
        sta     nrnd
        rts

emit:   stx     emitx                   ; (X kept)
        ldx     outn
        sta     outp,x
        inc     outn
        ldx     emitx
        rts
emitd:  ora     #'0'
        jmp     emit
emitsg: lda     sgn
        beq     @r
        lda     #'-'
        jmp     emit
@r:     rts

; plain: digits written without exponent, after the sign.
plain:  jsr     emitsg
        lda     xexp
        bmi     @frac
        ldx     #0                      ; X+1 digits before the point
@i:     stx     tmp3
        jsr     dg
        jsr     emitd
        ldx     tmp3
        inx
        txa
        sec
        sbc     #1
        cmp     xexp
        bne     @i
        cpx     ndig
        bcs     @r
        lda     #'.'
        jsr     emit
@f:     stx     tmp3
        lda     digits,x
        jsr     emitd
        ldx     tmp3
        inx
        cpx     ndig
        bne     @f
@r:     rts
@frac:  lda     #'.'
        jsr     emit
        lda     #$FF
        sec
        sbc     xexp                    ; -X-1 zeros
        beq     @fd
        tax
@z:     lda     #'0'
        jsr     emit
        dex
        bne     @z
@fd:    ldx     #0
        beq     @f                      ; always

; The length plain would write.
plainlen:
        lda     sgn
        ldx     xexp
        bmi     @frac
        sec                             ; + X + 1
        adc     xexp
        ldx     ndig
        dex
        cpx     xexp                    ; ndig - 1 > X: a point and the rest
        bcc     @r
        beq     @r
        sec
        adc     ndig
        sec
        sbc     xexp
        sec
        sbc     #1
@r:     rts
@frac:  clc
        adc     ndig
        sec
        sbc     xexp                    ; + 1 + (-X - 1) + ndig
        rts

; rnd written with the point after its first A digits (A = 0: before
; them, $80: none). The sign is the caller's.
rndpt:  sta     tmp4
        ldx     #0
@l:     cpx     tmp4
        bne     @d
        lda     #'.'
        stx     tmp3
        jsr     emit
        ldx     tmp3
@d:     cpx     nrnd
        beq     @r
        lda     rnd,x
        stx     tmp3
        jsr     emitd
        ldx     tmp3
        inx
        bne     @l
@r:     rts

; Overflow: n '>' characters.
overflow:
        lda     #0
        sta     outn
@l:     lda     outn
        cmp     room
        bcs     @r
        lda     #'>'
        jsr     emit
        jmp     @l
@r:     rts

; The general format, ACC unpacked into digits: outp/outn, n = room.
general:
        lda     ndig
        bne     @nz
        lda     #'0'
        jmp     emit
@nz:    jsr     plainlen
        cmp     room
        beq     @plain
        bcs     @round
@plain: jmp     plain
@round: lda     xexp
        bpl     @fx
        cmp     #<-3
        bcs     @fx
        jmp     sci
@fx:    lda     xexp                    ; I: the integer digits
        bpl     @ip
        lda     #$FF
@ip:    clc
        adc     #1
        clc
        adc     sgn
        sta     tmp1
        lda     room                    ; dec = n - s - I - 1
        clc
        sbc     tmp1
        sta     tmp2                    ; (signed)
        lda     xexp                    ; below .1: three decimals or nothing
        bpl     @dec
        cmp     #$FF
        beq     @dec
        lda     tmp2
        bmi     @sci
        cmp     #3
        bcs     @dec
@sci:   jmp     sci
@dec:   lda     tmp2
        jmi     @minus1
        sec                             ; keep = X + 1 + dec
        adc     xexp
        sta     tmp1
        jsr     round
        lda     carried
        bne     @pow10
        lda     tmp1
        beq     @zero
        bmi     @zero
        jsr     emitsg
        lda     xexp
        bmi     @small
        clc
        adc     #1
        jmp     rndpt
@small: lda     #'.'                    ; '.', the zeros, the digits
        jsr     emit
        lda     #$FF
        sec
        sbc     xexp
        beq     @sd
        tax
@sz:    lda     #'0'
        jsr     emit
        dex
        bne     @sz
@sd:    lda     #$80                    ; never the point again
        jmp     rndpt
@zero:  lda     #'0'                    ; nothing kept: 0., unsigned
        jsr     emit
        lda     room
        cmp     #2
        bcc     @r
        lda     #'.'
        jmp     emit
@r:     rts
@pow10: jsr     one                     ; a power of ten, written short
        jsr     plain
        ldx     #0
@pt:    cpx     outn
        beq     @nopt
        lda     outp,x
        inx
        cmp     #'.'
        bne     @pt
        dex                             ; x: where the point is
        jmp     @fit
@nopt:  lda     #'.'
        jsr     emit
        ldx     outn
        dex
@fit:   lda     outn
        cmp     room
        beq     @r
        bcc     @r
        cpx     room                    ; the point within n: cut there
        beq     @cut
        bcc     @cut
        jmp     overflow
@cut:   lda     room
        sta     outn
        rts
@minus1:
        cmp     #$FF
        jne     @sci
        lda     xexp                    ; the integer part fills the field
        clc
        adc     #1
        jsr     round
        lda     carried
        bne     @cs
        jsr     emitsg
        lda     #$80
        jmp     rndpt
@cs:    jsr     one
        jmp     sci

; digits = 1 at X + 1: the power of ten a rounding carried into.
one:    lda     #1
        sta     digits
        sta     ndig
        inc     xexp
        rts

; The exponent form: d.ddd E X.
sci:    lda     #0
        sta     outn
        ldx     #'E'                    ; es: E, the sign, the digits, in wide2
        stx     wide2
        ldx     #1
        lda     xexp
        bpl     @p
        lda     #'-'
        sta     wide2,x
        inx
        lda     #0
        sec
        sbc     xexp
@p:     ldy     #0                      ; tens
@t:     cmp     #10
        bcc     @u
        sbc     #10
        iny
        bne     @t
@u:     pha
        tya
        beq     @nt
        ora     #'0'
        sta     wide2,x
        inx
@nt:    pla
        ora     #'0'
        sta     wide2,x
        inx
        stx     cnt                     ; len(es)
        lda     room                    ; k = n - s - len(es), < 1: none
        sec
        sbc     sgn
        jcc     @ov                     ; (n = 0 and a sign: not a wrap)
        sec
        sbc     cnt
        jcc     @ov
        jeq     @ov
        sta     tmp1
        lda     ndig
        cmp     #1
        bne     @many
        jsr     emitsg                  ; one digit, exactly
        lda     digits
        jsr     emitd
        lda     xexp
        bpl     @es
        lda     tmp1
        cmp     #2
        bcc     @es
        lda     #'.'
        jsr     emit
        jmp     @es
@many:  lda     ndig                    ; all of them fit
        cmp     tmp1
        bcs     @rd
        jsr     emitsg
        lda     #0
        sta     nrnd
@cpy:   ldx     nrnd
        lda     digits,x
        sta     rnd,x
        inc     nrnd
        lda     nrnd
        cmp     ndig
        bne     @cpy
        lda     #1
        jsr     rndpt
        jmp     @es
@rd:    lda     tmp1
        cmp     #2
        bcs     @dec
        lda     #1                      ; room for one digit only
        jsr     round
        lda     carried
        bne     @ov
        jsr     emitsg
        lda     #$80
        jsr     rndpt
        jmp     @es
@dec:   sec                             ; 1 + (k - 2) digits
        sbc     #1
        jsr     round
        jsr     emitsg
        lda     #1
        clc
        adc     carried
        jsr     rndpt
        lda     tmp1                    ; cut to k after the sign
        clc
        adc     sgn
        cmp     outn
        bcs     @es
        sta     outn
@es:    ldx     #0
@ec:    lda     wide2,x
        stx     tmp3
        jsr     emit
        ldx     tmp3
        inx
        cpx     cnt
        bne     @ec
        rts
@ov:    jmp     overflow

; /F$ and /FI: rounded to A decimals, exactly that many written.
fixed:  sta     tmp4                    ; places
        sec
        adc     xexp                    ; keep = X + 1 + places
        ldx     ndig
        bne     @k
        lda     #$80                    ; zero: nothing kept
@k:     tax
        bmi     @kr
        cmp     room                    ; more digits than room: too wide
        beq     @kr
        jcs     overflow
@kr:    jsr     round
        ; body: rnd padded on the left with zeros to places + 1 digits
        lda     nrnd
        sta     tmp1                    ; 0: the value rounds to zero
        sec
        sbc     tmp4
        bcc     @pad
        beq     @pad
        sta     tmp2                    ; digits before the point
        jmp     @len
@pad:   lda     #1                      ; "0.dd": the zeros go in front
        sta     tmp2
        lda     tmp4
        clc
        adc     #1
        sec
        sbc     nrnd
        tax                             ; that many zeros
        beq     @len
@ins:   ldy     nrnd                    ; shift rnd right by one, 0 in front
@iy:    dey
        bmi     @i0
        lda     rnd,y
        sta     rnd+1,y
        jmp     @iy
@i0:    lda     #0
        sta     rnd
        inc     nrnd
        dex
        bne     @ins
@len:   lda     nrnd                    ; s + digits + point
        clc
        adc     sgn
        ldx     tmp4
        beq     @l2
        clc
        adc     #1
@l2:    cmp     room
        bcc     @fits
        beq     @fits
        ldx     ndig                    ; too long: the leading zero goes,
        beq     @ov                     ; but never from an exact zero
        ldx     tmp4
        beq     @ov
        ldx     rnd
        bne     @ov
        ldx     tmp2
        dex
        bne     @ov
        sec
        sbc     #1
        cmp     room
        beq     @drop
        bcs     @ov
@drop:  ldx     #1                      ; rnd without its first digit
@dl:    lda     rnd,x
        sta     rnd-1,x
        inx
        cpx     nrnd
        bne     @dl
        dec     nrnd
        dec     tmp2
@fits:  lda     tmp1                    ; -0.00: the sign's place, blank
        bne     @sg
        lda     sgn
        beq     @w
        lda     #' '
        jsr     emit
        jmp     @w
@sg:    jsr     emitsg
@w:     lda     tmp4
        bne     @wp
        lda     #$80
        jmp     rndpt
@wp:    lda     tmp2
        jmp     rndpt
@ov:    jmp     overflow

; /F*: a star a unit, n at most, nothing for less than one.
bar:    lda     #' '
        jsr     emit
        lda     sgn
        bne     @r
        lda     xexp
        bmi     @r
        cmp     #2
        bcs     @full                   ; 100 or more
        ldx     #0
        jsr     dg
        ldy     xexp
        beq     @n
        sta     tmp1                    ; two digits: d0 * 10 + d1
        asl     a
        asl     a
        adc     tmp1
        asl     a
        sta     tmp1
        inx
        jsr     dg
        clc
        adc     tmp1
@n:     cmp     room
        bcc     @k
@full:  lda     room
@k:     tax
        beq     @r
@s:     lda     #'*'
        stx     tmp1
        jsr     emit
        ldx     tmp1
        dex
        bne     @s
@r:     rts

names:  .byte   "ERROR", 0, "NA", 0, "TRUE", 0, "FALSE", 0
nameoff: .byte  0, 0, 6, 9, 14

; void __fastcall__ vc_format(unsigned char w): ACC as a cell of width w
; shows it with the format vc_fmt (G I L R $ * as 1-6, 0 the general one),
; into vc_out: w characters and a zero.
        .export _vc_fmt
        .segment "BSS"
_vc_fmt: .res   1
        .segment "VCC"
_vc_format:
        sta     fieldw
        tax
        dex
        stx     room                    ; n = w - 1
        lda     #0
        sta     outn
        sta     sgn
        lda     _vc_acc+VT
        beq     @num
        cmp     #T_EMPTY
        bcs     @place
        tax
        ldy     nameoff,x
@nm:    lda     names,y
        beq     @place
        ldx     outn
        cpx     room
        bcs     @place
        jsr     emit
        iny
        bne     @nm
@num:   jsr     unpackdig
        lda     _vc_acc+VS
        beq     @pos
        lda     ndig
        beq     @pos
        inc     sgn
@pos:   ldx     _vc_fmt
        cpx     #6
        bne     @nb
        jsr     bar
        jmp     @left
@nb:    cpx     #5
        bne     @ni
        lda     #2
        jsr     fixed
        jmp     @place
@ni:    cpx     #2
        bne     @g
        lda     #0
        jsr     fixed
        jmp     @place
@g:     jsr     general
@place: ldx     fieldw                  ; vc_out: w blanks, then the text
        lda     #0
        sta     _vc_out,x
@bl:    dex
        bmi     @put
        lda     #' '
        sta     _vc_out,x
        bne     @bl
@put:   lda     outn
        cmp     fieldw                  ; never past the field (a guard)
        beq     :+
        bcc     :+
        jsr     overflow
:       lda     outn
        beq     @r
        lda     _vc_fmt
        cmp     #3
        beq     @lfmt
        lda     fieldw                  ; right-aligned: from w - outn
        sec
        sbc     outn
        tax
        ldy     #0
@cp:    lda     outp,y
        sta     _vc_out,x
        inx
        iny
        cpy     outn
        bne     @cp
@r:     rts
@lfmt:  ldx     #1                      ; left: after one blank
        ldy     #0
@lc:    cpx     fieldw
        bcs     @r
        lda     outp,y
        sta     _vc_out,x
        inx
        iny
        cpy     outn
        bne     @lc
        rts
@left:  ldx     fieldw                  ; the bar: as written, from the left
        lda     #0
        sta     _vc_out,x
@b2:    dex
        bmi     @bp
        lda     #' '
        sta     _vc_out,x
        bne     @b2
@bp:    ldy     #0
@bc:    cpy     outn
        beq     @r
        cpy     fieldw
        bcs     @r
        lda     outp,y
        sta     _vc_out,y
        iny
        bne     @bc

; -- the cell table -----------------------------------------------------------------
; visicalc.c builds it: the value cells (numbers and formulas; labels are not
; in it) of each column, rows ascending, 8 bytes each -- the row (0: a dead
; entry) and the packed value, ERROR for a formula until the recalculation
; has reached it. vc_colptr[c] is where column c starts, vc_colptr[c + 1]
; where it ends.

        .export _vc_eval, _vc_lookup, _vc_entry
        .export _vc_cellref, _vc_refc, _vc_refr, _vc_scratch
        .export _vc_colplo, _vc_colphi, _vc_line
ENTRY   = 8
NCOLS   = 63                    ; A..BK
MAXDEPTH = 24                   ; nested operands, parentheses and calls
VSTACK  = 16                    ; values put aside

; The fixed tables live in $0C00-$0FFF, the second ProDOS buffer: the
; overlay keeps one file open, whose buffer is the first ($0800).
.ifndef VC_LOW
VC_LOW  = $0C00
.endif
rowlo   = VC_LOW                ; where row r's lines start, 0: none
rowhi   = VC_LOW + $100
_vc_line = VC_LOW + $200        ; the line read (the formula evaluated in it)
ln      = _vc_line
_vc_colplo = VC_LOW + $300      ; where column c's entries start (c = 63:
_vc_colphi = VC_LOW + $340      ; the table's end)
colplo  = _vc_colplo
colphi  = _vc_colphi
colw    = VC_LOW + $380         ; per-column widths, 0: the sheet's
colx    = VC_LOW + $3C0         ; where a column is on the screen, 0: off it
        .segment "BSS"
_vc_entry: .res 2               ; the entry vc_lookup found, or 0
evstart: .res   1               ; where the formula starts in ln
; One area, three uses: the value stack (recalculating), the fill points
; of pass 2 (reading), the cursor's line, a formatted number and its
; rounded digits (showing).
_vc_scratch:
vstk:   .res    240
fill    = vstk                  ; 2 x 63
sline   = vstk                  ; 80
outp    = vstk + 80             ; 80
rnd     = vstk + 160            ; 80
vsp:    .res    1               ; offset of the next free slot
depth:  .res    1
evsp:   .res    1               ; S at vc_eval's entry, for a syntax error
op:     .res    1
_vc_refc:
refc:   .res    1               ; a reference read: column, row
_vc_refr:
refr:   .res    1
refc2:  .res    1
refr2:  .res    1
fid:    .res    1               ; the function being called
lf_acc: .res    9               ; a list function's state
lf_cnt: .res    2
lf_flg: .res    1               ; 1 ERROR, 2 NA, 4 not a number, 8 not a truth value
lf_k:   .res    1               ; CHOOSE: the item wanted, then counting down
lf_bool: .res   1               ; AND/OR so far
lf_first: .res  1
lf_sel: .res    1

; ACC = the value of cell (refc, refr): its entry's, or EMPTY.
; void __fastcall__ vc_lookup(unsigned int colrow): low byte the column.
        .segment "CODE"
_vc_lookup:
        sta     refc
        stx     refr
lookup: jsr     find
        bcs     @empty
        inc     ptr1                    ; the value, after the row
        bne     :+
        inc     ptr1+1
:       jmp     unpack
@empty: lda     #T_EMPTY
        sta     _vc_acc+VT
        rts

; The entry of (refc, refr) at ptr1 and in vc_entry, C clear; C set when
; there is none.
find:   lda     #0
        sta     _vc_entry
        sta     _vc_entry+1
        ldx     refc
        cpx     #NCOLS
        bcs     @no
        lda     colplo,x
        sta     ptr1
        lda     colphi,x
        sta     ptr1+1
@l:     lda     ptr1                    ; the column's end?
        cmp     colplo+1,x
        lda     ptr1+1
        sbc     colphi+1,x
        bcs     @no
        ldy     #0
        jsr     trd1
        beq     @next                   ; dead
        cmp     refr
        beq     @yes
        bcs     @no                     ; past it: rows ascend
@next:  lda     ptr1
        clc
        adc     #ENTRY
        sta     ptr1
        bcc     @l
        inc     ptr1+1
        bne     @l                      ; always
@yes:   lda     ptr1
        sta     _vc_entry
        lda     ptr1+1
        sta     _vc_entry+1
        clc
        rts
@no:    sec
        rts

; -- walking the formula ----------------------------------------------------------

; peek, Escape asked for first (tick): every operand starts with it.
ppeek:  jsr     poll
peek:   ldy     #0
        lda     (ptr2),y
        rts
adv:    inc     ptr2
        bne     :+
        inc     ptr2+1
:       rts
        .segment "VCB"

; A syntax error: back to vc_eval's caller with ERROR.
abort:  ldx     evsp
        txs
        jsr     seterror
        lda     #0
        tax
        rts

push:   lda     vsp
        cmp     #9 * VSTACK
        bcs     abort
        tax
        ldy     #0
@l:     lda     _vc_acc,y
        sta     vstk,x
        inx
        iny
        cpy     #9
        bne     @l
        stx     vsp
        rts
; ACC = the value put aside last
pop:    lda     vsp
        sec
        sbc     #9
        sta     vsp
        tax
        ldy     #0
@l:     lda     vstk,x
        sta     _vc_acc,y
        inx
        iny
        cpy     #9
        bne     @l
        rts

; EMPTY counts as 0 (in ACC, in ARG)
numacc: lda     _vc_acc+VT
        cmp     #T_EMPTY
        bne     :+
        jmp     setzero
:       rts
numarg: lda     _vc_arg+VT
        cmp     #T_EMPTY
        bne     :+
        jsr     swap
        jsr     setzero
        jmp     swap
:       rts

; The worse of ACC and ARG when either is not a number: ERROR before NA,
; ERROR for a truth value. C set when ACC now holds the outcome.
worst:  lda     _vc_acc+VT
        ora     _vc_arg+VT
        beq     @num
        lda     _vc_acc+VT
        cmp     #T_ERROR
        beq     @set
        lda     _vc_arg+VT
        cmp     #T_ERROR
        beq     @set
        cmp     #T_NA
        beq     @set
        lda     _vc_acc+VT
        cmp     #T_NA
        beq     @set
        lda     #T_ERROR
@set:   sta     _vc_acc+VT
        sec
        rts
@num:   clc
        rts

; unsigned char __fastcall__ vc_eval(void): vc_line into ACC; 0.
_vc_eval:
        tsx
        stx     evsp
        lda     #0
        sta     vsp
        sta     depth
        lda     evstart
        sta     ptr2
        lda     #>ln
        sta     ptr2+1
        jsr     peek                    ; "+7" alone: VisiCalc reads ERROR
        cmp     #'+'
        bne     @go
        ldx     ptr2
        inx
        stx     ptr1
        lda     ptr2+1
        sta     ptr1+1
        jsr     parse
        tya
        beq     @go
        lda     (ptr1),y
        bne     @go
        jmp     abort
@go:    jsr     expr
        jsr     peek
        beq     @end
        jmp     abort                   ; something left over
@end:   jsr     numacc
        lda     #0
        tax
        rts

; ACC = the expression at ptr2: operands and operators, left to right.
expr:   jsr     operand
@loop:  jsr     peek
        ldx     #4
@op:    cmp     ops,x
        beq     @arith
        dex
        bpl     @op
        cmp     #'<'
        beq     @cmp
        cmp     #'>'
        beq     @cmp
        cmp     #'='
        beq     @cmp
        rts
@arith: stx     op
        jsr     adv
        lda     op
        pha
        jsr     push
        jsr     operand
        jsr     acc2arg
        jsr     pop
        pla
        jsr     arith
        jmp     @loop
@cmp:   jsr     adv                     ; the outcomes accepted: 1 <, 2 >,
        ldx     #4                      ; 4 =; <= 5, >= 6, <> 3
        cmp     #'='
        beq     @c3
        ldx     #1
        cmp     #'<'
        beq     @lt
        inx                             ; '>'
        jsr     peek
        cmp     #'='
        bne     @c3
        ldx     #6
        bne     @c2                     ; always
@lt:    jsr     peek
        ldx     #5
        cmp     #'='
        beq     @c2
        ldx     #3
        cmp     #'>'
        beq     @c2
        ldx     #1
        bne     @c3                     ; always
@c2:    jsr     adv
@c3:    txa
        ora     #$80                    ; a comparison
        pha
        jsr     push
        jsr     operand
        jsr     acc2arg
        jsr     pop
        pla
        jsr     arith
        jmp     @loop

ops:    .byte   "+-*/^"

; ACC = ACC (op A) ARG. A: 0..4 for + - * / ^, $80 + the outcomes of a
; comparison (1 <, 2 >, 4 =).
arith:  sta     op
        jsr     numacc
        jsr     numarg
        lda     op                      ; two truth values: = and <> only
        bpl     @w
        lda     _vc_acc+VT
        jsr     istruth
        bcc     @w
        lda     _vc_arg+VT
        jsr     istruth
        bcc     @w
        lda     op
        and     #7
        cmp     #3
        beq     @bool
        cmp     #4
        bne     @berr
@bool:  lda     _vc_acc+VT              ; equal: the outcome 4, else 2
        eor     _vc_arg+VT
        beq     @same
        lda     #2
        bne     @out
@same:  lda     #4
        bne     @out
@berr:  lda     #T_ERROR
        sta     _vc_acc+VT
        rts
@w:     jsr     worst
        bcc     @nums
        rts
@nums:  lda     op
        bmi     @cmpn
        cmp     #4
        beq     @pow
        asl     a
        tax
        lda     arithv+1,x
        pha
        lda     arithv,x
        pha
        rts
@pow:   jmp     power
@cmpn:  jsr     _vc_cmp                 ; -1, 0, 1 -> 1 (<), 4 (=), 2 (>)
        tax
        beq     @eq
        bmi     @lt
        lda     #2
        bne     @out
@lt:    lda     #1
        bne     @out
@eq:    lda     #4
@out:   ldx     #T_FALSE                ; is that outcome accepted by op?
        and     op
        beq     @f
        dex
@f:     stx     _vc_acc+VT
        rts
arithv: .word   _vc_add-1, _vc_sub-1, _vc_mul-1, _vc_div-1

; C set for TRUE or FALSE in A.
istruth:
        cmp     #T_TRUE
        bcc     @n
        cmp     #T_EMPTY
        bcs     @n
        sec
        rts
@n:     clc
        rts

; ACC = the operand at ptr2.
operand:
        inc     depth
        lda     depth
        cmp     #MAXDEPTH
        bcc     :+
        jmp     abort
:       jsr     opnd
        dec     depth
        rts
opnd:   jsr     ppeek
        cmp     #'-'
        bne     @plus
        jsr     adv
        jsr     operand
        jsr     numacc
        lda     _vc_acc+VT
        beq     @neg
        cmp     #T_TRUE
        bcc     @r                      ; ERROR, NA: as they are
        lda     #T_ERROR
        sta     _vc_acc+VT
@r:     rts
@neg:   lda     _vc_acc+VM
        beq     @r                      ; -0 is 0
        lda     _vc_acc+VS
        eor     #$80
        sta     _vc_acc+VS
        rts
@plus:  cmp     #'+'
        bne     @paren
        jsr     adv
        jmp     operand
@paren: cmp     #'('
        bne     @fn
        jsr     adv
        jsr     expr
        jsr     peek
        beq     @r                      ; the end closes what is open
        cmp     #')'
        bne     @bad
        jmp     adv
@fn:    cmp     #'@'
        bne     @num
        jmp     function
@num:   cmp     #'.'
        beq     @lit
        cmp     #'0'
        bcc     @ref
        cmp     #'9' + 1
        bcs     @ref
@lit:   lda     ptr2
        sta     ptr1
        lda     ptr2+1
        sta     ptr1+1
        jsr     parse
        tya
        beq     @bad
        clc
        adc     ptr2
        sta     ptr2
        bcc     :+
        inc     ptr2+1
:       rts
@ref:   jsr     ref
        bcs     @bad
        jsr     isrange
        beq     @bad
        jmp     lookup
@bad:   jmp     abort
        .segment "CODE"

; A cell name at ptr2 (A1, BK254) into refc, refr, ptr2 after it; C set if
; there is none (ptr2 then moved).
ref:    jsr     letter
        bcs     @no
        sta     refc
        jsr     adv
        jsr     letter
        bcs     @digits
        ldx     refc                    ; two letters: (first + 1) * 26 + second
        inx
        stx     tmp1
        sta     tmp2
        lda     #0
        ldx     #26
@m:     clc
        adc     tmp1
        bcs     @no
        dex
        bne     @m
        clc
        adc     tmp2
        bcs     @no
        sta     refc
        jsr     adv
@digits:
        lda     #0
        sta     refr
        ldx     #0
@d:     jsr     peek
        sec
        sbc     #'0'
        cmp     #10
        bcs     @end
        sta     tmp1
        cpx     #3
        bcs     @no                     ; a fourth digit
        lda     refr                    ; refr * 10 + digit, 255 at most
        cmp     #26
        bcs     @no
        asl     a
        sta     tmp2
        asl     a
        asl     a
        adc     tmp2
        adc     tmp1
        bcs     @no
        sta     refr
        inx
        jsr     adv
        jmp     @d
@end:   txa
        beq     @no
        lda     refr
        beq     @no
        cmp     #255
        bcs     @no
        lda     refc
        cmp     #NCOLS
        bcs     @no
        clc
        rts
@no:    sec
        rts
; The letter at ptr2: C clear and A = 0..25, or C set.
letter: jsr     peek
        sec
        sbc     #'A'
        cmp     #26
        rts

; unsigned char __fastcall__ vc_cellref(const char* s): the cell name at s
; into vc_refc, vc_refr; its length, 0 if there is none.
_vc_cellref:
        sta     ptr2
        stx     ptr2+1
        sta     tmp3
        jsr     ref
        lda     #0
        bcs     @r
        lda     ptr2
        sec
        sbc     tmp3
@r:     ldx     #0
        rts

; Z set when "..." follows: ptr2 then past it.
isrange: ldy    #0
@l:     lda     (ptr2),y
        cmp     #'.'
        bne     @no
        iny
        cpy     #3
        bne     @l
        lda     ptr2
        clc
        adc     #3
        sta     ptr2
        bcc     :+
        inc     ptr2+1
:       lda     #0
        rts
@no:    lda     #1
        rts
        .segment "VCB"

; -- functions ------------------------------------------------------------------------

; The names, in the order of the function numbers below, each ended by 0.
fnames: .byte   "NA",0,"ERROR",0,"PI",0,"TRUE",0,"FALSE",0
        .byte   "ABS",0,"INT",0,"NOT",0,"ISNA",0,"ISERROR",0
        .byte   "SQRT",0,"EXP",0,"LN",0,"LOG10",0,"SIN",0,"COS",0,"TAN",0
        .byte   "ASIN",0,"ACOS",0,"ATAN",0
        .byte   "SUM",0,"MIN",0,"MAX",0,"COUNT",0,"AVERAGE",0,"AND",0,"OR",0,"CHOOSE",0
        .byte   "IF",0,"NPV",0,"LOOKUP",0,0
F_PI    = 2
F_ABS   = 5
F_INT   = 6
F_NOT   = 7
F_ISNA  = 8
F_ISERR = 9
F_SQRT  = 10
F_SUM   = 20
F_MIN   = 21
F_MAX   = 22
F_COUNT = 23
F_AVG   = 24
F_AND   = 25
F_OR    = 26
F_CHOOSE = 27
F_IF    = 28
F_NPV   = 29
F_LOOKUP = 30

pi:     .byte   0, 0, 65, $03, $14, $15, $92, $65, $36

        .segment "BSS"
fname:  .res    8
rc1:    .res    1               ; a range: its columns and rows, and where
rc2:    .res    1               ; the walk is
rr1:    .res    1
rr2:    .res    1
itc:    .res    1
itr:    .res    1
npv_f:  .res    9
npv_p:  .res    9
hitc:   .res    1
hitr:   .res    1

        .segment "VCB"
function:
        jsr     adv                     ; the name: letters, then digits too
        ldx     #0
@n:     jsr     peek
        cmp     #'A'
        bcc     @dig
        cmp     #'Z' + 1
        bcc     @take
@dig:   cpx     #0
        beq     @end
        cmp     #'0'
        bcc     @end
        cmp     #'9' + 1
        bcs     @end
@take:  cpx     #7
        bcs     @bad
        sta     fname,x
        inx
        jsr     adv
        jmp     @n
@end:   lda     #0
        sta     fname,x
        ldy     #0                      ; which one
        sty     fid
@try:   ldx     #0
@cmp:   lda     fnames,y
        cmp     fname,x
        bne     @skip
        iny
        inx
        cmp     #0
        bne     @cmp
        beq     @found
@skip:  lda     fnames,y                ; to the next name
        beq     @nx
        iny
        bne     @skip
@nx:    iny
        inc     fid
        lda     fnames,y
        bne     @try
@bad:   jmp     abort
@found: lda     fid
        cmp     #F_ABS
        bcs     @args
        tax                             ; NA ERROR PI TRUE FALSE
        cpx     #F_PI
        bne     @const
        ldx     #8
@p:     lda     pi,x
        sta     _vc_acc,x
        dex
        bpl     @p
        rts
@const: lda     ctype,x
        sta     _vc_acc+VT
        rts
@args:  jsr     peek
        cmp     #'('
        bne     @bad
        jsr     adv
        lda     fid
        cmp     #F_SUM
        bcs     @more
        pha
        jsr     expr                    ; one value
        jsr     argend
        bcc     @bad                    ; more than one
        pla
        jmp     func1
@more:  cmp     #F_IF
        bcs     @three
        jmp     listf
@three: bne     @two
        jmp     iff
@two:   jmp     rangef
ctype:  .byte   T_NA, T_ERROR, 0, T_TRUE, T_FALSE

; After an argument: C clear for a comma (more follow), C set for the
; closing parenthesis or the end of the formula.
argend: jsr     peek
        beq     @end
        cmp     #')'
        beq     @close
        cmp     #','
        bne     @bad
        jsr     adv
        clc
        rts
@close: jsr     adv
@end:   sec
        rts
@bad:   jmp     abort

; ACC a number: C clear. ERROR or NA: C set, as they are; a truth value:
; ERROR, C set. EMPTY counts as 0.
num1:   jsr     numacc
        lda     _vc_acc+VT
        beq     @n
        cmp     #T_TRUE
        bcc     @s
        lda     #T_ERROR
        sta     _vc_acc+VT
@s:     sec
        rts
@n:     clc
        rts

; The one-value functions; A = which.
func1:  cmp     #F_ISNA
        bcc     @abs
        bne     @iserr
        jsr     numacc
        ldx     #T_TRUE
        lda     _vc_acc+VT
        cmp     #T_NA
        beq     @t
        inx
@t:     stx     _vc_acc+VT
        rts
@iserr: cmp     #F_ISERR
        bne     @rom
        jsr     numacc
        ldx     #T_TRUE
        lda     _vc_acc+VT
        cmp     #T_ERROR
        beq     @t
        inx
        bne     @t
@abs:   cmp     #F_NOT
        beq     @not
        pha
        jsr     num1
        pla
        bcs     @r
        cmp     #F_INT
        beq     @int
        lda     #0                      ; ABS
        sta     _vc_acc+VS
@r:     rts
@int:   jmp     _vc_int
@not:   jsr     numacc
        lda     _vc_acc+VT
        jsr     istruth
        bcs     @flip
        lda     _vc_acc+VT
        beq     @err
        cmp     #T_TRUE
        bcc     @r                      ; ERROR, NA
@err:   lda     #T_ERROR
        sta     _vc_acc+VT
        rts
@flip:  eor     #T_TRUE ^ T_FALSE
        sta     _vc_acc+VT
        rts
@rom:   pha
        jsr     num1
        pla
        bcs     @r
        jmp     romfn

; -- the list functions: SUM MIN MAX COUNT AVERAGE AND OR CHOOSE --------------------

; The state, saved around an argument's own evaluation: it may call one.
LFS     = 17                    ; fid .. lf_sel, contiguous in BSS

listf:  lda     #0
        sta     lf_cnt
        sta     lf_cnt+1
        sta     lf_flg
        sta     lf_k
        sta     lf_sel
        lda     #1
        sta     lf_first
        ldx     #T_TRUE                 ; AND starts true, OR false
        lda     fid
        cmp     #F_AND
        beq     @b
        inx
@b:     stx     lf_bool
        jsr     setzero
        ldx     #8
@z:     lda     _vc_acc,x
        sta     lf_acc,x
        dex
        bpl     @z
@arg:   lda     ptr2                    ; a range?
        pha
        lda     ptr2+1
        pha
        jsr     range
        bcs     @value
        pla
        pla
@cell:  jsr     rnext
        bcs     @next
        jsr     lookup
        lda     _vc_acc+VT
        cmp     #T_EMPTY
        bne     @feed
        lda     fid                     ; a blank in a range: only MIN and
        cmp     #F_MIN                  ; MAX count it (as 0)
        beq     @feed
        cmp     #F_MAX
        bne     @cell
@feed:  jsr     feed
        jmp     @cell
@value: pla
        sta     ptr2+1
        pla
        sta     ptr2
        jsr     lfsave
        jsr     expr
        jsr     lfrest
        jsr     feed
@next:  jsr     argend
        bcc     @arg
        jmp     lfend

lfsave: lda     vsp
        cmp     #9 * VSTACK - LFS
        bcs     @bad
        tax
        ldy     #0
@l:     lda     fid,y
        sta     vstk,x
        inx
        iny
        cpy     #LFS
        bne     @l
        stx     vsp
        rts
@bad:   jmp     abort
lfrest: lda     vsp
        sec
        sbc     #LFS
        sta     vsp
        tax
        ldy     #0
@l:     lda     vstk,x
        sta     fid,y
        inx
        iny
        cpy     #LFS
        bne     @l
        rts

; The flag for ACC's type: 1 ERROR, 2 NA, 4 a truth value; 0 a number.
tflag:  lda     _vc_acc+VT
        beq     @r
        cmp     #T_ERROR
        beq     @r                      ; 1
        cmp     #T_NA
        beq     @r                      ; 2
        lda     #4
@r:     ora     #0                      ; Z: a number
        rts

; One value into the list function's state.
feed:   lda     fid
        cmp     #F_COUNT
        bne     @ch
        inc     lf_cnt
        bne     @r
        inc     lf_cnt+1
@r:     rts
@ch:    cmp     #F_CHOOSE
        bne     @ao
        lda     lf_sel
        bne     @r                      ; decided
        lda     lf_first
        beq     @item
        lda     #0
        sta     lf_first
        jsr     num1
        bcs     @decide                 ; ERROR, NA: the outcome
        jsr     byteval                 ; the item wanted, 1..255 (0: none)
        sta     lf_k
        bne     @r
        lda     #T_NA
        sta     _vc_acc+VT
        bne     @decide
@item:  dec     lf_k
        bne     @r
@decide: ldx    #8
@dc:    lda     _vc_acc,x
        sta     lf_acc,x
        dex
        bpl     @dc
        inc     lf_sel
        rts
@ao:    cmp     #F_AND
        bcc     @num
        jsr     numacc                  ; a blank cell read: 0, no truth value
        jsr     tflag                   ; AND, OR
        cmp     #4
        beq     @truth
        tax
        bne     @flag
        lda     #8                      ; a number (or a blank): not a truth value
        bne     @flag
@truth: lda     _vc_acc+VT
        ldx     fid
        cpx     #F_AND
        beq     @and
        cmp     #T_TRUE                 ; OR: one true makes it true
        bne     @r
        sta     lf_bool
        rts
@and:   cmp     #T_FALSE
        bne     @r
        sta     lf_bool
        rts
@flag:  ora     lf_flg
        sta     lf_flg
        rts
@num:   jsr     numacc                  ; SUM MIN MAX AVERAGE
        jsr     tflag
        bne     @flag
        lda     fid
        cmp     #F_MIN
        beq     @mm
        cmp     #F_MAX
        beq     @mm
        jsr     lfarg                   ; SUM, AVERAGE: lf_acc += ACC
        jsr     _vc_add
        jsr     tflag
        bne     @flag                   ; out of range
        jsr     tolf
        inc     lf_cnt
        bne     @r2
        inc     lf_cnt+1
@r2:    rts
@mm:    lda     lf_first
        beq     @cmpm
        lda     #0
        sta     lf_first
        jmp     tolf
@cmpm:  jsr     lfarg
        jsr     _vc_cmp                 ; ACC against the best so far
        tax
        beq     @r2
        lda     fid
        cmp     #F_MIN
        beq     @min
        txa
        bmi     @r2
        jmp     tolf
@min:   txa
        bpl     @r2
        jmp     tolf

; ARG = lf_acc; lf_acc = ACC
lfarg:  ldx     #8
@l:     lda     lf_acc,x
        sta     _vc_arg,x
        dex
        bpl     @l
        rts
tolf:   ldx     #8
@l:     lda     _vc_acc,x
        sta     lf_acc,x
        dex
        bpl     @l
        rts

; The outcome of a list function.
lfend:  lda     fid
        cmp     #F_COUNT
        bne     @ch
@cnt:   lda     lf_cnt
        ldx     lf_cnt+1
        jmp     setint
@ch:    cmp     #F_CHOOSE
        bne     @flags
        lda     lf_sel
        beq     @none
@acc:   ldx     #8
@l:     lda     lf_acc,x
        sta     _vc_acc,x
        dex
        bpl     @l
        rts
@none:  lda     lf_first                ; no value at all: ERROR
        bne     @err
@na:    lda     #T_NA
        bne     @set
@flags: lda     lf_flg
        lsr     a
        bcs     @err                    ; ERROR first
        lsr     a
        bcs     @na                     ; then NA
        bne     @err                    ; then a wrong type
        lda     fid
        cmp     #F_AND
        bcc     @nums
        lda     lf_bool                 ; AND, OR
@set:   sta     _vc_acc+VT
        rts
@err:   lda     #T_ERROR
        bne     @set
@nums:  cmp     #F_AVG
        bne     @mm
        lda     lf_cnt
        ora     lf_cnt+1
        beq     @err                    ; 0 / 0
        lda     lf_cnt
        ldx     lf_cnt+1
        jsr     setint
        jsr     acc2arg
        jsr     @acc
        jmp     _vc_div
@mm:    cmp     #F_SUM
        beq     @acc
        lda     lf_first                ; MIN, MAX of nothing: 0
        beq     @acc
        jmp     setzero

; ACC (a number) as a byte: its integer part, 1..255, or 0 when outside.
byteval:
        lda     _vc_acc+VS
        bmi     @z
        jsr     unpackdig
        lda     xexp
        bmi     @z
        cmp     #3
        bcs     @z
        ldx     #0
        stx     tmp1
@d:     lda     tmp1                    ; tmp1 * 10 + digit
        asl     a
        sta     tmp2
        asl     a
        asl     a
        clc
        adc     tmp2
        bcs     @z
        sta     tmp2
        jsr     dg
        clc
        adc     tmp2
        bcs     @z
        sta     tmp1
        cpx     xexp
        beq     @r
        inx
        bne     @d
@r:     lda     tmp1
        rts
@z:     lda     #0
        rts

; ACC = the unsigned integer A (low), X (high).
setint: sta     tmp1
        stx     tmp2
        lda     #0
        sta     ndig
        ldy     #8                      ; 10000 1000 100 10 1
@p:     ldx     #0
@s:     lda     tmp1
        sec
        sbc     pow10,y
        pha
        lda     tmp2
        sbc     pow10+1,y
        bcc     @lt
        sta     tmp2
        pla
        sta     tmp1
        inx
        bne     @s
@lt:    pla
        txa
        ldx     ndig
        bne     @keep
        cmp     #0
        beq     @nx                     ; leading zeros
@keep:  sta     digits,x
        inc     ndig
@nx:    dey
        dey
        bpl     @p
        lda     #0
        sta     _vc_acc+VT
        sta     _vc_acc+VS
        lda     ndig
        bne     @nz
        jmp     setzero
@nz:    sec
        sbc     #1
        sta     xexp
        jmp     packdig
        .segment "CODE"
pow10:  .word   1, 10, 100, 1000, 10000
        .segment "VCB"

; -- ranges -------------------------------------------------------------------------

; A range at ptr2 (A1...A9): rc1/rr1 to rc2/rr2, low to high, the walk
; ready; C clear. C set when there is none (ptr2 moved).
range:  jsr     ref
        bcs     @no
        jsr     isrange
        bne     @no
        lda     refc
        sta     rc1
        lda     refr
        sta     rr1
        jsr     ref
        bcs     @bad
        lda     refc
        sta     rc2
        lda     refr
        sta     rr2
        lda     rc1                     ; a row or a column, nothing wider
        cmp     rc2
        beq     @order
        lda     rr1
        cmp     rr2
        bne     @bad
@order: lda     rc1
        cmp     rc2
        bcc     @r
        ldx     rc2
        sta     rc2
        stx     rc1
@r:     lda     rr1
        cmp     rr2
        bcc     @w
        ldx     rr2
        sta     rr2
        stx     rr1
@w:     lda     rc1
        sta     itc
        lda     rr1
        sta     itr
        dec     itr                     ; rnext moves first
        clc
        rts
@no:    sec
        rts
@bad:   jmp     abort

; The next cell of the range into refc/refr: C clear; C set at its end.
; (Escape is asked for at each: tick.)
rnext:  jsr     poll
        lda     itr
        cmp     rr2
        bcc     @row
        lda     itc                     ; the row range's next column
        cmp     rc2
        bcs     @end
        inc     itc
        lda     rr1
        sta     itr
        bcc     @set                    ; (C clear from the cmp) always
@row:   inc     itr
@set:   lda     itc
        sta     refc
        lda     itr
        sta     refr
        clc
        rts
@end:   sec
        rts

; -- IF, NPV, LOOKUP -------------------------------------------------------------------

iff:    jsr     expr                    ; the condition
        jsr     numacc
        lda     _vc_acc+VT
        cmp     #T_TRUE                 ; TRUE: 0, FALSE: 1
        beq     @code0
        cmp     #T_FALSE
        beq     @code1
        cmp     #0                      ; ERROR, NA: the outcome; a number: ERROR
        bne     @keep
        lda     #T_ERROR
        sta     _vc_acc+VT
@keep:  jsr     push
        lda     #2
        bne     @code
@code1: lda     #1
        bne     @code
@code0: lda     #0
@code:  pha
        jsr     argend
        bcs     @bad
        jsr     expr
        jsr     push
        jsr     argend
        bcs     @bad
        jsr     expr
        jsr     argend
        bcc     @bad
        jsr     acc2arg                 ; ARG = the "false" value
        jsr     pop                     ; ACC = the "true" one
        pla
        beq     @r
        cmp     #1
        bne     @c
        jmp     swap
@c:     jmp     pop                     ; the condition's own ERROR or NA
@r:     rts
@bad:   jmp     abort

; NPV(rate, range) and LOOKUP(value, range).
rangef: lda     fid                     ; (a call in the value sets fid)
        pha
        jsr     expr
        pla
        sta     fid
        jsr     argend
        bcs     @bad
        jsr     range
        bcs     @bad
        jsr     argend
        bcc     @bad
        jsr     num1
        bcs     @r
        lda     fid
        cmp     #F_NPV
        beq     npv
        jmp     lookupf
@bad:   jmp     abort
@r:     rts

npv:    jsr     acc2arg                 ; f = 1 + rate
        lda     #1
        ldx     #0
        jsr     setint
        jsr     _vc_add
        jsr     num1
        bcs     @r
        ldx     #8
@f:     lda     _vc_acc,x
        sta     npv_f,x
        dex
        bpl     @f
        lda     #1                      ; p = 1
        ldx     #0
        jsr     setint
        jsr     @top
        jsr     setzero                 ; the sum
        jsr     tolf
@cell:  jsr     rnext
        bcs     @done
        ldx     #8                      ; p = p * f
@p:     lda     npv_p,x
        sta     _vc_acc,x
        lda     npv_f,x
        sta     _vc_arg,x
        dex
        bpl     @p
        jsr     _vc_mul
        jsr     num1
        bcs     @r
        jsr     @top
        jsr     lookup                  ; v / p, added
        jsr     num1
        bcs     @r
        ldx     #8
@q:     lda     npv_p,x
        sta     _vc_arg,x
        dex
        bpl     @q
        jsr     _vc_div
        jsr     num1
        bcs     @r
        jsr     lfarg
        jsr     _vc_add
        jsr     num1
        bcs     @r
        jsr     tolf
        jmp     @cell
@done:  ldx     #8
@d:     lda     lf_acc,x
        sta     _vc_acc,x
        dex
        bpl     @d
@r:     rts
@top:   ldx     #8                      ; npv_p = ACC
@t:     lda     _vc_acc,x
        sta     npv_p,x
        dex
        bpl     @t
        rts

lookupf:
        lda     rc1                     ; two cells at least
        cmp     rc2
        bne     @ok
        lda     rr1
        cmp     rr2
        bne     @ok
        jmp     seterror
@ok:    jsr     tolf                    ; lf_acc: the value looked for
        lda     #0
        sta     hitc
@cell:  jsr     rnext
        bcs     @done
        jsr     lookup
        jsr     num1
        bcs     @r
        jsr     lfarg
        jsr     _vc_cmp
        cmp     #1
        beq     @done                   ; past it
        lda     refc
        sta     hitc
        lda     refr
        sta     hitr
        inc     hitc                    ; (+1: 0 means none)
        jmp     @cell
@done:  lda     hitc
        bne     @hit
        lda     #T_NA
        sta     _vc_acc+VT
@r:     rts
@hit:   ldx     hitc                    ; the cell beside: right of a column,
        dex                             ; under a row
        lda     rc1
        cmp     rc2
        bne     @below
        inx
        bne     @at
@below: inc     hitr
@at:    stx     refc
        lda     hitr
        sta     refr
        cmp     #255
        bcs     @e
        cpx     #NCOLS
        bcs     @e
        jsr     lookup
        jmp     numacc
@e:     jmp     seterror

; -- powers and the transcendental functions, on Applesoft's ROM --------------------
; VisiCalc computes these with its own decimal series; the overlay has no
; room for them and hands the work to the ROM: x is rebuilt there digit by
; digit (MUL10, then a digit added), the function or FPWRT run, and FOUT's
; nine digits read back. The ROM's zero page ($50-$FF, cc65's own in it) is
; saved in rom_zp and put back; the language card is switched off for the
; ROM ($C082) and back on bank 2 ($C080), interrupts off in between; the
; ROM's errors (an overflow, the logarithm of a negative number...) go
; through ONERR to rom_trap: ERROR. Only absolute variables are touched
; while the ROM's zero page is in place.

GIVAYF  = $E2F2
MOVMF   = $EB2B
MOVFM   = $EAF9
CONUPK  = $E9E3
FADD    = $E7BE
FSUB    = $E7A7
FMULT   = $E97F
FDIV    = $EA66
FPWRT   = $EE97
FOUT    = $ED34
NEGOP   = $EED0
MUL10   = $EA39
DIV10   = $EA55
FACEXP  = $9D

        .segment "BSS"
rop:    .res    1               ; the function number, or 0 for a power
rsp:    .res    1
rdig:   .res    14              ; the operands: digits, count, X, sign
rnd2:   .res    1
rx2:    .res    1
rsg2:   .res    1
rx:     .res    5               ; ROM numbers
rt:     .res    5
rone:   .res    5
rstr:   .res    20
rstep:  .res    1

; ACC = f(ACC), f = A (F_SQRT...).
        .segment "VCB"
romfn:  sta     rop
        jmp     romgo
; ACC = ACC ^ ARG. 0 to a power <= 0 is ERROR, as VisiCalc has it (the
; ROM says 1 for 0^0, 0 for 0^-1).
power:  lda     _vc_acc+VM
        bne     @go
        lda     _vc_arg+VS
        bmi     @e
        lda     _vc_arg+VM
        bne     @go
@e:     jmp     seterror
@go:    lda     #0
        sta     rop
        jsr     swap                    ; the exponent's digits first, into rdig
        jsr     digs
        ldx     #13
@c:     lda     digits,x
        sta     rdig,x
        dex
        bpl     @c
        lda     ndig
        sta     rnd2
        lda     xexp
        sta     rx2
        lda     sgn
        sta     rsg2
        jsr     swap
romgo:  jsr     digs                    ; x's into digits/ndig/xexp/sgn
        lda     xexp                    ; beyond the ROM's range: ERROR
        bmi     @ok
        cmp     #38
        bcc     @ok
        jmp     seterror
@ok:    jsr     zpat                    ; the zero page aside, in copy_buf
        ldy     #0                      ; + 256 (ptr4 is saved holding that
@s:     lda     $0050,y                 ; address, and is put back to it)
        sta     (ptr4),y
        iny
        cpy     #$B0
        bne     @s
        lda     #$80                    ; ONERR: errors come to rom_trap
        sta     $D8
        lda     #$4C
        sta     $B7
        lda     #<rom_trap
        sta     $F4
        lda     #>rom_trap
        sta     $F5
        lda     #0
        sta     $A4                     ; FOUT counts on it
        php
        sei
        tsx
        stx     rsp
        bit     $C082
        jsr     romrun
        lda     #0
rback:  bit     $C080
        plp
        sta     rstep                   ; 1: the ROM refused
        jsr     zpat
        ldy     #0
@r:     lda     (ptr4),y
        sta     $0050,y
        iny
        cpy     #$B0
        bne     @r
        lda     rstep
        beq     @parse
        jmp     seterror
@parse: lda     #0                      ; FOUT's text: a sign, the number
        sta     tmp4
        ldx     #0
@sk:    lda     rstr,x
        cmp     #' '
        beq     @nx
        cmp     #'-'
        bne     @num
        lda     #$80
        sta     tmp4
@nx:    inx
        cpx     #19
        bcc     @sk
@num:   txa
        clc
        adc     #<rstr
        ldx     #>rstr
        bcc     :+
        inx
:       jsr     _vc_parse
        tax
        beq     @bad
        lda     _vc_acc+VT
        bne     @done
        lda     _vc_acc+VM
        beq     @done
        lda     tmp4
        sta     _vc_acc+VS
@done:  rts
@bad:   jmp     seterror

zpat:   lda     rbuf
        sta     ptr4
        ldx     rbuf+1
        inx
        stx     ptr4+1
        rts

rom_trap:
        ldx     rsp
        txs
        lda     #1
        jmp     rback

; ACC's digits, its exponent X and its sign (1 negative) for the ROM.
digs:   jsr     unpackdig
        lda     #0
        sta     sgn
        lda     _vc_acc+VS
        beq     :+
        inc     sgn
:       rts

; In ROM mode. FAC = x (digits), then the operation, FOUT into rstr.
romrun: jsr     load                    ; FAC = x
        lda     rop
        bne     @fn
        ldx     #<rx                    ; a power: x aside, FAC = y, ARG = x
        ldy     #>rx
        jsr     MOVMF
        ldx     #13
@cy:    lda     rdig,x
        sta     digits,x
        dex
        bpl     @cy
        lda     rnd2
        sta     ndig
        lda     rx2
        sta     xexp
        lda     rsg2
        sta     sgn
        jsr     load
        lda     #<rx
        ldy     #>rx
        jsr     CONUPK
        lda     FACEXP
        jsr     FPWRT
        jmp     rdone
@fn:    sec
        sbc     #F_SQRT
        asl     a
        tax
        lda     romv+1,x
        pha
        lda     romv,x
        pha
        rts                             ; to the function, which comes back to:
rdone:  jsr     FOUT
        ldy     #0
@c:     lda     $0100,y
        sta     rstr,y
        beq     @e
        iny
        cpy     #19
        bne     @c
        lda     #0
        sta     rstr,y
@e:     rts

romv:   .word   f_sqr-1, f_exp-1, f_log-1, f_log10-1, f_sin-1, f_cos-1, f_tan-1
        .word   f_asin-1, f_acos-1, f_atn-1

f_sqr:  jsr     $EE8D
        jmp     rdone
f_exp:  jsr     $EF09
        jmp     rdone
f_log:  jsr     $E941
        jmp     rdone
f_sin:  jsr     $EFF1
        jmp     rdone
f_cos:  jsr     $EFEA
        jmp     rdone
f_tan:  jsr     $F03A
        jmp     rdone
f_atn:  jsr     $F09E
        jmp     rdone
f_log10:
        jsr     $E941                   ; ln x / ln 10
        ldx     #<rt
        ldy     #>rt
        jsr     MOVMF
        lda     #0
        ldy     #10
        jsr     GIVAYF
        jsr     $E941
        lda     #<rt
        ldy     #>rt
        jsr     FDIV
        jmp     rdone
f_asin: jsr     asin
        jmp     rdone
f_acos: jsr     asin                    ; pi/2 - asin x
        lda     #<pihalf
        ldy     #>pihalf
        jsr     FSUB
        jmp     rdone
; asin x = 2 atn(x / (1 + sqr(1 - x^2))): no division by zero at |x| = 1
asin:   ldx     #<rx
        ldy     #>rx
        jsr     MOVMF                   ; x
        lda     #<rx
        ldy     #>rx
        jsr     FMULT                   ; x^2
        ldx     #<rt
        ldy     #>rt
        jsr     MOVMF
        lda     #0
        ldy     #1
        jsr     GIVAYF
        ldx     #<rone
        ldy     #>rone
        jsr     MOVMF                   ; 1
        lda     #<rt
        ldy     #>rt
        jsr     MOVFM
        lda     #<rone
        ldy     #>rone
        jsr     FSUB                    ; 1 - x^2
        jsr     $EE8D                   ; its root
        lda     #<rone
        ldy     #>rone
        jsr     FADD                    ; + 1
        lda     #<rx
        ldy     #>rx
        jsr     FDIV                    ; x / that
        jsr     $F09E
        ldx     #<rt
        ldy     #>rt
        jsr     MOVMF
        lda     #<rt
        ldy     #>rt
        jmp     FADD                    ; twice
pihalf: .byte   $81, $49, $0F, $DA, $A2


; FAC = the number digits/ndig/xexp/sgn: digit by digit, then scaled.
load:   lda     #0
        tay
        jsr     GIVAYF
        lda     #0
        sta     rstep
@d:     ldx     rstep
        cpx     ndig
        bcs     @scale
        jsr     MUL10
        ldx     #<rt
        ldy     #>rt
        jsr     MOVMF
        ldx     rstep
        ldy     digits,x
        lda     #0
        jsr     GIVAYF
        lda     #<rt
        ldy     #>rt
        jsr     FADD
        inc     rstep
        bne     @d
@scale: lda     ndig                    ; times 10^(X - ndig + 1)
        beq     @sign
        sec
        sbc     #1
        sta     rstep
        lda     xexp
        sec
        sbc     rstep
        sta     rstep
@up:    lda     rstep
        beq     @sign
        bmi     @down
        jsr     MUL10
        dec     rstep
        jmp     @up
@down:  jsr     DIV10
        inc     rstep
        jmp     @up
@sign:  lda     sgn
        beq     @r
        jmp     NEGOP
@r:     rts


; == the overlay: the file, the table, the screen ==================================
;
; Everything below calls the program through its service table the way cc65
; code does (arguments on the C stack, the last one in A/X), through jtab:
; a JMP per service, filled at the entry from the table the core passes.
; The services are cc65 code: they spend the zero page (ptr1-4, tmp1-4,
; sreg), so nothing below keeps a value there across a call.

        .export _plugin_entry
        .import pushax, pusha, pusheax
        .import _vc_ofs                 ; visicalc.c: the services' offsets
        .import __BSS_RUN__, __BSS_SIZE__

.ifndef VC_TOP
VC_TOP  = $4000                         ; the end of the big overlay window
.endif
NFIELDS = 5                             ; full, copy_buf, note, selected, cfg_path
NSVC    = 14
J_FOPEN = jtab
J_FREAD = jtab + 3
J_FSEEK = jtab + 6
J_FCLOSE = jtab + 9
J_STRCPY = jtab + 12
J_CGETC = jtab + 15
J_GOTOXY = jtab + 18
J_CPUTS = jtab + 21
J_REVERS = jtab + 24
J_CLRSCR = jtab + 27
J_BAR   = jtab + 30
J_KEYS  = jtab + 33
J_RAMFMT = jtab + 36
J_AUXOK = jtab + 39
SHEETROWS = 20
RBSZ    = 255                           ; reads into copy_buf[0..254]
E_SIZE  = 23                            ; struct Entry: size

        .segment "BSS"
jtab:   .res    3 * NSVC
fields: .res    2 * NFIELDS             ; full, copy_buf, note, selected
fullp   = fields
rbuf    = fields + 2
notep   = fields + 4
selp    = fields + 6
cfgp    = fields + 8
fh:     .res    2                       ; the file
fsize:  .res    2
fpos:   .res    2                       ; rbuf[0]'s offset
have:   .res    1
at:     .res    1
eof:    .res    1
cut:    .res    1                       ; a read failed
lnlen:  .res    1
lnlong: .res    1
lnoff:  .res    2
contp:  .res    1                       ; where the contents start in ln
cfmt:   .res    1
lc:     .res    1
lr:     .res    1
width:  .res    1
gfmt:   .res    1
order:  .res    1
unord:  .res    1
window2: .res   1
cells_end: .res 2
spanend: .res   2
curc:   .res    1
curr:   .res    1
leftc:  .res    1
top:    .res    1
lastk:  .res    2
nvals:  .res    2
cnt0:   .res    1                       ; loops
cnt1:   .res    1
ep:     .res    2                       ; an entry
key:    .res    1
entsp:  .res    1
apiver: .res    1
auxed:  .res    1                       ; the table is in the auxiliary bank
roomaux: .res   1                       ; a table refused: 1 for the auxiliary bank's room
spinok: .res    1                       ; 1 while reading and recalculating
ecol:   .res    1
erow:   .res    1
moff:   .res    2
drawn:  .res    1                       ; ui: the screen shows the window
oleft:  .res    1                       ; ... from oleft, otop, the cursor
otop:   .res    1                       ; at oc, orow
oc:     .res    1
orow:   .res    1

; -- the services -------------------------------------------------------------------

; void plugin_entry(const struct A2fcApi* api)
        .segment "CODE"
_plugin_entry:
        sta     ptr1
        stx     ptr1+1
        tsx                             ; for leave: S as the core's
        stx     entsp                   ; call left it
        ldy     #0                      ; the API's version
        lda     (ptr1),y
        sta     apiver
        sty     auxed
        sta     $C056                   ; LORES: $2000-$3FFF is ours, MAIN
        sta     $C002
        sta     $C004
        ldx     #0                      ; the four fields
@f:     txa
        lsr     a
        tay
        lda     _vc_ofs,y
        tay
        lda     (ptr1),y
        sta     fields,x
        iny
        lda     (ptr1),y
        sta     fields+1,x
        inx
        inx
        cpx     #2 * NFIELDS
        bne     @f
        lda     #NFIELDS                ; the services, as JMPs
        sta     cnt0
        ldx     #0
@j:     ldy     cnt0
        lda     _vc_ofs,y
        tay
        lda     #$4C
        sta     jtab,x
        lda     (ptr1),y
        sta     jtab+1,x
        iny
        lda     (ptr1),y
        sta     jtab+2,x
        inx
        inx
        inx
        inc     cnt0
        cpx     #3 * NSVC
        bne     @j
        jmp     main


; gotoxy(A, X), then cputs(ep).
putxy:  stx     key
        jsr     pusha
        lda     key
        jsr     J_GOTOXY
        lda     ep
        ldx     ep+1
        jmp     J_CPUTS

; -- the file -----------------------------------------------------------------------

; fseek(fh, A/X, SEEK_SET); the buffer emptied. cut on a refusal.
seekto: sta     fpos
        stx     fpos+1
        lda     #0
        sta     have
        sta     at
        sta     eof
        lda     fh
        ldx     fh+1
        jsr     pushax
        lda     #0
        sta     sreg
        sta     sreg+1
        lda     fpos
        ldx     fpos+1
        jsr     pusheax
        lda     _vc_ofs + NFIELDS + NSVC        ; SEEK_SET (cc65's is 2)
        ldx     #0
        jsr     J_FSEEK
        stx     tmp1
        ora     tmp1
        beq     @r
        lda     #1
        sta     cut
        sta     eof
@r:     rts

; The next line into ln, its offset in lnoff, C set; C clear when the file
; has none left. CR or LF ends a line, a zero byte the file (DOS 3.3 text).
; The bytes lose their high bit. A file that stops short of its size, or
; would pass 64 KB, is cut.
rdline: lda     #0
        sta     lnlen
        sta     lnlong
        lda     fpos
        clc
        adc     at
        sta     lnoff
        lda     fpos+1
        adc     #0
        sta     lnoff+1
@next:  lda     at
        cmp     have
        bne     @byte
        lda     eof
        jne     @end
        lda     fpos                    ; fpos += have
        clc
        adc     have
        sta     fpos
        bcc     :+
        inc     fpos+1
        beq     @cut
:       lda     #0
        sta     at
        jsr     tick
        lda     rbuf                    ; fread(rbuf, 1, 255, fh)
        ldx     rbuf+1
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     #RBSZ
        ldx     #0
        jsr     pushax
        lda     fh
        ldx     fh+1
        jsr     J_FREAD
        sta     have
        tax
        bne     @next
        lda     #1
        sta     eof
        lda     fpos                    ; nothing: before the size, an error
        cmp     fsize
        lda     fpos+1
        sbc     fsize+1
        bcs     @end
@cut:   lda     #1
        sta     cut
        sta     eof
        bne     @end
@byte:  lda     rbuf
        sta     ptr1
        lda     rbuf+1
        sta     ptr1+1
        ldy     at
        lda     (ptr1),y
        and     #$7F
        bne     @c
        sta     have                    ; a zero: the end of the text
        sty     have
        lda     #1
        sta     eof
        bne     @end
@c:     inc     at
        cmp     #$0D
        beq     @line
        cmp     #$0A
        beq     @line
        ldx     lnlen
        cpx     #255
        bcs     @long
        sta     ln,x
        inc     lnlen
        jne     @next
@long:  lda     #1
        sta     lnlong
        jne     @next
@line:  jsr     @term
        sec
        rts
@end:   jsr     @term
        lda     lnlen
        cmp     #1                      ; C: a last line without its CR
        rts
@term:  ldx     lnlen
        lda     #0
        sta     ln,x
        rts

; The resident's activity cell turns, / and \ (spin.h), and Escape stops
; the reading or the recalculation, whose length is the file's to decide
; (13 @NPV over 120 cells in each of 120 cells: an hour and a half at
; 1 MHz, and no key was read before the sheet showed). The keyboard is
; asked here -- at every read of the file, column or row -- and, since one
; formula can walk thousands of cells, at every operand (ppeek) and every
; cell of a range (rnext): never further apart than one operation, one
; function of the ROM.
;
; Only Escape is taken, its strobe cleared by a store. Any other key stays
; in the keyboard register, as it always did while the sheet was computed:
; the sheet's first cgetc gets it (a Space typed ahead pages once).
;
; Leaving from here goes through `leave`, as every refusal does: S as
; plugin_entry found it, the file closed, /RAM rebuilt if the table was in
; the auxiliary bank. Nothing else is held at these places: the ROM bridge
; (romgo: the language card off, the zero page $50-$FF aside, ONERR, the
; interrupts off) and the bank switches (trd1...) are closed again before
; they return, and call nothing that comes here; no argument is on the C
; stack (tools/test_visicalc.py, Escape, holds all of that).
.ifndef VC_TICK
VC_TICK = $06F7                         ; row 21, column 79 (spin.h)
.endif
KBD     = $C000                         ; bit 7: a key is waiting
KBDSTRB = $C010
tick:   lda     spinok                  ; not over a sheet on the screen
        beq     tickr
        lda     #$AF
        cmp     VC_TICK
        bne     :+
        lda     #$DC
:       sta     VC_TICK
poll:   lda     KBD
        cmp     #$9B                    ; Escape, waiting
        bne     tickr
        sta     KBDSTRB                 ; taken
        jsr     close
        lda     #<m_stop
        ldx     #>m_stop
        jmp     leave
tickr:  rts

; A cell line in ln (`>B3:/F$...`): its column and row in lc, lr, where its
; contents start in contp, past the formats, the last of which in cfmt
; (G I L R $ * as 1-6, 0 none or D). C clear; C set when it is not one.
fmtch:  .byte   "GILR$*D"
cellline:
        lda     ln
        cmp     #'>'
        bne     @no
        lda     #<(ln + 1)
        ldx     #>ln
        jsr     _vc_cellref
        tax
        beq     @no
        inx                             ; past '>' and the name: ':'
        lda     ln,x
        cmp     #':'
        bne     @no
        inx
        lda     refc
        sta     lc
        lda     refr
        sta     lr
        lda     #0
        sta     cfmt
@f:     lda     ln,x
        cmp     #'/'
        bne     @done
        lda     ln+1,x
        cmp     #'F'
        bne     @done
        lda     ln+2,x
        beq     @done
        ldy     #6
@k:     cmp     fmtch,y
        beq     @set
        dey
        bpl     @k
        bmi     @skip                   ; an unknown format: passed over
@set:   iny
        cpy     #7
        bne     :+
        ldy     #0                      ; D: the default
:       sty     cfmt
@skip:  inx
        inx
        inx
        bne     @f
@done:  stx     contp
        clc
        rts
@no:    sec
        rts

; The kind of the contents: 0 a label, a repeated label or nothing (a
; format alone); 1 a value; 2 another command (VisiCalc 2's /GCC column
; width, Advanced VisiCalc's /A attributes: no cell). In A, flags set.
kind:   ldx     contp
        lda     ln,x
        beq     @r
        cmp     #'"'
        beq     @z
        cmp     #'A'                    ; a letter starts a label
        bcc     :+
        cmp     #'Z' + 1
        bcc     @z
:       cmp     #'/'
        bne     @v
        lda     ln+1,x
        cmp     #'-'
        beq     @z
        lda     #2
        rts
@v:     lda     #1
        rts
@z:     lda     #0
@r:     rts

        .segment "VCA"

; -- pass 1 ------------------------------------------------------------------------

; A = the decimal number at ln,x (0 when past 255: /GC2609 is no 9); X
; after its digits.
number: lda     #0
        sta     tmp1
        sta     tmp4                    ; past 255
@l:     lda     ln,x
        sec
        sbc     #'0'
        cmp     #10
        bcs     @e
        sta     tmp2
        inx
        lda     tmp1
        cmp     #26
        bcs     @big
        asl     a
        sta     tmp3
        asl     a
        asl     a
        adc     tmp3
        adc     tmp2
        sta     tmp1
        bcc     @l
@big:   inc     tmp4                    ; (255 digits at most)
        bne     @l                      ; always
@e:     lda     tmp4
        beq     :+
        lda     #0
        rts
:       lda     tmp1
        rts

; The settings of a line, window 1's (what follows a ';' is the second
; window's). /X>A1:>B3: gives window 1's corner, then its cursor.
globals:
        lda     window2
        bne     @r
        ldx     #0
@sc:    lda     ln,x
        beq     @g
        inx
        cmp     #';'
        bne     @sc
        dex
        lda     #0
        sta     ln,x
        inc     window2
@g:     lda     ln+1
        cmp     #'X'
        beq     @x
        cmp     #'G'
        bne     @r
        lda     ln+2
        cmp     #'C'
        bne     @gf
        ldx     #3
        lda     ln,x
        beq     @r
        jsr     number
        cmp     #3
        bcc     @r
        cmp     #78
        bcs     @r
        ldy     ln,x                    ; nothing after the digits
        bne     @r
        sta     width
@r:     rts
@gf:    ldx     ln+4
        bne     @r
        cmp     #'F'
        bne     @go
        lda     ln+3
        ldy     #6
@k:     cmp     fmtch,y
        beq     @fs
        dey
        bpl     @k
        rts
@fs:    iny
        cpy     #7
        bne     :+
        ldy     #0
:       sty     gfmt
        rts
@go:    cmp     #'O'
        bne     @r
        lda     ln+3
        cmp     #'C'
        beq     @os
        cmp     #'R'
        bne     @r
@os:    sta     order
        rts
@x:     lda     #0                      ; the names after '>': corner, cursor
        sta     cnt1
        ldx     #0
@xl:    lda     ln,x
        beq     @r
        inx
        cmp     #'>'
        bne     @xl
        stx     cnt0
        txa
        clc
        adc     #<ln
        ldx     #>ln
        jsr     _vc_cellref
        tay
        beq     @xn
        clc
        adc     cnt0
        tax
        lda     ln,x
        cmp     #':'
        bne     @xn
        lda     cnt1
        bne     @cur
        lda     refc
        sta     leftc
        lda     refr
        sta     top
        inc     cnt1
        bne     @xl
@cur:   lda     refc
        sta     curc
        lda     refr
        sta     curr
        rts
@xn:    ldx     cnt0
        jmp     @xl

; Pass 1: the value cells counted (into colplo/colphi), the rows located,
; the settings read. C set when this is no worksheet.
scan:   ldx     #0
        txa
@z:     sta     rowlo,x
        sta     rowhi,x
        inx
        bne     @z
        ldx     #63
@zc:    sta     colplo,x
        sta     colphi,x
        sta     colw,x
        dex
        bpl     @zc
        sta     gfmt
        sta     unord
        sta     window2
        sta     curc
        sta     leftc
        sta     cells_end
        sta     cells_end+1
        sta     nvals
        sta     nvals+1
        lda     #$FF
        sta     lastk
        sta     lastk+1
        lda     #9
        sta     width
        lda     #'C'
        sta     order
        lda     #1
        sta     curr
        sta     top
        lda     #0
        tax
        jsr     seekto
@line:  jsr     rdline
        bcs     :+
        jmp     @end
:       jsr     cellline
        jcs     @other
        lda     cells_end+1             ; a cell after the settings
        ora     cells_end
        beq     :+
        sta     unord
:       jsr     kind
        cmp     #2
        bne     @key
        lda     ln+1,x                  ; /GCC: a column's width
        cmp     #'G'
        bne     @line
        lda     ln+2,x
        cmp     #'C'
        bne     @line
        lda     ln+3,x
        cmp     #'C'
        bne     @line
        inx
        inx
        inx
        inx
        jsr     number
        tay
        beq     @line
        cmp     #78
        bcs     @line
        ldx     window2
        bne     @line
        ldx     lc
        sta     colw,x
        jmp     @line
@key:   lda     lr                      ; key = row * 64 + column, descending
        lsr     a
        sta     tmp2
        lda     #0
        ror     a
        lsr     tmp2
        ror     a
        ora     lc
        sta     tmp1                    ; tmp2:tmp1
        cmp     lastk
        lda     tmp2
        sbc     lastk+1
        bcc     :+
        lda     #1
        sta     unord
:       lda     tmp1
        sta     lastk
        lda     tmp2
        sta     lastk+1
        ldx     lr
        lda     rowlo,x
        ora     rowhi,x
        bne     :+
        lda     lnoff                   ; + 1: 0 says none
        clc
        adc     #1
        sta     rowlo,x
        lda     lnoff+1
        adc     #0
        sta     rowhi,x
:       jsr     kind
        jeq     @line
        ldx     lc
        inc     colplo,x
        bne     :+
        inc     colphi,x
:       inc     nvals
        bne     :+
        inc     nvals+1
:       jmp     @line
@other: lda     ln
        jeq     @line
        cmp     #'/'
        bne     @bad
        lda     cells_end
        ora     cells_end+1
        bne     :+
        lda     lnoff
        sta     cells_end
        lda     lnoff+1
        sta     cells_end+1
:       jsr     globals
        jmp     @line
@bad:   sec
        rts
@end:   lda     cells_end
        ora     cells_end+1
        bne     :+
        jsr     here
        sta     cells_end
        stx     cells_end+1
:       lda     cut
        bne     @bad
        lda     lastk+1                 ; no cell at all
        cmp     #$FF
        beq     @bad
        clc
        rts
; A/X = fpos + at
here:   lda     fpos
        clc
        adc     at
        pha
        lda     fpos+1
        adc     #0
        tax
        pla
        rts

; -- the table ------------------------------------------------------------------------

; The table after the overlay: column after column, counts into pointers.
; C set when it does not fit (toobig says so; roomaux: against which bank).
; A column of 256 values or more leaves from here with its own words: it
; was refused as "N values, room for M", M the main bank's room -- which
; is not what stopped it (the auxiliary bank holds 4,064), and under the
; tests' larger table was more than N.
table:  ldx     #62                     ; 256 or more in a column: out of
@chk:   lda     colphi,x                ; order and repeated, never
        bne     @col                    ; VisiCalc's
        dex
        bpl     @chk
        lda     #0
        sta     roomaux
        lda     nvals+1                 ; 8 bytes a value: 8,191 at most
        cmp     #$20                    ; (fits counts in 16 bits)
        bcs     @aux
        lda     #<(__BSS_RUN__ + __BSS_SIZE__)
        ldx     #>(__BSS_RUN__ + __BSS_SIZE__)
        ldy     #>VC_TOP
        jsr     fits
        bcc     @main
@aux:   lda     $BF98                   ; the auxiliary bank: a 128 KB machine
        and     #$30                    ; (ProDOS MACHID), API 6 (its
        cmp     #$30                    ; consent), room
        bne     @no
        lda     apiver
        cmp     #6
        bcc     @no
        inc     roomaux                 ; too big now means: for that bank
        lda     nvals+1
        cmp     #$20
        bcs     @no
        lda     #<AUXLOW
        ldx     #>AUXLOW
        ldy     #>AUXTOP
        jsr     fits
        bcs     @no
        dec     roomaux                 ; it fits there: refused, what is
        jsr     J_AUXOK                 ; left is the main bank (no question
        tax                             ; if /RAM is empty)
        beq     @no
        inc     auxed
        jsr     taux
        jmp     place
@main:  jsr     tmain
        jmp     place
@no:    sec
        rts
@col:   jsr     close
        lda     #<m_col
        ldx     #>m_col
        jmp     leave
.ifndef VC_AUXLOW
VC_AUXLOW = $4000                       ; the auxiliary bank's $4000-$BEFF
VC_AUXTOP = $BF00                       ; (the tests have no such bank)
.endif
AUXLOW  = VC_AUXLOW
AUXTOP  = VC_AUXTOP

; "Sheet too big: N values, room for M." and out. M is the room of the bank
; the table could have gone to: the auxiliary one on a machine that has it
; (it said the main bank's 241 there too, for a sheet of 5,000 values that
; 4,064 would not hold either), the main one otherwise, or when the
; auxiliary bank fitted and was refused. Here, with the reading phase: the
; part that stays has no room for it.
toobig: jsr     close
        ldy     #0
@bm:    lda     m_big,y
        sta     _vc_out,y
        beq     @bn
        iny
        bne     @bm
@bn:    lda     nvals
        ldx     nvals+1
        jsr     udec
        ldx     #0
@b2:    lda     m_big2,x
        sta     _vc_out,y
        beq     @b3
        inx
        iny
        bne     @b2
@b3:    lda     roomaux
        beq     @mroom
        lda     #<((AUXTOP - AUXLOW) / 8)
        ldx     #>((AUXTOP - AUXLOW) / 8)
        jmp     @room
@mroom: lda     #<VC_TOP                ; (VC_TOP - the BSS's end) / 8:
        sec                             ; the main bank's room (colplo
        sbc     #<(__BSS_RUN__ + __BSS_SIZE__)  ; holds counts here)
        sta     tmp1
        lda     #>VC_TOP
        sbc     #>(__BSS_RUN__ + __BSS_SIZE__)
        bcs     :+
        lda     #0                      ; (none)
        sta     tmp1
:       lsr     a
        ror     tmp1
        lsr     a
        ror     tmp1
        lsr     a
        ror     tmp1
        tax
        lda     tmp1
@room:  jsr     udec
        lda     #'.'
        sta     _vc_out,y
        lda     #0
        sta     _vc_out+1,y
        lda     #<_vc_out
        ldx     #>_vc_out
        jmp     leave
m_big:  .asciiz "Sheet too big: "
m_big2: .asciiz " values, room for "
m_col:  .asciiz "Sheet too big: over 255 values in one column."

; C clear when nvals entries fit from A/X up to page Y; the start in ptr1.
fits:   sta     ptr1
        stx     ptr1+1
        sty     tmp2
        lda     nvals                   ; ptr1 + 8 * nvals <= Y * 256
        sta     tmp1
        lda     nvals+1
        asl     tmp1
        rol     a
        asl     tmp1
        rol     a
        asl     tmp1
        rol     a
        tax
        lda     tmp1
        clc
        adc     ptr1
        txa
        adc     ptr1+1
        bcs     @no
        cmp     tmp2
        bcc     @r                      ; below page Y
        bne     @no
        lda     tmp1                    ; on page Y: only at its start
        clc
        adc     ptr1
        beq     @r                      ; (C clear)
@no:    sec
@r:     rts

; Column after column from ptr1, the counts made pointers; C clear.
place:  ldx     #0
@c:     lda     #0
        sta     tmp1
        ldy     colplo,x                ; count * 8
        lda     ptr1
        sta     colplo,x
        lda     ptr1+1
        sta     colphi,x
        tya
        asl     a
        rol     tmp1
        asl     a
        rol     tmp1
        asl     a
        rol     tmp1
        clc
        adc     ptr1
        sta     ptr1
        lda     ptr1+1
        adc     tmp1
        sta     ptr1+1
        inx
        cpx     #63
        bne     @c
        lda     ptr1
        sta     colplo,x
        lda     ptr1+1
        sta     colphi,x
        clc
        rts

; ep = the entry at fill[lc] (a column's next place, filled downward)
; Pass 2: the value cells into the table: a typed number with its value, a
; formula with ERROR until the recalculation reaches it.
fillt:  ldx     #62
@i:     lda     colplo+1,x              ; each column filled from its end
        sta     fill,x
        lda     colphi+1,x
        sta     fill+63,x
        dex
        bpl     @i
        lda     #0
        tax
        jsr     seekto
@line:  jsr     rdline
        bcs     :+
        jmp     @sort
:       jsr     cellline
        bcs     @line
        jsr     kind
        beq     @label
        cmp     #2
        beq     @line
        ldx     lc                      ; fill[lc] -= 8
        lda     fill,x
        sec
        sbc     #8
        sta     fill,x
        sta     ep
        lda     fill+63,x
        sbc     #0
        sta     fill+63,x
        sta     ep+1
        lda     contp                   ; a typed number: all of it parses
        clc
        adc     #<ln
        ldx     #>ln
        jsr     _vc_parse
        tay
        beq     @f
        clc                             ; the byte after the number
        adc     contp
        tax
        lda     ln,x
        bne     @f
        lda     _vc_acc+VT
        beq     @put
@f:     lda     #T_ERROR
        sta     _vc_acc+VT
@put:   lda     ep
        sta     ptr3
        ldx     ep+1
        stx     ptr3+1
        ldy     #0
        lda     lr
        jsr     twr3
        lda     ptr3
        clc
        adc     #1
        bcc     :+
        inx
:       jsr     _vc_pack
        jmp     @line
@label: lda     unord                   ; out of order: a label over an
        beq     @line                   ; earlier value of its cell
        jsr     colscan
@kl:    jsr     colnext
        bcs     @line
        ldy     #0
        jsr     trd3
        cmp     lr
        bne     @kl
        tya
        jsr     twr3
        beq     @kl
@sort:  lda     unord
        bne     :+
        rts
:       ; Out of order: each column sorted by row, stable (the later of two
        ; lines of one cell comes first, having been filled last), then the
        ; earlier ones given up.
        lda     #0
        sta     lc
@col:   ldx     lc
        lda     fill,x                  ; the column's entries: fill[lc] on
        sta     ptr3
        lda     fill+63,x
        sta     ptr3+1
@ins:   jsr     cend                    ; insertion: ptr3 walks, ptr4 sinks
        bcs     @dd
        lda     ptr3
        sta     ptr4
        lda     ptr3+1
        sta     ptr4+1
@sink:  ldx     lc                      ; at the column's start?
        lda     ptr4
        cmp     fill,x
        lda     ptr4+1
        sbc     fill+63,x
        bcc     @adv
        beq     @eqs
        bcs     @cmp
@eqs:   lda     ptr4
        cmp     fill,x
        beq     @adv
@cmp:   lda     ptr4                    ; ptr1 = ptr4 - 8
        sec
        sbc     #8
        sta     ptr1
        lda     ptr4+1
        sbc     #0
        sta     ptr1+1
        ldy     #0
        jsr     trd1
        sta     tmp1
        jsr     trd4
        cmp     tmp1
        bcs     @adv
        ldy     #7                      ; swap the two
@sw:    jsr     trd4
        sta     tmp1
        jsr     trd1
        jsr     twr4
        lda     tmp1
        jsr     twr1
        dey
        bpl     @sw
        lda     ptr1
        sta     ptr4
        lda     ptr1+1
        sta     ptr4+1
        jmp     @sink
@adv:   jsr     step3
        jmp     @ins
@dd:    jsr     colscan                 ; equal rows: the first kept
        lda     #0
        sta     cnt0
@d:     jsr     colnext
        bcs     @nc
        ldy     #0
        jsr     trd3
        beq     @d
        cmp     cnt0
        bne     @keep
        tya
        jsr     twr3
        beq     @d
@keep:  sta     cnt0
        jmp     @d
@nc:    inc     lc
        lda     lc
        cmp     #63
        jne     @col
        rts
        .segment "CODE"

; Column lc's filled entries, from fill[lc]: colscan readies ptr3 (8 bytes
; before), colnext moves it on, C set at the column's end.
colscan:
        ldx     lc
        lda     fill,x
        sec
        sbc     #8
        sta     ptr3
        lda     fill+63,x
        sbc     #0
        sta     ptr3+1
        rts
colnext:
        jsr     step3
; C set when ptr3 is at column lc's end
cend:   ldx     lc
        lda     ptr3
        cmp     colplo+1,x
        lda     ptr3+1
        sbc     colphi+1,x
        rts
step3:  lda     ptr3
        clc
        adc     #8
        sta     ptr3
        bcc     :+
        inc     ptr3+1
:       rts

; -- reading rows again ----------------------------------------------------------------

; The file from the first line that may hold rows cnt0 (low) .. cnt1 (high)
; up to spanend: the first line of the highest of them, to where the next
; lower row starts. Out of VisiCalc's order: everything.
span:   lda     #$FF
        sta     spanend
        sta     spanend+1
        lda     #0
        tax
        ldy     unord
        bne     @go
        lda     cells_end
        sta     spanend
        lda     cells_end+1
        sta     spanend+1
        ldx     cnt0                    ; the next lower row's start
@lo:    dex
        beq     @hi
        lda     rowlo,x
        ora     rowhi,x
        beq     @lo
        jsr     rowoff
        sta     spanend
        stx     spanend+1
@hi:    ldx     cnt1                    ; the highest row with lines
@h:     lda     rowlo,x
        ora     rowhi,x
        bne     @at
        dex
        cpx     cnt0
        bcs     @h
        lda     spanend                 ; none: nothing to read
        ldx     spanend+1
        jmp     @go
@at:    jsr     rowoff
@go:    jmp     seekto
; A/X = where row X's lines start (rowat - 1)
rowoff: lda     rowlo,x
        sec
        sbc     #1
        pha
        lda     rowhi,x
        sbc     #0
        tax
        pla
        rts

; The next line of the span: C clear and a cell line in ln; C set at its end.
nextcell:
        jsr     rdline
        bcc     @end
        lda     lnoff
        cmp     spanend
        lda     lnoff+1
        sbc     spanend+1
        bcs     @end
        jsr     cellline
        bcs     nextcell
        jsr     kind                    ; a command typed at a cell (/GCC,
        cmp     #2                      ; /A...) is not its contents
        beq     nextcell
        clc
        rts
@end:   sec
        rts
        .segment "VCB"

; The formula of the entry at ptr3 (column lc), evaluated into it: its
; line found again in its row -- the last one, out of VisiCalc's order. A
; typed number is left as it is. ptr3 and lc come back as they were.
evaluate:
        ldy     #1
        jsr     trd3
        cmp     #$40 | T_ERROR
        jne     @r
        lda     ptr3
        sta     ep
        lda     ptr3+1
        sta     ep+1
        dey
        jsr     trd3
        sta     cnt0
        sta     cnt1
        sta     erow
        lda     lc
        sta     ecol
        jsr     span
        lda     #0
        sta     key                     ; the kind of the line found
@l:     jsr     nextcell
        bcs     @done
        lda     lc
        cmp     ecol
        bne     @l
        lda     lr
        cmp     erow
        bne     @l
        jsr     kind
        ldx     lnlong
        beq     :+
        lda     #0                      ; too long: no formula
:       sta     key
        lda     lnoff
        sta     moff
        lda     lnoff+1
        sta     moff+1
        lda     unord
        bne     @l                      ; out of order, the last line wins
        beq     @have
@done:  lda     unord
        beq     @have
        lda     key
        cmp     #1
        bne     @have
        lda     moff                    ; that line again
        ldx     moff+1
        jsr     seekto
        jsr     rdline
        jsr     cellline
@have:  lda     key
        cmp     #1
        bne     @err
        lda     contp
        sta     evstart
        jsr     _vc_eval
        jmp     @put
@err:   lda     #T_ERROR
        sta     _vc_acc+VT
@put:   lda     ep
        clc
        adc     #1
        ldx     ep+1
        bcc     :+
        inx
:       jsr     _vc_pack
        lda     ep
        sta     ptr3
        lda     ep+1
        sta     ptr3+1
        lda     ecol
        sta     lc
@r:     rts

; ptr3 = column lc's entry number colx[lc]
colat:  ldx     lc
        lda     colx,x
        ldy     #0
        sty     tmp1
        asl     a
        rol     tmp1
        asl     a
        rol     tmp1
        asl     a
        rol     tmp1
        clc
        adc     colplo,x
        sta     ptr3
        lda     tmp1
        adc     colphi,x
        sta     ptr3+1
        rts

; The recalculation VisiCalc makes on loading: once, column by column, or
; row by row (colx[c] then counts the entries of column c passed).
recalc: lda     #0
        sta     lc
        ldx     #62
@z:     sta     colx,x
        dex
        bpl     @z
        lda     order
        cmp     #'R'
        beq     @rows
@col:   jsr     tick
        jsr     colat
@e:     jsr     cend
        bcs     @nc
        ldy     #0
        jsr     trd3
        beq     :+
        jsr     evaluate
:       jsr     step3
        jmp     @e
@nc:    inc     lc
        lda     lc
        cmp     #63
        bne     @col
        rts
@rows:  lda     #1
        sta     cnt1
@r:     jsr     tick
        lda     #0
        sta     lc
@c:     jsr     colat
@sk:    jsr     cend
        bcs     @n
        ldy     #0
        jsr     trd3
        cmp     cnt1
        bcs     @at
        ldx     lc
        inc     colx,x
        jsr     step3
        jmp     @sk
@at:    bne     @n
        lda     cnt1                    ; (evaluate spends cnt0, cnt1)
        pha
        jsr     evaluate
        pla
        sta     cnt1
@n:     inc     lc
        lda     lc
        cmp     #63
        bne     @c
        inc     cnt1
        lda     cnt1
        cmp     #255
        bne     @r
        rts
        .segment "VCC"

; -- the screen -------------------------------------------------------------------------

; A = column X's width
colwid: lda     colw,x
        bne     :+
        lda     width
:       rts

; colx: where each column from leftc starts, while they fit in 80.
layout: lda     #3
        sta     tmp4
        ldx     #0
@c:     lda     #0
        sta     colx,x
        cpx     leftc
        bcc     @n
        jsr     colwid
        clc
        adc     tmp4
        cmp     #81
        bcs     @full
        ldy     tmp4
        sta     tmp4
        tya
        sta     colx,x
        bne     @n
@full:  lda     #80
        sta     tmp4
@n:     inx
        cpx     #63
        bne     @c
        rts

; The column name of X at vc_out,y; Y after it.
colname:
        txa
        ldx     #'@'
@t:     cmp     #26
        bcc     @u
        sbc     #26
        inx
        bne     @t
@u:     cpx     #'@'
        beq     :+
        pha
        txa
        sta     _vc_out,y
        iny
        pla
:       clc
        adc     #'A'
        sta     _vc_out,y
        iny
        rts
        .segment "CODE"


; A/X as decimal at vc_out,y, no leading zeros, zero-ended; Y after it.
udec:   sta     tmp1
        stx     tmp2
        lda     #0
        sta     tmp3                    ; a digit written
        ldx     #8                      ; pow10: 10000 1000 100 10 1
@p:     lda     #0
        sta     tmp4
@s:     lda     tmp1
        sec
        sbc     pow10,x
        pha
        lda     tmp2
        sbc     pow10+1,x
        bcc     @lt
        sta     tmp2
        pla
        sta     tmp1
        inc     tmp4
        bne     @s
@lt:    pla
        lda     tmp4
        ora     tmp3
        bne     @w
        txa
        bne     @n                      ; a leading zero, not the last digit
@w:     lda     tmp4
        ora     #'0'
        sta     _vc_out,y
        iny
        sta     tmp3
@n:     dex
        dex
        bpl     @p
        lda     #0
        sta     _vc_out,y
        rts
        .segment "VCC"

; The text of the cell line in ln, A characters wide, into vc_out.
celltext:
        sta     cnt0
        lda     cfmt
        bne     :+
        lda     gfmt
:       sta     _vc_fmt
        jsr     kind
        beq     @label
        lda     lc
        ldx     lr
        jsr     _vc_lookup
        lda     cnt0
        jmp     _vc_format
@label: ldx     cnt0                    ; w blanks
        lda     #0
        sta     _vc_out,x
@b:     dex
        bmi     @t
        lda     #' '
        sta     _vc_out,x
        bne     @b
@t:     ldx     contp
        lda     ln,x
        beq     @r
        cmp     #'"'
        beq     @lab
        cmp     #'/'
        bne     @lab1                   ; a letter: the label from there
        inx                             ; /-: the rest repeated
        inx
        lda     ln,x
        beq     @r
        stx     tmp3
        ldy     #0
@rp:    lda     ln,x
        bne     :+
        ldx     tmp3
        lda     ln,x
:       sta     _vc_out,y
        inx
        iny
        cpy     cnt0
        bne     @rp
@r:     rts
@lab:   inx                             ; the label: its length, w at most
@lab1:  stx     tmp3
        ldy     #0
@ln:    lda     ln,x
        beq     @lend
        inx
        iny
        cpy     cnt0
        bne     @ln
@lend:  sty     tmp2                    ; n
        lda     #0                      ; from the left, or right for /FR
        ldx     _vc_fmt
        cpx     #4
        bne     :+
        lda     cnt0
        sec
        sbc     tmp2
:       tay
        ldx     tmp3
@cp:    lda     tmp2
        beq     @r
        lda     ln,x
        sta     _vc_out,y
        inx
        iny
        dec     tmp2
        jmp     @cp

; vc_out at (A, X)
putout: ldy     #<_vc_out
        sty     ep
        ldy     #>_vc_out
        sty     ep+1
        jmp     putxy

; The screen row of sheet row A: A - top + 2, in X.
scrow:  sec
        sbc     top
        clc
        adc     #2
        tax
        rts

; The sheet from (leftc, top): the column names, the row numbers, the cells,
; the cursor in inverse, and on the first row the cursor's name and
; contents as VisiCalc shows them -- B3 /F$ (V) +A1*2.
draw:   jsr     layout
        jsr     J_CLRSCR
        lda     #0                      ; the column names
        sta     lc
@cn:    ldx     lc
        lda     colx,x
        beq     @cnn
        ldy     #0
        jsr     colname
        lda     #0
        sta     _vc_out,y
        ldx     lc
        jsr     colwid
        lsr     a
        clc
        adc     colx,x
        cpx     #26                     ; two letters: one to the left
        bcc     :+
        sbc     #1
:
        ldx     #1
        jsr     putout
@cnn:   inc     lc
        lda     lc
        cmp     #63
        bne     @cn
        lda     #0                      ; the row numbers, on three places
        sta     cnt1
@rn:    lda     top
        clc
        adc     cnt1
        cmp     #255
        bcs     @rne
        ldy     #0
        ldx     #' '
        cmp     #100
        bcs     @r3
        stx     _vc_out
        iny
        cmp     #10
        bcs     @r3
        stx     _vc_out+1
        iny
@r3:    ldx     #0
        jsr     udec
        lda     cnt1
        clc
        adc     #2
        tax
        lda     #0
        jsr     putout
        inc     cnt1
        lda     cnt1
        cmp     #SHEETROWS
        bne     @rn
@rne:   lda     #0
        sta     sline
        lda     top                     ; the cells of rows top..bottom
        sta     cnt0
        clc
        adc     #SHEETROWS - 1
        bcs     @254
        cmp     #255
        bcc     :+
@254:   lda     #254
:       sta     cnt1
        sta     erow                    ; (the bottom row, kept)
        jsr     span
@cell:  jsr     nextcell
        bcs     @cur
        lda     lr
        cmp     top
        bcc     @cell
        cmp     erow
        beq     :+
        bcs     @cell
:       lda     lc
        cmp     curc
        bne     @nc
        lda     lr
        cmp     curr
        bne     @nc
        ldx     #78                     ; the cursor's line, kept
@sl:    lda     ln+1,x
        sta     sline,x
        dex
        bpl     @sl
        lda     #0
        sta     sline+79
@nc:    ldx     lc
        lda     colx,x
        beq     @cell
        lda     lnlong
        bne     @cell
        jsr     colwid
        jsr     celltext
        lda     lr
        jsr     scrow
        ldy     lc
        lda     colx,y
        jsr     putout
        jmp     @cell
@cur:
; The first row -- the cursor's name and contents, from sline -- and the
; cursor in inverse.
curshow:
        ldx     curc
        ldy     #0
        jsr     colname
        lda     curr
        ldx     #0
        jsr     udec
        lda     sline
        bne     :+
        jmp     @show
:       lda     #'>'
        sta     ln
        ldx     #79
@cp:    lda     sline,x
        sta     ln+1,x
        dex
        bpl     @cp
        sty     cnt1
        jsr     cellline
        ldy     cnt1
        ldx     cfmt
        beq     @nf
        lda     #' '
        sta     _vc_out,y
        lda     #'/'
        sta     _vc_out+1,y
        lda     #'F'
        sta     _vc_out+2,y
        lda     fmtch-1,x
        sta     _vc_out+3,y
        tya
        clc
        adc     #4
        tay
@nf:    sty     cnt1
        jsr     kind
        ldy     cnt1
        ldx     #'L'
        cmp     #0
        beq     :+
        ldx     #'V'
:       lda     #' '
        sta     _vc_out,y
        sta     _vc_out+4,y
        lda     #'('
        sta     _vc_out+1,y
        txa
        sta     _vc_out+2,y
        lda     #')'
        sta     _vc_out+3,y
        tya
        clc
        adc     #5
        tay
        ldx     contp
        lda     ln,x
        cmp     #'"'
        bne     @ct
        inx
@ct:    lda     ln,x
        sta     _vc_out,y
        beq     @show
        inx
        iny
        cpy     #79
        bcc     @ct
        lda     #0
        sta     _vc_out,y
@show:  lda     #' '                    ; blanks to the end of the row
@pad:   cpy     #79
        bcs     @pe
        sta     _vc_out,y
        iny
        bne     @pad
@pe:    lda     #0
        sta     _vc_out,y
        tax
        jsr     putout
        ldx     curc                    ; the cursor in inverse
        lda     colx,x
        bne     :+
        rts
:       lda     sline
        bne     :+
        sta     cfmt                    ; a blank cell: a blank label
        sta     contp
        sta     ln
:       ldx     curc
        jsr     colwid
        jsr     celltext
        lda     #1
        jsr     J_REVERS
        lda     curr
        jsr     scrow
        ldy     curc
        lda     colx,y
        jsr     putout
        lda     #0
        jmp     J_REVERS

; sline = the line of cell (A, X) without its '>' (the last one), or "".
findline:
        sta     ecol
        stx     erow
        stx     cnt0
        stx     cnt1
        lda     #0
        sta     sline
        jsr     span
@l:     jsr     nextcell
        bcs     @r
        lda     lc
        cmp     ecol
        bne     @l
        lda     lr
        cmp     erow
        bne     @l
        ldx     #78
@c:     lda     ln+1,x
        sta     sline,x
        dex
        bpl     @c
        lda     #0
        sta     sline+79
        beq     @l                      ; always
@r:     rts

; Cell (A, X) drawn again, plainly (the cursor leaving it).
cellnorm:
        tay
        lda     colx,y
        beq     @r
        tya
        jsr     findline
        lda     sline
        beq     @blank
        jsr     again
        jmp     @t
@blank: sta     cfmt
        sta     contp
        sta     ln
@t:     ldx     ecol
        jsr     colwid
        jsr     celltext
        lda     erow
        jsr     scrow
        ldy     ecol
        lda     colx,y
        jmp     putout
@r:     rts

; ln = '>' and sline, read as a cell line.
again:  lda     #'>'
        sta     ln
        ldx     #79
@c:     lda     sline,x
        sta     ln+1,x
        dex
        bpl     @c
        jmp     cellline
        .segment "CODE"

; -- the entry's work -------------------------------------------------------------------

main:   lda     fullp                   ; nothing to open: no path
        sta     ptr1
        lda     fullp+1
        sta     ptr1+1
        ldy     #0
        lda     (ptr1),y
        jeq     notvc
        lda     selp                    ; the size: 16 bits, under 64 KB
        sta     ptr1
        lda     selp+1
        sta     ptr1+1
        ldy     #E_SIZE + 3
        lda     (ptr1),y
        dey
        ora     (ptr1),y
        jne     notvc
        dey
        lda     (ptr1),y
        sta     fsize+1
        dey
        lda     (ptr1),y
        sta     fsize
        and     fsize+1
        cmp     #$FF
        jeq     notvc
        lda     fullp
        ldx     fullp+1
        jsr     open
        jeq     notvc
        lda     #0
        sta     cut
        lda     #1
        sta     spinok
        jsr     scan
        jcs     @bad
        jsr     table
        bcs     @big
        jsr     fillt
        lda     #0
        jsr     phase
        bcs     @r
        jsr     recalc
        lda     cut
        bne     @bad
        lda     #1
        jsr     phase
        bcs     @r
        lda     #0
        sta     spinok
        jsr     ui
        jsr     close
        lda     #0
        sta     _vc_out
        lda     #<_vc_out
        ldx     #>_vc_out
        jmp     leave
@r:     rts
@big:   jmp     toobig                  ; (with the reading phase, still there)
@bad:   jsr     close
        lda     cut
        beq     notvc
        lda     #<m_cut
        ldx     #>m_cut
        jmp     leave
notvc:  lda     #<m_not
        ldx     #>m_not
        jmp     leave

close:  lda     fh
        ldx     fh+1
        jmp     J_FCLOSE

; Phase A (0: recalculating, 1: showing) from VISICALC.BIN, beside the
; overlay, into the swap area: the worksheet closed meanwhile (one file
; open at a time: $0C00 is the second ProDOS buffer) and opened again.
; C set when it could not be done -- the note is then set, nothing open.
; A CLOSE that fails keeps its file and its $0800 buffer (cc65's close):
; the next fopen would get $0C00, where the overlay keeps tables ProDOS
; would then read blocks over. Nothing more is opened then: the overlay
; leaves.
.ifdef VC_FLAT
phase:  clc                             ; tests: every phase in place
        rts
.else
shutno: lda     #<m_close               ; a CLOSE failed
        ldx     #>m_close
        jsr     leave
        sec
        rts
phase:  sta     key
        jsr     close
        tax
        bne     shutno                  ; (0, or -1)
        lda     cfgp                    ; the directory of A2FILE.CFG
        sta     ptr1
        lda     cfgp+1
        sta     ptr1+1
        ldy     #0
        ldx     #0
@p:     lda     (ptr1),y
        beq     @n
        sta     _vc_out,y
        iny
        cpy     #64
        bcs     @fail
        cmp     #'/'
        bne     @p
        tya
        tax
        bne     @p
@n:     txa                             ; no '/': no path
        beq     @fail
        ldy     #0
@nm:    lda     s_bin,y
        sta     _vc_out,x
        inx
        iny
        cmp     #0
        bne     @nm
        lda     #<_vc_out
        ldx     #>_vc_out
        jsr     open
        beq     @fail
        lda     #0                      ; fseek(fh, key * VC_SWAP)
        tax
        ldy     key
        beq     :+
        lda     #<VC_SWAP
        ldx     #>VC_SWAP
:       jsr     seekto
        lda     #<SWAPAT                ; fread(SWAPAT, 1, VC_SWAP, fh)
        ldx     #>SWAPAT
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     #<VC_SWAP
        ldx     #>VC_SWAP
        jsr     pushax
        lda     fh
        ldx     fh+1
        jsr     J_FREAD
        cmp     #<VC_SWAP
        bne     @shut
        cpx     #>VC_SWAP
        bne     @shut
        lda     SWAPAT                  ; the same link?
        cmp     #<VC_ID
        bne     @shut
        lda     SWAPAT+1
        cmp     #>VC_ID
        bne     @shut
        jsr     close
        tax
        jne     shutno
        lda     fullp                   ; the worksheet again
        ldx     fullp+1
        jsr     open
        beq     @rf
        clc
        rts
@shut:  jsr     close
@fail:  lda     #<m_bin
        ldx     #>m_bin
        jsr     leave
        sec
        rts
@rf:    lda     #<m_cut
        ldx     #>m_cut
        jsr     leave
        sec
        rts
.endif

; fh = fopen(A/X, "rb"); Z set when it failed. The reader starts afresh.
open:   jsr     pushax
        lda     #0
        sta     fpos
        sta     fpos+1
        sta     have
        sta     at
        sta     eof
        lda     #<s_rb
        ldx     #>s_rb
        jsr     J_FOPEN
        sta     fh
        stx     fh+1
        ora     fh+1
        rts

        .segment "VCC"

; The keys, until Escape.
ui:     lda     #0
        sta     drawn
@loop:  lda     curr                    ; the cursor on the screen, whole
        cmp     top
        bcs     :+
        sta     top
:       sec                             ; curr - 19 > top: top = curr - 19
        sbc     #SHEETROWS - 1
        bcc     :+
        cmp     top
        bcc     :+
        beq     :+
        sta     top
:       lda     curc
        cmp     leftc
        bcs     @fit
        sta     leftc
@fit:   jsr     layout
        ldx     curc
        lda     colx,x
        bne     @ok
        lda     leftc
        cmp     curc
        bcs     @ok
        inc     leftc
        bne     @fit
@ok:    lda     drawn                   ; the same window: only the cursor
        beq     @full                   ; moves
        lda     leftc
        cmp     oleft
        bne     @full
        lda     top
        cmp     otop
        bne     @full
        lda     oc
        ldx     orow
        jsr     cellnorm
        lda     curc
        ldx     curr
        jsr     findline
        jsr     curshow
        jmp     @bar
@full:  jsr     draw
        lda     #1
        sta     drawn
@bar:   lda     leftc
        sta     oleft
        lda     top
        sta     otop
        lda     curc
        sta     oc
        lda     curr
        sta     orow
        jsr     J_BAR
        lda     selp
        ldx     selp+1
        jsr     J_CPUTS
        lda     #30
        jsr     pusha
        lda     #<s_keys
        ldx     #>s_keys
        jsr     J_KEYS
        jsr     J_CGETC
        and     #$7F
        cmp     #$1B
        jeq     @end
        cmp     #'a'                    ; letters in capitals
        bcc     :+
        and     #$DF
:       cmp     #'Q'
        jeq     @end
        ldx     curr
        cmp     #$0B                    ; up
        bne     :+
        dex
        beq     :+
        stx     curr
:       cmp     #$0A                    ; down
        bne     :+
        cpx     #254
        bcs     :+
        inc     curr
:       ldx     curc
        cmp     #$08                    ; left
        bne     :+
        dex
        bmi     :+
        stx     curc
:       cmp     #$15                    ; right
        bne     :+
        cpx     #62
        bcs     :+
        inc     curc
:       cmp     #' '                    ; a screen down
        beq     @down
        cmp     #$0D
        bne     @up
@down:  lda     curr
        clc
        adc     #SHEETROWS
        bcs     :+
        cmp     #255
        bcc     :++
:       lda     #254
:       sta     curr
        lda     top
        clc
        adc     #SHEETROWS
        cmp     #254 - SHEETROWS + 2
        bcc     :+
        lda     #254 - SHEETROWS + 1
:       sta     top
        jmp     @loop
@up:    cmp     #'B'
        bne     @right
        lda     curr
        sec
        sbc     #SHEETROWS
        beq     :+
        bcs     :++
:       lda     #1
:       sta     curr
        lda     top
        sec
        sbc     #SHEETROWS
        beq     :+
        bcs     :++
:       lda     #1
:       sta     top
        jmp     @loop
@right: cmp     #'>'
        beq     :+
        cmp     #'.'
        bne     @left
:       ldx     leftc                   ; the first column off the screen
@rf:    lda     colx,x
        beq     :+
        inx
        cpx     #63
        bne     @rf
        jmp     @loop
:       stx     leftc
        stx     curc
        jmp     @loop
@left:  cmp     #'<'
        beq     :+
        cmp     #','
        bne     @home
:       lda     #3                      ; back while they fit before leftc
        sta     tmp4
@lf:    ldx     leftc
        beq     @lset
        dex
        jsr     colwid
        clc
        adc     tmp4
        cmp     #81
        bcs     @lset
        sta     tmp4
        dec     leftc
        jmp     @lf
@lset:  lda     leftc
        sta     curc
        jmp     @loop
@home:  cmp     #'R'
        bne     @l2
        lda     #0
        sta     curc
        sta     leftc
        lda     #1
        sta     curr
        sta     top
@l2:    jmp     @loop
@end:   rts

        .segment "RODATA"
s_rb:   .asciiz "rb"
s_bin:  .asciiz "VISICALC.BIN"
m_bin:  .asciiz "VISICALC.BIN missing or not from this build."
s_keys: .asciiz "SPC Page,B Back,<> Cols,R A1,ESC"
m_not:  .asciiz "Not a VisiCalc worksheet (T shows it as text)."
m_cut:  .asciiz "Read error."
m_close: .asciiz "Close error."
m_ram:  .asciiz " /RAM rebuilt."
m_stop: .asciiz "Stopped."
