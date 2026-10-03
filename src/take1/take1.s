; take1.s -- TAKE1.SYSTEM, the Take 1 movie player of A2 File Cmd.
;
; A ProDOS interpreter (JMP, $EE $EE, buffer length, path at $2006): A2 File
; Cmd loads it at $2000 with a command (dos.s: an image and the movie's
; T/S list, a unit and the T/S list, or an extracted movie's path), the
; prefix set to its own directory. The program moves itself out of the
; hi-res pages (take1.cfg), reads the movie, and has the engine (engine.s)
; play it through the hooks below; then it holds the last frame two
; seconds and plays it again, until Escape. Escape, or a refused movie
; followed by a key, return to A2 File Cmd: A2FILE.SYSTEM is loaded again
; from the prefix (QUIT to ProDOS only if that fails).
;
; Keys: Escape returns, Space pauses and resumes, Tab switches between the
; original speed (the default: the frame waits, pauses and fade delays of
; the original) and the accelerated one (none of them); Return and the
; paddle buttons answer a wait. Other keys are ignored.
;
; The label t1_shown is the instant a frame becomes visible: right after
; the soft switch that shows it (an emulator may break there to capture
; frames; the page shown is t1_front, $20 or $40, page 1 or 2).
;
; Data safety: read-only; the only MLI calls are OPEN, SET_MARK, READ,
; CLOSE, READ_BLOCK and QUIT. Main memory only: no auxiliary memory, so
; /RAM is untouched. The pages the program keeps are marked in the ProDOS
; system bitmap while it runs (not the hi-res pages, where the loader's
; I/O buffers go, nor the pages ProDOS reads into) and the bitmap is given
; back as it was before A2FILE.SYSTEM is loaded. Memory map: take1.cfg.
;
; Plain 6502: the same file serves both editions.

        .import t1_play, t1_name, t1_err, t1_front, dstart
        .export t1_show, t1_wait, t1_fc, t1_delay, t1_tick, t1_shown, path0
        .export t1_mode := mode, t1_sound := sound
        .import __HICODE_LOAD__, __HICODE_RUN__, __HICODE_SIZE__, __HIDATA_SIZE__
        .import __RODATA_LOAD__, __RODATA_RUN__, __RODATA_SIZE__
        .import __HIDATA_LOAD__, __HIDATA_RUN__, __LOADER_RUN__, __LOADER_SIZE__

        .import __CODE_LOAD__, __CODE_RUN__, __CODE_SIZE__
        .import __TIMED_LOAD__, __TIMED_RUN__, __TIMED_SIZE__
        .import __BSS_RUN__, __BSS_SIZE__
        .import __HIBSS_RUN__, __HIBSS_SIZE__

MLI     = $BF00
BITMAP  = $BF58                 ; 24 bytes, one bit a page, $80 = lowest
KBD     = $C000
STORE80OFF = $C000              ; (write)
CLR80VID = $C00C
KBDSTRB = $C010
SPKR    = $C030
TXTCLR  = $C050
TXTSET  = $C051
MIXCLR  = $C052
LOWSCR  = $C054
HISCR   = $C055
HIRES   = $C057
SETAN3  = $C05F
PB0     = $C061
PB1     = $C062
ROMIN   = $C082
PATHMAX = 64

        .zeropage
src:    .res 2
dst:    .res 2
cnt:    .res 2
wn:     .res 2                  ; steps left to wait
msgp:   .res 2
fxp:    .res 2                  ; the sound's steps
zflag:  .res 1                  ; copy: 1, zero: 0
w4:     .res 1                  ; frame-wait steps, for the 18 cycles
tcnt:   .res 1                  ; a sound's toggles and steps
tpv:    .res 1

        .bss
savebm: .res 24                 ; the system bitmap as it was
mode:   .res 1                  ; 1 original speed, 0 accelerated
seed:   .res 2                  ; the sounds' random numbers
scnt:   .res 2

; -- at $2000: the interpreter header, then the start ------------------------
        .segment "LOADER"
        jmp     start
        .byte   $EE, $EE
        .byte   PATHMAX + 1     ; the path buffer's length
path0:  .byte   0               ; the launcher stores the command here
        .res    PATHMAX
start:  cld
        ldx     #$FF
        txs
        lda     #<__TIMED_LOAD__        ; the program, to low memory (CODE
        sta     src                     ; follows TIMED)
        lda     #>__TIMED_LOAD__
        sta     src+1
        lda     #<__TIMED_RUN__
        sta     dst
        lda     #>__TIMED_RUN__
        sta     dst+1
        lda     #<(__TIMED_SIZE__ + __CODE_SIZE__)
        ldx     #>(__TIMED_SIZE__ + __CODE_SIZE__)
        jsr     copy
        lda     #<__HICODE_LOAD__       ; and to high memory (RODATA, HIDATA follow)
        sta     src
        lda     #>__HICODE_LOAD__
        sta     src+1
        lda     #<__HICODE_RUN__
        sta     dst
        lda     #>__HICODE_RUN__
        sta     dst+1
        lda     #<(__HICODE_SIZE__ + __RODATA_SIZE__ + __HIDATA_SIZE__)
        ldx     #>(__HICODE_SIZE__ + __RODATA_SIZE__ + __HIDATA_SIZE__)
        jsr     copy
        lda     #<__BSS_RUN__           ; variables to zero
        sta     dst
        lda     #>__BSS_RUN__
        sta     dst+1
        lda     #<__BSS_SIZE__
        ldx     #>__BSS_SIZE__
        jsr     zero
        lda     #<__HIBSS_RUN__
        sta     dst
        lda     #>__HIBSS_RUN__
        sta     dst+1
        lda     #<__HIBSS_SIZE__
        ldx     #>__HIBSS_SIZE__
        jsr     zero
        ldx     #23                     ; the bitmap as it is, given back on
