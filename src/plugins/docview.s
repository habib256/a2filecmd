; docview.s -- Epistole's calculations for docview.c, in Applesoft's floating
; point: the numbers are the ROM's packed ones, 5 bytes (an exponent byte, 0
; for zero, then four mantissa bytes, the sign in the place of the leading
; 1), and every operation is the ROM's own.
;
; unsigned char __fastcall__ fp_op(unsigned char op): fp_x = fp_x OP fp_y
; (FP_ADD... FP_GE), OP(fp_x) (FP_SIN... FP_NEG), fp_x = fp_n (FP_INT16, a
; signed 16-bit integer), or fp_text = fp_x as BASIC prints it (FP_FOUT,
; zero-ended, at most 16 characters). A comparison leaves 1 or 0. Returns 0,
; or 1 when the ROM refused: division by zero, overflow, a logarithm or a
; square root out of range -- fp_x is then unchanged.
;
; The ROM is read with the language card switched off ($C082) and put back
; on bank 2 for reading ($C080), the state crt0 leaves, interrupts off in
; between, as awdata.s does. The ROM's arithmetic uses the zero page from
; $50 up, the cc65 runtime's among it: $50-$FF is saved first, at fp_zsave
; (176 bytes the caller gives), and put back after -- ptr4, the pointer to
; it, is in that range: it is saved holding fp_zsave, and set again before
; the copy back, which writes the same value into it. Its errors go to ERROR ($D412), which would leave for BASIC. With
; ONERR on ($D8 bit 7) ERROR goes to HANDLERR ($F2E9), which sets TXTPTR
; ($B8-$B9) from $F4-$F5 and calls CHRGOT at $B7 in the zero page: a JMP
; opcode at $B7 and fp_trap in $F4-$F5 bring it back here, where the stack
; is put back as it was before the call. FOUT counts on $A4 being 0, as
; BASIC leaves it.

        .export _fp_op, _fp_x, _fp_y, _fp_n, _fp_text, _fp_zsave
        .export _calc_eval, _calc_assign, _calc_forget, _calc_format, _calc_vars
        .importzp ptr1, ptr2, ptr3, ptr4, tmp1, tmp2, tmp3
        .segment "CODE"

FADD    = $E7BE                 ; FAC = (A,Y) + FAC
FSUB    = $E7A7                 ; FAC = (A,Y) - FAC
FMULT   = $E97F                 ; FAC = (A,Y) * FAC
FDIV    = $EA66                 ; FAC = (A,Y) / FAC
FPWRT   = $EE97                 ; FAC = ARG ^ FAC, A = FAC's exponent
CONUPK  = $E9E3                 ; ARG = (A,Y)
MOVFM   = $EAF9                 ; FAC = (A,Y)
MOVMF   = $EB2B                 ; (X,Y) = FAC, rounded
FCOMP   = $EBB2                 ; A = 0, 1 or $FF: FAC =, >, < (A,Y)
GIVAYF  = $E2F2                 ; FAC = the signed integer A (high), Y (low)
FOUT    = $ED34                 ; FAC as text at $0100
NEGOP   = $EED0                 ; FAC = -FAC
FACEXP  = $9D

; The operations, in docview.c's order.
FP_ADD   = 0
FP_SUB   = 1
FP_MUL   = 2
FP_DIV   = 3
FP_POW   = 4
FP_LT    = 5                    ; the comparisons: 5 to 10
FP_GE    = 10
FP_EQ    = 7
FP_NE    = 8
FP_LE    = 9
FP_GT    = 6
FP_SIN   = 11                   ; the functions of fp_x: 11 to 21
FP_ABS   = 18
FP_INT   = 20
FP_NEG   = 21
FP_INT16 = 22
FP_FOUT  = 23

_fp_op: sta     op
        jsr     zpoint
        ldy     #0
save:   lda     $0050,y
        sta     (ptr4),y
        iny
        cpy     #$B0
        bne     save
        lda     #$80                    ; ONERR on: errors come to fp_trap
        sta     $D8
        lda     #$4C                    ; CHRGOT: JMP (TXTPTR = $F4-$F5)
        sta     $B7
        lda     #<fp_trap
        sta     $F4
        lda     #>fp_trap
        sta     $F5
        lda     #0
        sta     $A4
        php
        sei
        tsx
        stx     stack
        bit     $C082                   ; the ROM
        jsr     dispatch
        lda     #0
