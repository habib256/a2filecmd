; Derived from cc65 V2.19 libsrc/apple2/crt0.s (Oliver Schmidt).
; Source: https://github.com/cc65/cc65/blob/V2.19/libsrc/apple2/crt0.s
; Local change: loader stages LC at __LCIMAGE_START__ before transient LOWBSS use.
;
; Oliver Schmidt, 2009-09-15
;
; Startup code for cc65 (Apple2 version)
;

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
        .import         __LCIMAGE_START__                        ; Linker generated
        .import         __LC_START__, __LC_LAST__       ; Linker generated

        .include        "zeropage.inc"
        .include        "apple2.inc"

; ------------------------------------------------------------------------

        .segment        "STARTUP"

        ; ProDOS TechRefMan, chapter 5.2.1:
        ; "For maximum interrupt efficiency, a system program should not
        ;  use more than the upper 3/4 of the stack."
        ldx     #$FF
        txs                     ; Init stack pointer

        ; Save space by putting some of the start-up code in the ONCE segment,
        ; which can be re-used by the BSS segment, the heap and the C stack.
        jsr     init
.ifdef A2FC_TRACE
        lda #1
        sta $03A1
.endif

        ; Clear the BSS data.
        jsr     zerobss
.ifdef A2FC_TRACE
        lda #2
        sta $03A1
.endif

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

        ; A2 File Cmd takes over the whole machine: A2FILE.SYSTEM loads it up
        ; to $BEFF, clobbering BASIC.SYSTEM if one was resident. So we ignore
        ; the ProDOS system bit map -- when relaunched via "-A2FILE.SYSTEM"
        ; from BASIC.SYSTEM's "]" prompt, BASIC.SYSTEM is still resident and
        ; its bit map would send us down the "basic" path, setting the C stack
        ; to BASIC's HIMEM (~$9600) -- right inside our own code, which the
        ; stack then corrupts as it grows. We always use the standalone stack
        ; top ($BF00, just under the ProDOS global page) and always quit to
        ; the ProDOS dispatcher, never back to a BASIC.SYSTEM we have erased.
        lda     #<quit
        ldx     #>quit
        sta     done+1
        stx     done+2

        lda     #<$BF00
        ldx     #>$BF00
        bne     :+              ; Branch always

        ; Get the highest available mem addr from the BASIC interpreter.
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

        ; The ROM first: a SYSTEM program launched by ProDOS starts with the
        ; ROM in, and the library's constructors count on it (the apple2
        ; target's initostype does jsr $FE1F, no bank switch). But A2FC is
        ; launched by its own loader, whose videomode() leaves language-card
        ; bank 2 mapped for reading -- and $FE1F then lands in ProDOS.
        bit     $C082
        ; Call the module constructors.
        jsr     initlib
.ifdef A2FC_TRACE
        lda #3
        sta $03A1
.endif

        ; Switch in LC bank 2 for W/O.
        bit     $C081
        bit     $C081

        ; Set the source start address.
        ; Aka __LCIMAGE_START__ iff segment LC exists.
        lda     #<__LCIMAGE_START__
        ldy     #>__LCIMAGE_START__
        sta     $9B
        sty     $9C

        ; Set the source last address.
        ; Aka __LCIMAGE_START__ + __LC_SIZE__ iff segment LC exists.
        lda     #<(__LCIMAGE_START__ + (__LC_LAST__ - __LC_START__))
        ldy     #>(__LCIMAGE_START__ + (__LC_LAST__ - __LC_START__))
        sta     $96
        sty     $97

        ; Set the destination last address.
        ; Aka __LC_RUN__ + __LC_SIZE__ iff segment LC exists.
        lda     #<__LC_LAST__
        ldy     #>__LC_LAST__
        sta     $94
        sty     $95

        ; Call into Applesoft Block Transfer Up -- which handles zero-
        ; sized blocks well -- to move the content of the LC memory area.
        jsr     $D39A           ; BLTU2

        ; Switch in LC bank 2 for R/O and return.
        bit     $C080
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