:       lda     BITMAP,x                ; the way out
        sta     savebm,x
        dex
        bpl     :-
        lda     #$E1
        sta     seed
        lda     #$AC
        sta     seed+1
        lda     #1
        sta     mode
        lda     #$20                    ; page 1 shown: page 2 is free
        sta     t1_front
        jsr     dstart                  ; the command (dos.s)
        bcc     :+
        jmp     refuse
:       ldx     #0                      ; mark the program's pages: $02-$03,
:       lda     marks,x                 ; $08-$1F, $80-$BE
        tay
        jsr     mark
        inx
        cpx     #nmarks
        bne     :-
        jmp     main

; A/X bytes from src to dst, upwards; zero: A/X zeros to dst.
zero:   ldy     #0                      ; (zflag 0: zeros, src unused)
        beq     copy2
copy:   ldy     #1
copy2:  sty     zflag
        sta     cnt
        stx     cnt+1
        ldy     #0
@copy:  lda     cnt
        ora     cnt+1
        beq     @done
        lda     #0
        ldx     zflag
        beq     :+
        lda     (src),y
:       sta     (dst),y
        inc     src
        bne     :+
        inc     src+1
:       inc     dst
        bne     :+
        inc     dst+1
:       lda     cnt
        bne     :+
        dec     cnt+1
:       dec     cnt
        jmp     @copy
@done:  rts

; Marks the pages from Y (high byte) for the run marks gives.
mark:   tya
        lsr
        lsr
        lsr
        sta     cnt
        tya
        and     #7
        tay
        lda     bits,y
        ldy     cnt
        ora     BITMAP,y
        sta     BITMAP,y
        rts

marks:  .byte   $02, $03
        .repeat $18, i
        .byte   $08 + i
        .endrepeat
        .repeat $3F, i
        .byte   $80 + i
        .endrepeat
