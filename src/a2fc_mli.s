; a2fc_mli.s -- two MLI calls for A2FC.
;
; unsigned char __fastcall__ mli_gfi(void* params);   GET_FILE_INFO ($C4)
; unsigned char __fastcall__ mli_sfi(void* params);   SET_FILE_INFO ($C3)
;   params: the parameter block prepared in C (param_count first, then a
;           pointer to a ProDOS name prefixed with its length); returns
;           the ProDOS error code, 0 if all is well.
;
; cc65 accepts neither .byte nor .word in inline asm, and the block's
; address follows the call: so the routine lives in DATA, where it can
; modify itself.
; unsigned char __fastcall__ mli_call(unsigned char cmd, void* params);
;   Any MLI call, for the overlays (READ_BLOCK, WRITE_BLOCK, ON_LINE...):
;   the command is the first argument, the block the second.
        .export _mli_gfi, _mli_sfi, _mli_call
        .import popa
; cc65's _oserror: report_error reads it. cc65 master (the 6502 version)
; names it ___oserror, with one more underscore for the C identifiers that
; start with one.
.ifdef CC65_MASTER
        .import ___oserror
oserror = ___oserror
.else
        .import __oserror
oserror = __oserror
.endif
        .segment "DATA"
_mli_call:
        sta     block
        stx     block+1
        jsr     popa
        sta     command
        bne     go              ; always taken: no command is 0
_mli_sfi:
        ldy     #$C3
        bne     call            ; always taken
_mli_gfi:
        ldy     #$C4
call:   sty     command
        sta     block
        stx     block+1
go:     jsr     $BF00
command:
        .byte   $C4
block:  .word   $0000
        ; The ProDOS code returned by the MLI (0 if all is well) also goes
        ; into _oserror: only cc65's stdio kept it up to date, and
        ; report_error otherwise displayed the reason for the PREVIOUS
        ; failure -- in plain words, hence confidently, since prodos_error
        ; translates the codes.
        sta     oserror
        ldx     #0
        rts

; unsigned char ram_format(void);
;
; Looks for the unit whose driver is ProDOS's /RAM -- recognised by its
; $FF00 address in DEVADR ($BF10), as in format.c -- and asks it for
; FORMAT ($03). The driver lives above $D000: the language card switches
; to bank 1, read and write, around the call, as format_mli.s does for
; the formatter -- but the return is to A2FC's bank 2, not to the ROM.
; Returns 1 if a /RAM was rebuilt from scratch, 0 otherwise (no /RAM on
; line, or the driver refused).
;
; The buffer announced is $2000, the graphics page: this call only takes
; place on return from a picture, where it is already lost and where the
; panels are about to be reread. FORMAT does not use it, but the driver
; reads the six bytes.
        .export _ram_format
_ram_format:
        ldy $BF31               ; DEVCNT: the number of units, minus one
scan:   lda $BF32,y             ; DEVLST
        and #$F0
        sta unit
        lsr a
        lsr a
        lsr a                   ; (unit >> 4) x 2: the index into DEVADR
        tax
        lda $BF10,x
        bne next
        lda $BF11,x
        cmp #$FF                ; $FF00: the /RAM driver
        beq found
next:   dey
        bpl scan
        lda #0                  ; no /RAM on line
        tax
        rts
found:  lda $BF10,x
        sta vec
        lda $BF11,x
        sta vec+1
        lda #3
        sta $42                 ; FORMAT command
        lda unit
        sta $43
        lda #$00
        sta $44
        sta $46
        sta $47                 ; block 0
        lda #$20
        sta $45                 ; buffer $2000
        php                     ; the driver runs with the language card
        sei                     ; switched: no interrupt during that time
        lda $C08B               ; bank 1, read and write
        lda $C08B
        jsr indirect
        lda #0                  ; the carry tells the error; make it the
        bcs :+                  ; result BEFORE plp restores the state
        lda #1
        ; We restore the state crt0 leaves -- bank 2 readable, write-
        ; protected -- and not the ROM ($C082, which is what the formatter
        ; does, having nothing in the language card). A2FC, for its part,
        ; runs its viewers, its prompts and its configuration from $D400.
        ; In practice the first MLI call that follows already puts bank 2
        ; back (measured: confirm() still answers if the ROM is restored),
        ; but that depends on the order of the calls, not on this
        ; routine's contract.