back:   bit     $C080                   ; the language card, bank 2, read
        plp
        sta     result
        jsr     zpoint                  ; the ROM used ptr4: set again, and
        ldy     #0                      ; put back with the value it had
rest:   lda     (ptr4),y
        sta     $0050,y
        iny
        cpy     #$B0
        bne     rest
        ldx     #0
        lda     result                  ; last: Z for the callers' bne
        rts
zpoint: lda     _fp_zsave               ; ptr4 = fp_zsave
        sta     ptr4
        lda     _fp_zsave+1
        sta     ptr4+1
        rts

; A ROM error: ERROR, HANDLERR, then here through CHRGOT's JMP. The ROM's
; own return addresses are dropped with the stack, and fp_x was not stored.
fp_trap:
        ldx     stack
        txs
        lda     #1
        jmp     back

dispatch:
        lda     op
        cmp     #FP_INT16
        beq     int16
        cmp     #FP_FOUT
        beq     fout
        cmp     #FP_SIN
        bcs     func
        cmp     #FP_LT
        bcs     compare
        cmp     #FP_POW
        beq     power
        jsr     loady                   ; x OP y: FAC = y, then x OP FAC
        ldx     op
        jsr     callbin
store:  ldx     #<_fp_x
        ldy     #>_fp_x
        jmp     MOVMF

power:  jsr     loady                   ; FAC = y, ARG = x
        lda     #<_fp_x
        ldy     #>_fp_x
        jsr     CONUPK
        lda     FACEXP
        jsr     FPWRT
        jmp     store

compare:
        jsr     loadx                   ; FAC = x, compared with y
        lda     #<_fp_y
        ldy     #>_fp_y
        jsr     FCOMP
        ldx     op                      ; the outcomes it accepts: bit 0
        and     #3                      ; for =, 1 for >, 2 for <
        tay
        lda     accept-FP_LT,x
        and     bits,y
        beq     :+
        lda     #1
:       tay
        lda     #0
        jsr     GIVAYF
        jmp     store

func:   jsr     loadx
        lda     op
        sec
        sbc     #FP_SIN
        tax
        jsr     callfun
        jmp     store

int16:  lda     _fp_n+1
        ldy     _fp_n
        jsr     GIVAYF
        jmp     store

fout:   jsr     loadx
        jsr     FOUT
        ldy     #0
:       lda     $0100,y
        sta     _fp_text,y
        beq     :+
        iny
        cpy     #16
        bne     :-
        lda     #0
        sta     _fp_text,y
:       rts

loadx:  lda     #<_fp_x
        ldy     #>_fp_x
        jmp     MOVFM
loady:  lda     #<_fp_y
        ldy     #>_fp_y
        jmp     MOVFM
; The ROM routine X of a table, through its address - 1 pushed and an RTS
; (no JMP indirect: the NMOS page bug). A binary one gets x in A, Y.
callbin:
        lda     binhi,x
        pha
        lda     binlo,x
        pha
        lda     #<_fp_x
        ldy     #>_fp_x
        rts
callfun:
        lda     funhi,x
        pha
        lda     funlo,x
        pha
        rts

.define BINS FADD-1, FSUB-1, FMULT-1, FDIV-1
; SIN COS TAN ATN LOG EXP SGN ABS SQR INT, then NEG.
.define FUNS $EFF1-1, $EFEA-1, $F03A-1, $F09E-1, $E941-1, $EF09-1, $EB90-1, $EBAF-1, $EE8D-1, $EC23-1, NEGOP-1


; -- the calculator ---------------------------------------------------------------
; Epistole's expressions, for docview.c (which says what they are). A
; variable is 12 bytes in calc_vars: its name (6 characters, zero-padded, 0
; first when the slot is free), 1 if its value is known (0: typed at print
; time), its value. An unknown variable, a function or an operator the ROM
; refuses, a syntax error: calc_eval gives 0, never a number.
;
; unsigned char __fastcall__ calc_eval(const char* p): p into fp_x; 1, or 0.
; void __fastcall__ calc_assign(const char* p): "NAME=expr"; unknown if the
;   expression is.
; void __fastcall__ calc_forget(const char* p): NAME, typed at print time.
; const char* __fastcall__ calc_format(unsigned char nd): fp_x with nd
;   decimals, rounded, a decimal comma; BASIC's own text (commas for points)
;   when that cannot be done (1E+10). Zero-ended; fp_x is spent.
;
; ptr1 walks the text; ptr2 is a variable; ptr3 what vpush copies. They and
; tmp1-tmp3 live through fp_op, which puts the zero page back.