nmarks  = * - marks

        .assert __CODE_LOAD__ = __TIMED_LOAD__ + __TIMED_SIZE__ && __CODE_RUN__ = __TIMED_RUN__ + __TIMED_SIZE__, error, "CODE must follow TIMED"
        .assert <__TIMED_RUN__ = 0, error, "TIMED must start a page"
        .assert __RODATA_LOAD__ = __HICODE_LOAD__ + __HICODE_SIZE__ && __RODATA_RUN__ = __HICODE_RUN__ + __HICODE_SIZE__, error, "RODATA must follow HICODE"
        .assert __HIDATA_LOAD__ = __RODATA_LOAD__ + __RODATA_SIZE__ && __HIDATA_RUN__ = __RODATA_RUN__ + __RODATA_SIZE__, error, "HIDATA must follow RODATA"
        .assert __LOADER_RUN__ + __LOADER_SIZE__ <= $4000, error, "the start code must stay in page 1"
        ; (BSS within $0200-$03CF: take1.cfg's LOWB area enforces it)

; -- the program --------------------------------------------------------------
        .code
main:   jsr     clr1                    ; plain 40-column hi-res, page 1,
        sta     STORE80OFF              ; full screen (black)
        sta     CLR80VID
        sta     SETAN3
        sta     HIRES
        sta     MIXCLR
        sta     LOWSCR
        sta     TXTCLR
@loop:  jsr     t1_play
        bcs     refuse
        lda     #30                     ; the end: two seconds, the keys read
        sta     cnt
@hold:  ldx     #0
:       jsr     keys
        jsr     unit
        dex
        bne     :-
        dec     cnt
        bne     @hold
        jmp     @loop

; Clears page 1.
clr1:   lda     #0
        sta     dst
        ldx     #$20
        stx     dst+1
        tay
:       sta     (dst),y
        iny
        bne     :-
        inc     dst+1
        dex
        bne     :-
        rts

; A refused movie (A = t1_err): the reason and t1_name on the text screen,
; then a key and the way back.
refuse: pha
        jsr     textscr
        pla
        tax
        dex
        cpx     #5
        bcc     :+
        ldx     #3
:       txa
        pha
        asl
        tay
        lda     whys,y
        pha
        lda     whys+1,y
        tay
        pla
        ldx     #10
        jsr     print
        pla
        cmp     #4                      ; the command: no name
        beq     :+
        lda     #<t1_name
        ldy     #>t1_name
        ldx     #11
        jsr     print
:       lda     #<skey
        ldy     #>skey
        ldx     #13
        jsr     print
        jsr     getkey
        jmp     back

; -- the timed loops ----------------------------------------------------------
; In one page (TIMED starts one: take1.cfg), so that no branch crosses a
; page and the cycles are the same wherever the program is linked.
        .segment "TIMED"
; The frame wait: A/X steps of 350 cycles, 18 more after every fourth.
t1_wait:
        sta     wn
        stx     wn+1
        lda     mode
        bne     @loop
        jmp     keys                    ; (accelerated: no wait)
@loop:  lda     wn                      ; 3
        ora     wn+1                    ; 3
        beq     @done                   ; 2
        lda     KBD                     ; 4
        bpl     :+                      ; 3
        jsr     keys
        lda     mode
        beq     @done
:       ldx     #61                     ; 2
:       dex                             ; 61 * 5 - 1
        bne     :-
        nop                             ; 2
        lda     wn                      ; 3
        bne     :+                      ; 3
        dec     wn+1
:       dec     wn                      ; 5
        inc     w4                      ; 5
        lda     w4                      ; 3
        and     #3                      ; 2
        bne     :++                     ; 3
        ldx     #3                      ; the 18 more (with the bne: 2, 14,
:       dex                             ; 3, - 1)
        bne     :-
        bit     wn
:       jmp     @loop                   ; 3: 350 a step
@done:  rts

; D(A): (5 A^2 + 27 A + 26) / 2 cycles, A = 0 counting as 256.
wait:   sec
@w2:    pha
@w3:    sbc     #1
        bne     @w3
        pla
        sbc     #1
        bne     @w2
        rts

; tcnt toggles, each after tpv steps.
tone:   ldy     tcnt                    ; (12 p + 11 cycles a toggle)
@t:     ldx     tpv                     ; 3
@s:     nop                             ; 12 p - 1
        nop
        bit     tcnt
        dex
        bne     @s
        lda     SPKR                    ; 4
        dey                             ; 2
        bne     @t                      ; 3
        rts

