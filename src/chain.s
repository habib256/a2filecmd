; chain.s -- launch a ProDOS program whatever its size.
;
;   extern unsigned int chain_addr;         load address ($2000 for a SYS)
;   void __fastcall__ chain_load(const char* path);
;
; The calling program is overwritten by what it loads: the work is done
; from a thunk copied to page $0300 (free under ProDOS, outside any
; program), which opens the file, reads it whole to chain_addr, closes
; it, switches the ROM back in for reading and jumps to it. A failure
; returns to ProDOS (QUIT, Bitsy Bye). Shared by A2FC (keys X and F) and
; by FORMAT.SYSTEM (return to A2FC).
;
;   void __fastcall__ chain_command(const char* name);
;
; An optional command for the loaded program, to be called BEFORE
; chain_load. This is the door BASIC.SYSTEM opens to its launchers, Bitsy
; Bye included: at startup it looks at $2006 for a name preceded by its
; length, and if there is one executes it as the command "-NAME" -- which
; runs an Applesoft program. So the thunk stores the name at
; chain_addr+6 just before jumping. Without a call, the first byte stays
; zero and nothing is written. 46 characters at most: a full path
; "/VOL/DIR/NAME" almost always fits (see run_selected).

        .export _chain_load, _chain_addr, _chain_command
        .import donelib
        .importzp ptr1

        .segment "BSS"
_chain_addr: .res 2

        .segment "RODATA"
stub_src:
        .org $0300
stub:   jsr $BF00               ; OPEN
        .byte $C8
        .word open_p
        bcs fail
        lda ref_num
        sta rd_ref
        sta cl_ref
        jsr $BF00               ; READ
        .byte $CA
        .word read_p
        bcs fail
        jsr $BF00               ; CLOSE
        .byte $CC
        .word close_p
        ldy cmd                 ; a command to pass?
        beq run
        clc                     ; yes: at chain_addr+6, length included
        lda rd_addr
        adc #6
        sta put+1
        lda rd_addr+1
        adc #0
        sta put+2
:       lda cmd,y
put:    sta $FFFF,y
        dey
        bpl :-
run:    bit $C082
        jmp (rd_addr)
fail:   jsr $BF00               ; QUIT : Bitsy Bye
        .byte $65
        .word quit_p
open_p: .byte 3
        .word path
        .word $BB00             ; 1 KB ProDOS buffer, out of reach of a
                                ; program loaded between $0800 and $BAFF
ref_num:
        .byte 0
read_p: .byte 4
rd_ref: .byte 0
rd_addr:
        .word $2000             ; chain_addr
rd_len: .word $2000             ; $BF00 - chain_addr
        .word 0
close_p:
        .byte 1
cl_ref: .byte 0
quit_p: .byte 4, 0
        .word 0
        .byte 0
        .word 0
path:   .res 64
cmd:    .res 47                 ; length then name (46 at most: what page 3
                                ; leaves), zero = no command
stub_end:
        .reloc
stub_len = stub_end - stub
; The thunk lives at $0300-$03CF: beyond that begin the vectors (BRK, RESET,
; DOS entry) that ProDOS and the monitor expect to find intact.
        .assert stub_len <= $D0, error, "the chain.s thunk overflows page 3"
cmd_src = stub_src + (cmd - stub)

        .segment "CODE"
_chain_load:
        sta ptr1
        stx ptr1+1
        ; The cc65 destructors first: doneirq gives back to ProDOS the
        ; interrupt entry taken at startup (music_irq). Without this each
        ; launch kept one, with a vector into overwritten memory: on the
        ; third F/ESC round trip, a crash into the monitor. ProDOS only
        ; has four of them.
        jsr donelib
        ldy #0                  ; copy the thunk to $0300
:       lda stub_src,y
        sta $0300,y
        iny
        cpy #stub_len
        bne :-
        lda _chain_addr         ; the address, and the length up to $BF00
        sta rd_addr
        sec
        lda #$00
        sbc _chain_addr
        sta rd_len
        lda _chain_addr+1
        sta rd_addr+1
        lda #$BF
        sbc _chain_addr+1
        sta rd_len+1
        ldy #0                  ; the path, prefixed with its length
:       lda (ptr1),y
        beq :+
        sta path+1,y
        iny
        cpy #63
        bne :-
:       sty path
        jmp stub

; Stores the name in the SOURCE thunk (RODATA, so in RAM and writable):
; the next chain_load carries it along with the rest of the thunk.
_chain_command:
        sta ptr1
        stx ptr1+1
        ldy #0
:       lda (ptr1),y
        beq :+
        sta cmd_src+1,y
        iny
        cpy #46
        bne :-
:       sty cmd_src
        rts