:       bit $C080
        plp
        ldx #0
        rts
indirect:
        jmp (vec)
vec:    .word 0
unit:   .byte 0

; unsigned int __fastcall__ panel_hash(const struct Panel* pan);
;
; A panel's fingerprint: every byte of its entry table (count entries of
; 29 bytes, at address e), folded into a word by rotation and addition,
; plus the number of entries, the window (first, more) and the first
; character of the path. The field offsets are those that a2fc.c checks
; against the fields of struct Panel. In C, cc65 made 325 bytes of it;
; here about a hundred. A full table (4,060 bytes) folds in a tenth of a
; second, far less than a panel takes to redraw.
        .export _panel_hash
        .importzp ptr1, ptr2, tmp1, tmp2, tmp3
        .segment "CODE"
_panel_hash:
        sta ptr1
        stx ptr1+1
        ldy #74                 ; e
        lda (ptr1),y
        sta ptr2
        iny
        lda (ptr1),y
        sta ptr2+1
        ldy #69                 ; first, high byte
        lda (ptr1),y
        sta tmp3                ; h high
        dey
        lda (ptr1),y            ; first, low byte
        ldy #64                 ; count
        clc
        adc (ptr1),y
        bcc :+
        inc tmp3
:       lda (ptr1),y
        sta tmp1                ; entries remaining
        ldy #67                 ; more
        clc
        adc (ptr1),y
        bcc :+
        inc tmp3
:       ldy #0                  ; path[0]
        clc
        adc (ptr1),y
        bcc :+
        inc tmp3
:       sta tmp2                ; h low
entry:  lda tmp1
        beq done
        dec tmp1
        ldy #0
byte:   lda tmp3
        cmp #$80                ; C = bit 15
        rol tmp2
        rol tmp3                ; h rotates by one bit
        lda (ptr2),y
        clc
        adc tmp2
        sta tmp2
        bcc :+
        inc tmp3
:       iny
        cpy #29
        bne byte
        clc
        lda ptr2
        adc #29
        sta ptr2
        bcc entry
        inc ptr2+1
        bne entry               ; always taken
done:   lda tmp2
        ldx tmp3
        rts

; void __fastcall__ aux_copy(unsigned int main_addr, unsigned int aux_addr,
;                            unsigned char to_aux);
;
; 512 bytes between the main bank and the auxiliary bank, through the //e
; firmware's AUXMOVE ($C311): A1/A2 the source, A4 the destination,
; C = 1 from main to auxiliary. Interrupts off for the duration of the
; copy: AUXMOVE switches RAMRD and RAMWRT, and the Mockingboard player
; does not expect to be woken up in the other bank.
        .export _aux_copy, _aux_hgr_to_aux
        .import popax
        .segment "CODE"
; void aux_hgr_to_aux(void): the whole HGR page 1, $2000-$3FFF, from main
; to auxiliary, in a single AUXMOVE (the AUX plane of a DHGR picture,
; decoded or read in main). Same interrupt guard.
_aux_hgr_to_aux:
        lda #$00
        sta $3C                 ; A1 = $2000
        sta $42                 ; A4 = $2000
        lda #$20
        sta $3D
        sta $43
        lda #$FF                ; A2 = $3FFF
        sta $3E
        lda #$3F
        sta $3F
        php
        sei
        sec                     ; main to auxiliary
        jsr $C311
        plp
        rts

_aux_copy:
        sta dir
        jsr popax
        sta aux
        stx aux+1
        jsr popax               ; the main address
        ldy dir
        beq from_aux
        sta $3C                 ; source: main
        stx $3D
        ldy aux
        sty $42                 ; destination: auxiliary
        ldy aux+1
        sty $43
        bne move                ; always taken: AUX >= $2000
from_aux:
        sta $42                 ; destination: main
        stx $43
        lda aux
        ldx aux+1
        sta $3C                 ; source: auxiliary
        stx $3D
move:   clc
        adc #$FF                ; A2 = A1 + 511
        sta $3E
        txa
        adc #$01
        sta $3F
        php
        sei
        lda dir
        cmp #1                  ; C = 1: main to auxiliary
        jsr $C311
        plp
        rts
dir:    .byte 0
aux:    .word 0