; A steps (0: 256) of 12 cycles.
steps:  tax
@s:     nop
        nop
        bit     tcnt
        dex
        bne     @s
        rts

; About 250 cycles with the jsr and rts; X and Y kept.
unit:   lda     #33
:       sec
        sbc     #1
        bne     :-
        rts

        .assert __TIMED_SIZE__ <= 256, error, "TIMED over one page"
        .code

; -- hooks ---------------------------------------------------------------------
; Shows page A ($20 / $40).
t1_show:
        cmp     #$40
        bne     :+
        sta     HISCR                   ; page 2 (carry set by the cmp)
        bcs     t1_shown
:       sta     LOWSCR
t1_shown:                               ; the frame is visible
        jmp     keys

; A fade's D(A) (the monitor's WAIT loop), at the original speed.
t1_delay:
        ldx     mode
        beq     keys
        jsr     wait
; Fade 14's ticks: the keys only.
t1_tick:
; Reads a key if there is one: Escape returns, Space pauses (until Space
; again), Tab switches the speed.
keys:   lda     KBD
        bpl     knone
        sta     KBDSTRB
        jsr     key
        cmp     #' '
        bne     knone
pause:  jsr     getkey
        jsr     key
        cmp     #' '
        bne     pause
knone:  rts

; One key in A: Escape returns, Tab switches; A = the key without bit 7.
key:    and     #$7F
        cmp     #$1B
        bne     :+
        jmp     back
:       cmp     #$09
        bne     :+
        pha
        lda     mode
        eor     #1
        sta     mode
        pla
:       rts

getkey: lda     KBD
        bpl     getkey
        sta     KBDSTRB
        rts

; A $FC element: A = the kind, X = t.
t1_fc:  cmp     #1
        beq     @pause
        bcs     :+
        jmp     @wait
:       cmp     #2
        beq     :+
        rts                             ; (another kind: none)
:       txa                             ; a sound: t mod 32, then - 18 if
        and     #31                     ; 18 or more
        cmp     #18
        bcc     :+
        sbc     #18
:       jmp     sound
@pause: stx     cnt                     ; t times D(141), original speed;
@p:     lda     cnt                     ; Return or Escape ends it
        beq     @pend
        lda     mode
        beq     @pend
        lda     #141
        jsr     wait
        lda     KBD
        bpl     :+
        sta     KBDSTRB
        jsr     key
        cmp     #$0D
        beq     @pend
        cmp     #' '
        bne     :+
        jsr     pause
:       dec     cnt
        jmp     @p
@pend:  rts
@wait:  lda     PB0                     ; a key (Return) or a button: from
        ora     PB1                     ; the buttons released
        bmi     @wait
@w:     lda     PB0
        ora     PB1
        bmi     @wend
        lda     KBD
        bpl     @w
        sta     KBDSTRB
        jsr     key
        cmp     #$0D
        bne     @w
@wend:  rts

; -- sounds ------------------------------------------------------------------------
; Sound A (0-17) on the speaker: its steps from fx (tone count, p; silence
; n; rough count; burst), each delay step 12 cycles.
SND_END = 0
SND_TONE = 1
SND_SIL = 2
SND_ROUGH = 3
SND_BURST = 4

sound:  asl
        tay
        lda     fxtab,y
        sta     fxp
        lda     fxtab+1,y
        sta     fxp+1
@step:  ldy     #0
        lda     (fxp),y
        beq     @done
        cmp     #SND_SIL
        bcc     @tone
        beq     @sil
        cmp     #SND_BURST
        beq     @burst
        iny                             ; rough: count toggles, random waits
        lda     (fxp),y
        sta     tcnt
        jsr     rough
        lda     #2
        bne     @next                   ; (always)
@tone:  iny
        lda     (fxp),y
        sta     tcnt
        iny
        lda     (fxp),y
        sta     tpv
        jsr     tone
        lda     #3
        bne     @next                   ; (always)
@sil:   iny
        lda     (fxp),y
        sta     scnt
        iny
        lda     (fxp),y
        sta     scnt+1
        jsr     silence
        lda     #3
        bne     @next                   ; (always)