NVARS   = 12
VSIZE   = 12
VNAME   = 6
VDEPTH  = 8                     ; values on the stack
ODEPTH  = 16                    ; operators
PAREN   = $FF

peek:   ldy     #0              ; A = *p
        lda     (ptr1),y
        rts
adv:    inc     ptr1
        bne     :+
        inc     ptr1+1
:       rts
skipsp: jsr     peek
        cmp     #' '
        bne     :+
        jsr     adv
        jmp     skipsp
:       rts

; C set for a digit; A kept.
isdigit:
        cmp     #'0'
        bcc     :+
        cmp     #'9' + 1
        bcs     :+
        sec
        rts
:       clc
        rts
; C set for a letter; A kept.
isalpha:
        sta     tmp1
        and     #$DF
        cmp     #'A'
        bcc     :+
        cmp     #'Z' + 1
        bcs     :+
        lda     tmp1
        sec
        rts
:       lda     tmp1
        clc
        rts

; nm = the name at p, upper case, VNAME characters counting; p after it.
pname:  ldx     #VNAME - 1
        lda     #0
:       sta     nm,x
        dex
        bpl     :-
        jsr     peek
        jsr     isalpha
        bcc     @done
        ldx     #0
@loop:  jsr     peek
        jsr     isalpha
        bcc     @dig
        and     #$DF
        bcs     @store                  ; always: isalpha's carry
@dig:   jsr     isdigit
        bcc     @done
@store: cpx     #VNAME
        bcs     @skip
        sta     nm,x
        inx
@skip:  jsr     adv
        jmp     @loop
@done:  rts

; The variable nm: C clear and ptr2 at it, or C set. With tmp2 nonzero it
; is made in the first free slot when missing (unknown), if there is one.
findvar:
        lda     #0
        sta     freev+1
        lda     #<_calc_vars
        sta     ptr2
        lda     #>_calc_vars
        sta     ptr2+1
        ldx     #NVARS
@next:  ldy     #0
        lda     (ptr2),y
        bne     @cmp
        lda     freev+1                 ; the first free one
        bne     @adv
        lda     ptr2
        sta     freev
        lda     ptr2+1
        sta     freev+1
        jmp     @adv
@cmp:   ldy     #VNAME - 1
:       lda     (ptr2),y
        cmp     nm,y
        bne     @adv
        dey
        bpl     :-
        clc
        rts
@adv:   lda     ptr2
        clc
        adc     #VSIZE
        sta     ptr2
        bcc     :+
        inc     ptr2+1
:       dex
        bne     @next
        lda     tmp2
        beq     @no
        lda     freev+1                 ; never 0: calc_vars is not in page 0
        beq     @no
        sta     ptr2+1
        lda     freev
        sta     ptr2
        ldy     #VNAME - 1
:       lda     nm,y
        sta     (ptr2),y
        dey
        bpl     :-
        ldy     #VNAME
        lda     #0
        sta     (ptr2),y
        clc
        rts
@no:    sec
        rts

times5: sta     tmp1                    ; X = A * 5
        asl
        asl
        clc
        adc     tmp1
        tax
        rts

; The 5 bytes at ptr3 onto the value stack; C set when it is full.
vpush:  lda     vsp
        cmp     #VDEPTH
        bcs     :++
        jsr     times5
        ldy     #0
:       lda     (ptr3),y
        sta     vstk,x
        inx
        iny
        cpy     #5
        bne     :-
        inc     vsp
        clc
:       rts

; A onto the operator stack; C set when it is full.
opush:  ldx     osp
        cpx     #ODEPTH
        bcs     :+
        sta     ostk,x
        inc     osp
        clc
:       rts

; The operator A on the value stack; C set if it cannot be done.
apply:  sta     aop
        cmp     #FP_SIN
        bcs     @un
        lda     vsp
        cmp     #2
        bcc     @fail
        dec     vsp
        lda     vsp                     ; the right operand into fp_y
        jsr     times5
        ldy     #0
