; Startup code for A2FILE.SYSTEM, the launcher (src/loader.c).
;
; Derived from cc65 V2.19 libsrc/apple2/crt0.s (Oliver Schmidt), trimmed for
; the launcher: no language-card image to relocate, and -- the point of this
; copy -- the C stack is ALWAYS placed at $BF00, never at BASIC's HIMEM.
;
; Why: when A2 File Cmd's "]" prompt is left with "-A2FILE.SYSTEM", the
; launcher is run from a resident BASIC.SYSTEM. The stock crt0 sees the
; ProDOS bit map say "BASIC.SYSTEM is here" and sets the C stack to BASIC's
; HIMEM (~$9600). But the launcher then reads A2FILE.CODE across $4000-$BE40,
; straight over $9600 -- clobbering its own stack mid-load, which hangs the
; machine right after the 80-column switch. A2FILE.CODE ends by $BE40 (A2FC
; keeps $BE40-$BF00 for its own stack), so $BF00 down is always clear of the
; bytes we load. We use it unconditionally.
;
; Oliver Schmidt, 2009-09-15

        .export         _exit, done, return
        .export         __STARTUP__ : absolute = 1      ; Mark as startup

        .import         initlib, donelib
        .import         zerobss
.ifndef CC65_MASTER
        .import         callmain
.endif

.ifdef CC65_MASTER
        ; cc65 master (la version 6502) : apple2/callmain.s y definit aussi
        ; _exit, que nous avons ici avec nos propres sorties. Ce callmain-ci
        ; le remplace -- main(void), pas d'arguments -- et la bibliotheque
        ; garde le sien.
        .export         callmain
        .import         _main, pushax
callmain:
        lda     #0
        tax
        jsr     pushax          ; argc = 0
        jsr     pushax          ; argv = NULL
        ldy     #4
        jmp     _main           ; son rts revient a l'appelant, sur _exit
.endif

        .include        "zeropage.inc"
        .include        "apple2.inc"

; ------------------------------------------------------------------------

        .segment        "STARTUP"

        ; ProDOS TechRefMan, chapter 5.2.1:
        ; "For maximum interrupt efficiency, a system program should not
        ;  use more than the upper 3/4 of the stack."
        ldx     #$FF
        txs                     ; Init stack pointer

        ; The machine check, in plain 6502 before anything from the
        ; apple2enh library runs (65C02 opcodes, the 80-column firmware):
        ; on a II+, an unenhanced IIe or a 64 KB machine the screen would
        ; just go blank, ProDOS alive underneath (a user saw exactly that,
        ; 2026-09-08). IIe or later ($FBB3 = $06), not the unenhanced IIe
        ; ($FBC0 = $EA : 6502, no MouseText), 128 KB and an 80-column card
        ; (MACHID $BF98, bits 5 and 1). Otherwise say so on the 40-column
        ; screen, wait for a key, and quit to ProDOS.
        lda     $FBB3
        cmp     #$06
        bne     unfit
.ifndef A2_6502
        lda     $FBC0
        cmp     #$EA
        beq     unfit
.endif
        lda     $BF98
        and     #$22
        cmp     #$22
        beq     fit
unfit:  jsr     $FC58           ; HOME
        ldx     #0
:       lda     unfit_msg,x
        beq     :+
        ora     #$80
        jsr     $FDED           ; COUT
        inx
        bne     :-
:       jsr     $FD0C           ; RDKEY
        jmp     quit
fit:
        jsr     init

        ; Clear the BSS data.
        jsr     zerobss

        ; Push the command-line arguments; and, call main().
        jsr     callmain

        ; Avoid a re-entrance of donelib. This is also the exit() entry.
_exit:  ldx     #<exit
        lda     #>exit
        jsr     reset           ; Setup RESET vector

        ; Switch in ROM, in case it wasn't already switched in by a RESET.
        bit     $C082

        ; Call the module destructors.
        jsr     donelib

        ; Restore the original RESET vector.
exit:   ldx     #$02
:       lda     rvsave,x
        sta     SOFTEV,x
        dex
        bpl     :-

        ; Copy back the zero-page stuff.
        ldx     #zpspace-1
:       lda     zpsave,x
        sta     sp,x
        dex
        bpl     :-

        ; ProDOS TechRefMan, chapter 5.2.1:
        ; "System programs should set the stack pointer to $FF at the
        ;  warm-start entry point."
        ldx     #$FF
        txs                     ; Re-init stack pointer

        ; We're done
        jmp     done

; ------------------------------------------------------------------------

        .segment        "ONCE"

        ; Save the zero-page locations that we need.
init:   ldx     #zpspace-1
:       lda     sp,x
        sta     zpsave,x
        dex
        bpl     :-

        ; Save the original RESET vector.
        ldx     #$02
:       lda     SOFTEV,x
        sta     rvsave,x
        dex
        bpl     :-

        ; Check for ProDOS.
        ldy     $BF00           ; MLI call entry point
        cpy     #$4C            ; Is MLI present? (JMP opcode)
        bne     basic

        ; The launcher takes over the whole machine on behalf of A2 File Cmd:
        ; the C stack is always $BF00 (see the file header), and we always
        ; quit to the ProDOS dispatcher, never back to BASIC.SYSTEM.
        lda     #<quit
        ldx     #>quit
        sta     done+1
        stx     done+2

        lda     #<$BF00
        ldx     #>$BF00
        bne     :+              ; Branch always

        ; No ProDOS at all (never, for a SYS program): fall back to HIMEM.
basic:  lda     HIMEM
        ldx     HIMEM+1

        ; Set up the C stack.
:       sta     sp
        stx     sp+1

        ; ProDOS TechRefMan, chapter 5.3.5:
        ; "Your system program should place in the RESET vector the
        ;  address of a routine that ... closes the files."
        ldx     #<_exit
        lda     #>_exit
        jsr     reset           ; Setup RESET vector

        ; Call the module constructors.
        jsr     initlib
        rts

; ------------------------------------------------------------------------

        .code

        ; Set up the RESET vector.
reset:  stx     SOFTEV
        sta     SOFTEV+1
        eor     #$A5
        sta     PWREDUP
return: rts

        ; Quit to the ProDOS dispatcher.
unfit_msg:
.ifdef A2_6502
        .byte   $0D, "A2 FILE CMD NEEDS AN APPLE IIE, IIC OR", $0D
        .byte   "IIGS WITH 128K AND AN 80-COLUMN CARD.", $0D, $0D
.else
        .byte   $0D, "A2 FILE CMD NEEDS AN ENHANCED APPLE IIE,", $0D
        .byte   "A IIC OR A IIGS, WITH 128K AND", $0D
        .byte   "AN 80-COLUMN CARD.", $0D, $0D
.endif
        .byte   "PRESS A KEY TO RETURN TO PRODOS.", $0D, 0

quit:   jsr     $BF00           ; MLI call entry point
        .byte   $65             ; Quit
        .word   q_param

; ------------------------------------------------------------------------

        .rodata

        ; MLI parameter list for quit
q_param:.byte   $04             ; param_count
        .byte   $00             ; quit_type
        .word   $0000           ; reserved
        .byte   $00             ; reserved
        .word   $0000           ; reserved

; ------------------------------------------------------------------------

        .data

        ; Final jump when we're done
done:   jmp     DOSWARM         ; Potentially patched at runtime

; ------------------------------------------------------------------------

        .segment        "INIT"

zpsave: .res    zpspace
rvsave: .res    3