@burst: jsr     rnd                     ; silence of 1-256 steps, half the
        jsr     steps                   ; time 512 more
        jsr     rnd
        lsr
        bcc     :+
        lda     #0
        jsr     steps
        lda     #0
        jsr     steps
:       jsr     rnd                     ; then 1-31 toggles (odd)
        and     #30
        ora     #1
        sta     tcnt
        jsr     rough
        lda     #1
@next:  clc
        adc     fxp
        sta     fxp
        bcc     @step
        inc     fxp+1
        bne     @step                   ; (always)
@done:  rts

; tcnt toggles, each after a random 1-256 steps.
rough:
@r:     jsr     rnd
        jsr     steps
        lda     SPKR
        dec     tcnt
        bne     @r
        rts

; scnt steps.
silence:
        lda     scnt
        beq     :+
        jsr     steps
:       ldy     scnt+1
        beq     @done
:       lda     #0
        jsr     steps
        dey
        bne     :-
@done:  rts

; A = a pseudo-random byte (a 16-bit Galois LFSR, never 0).
rnd:    lsr     seed+1
        ror     seed
        bcc     :+
        lda     seed+1
        eor     #$B4
        sta     seed+1
:       lda     seed
        rts

; -- leaving ---------------------------------------------------------------------
; Back to A2 File Cmd: text screen, the bitmap as it was, then the thunk
; from page 3.
back:   ldx     #$FF
        txs
        sta     TXTSET
        sta     LOWSCR
        ldx     #23
:       lda     savebm,x
        sta     BITMAP,x
        dex
        bpl     :-
        ldy     #0
:       lda     thunk_src,y
        sta     $0300,y
        iny
        cpy     #thunk_len
        bne     :-
        jmp     $0300

; The text screen, 40 columns, cleared, the title on row 8.
textscr:
        sta     STORE80OFF
        sta     CLR80VID
        sta     TXTSET
        sta     LOWSCR
        ldx     #23
@clr:   jsr     textrow
        lda     #$A0
        ldy     #39
:       sta     (dst),y
        dey
        bpl     :-
        dex
        bpl     @clr
        ldx     #8
        lda     #<title
        ldy     #>title
; The string at A/Y (length first) on text row X, 40 characters at most.
print:  sta     msgp
        sty     msgp+1
        jsr     textrow
        ldy     #0
        lda     (msgp),y
        tax
        beq     @done
:       iny
        lda     (msgp),y
        ora     #$80
        dey
        sta     (dst),y
        iny
        dex
        bne     :-
@done:  rts

; dst = the start of text row X (page 1).
textrow:
        txa
        and     #7
        lsr
        sta     dst+1
        lda     #0
        ror
        sta     dst
        txa
        lsr
        lsr
        lsr
        tay
        lda     dst
        clc
        adc     rowx40,y
        sta     dst
        lda     dst+1
        adc     #$04
        sta     dst+1
        rts

        .segment "HIDATA"
bits:   .byte   $80, $40, $20, $10, $08, $04, $02, $01
rowx40: .byte   $00, $28, $50
.macro  PSTR    str                     ; a string, its length first
        .byte   .strlen(str), str
.endmacro
title:  PSTR    "TAKE 1"
whys:   .word   snotf, scant, sbig, sdamg, scmd
snotf:  PSTR    "FILE NOT FOUND:"
scant:  PSTR    "FILE CANNOT BE READ:"
sbig:   PSTR    "FILE TOO LARGE TO PLAY:"
sdamg:  PSTR    "NOT A VALID TAKE 1 FILE:"
scmd:   PSTR    "THE COMMAND IS NOT UNDERSTOOD."
skey:   PSTR    "PRESS A KEY TO RETURN."

fxtab:  .word   fx0, fx1, fx2, fx3, fx4, fx5, fx6, fx7, fx8, fx9
        .word   fx10, fx11, fx12, fx13, fx14, fx15, fx16, fx17
.macro  TONE c, p
        .byte   SND_TONE, c, p