:       lda     vstk,x
        sta     _fp_y,y
        inx
        iny
        cpy     #5
        bne     :-
        beq     @x                      ; always
@un:    lda     vsp
        beq     @fail
@x:     ldx     vsp
        dex
        txa
        jsr     times5
        stx     tmp3
        ldy     #0
:       lda     vstk,x
        sta     _fp_x,y
        inx
        iny
        cpy     #5
        bne     :-
        lda     aop
        jsr     _fp_op
        bne     @fail
        ldx     tmp3
        ldy     #0
:       lda     _fp_x,y
        sta     vstk,x
        inx
        iny
        cpy     #5
        bne     :-
        clc
        rts
@fail:  sec
        rts

; fp_x = fp_x OP constant (X: 0 ten, 5 a half, 10 32,768); A = fp_op's.
op_k:   pha
        ldy     #0
:       lda     consts,x
        sta     _fp_y,y
        inx
        iny
        cpy     #5
        bne     :-
        pla
        jmp     _fp_op

; A number at p onto the value stack: nine digits count, then the others
; only as tens; one decimal comma or point. C set if it cannot be.
number: lda     #0
        ldx     #7
:       sta     acc,x                   ; acc, frac, dot, extra, ndig, tmpf
        dex
        bpl     :-
@loop:  jsr     peek
        jsr     isdigit
        bcc     @nd
        sbc     #'0'                    ; carry set
        sta     tmp1
        lda     ndig
        cmp     #9
        bcs     @full
        lda     acc                     ; leading zeros count for nothing
        ora     acc+1
        ora     acc+2
        ora     acc+3
        ora     tmp1
        beq     @lz
        jsr     mul10
        inc     ndig
@lz:    lda     dot
        beq     @adv
        inc     frac
        bne     @adv                    ; always
@full:  lda     dot
        bne     @adv
        inc     extra
        bne     @adv                    ; always
@nd:    cmp     #','
        beq     @dot
        cmp     #'.'
        bne     @e
@dot:   lda     dot
        bne     @e
        inc     dot
@adv:   jsr     adv
        jmp     @loop
@e:     and     #$DF                    ; 1,5E2: tens, up or down
        cmp     #'E'
        bne     @conv
        jsr     adv
        jsr     peek
        ldx     #0                      ; X: 0 up, 1 down
        cmp     #'+'
        beq     :+
        cmp     #'-'
        bne     :++
        inx
:       jsr     adv
:       lda     #0
        sta     tmp2
@edig:  jsr     peek
        jsr     isdigit
        bcc     @eend
        sbc     #'0'
        sta     tmp1
        lda     tmp2                    ; tmp2 = tmp2 * 10 + digit
        asl
        asl
        adc     tmp2
        asl
        adc     tmp1
        sta     tmp2
        cmp     #40                     ; past 1E38: the ROM refuses it anyway
        bcc     :+
        jmp     @err
:       jsr     adv
        jmp     @edig
@eend:  lda     tmp2
        dex
        beq     :+
        clc
        adc     extra
        sta     extra
        bcc     @conv                   ; always
:       clc
        adc     frac
        sta     frac
@conv:  lda     acc+1                   ; fp_n = acc >> 15 (acc < 2^30)
        asl
        lda     acc+2
        rol
        sta     _fp_n
        lda     acc+3
        rol
        sta     _fp_n+1
        lda     #FP_INT16
        jsr     _fp_op
        bne     @err
        lda     #FP_MUL
        ldx     #10
        jsr     op_k
        bne     @err
        ldx     #4
:       lda     _fp_x,x
        sta     tmpf,x
        dex
        bpl     :-
        lda     acc                     ; + (acc & $7FFF)
        sta     _fp_n
        lda     acc+1
        and     #$7F
        sta     _fp_n+1
        lda     #FP_INT16
        jsr     _fp_op
        bne     @err
        ldx     #4
:       lda     tmpf,x
        sta     _fp_y,x
        dex
        bpl     :-
        lda     #FP_ADD
        jsr     _fp_op
        bne     @err
@div:   lda     frac
        beq     @mul
        dec     frac
        lda     #FP_DIV
        ldx     #0
        jsr     op_k
        beq     @div