.endmacro
.macro  SIL n
        .byte   SND_SIL, <(n), >(n)
.endmacro
.macro  ROUGH c
        .byte   SND_ROUGH, c
.endmacro
fx0:    TONE 24, 8
        TONE 24, 6
        .byte   SND_END
fx1:    TONE 10, 11
        TONE 19, 15
        TONE 5, 23
        .byte   SND_END
fx2:    TONE 3, 21
        SIL 3457
        TONE 3, 24
        .byte   SND_END
fx3:    TONE 56, 112
        TONE 3, 21
        .byte   SND_END
fx4:    TONE 44, 136
        TONE 32, 168
        TONE 3, 21
        .byte   SND_END
fx5:    TONE 10, 10
        TONE 19, 14
        .byte   SND_BURST, SND_BURST
        SIL 1
        .byte   SND_BURST
        SIL 257
        ROUGH 6
        SIL 1
        ROUGH 5
        SIL 769
        ROUGH 4
        .byte   SND_END
fx6:    TONE 10, 11
        TONE 20, 15
        .byte   SND_BURST, SND_BURST, SND_BURST
        SIL 64
        ROUGH 10
        SIL 127
        ROUGH 9
        SIL 129
        ROUGH 8
        SIL 641
        ROUGH 7
        SIL 1665
        ROUGH 6
        SIL 129
        ROUGH 5
        SIL 1665
        ROUGH 3
        .byte   SND_END
fx7:    TONE 96, 32
        TONE 18, 33
        TONE 16, 36
        TONE 10, 41
        TONE 3, 160
        TONE 3, 208
        .byte   SND_END
fx8:    .repeat 10, i
        TONE 16, 192 - 16 * i - (i / 9) * 16
        .endrepeat
        .byte   SND_END
fx9:    .repeat 11, i
        TONE 16, 32 + 16 * i
        .endrepeat
        .byte   SND_END
fx10:    TONE 36, 168
        .byte   SND_END
fx11:    TONE 42, 152
        .byte   SND_END
fx12:    TONE 48, 136
        .byte   SND_END
fx13:    TONE 54, 128
        .byte   SND_END
fx14:    TONE 60, 112
        .byte   SND_END
fx15:    TONE 66, 100
        .byte   SND_END
fx16:    TONE 72, 90
        .byte   SND_END
fx17:    TONE 78, 84
        .byte   SND_END

; The way back, run from page 3: A2FILE.SYSTEM from the prefix, read to
; $2000 (up to $BB00, the I/O buffer: this program is over by then) with
; OPEN, READ and CLOSE; a failure goes to ProDOS's QUIT.
thunk_src:
        .org    $0300
thunk:  jsr     MLI             ; OPEN
        .byte   $C8
        .word   t_open
        bcs     t_quit
        lda     t_ref
        sta     t_rdref
        sta     t_clref
        jsr     MLI             ; READ, up to $9B00 bytes
        .byte   $CA
        .word   t_read
        bcs     t_close
        lda     t_got+1         ; the whole file: less than asked
        cmp     #$9B
        bcs     t_close
        ora     t_got
        beq     t_close
        jsr     MLI             ; CLOSE
        .byte   $CC
        .word   t_closep
        bcs     t_quit
        bit     ROMIN
        jmp     $2000
t_close:
        jsr     MLI
        .byte   $CC
        .word   t_closep
t_quit: jsr     MLI             ; QUIT
        .byte   $65
        .word   t_quitp
t_open: .byte   3
        .word   t_name
        .word   $BB00
t_ref:  .byte   0
t_read: .byte   4
t_rdref:
        .byte   0
        .word   $2000
        .word   $9B00
t_got:  .word   0
t_closep:
        .byte   1
t_clref:
        .byte   0
t_quitp:
        .byte   4, 0
        .word   0
        .byte   0
        .word   0
t_name: .byte   13, "A2FILE.SYSTEM"
thunk_end:
        .reloc
thunk_len = thunk_end - thunk
        .assert thunk_len <= $D0, error, "the return thunk overflows page 3"