@err:   sec
        rts
@mul:   lda     extra
        beq     @push
        dec     extra
        lda     #FP_MUL
        ldx     #0
        jsr     op_k
        beq     @mul
        bne     @err
@push:  lda     #<_fp_x
        sta     ptr3
        lda     #>_fp_x
        sta     ptr3+1
        jmp     vpush

; acc = acc * 10 + tmp1
mul10:  jsr     acc2                    ; acc * 2, kept in tmpf
        ldx     #3
:       lda     acc,x
        sta     tmpf,x
        dex
        bpl     :-
        jsr     acc2                    ; * 8
        jsr     acc2
        ldx     #0
        clc
        php
:       plp
        lda     acc,x
        adc     tmpf,x
        sta     acc,x
        php
        inx
        cpx     #4
        bne     :-
        plp
        lda     acc                     ; + the digit
        clc
        adc     tmp1
        sta     acc
        bcc     :+
        inc     acc+1
        bne     :+
        inc     acc+2
        bne     :+
        inc     acc+3
:       rts
acc2:   asl     acc
        rol     acc+1
        rol     acc+2
        rol     acc+3
        rts

; nm, a function: C clear and X its number (SIN 0 ... INT 9), or C set.
funcidx:
        lda     nm+3
        bne     @no
        ldx     #0
        ldy     #0
@f:     lda     funcs,y
        cmp     nm
        bne     @n
        lda     funcs+1,y
        cmp     nm+1
        bne     @n
        lda     funcs+2,y
        cmp     nm+2
        beq     @yes
@n:     iny
        iny
        iny
        inx
        cpx     #10
        bne     @f
@no:    sec
        rts
@yes:   clc
        rts

_calc_eval:
        sta     ptr1
        stx     ptr1+1
        lda     #0
        sta     vsp
        sta     osp
        lda     #1
        sta     expect
@loop:  jsr     skipsp
        ldx     expect
        bne     @operand
        jmp     @operator

@operand:
        cmp     #'+'                    ; a sign that changes nothing
        bne     :+
        jsr     adv
        jmp     @loop
:       ldx     #FP_NEG
        cmp     #'-'
        beq     :+
        ldx     #PAREN
        cmp     #'('
        bne     @value
:       txa
@pushadv:
        jsr     opush
        bcs     @fail
        jsr     adv
        jmp     @loop
@value: jsr     isdigit
        bcs     @num
        cmp     #','
        beq     @num
        cmp     #'.'
        beq     @num
        jsr     isalpha
        bcc     @fail
        jsr     pname
        jsr     peek
        cmp     #'('
        bne     @var
        jsr     funcidx                 ; a function, applied at its )
        bcs     @fail
        txa
        clc
        adc     #FP_SIN
        jsr     opush
        bcs     @fail
        lda     #PAREN
        bne     @pushadv                ; always
@num:   jsr     number
        bcs     @fail
        bcc     @got                    ; always
@var:   lda     #0
        sta     tmp2
        jsr     findvar
        lda     #<zero5                 ; never set: 0
        ldx     #>zero5
        bcs     :+
        ldy     #VNAME                  ; typed at print time: no value
        lda     (ptr2),y
        beq     @fail
        lda     ptr2
        clc
        adc     #VNAME + 1
        ldx     ptr2+1
        bcc     :+
        inx
:       sta     ptr3
        stx     ptr3+1
        jsr     vpush
        bcs     @fail
@got:   lda     #0
        sta     expect
        jmp     @loop

@fail:  lda     #0
        tax
        rts

@operator:
        cmp     #0
        beq     @close
        cmp     #')'
        beq     @close
        ldx     #7
:       cmp     opch,x
        beq     :+
        dex
        bpl     :-
        bmi     @fail                   ; always
:       lda     opval,x
        sta     curop
        jsr     adv
        lda     curop                   ; < > with a second character
        cmp     #FP_LT
        bne     @gt
        jsr     peek
        ldx     #FP_NE
        cmp     #'>'
        beq     @two
        ldx     #FP_LE
        cmp     #'='
        beq     @two
        bne     @reduce                 ; always
@gt:    cmp     #FP_GT
        bne     @reduce
        jsr     peek
        ldx     #FP_GE
        cmp     #'='
        bne     @reduce
@two:   stx     curop
        jsr     adv
@reduce:                                ; what binds as close or closer first
        ldx     osp
        beq     @push
        lda     ostk-1,x
        cmp     #PAREN
        beq     @push
        tay
        lda     prec,y
        ldy     curop
        cmp     prec,y
        bcc     @push
        dec     osp
        lda     ostk-1,x
        jsr     apply
        bcs     @fail
        jmp     @reduce
@push:  lda     curop
        jsr     opush
        bcs     @fail
        lda     #1
        sta     expect
        jmp     @loop

@close: sta     curop                   ; 0: the end; ')'
@pop:   ldx     osp
        beq     :+
        lda     ostk-1,x
        cmp     #PAREN
        beq     :+
        dec     osp
        jsr     apply
        bcs     @fail2
        jmp     @pop
:       lda     curop
        bne     @rparen
        ldx     osp                     ; the end: an open ( is an error
        bne     @fail2
        lda     vsp
        cmp     #1
        bne     @fail2
        ldx     #4
:       lda     vstk,x
        sta     _fp_x,x
        dex
        bpl     :-
        lda     #1
        ldx     #0
        rts
@rparen:
        ldx     osp                     ; a ) with no (
        beq     @fail2
        dec     osp
        jsr     adv
        ldx     osp                     ; a function's ): apply it
        beq     :+
        lda     ostk-1,x
        cmp     #FP_SIN
        bcc     :+
        cmp     #FP_NEG
        bcs     :+
        dec     osp
        jsr     apply
        bcs     @fail2
:       jmp     @loop
@fail2: jmp     @fail

_calc_assign:
        sta     ptr1
        stx     ptr1+1
        jsr     pname
        lda     nm
        beq     @r
        jsr     skipsp
        cmp     #'='
        bne     @r
        jsr     adv
        ldx     #VNAME - 1              ; the name, which calc_eval's own
:       lda     nm,x                    ; names overwrite
        sta     aname,x
        dex
        bpl     :-
        lda     ptr1                    ; first the value: X=X+1 reads X
        ldx     ptr1+1                  ; as it was (0 if never set)
        jsr     _calc_eval
        sta     aent
        ldx     #VNAME - 1
:       lda     aname,x
        sta     nm,x
        dex
        bpl     :-
        lda     #1
        sta     tmp2
        jsr     findvar
        bcs     @r
        lda     aent
        ldy     #VNAME
        sta     (ptr2),y                ; known: calc_eval's 1 or 0
        tax
        beq     @r
        ldx     #0
:       iny
        lda     _fp_x,x
        sta     (ptr2),y
        inx
        cpx     #5
        bne     :-
@r:     rts

_calc_forget:
        sta     ptr1
        stx     ptr1+1
        jsr     pname
        lda     nm
        beq     :+
        lda     #1
        sta     tmp2
        jsr     findvar
        bcs     :+
        ldy     #VNAME
        lda     #0
        sta     (ptr2),y
:       rts

_calc_format:
; Epistole's own: BASIC's text of |x| + half a unit of the last decimal, its
; decimals cut or padded to nd, a decimal comma, an exponent kept where
; BASIC writes one (2/3 with 2: 0,67; 1E10: 1E+10,00; 0,0001: 5,10E-03).
; The minus sign only with nd = 0 and |x| >= 1, as Epistole prints it.
        sta     nd
        lda     _fp_x+1                 ; the sign, for nd = 0 and |x| >= 1
        and     #$80
        ldx     nd
        bne     :+
        ldx     _fp_x
        cpx     #$81
        bcs     :++
:       lda     #0
:       sta     neg
        lda     #FP_ABS
        jsr     _fp_op
        ldx     #4
:       lda     _fp_x,x
        sta     tmpf,x
        lda     consts+5,x              ; fp_x = .5, then / 10 nd times
        ldy     _fp_x
        bne     :+
        lda     #0                      ; 0 is 0,00: nothing added to it
:       sta     _fp_x,x
        dex
        bpl     :--
        lda     nd
        sta     cnt
@half:  lda     cnt
        beq     :+
        dec     cnt
        lda     #FP_DIV
        ldx     #0
        jsr     op_k
        beq     @half
:       ldx     #4                      ; + |x|
:       lda     tmpf,x
        sta     _fp_y,x
        dex
        bpl     :-
        lda     #0
        sta     numbuf
        lda     #FP_ADD
        jsr     _fp_op
        beq     :+
        jmp     @ret                    ; too large: nothing (never here)
:
        lda     #FP_FOUT
        jsr     _fp_op
        ldx     #0
        lda     neg
        beq     :+
        lda     #'-'
        sta     numbuf
        inx
:       ldy     #0                      ; the integer part, "0" if none
        lda     _fp_text
        cmp     #'.'
        bne     @int
        lda     #'0'
        sta     numbuf,x
        inx
@int:   lda     _fp_text,y
        beq     @nodot
        cmp     #'.'
        beq     @dot
        sta     numbuf,x
        inx
        iny
        bne     @int                    ; always
@nodot: jsr     @comma                  ; no decimals written: all zeros
@zeros: lda     cnt
        beq     @end
        lda     #'0'
        sta     numbuf,x
        inx
        dec     cnt
        jmp     @zeros
@dot:   iny
        jsr     @comma
@frac:  lda     _fp_text,y              ; the decimals, nd of them
        jsr     isdigit
        bcc     @pad
        lda     cnt
        beq     :+
        lda     _fp_text,y
        sta     numbuf,x
        inx
        dec     cnt
:       iny
        bne     @frac                   ; always
@pad:   lda     cnt
        beq     @exp
        lda     #'0'
        sta     numbuf,x
        inx
        dec     cnt
        bne     @pad                    ; always
@exp:   lda     _fp_text,y              ; E+09, E-03
        sta     numbuf,x
        beq     @ret
        inx
        iny
        bne     @exp                    ; always
@end:   lda     #0
        sta     numbuf,x
@ret:   lda     #<numbuf
        ldx     #>numbuf
        rts
@comma: lda     nd                      ; ',' if there are decimals; cnt = nd
        sta     cnt
        beq     :+
        lda     #','
        sta     numbuf,x
        inx
:       rts

        .segment "RODATA"
consts: .byte   $84, $20, 0, 0, 0       ; 10
        .byte   $80, $00, 0, 0, 0       ; .5
        .byte   $90, $00, 0, 0, 0       ; 32,768
zero5:  .byte   0, 0, 0, 0, 0
funcs:  .byte   "SINCOSTANATNLOGEXPSGNABSSQRINT"
opch:   .byte   "+-*/^=<>"
opval:  .byte   FP_ADD, FP_SUB, FP_MUL, FP_DIV, FP_POW, FP_EQ, FP_LT, FP_GT
; How close each operator binds: comparisons, + -, * /, ^, then a sign:
; -2^2 is 4 in Epistole, 2^3^2 is 64.
prec:   .byte   2, 2, 3, 3, 4, 1, 1, 1, 1, 1, 1
        .byte   6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 5
binlo:  .lobytes BINS
binhi:  .hibytes BINS
funlo:  .lobytes FUNS
funhi:  .hibytes FUNS
; FCOMP's answer, A and 3: 0 equal, 1 greater, 3 less. Accepted for
; < > = <> <= >=, as bits: 1 equal, 2 greater, 8 less.
bits:   .byte   1, 2, 0, 8
accept: .byte   8, 2, 1, 2|8, 1|8, 1|2

        .segment "BSS"
_fp_x:  .res    5
_fp_y:  .res    5
_fp_n:  .res    2
_fp_text: .res  17
op:     .res    1
result: .res    1
stack:  .res    1
_fp_zsave: .res  2              ; 176 bytes for $50-$FF (docview.c: in copy_buf)
_calc_vars: .res NVARS * VSIZE
vstk:   .res    VDEPTH * 5
vsp:    .res    1
ostk:   .res    ODEPTH
osp:    .res    1
nm:     .res    VNAME
expect: .res    1
curop:  .res    1
aop:    .res    1
freev:  .res    2
aent:   .res    1
aname:  .res    VNAME
acc:    .res    4               ; number: these 8 cleared together
frac:   .res    1
dot:    .res    1
extra:  .res    1
ndig:   .res    1
tmpf:   .res    5
nd:     .res    1
neg:    .res    1
cnt:    .res    1
len:    .res    1
comma:  .res    1
numbuf: .res    24
