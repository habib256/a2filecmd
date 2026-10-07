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
        jsr findram
        bcc found
        lda #0                  ; no /RAM on line
        tax
        rts

; Carry clear and X = its DEVADR index, unit set, when a /RAM is on line.
findram:
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
        bne next
        clc
        rts
next:   dey
        bpl scan
        sec
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
; An NMOS 6502 (the 6502 edition) reads JMP (vec)'s high byte from the
; start of the same page when vec ends a page: the /RAM rebuild would jump
; anywhere. Code above this word grew with ram_empty; keep it off $xxFF.
.assert <vec <> $FF, lderror, "ram_format's JMP (vec) must not straddle a page (NMOS 6502)"
rbparm: .byte 3                 ; ram_empty's READ_BLOCK: the unit found,
unit:   .byte 0                 ; copy_buf, block 2
        .word _copy_buf
        .word 2

; unsigned char ram_empty(void);
;
; 1 when ProDOS's /RAM is on line and holds no file: its volume directory
; (block 2, read into copy_buf) is a volume header whose file count is 0.
; Anything else -- no /RAM found (the auxiliary bank may serve another
; driver), a read error, an unexpected header -- answers 0, and the user
; is asked before the auxiliary bank is used, as before. Writes copy_buf,
; which loading an overlay overwrites anyway.
        .export _ram_empty
        .import _copy_buf
_ram_empty:
        jsr findram
        bcs no
        jsr $BF00
        .byte $80               ; READ_BLOCK
        .word rbparm
        bcs no
        lda _copy_buf+4         ; storage type $F: a volume header
        cmp #$F0
        bcc no
        lda _copy_buf+$25       ; its file count
        ora _copy_buf+$26
        bne no
        lda #1
        .byte $2C               ; BIT abs: skips the lda #0
no:     lda #0
        ldx #0
        rts

; unsigned int __fastcall__ panel_hash(const struct Panel* pan);
;
; A panel's fingerprint, for its tags: they are bits by entry index, kept
; aside while a big overlay covers the entry tables (keep_tags, a2fc.c) and
; valid afterwards only if the same names are back at the same indexes. So
; the word folds the path and the entry count (bytes 0-64 of struct Panel)
; and the name and type of every entry (bytes 0-17 of its 29; add_entry
; pads a name with zeros): h = rol16(h), then high ^= b, then low =
; rol8(low + high) (eight bits, no carry). Another window of the same
; directory holds other names. Sizes and dates are left out: a file saved
; by the editor keeps its tag.
; The exclusive-or is what makes the fold non-linear. With rotation and
; addition alone, a byte's weight depended only on its distance modulo 16
; from the end: two entries 8 apart exchanged (18 bytes each, a rotation
; by 144 = 9 x 16), or "AB" turned into "CA" (2B + A = 2A + C), left the
; word unchanged, and a tag then marked another file (bug hunt 2,
; tools/test_keep_tags.py plays both cases and random permutations).
; Without the final rotation (bug hunt 3), two edits two bytes apart in one
; name, +4 then +1 ("PIC.00" become "PIG.10"), still cancelled out: 21
; collisions in the 90,531 two-byte edits of three names where 1.4 are
; expected. The rotation (3 bytes) leaves none in that set, nor in any
; two-byte edit within three positions, and each step stays a bijection
; of h for a given byte.
; The field offsets are those tools/test_abi_freeze.py freezes. A full
; table folds in about a tenth of a second.
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
        lda #0
        sta tmp2                ; h low
        sta tmp3                ; h high
        ldy #64                 ; count, then the path down to its first byte
        lda (ptr1),y
        sta tmp1                ; entries remaining
:       lda (ptr1),y
        jsr fold
        dey
        bpl :-
entry:  lda tmp1
        beq done
        dec tmp1
        ldy #17                 ; the type, then the name
:       lda (ptr2),y
        jsr fold
        dey
        bpl :-
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
fold:   tax                     ; X = the byte (free in both loops above)
        lda tmp3
        cmp #$80                ; C = bit 15
        rol tmp2                ; h = rol(h)
        rol tmp3
        txa
        eor tmp3                ; high ^= byte
        sta tmp3
        clc
        adc tmp2                ; low += high, no carry out
        cmp #$80                ; then low = rol8(low): C = bit 7
        rol a
        sta tmp2
        rts

; unsigned char paths_nested(void);
;
; Non-zero when one of `full` and `other_full` is the other or lies inside
; it: equal, or equal up to the end of one where the other goes on with a
; '/'. copy_one refuses such a directory copy both ways (a2fc.c).
        .export _paths_nested
        .import _full, _other_full
_paths_nested:
        ldy #$FF
pnext:  iny
        lda _full,y
        beq pend                ; `full` ends here
        cmp _other_full,y
        beq pnext
        ldx _other_full,y       ; they part: nested if other_full ends
        bne pno                 ; where full goes on with a '/'
pslash: cmp #'/'
        beq pyes
pno:    lda #0
        tax
        rts
pend:   lda _other_full,y       ; equal, or other_full goes on with a '/'
        bne pslash
pyes:   ldx #0
        lda #1
        rts

; void __fastcall__ keep_tags(unsigned char save);
;
; The tags of both panels, set aside in picked[] while an image, the help
; or the editor overwrites the entry tables (save = 1), then given back
; once the panels have been reread (save = 0) -- to a panel that shows the
; same names at the same indexes, and only to that one. A tag is a bit by
; index: after an overlay that added a file (MOVE, an extraction), changed
; the directory (GOTO, FIND) or stepped to another window of a large
; folder (Left/Right in a viewer), the old bits would mark other files,
; and D asks for tagged files by their number, not by their names. Such a
; panel comes back untagged: read_panel has emptied its tags. panel_hash
; is a 16-bit fingerprint: a changed panel passes for unchanged about once
; in 65,536 for an arbitrary change (tools/test_keep_tags.py measures the
; rate on random edits); it is a probability, not a proof, and a table
; that D reads should still be looked at. A caller whose tables are
; covered by its own overlay points the panel at the names its bits refer
; to first (the batch, at its snapshot). A save is taken once per media
; session (overlay_run): an album that steps to another window of a large
; folder and back must find the bits of the window they were set in, not
; an empty set re-saved under the other window's fingerprint.
        .export _keep_tags
        .import _panels, _picked
        .importzp ptr3, tmp4
PANEL_SIZE = 98                 ; sizeof(struct Panel): test_keep_tags.py checks all three
TAGS       = 76                 ; offsetof(struct Panel, tags)
TAG_BYTES  = 18                 ; sizeof panels[0].tags
        .segment "LOWBSS"
        .export tag_print       ; the benches read it
tag_print:      .res 4          ; low bytes of both panels, then high bytes
        .segment "CODE"
_keep_tags:
        sta tmp4                ; panel_hash leaves tmp4 and ptr3 alone
        ldx #1
kpanel: stx ptr3
        ldy pan_lo,x
        lda pan_hi,x
        tax
        tya
        jsr _panel_hash         ; ptr1 stays on the panel
        ldy ptr3
        pha
        lda tmp4
        beq kgive
        pla
        sta tag_print,y
        txa
        sta tag_print+2,y
        ldx kept_at,y
        ldy #TAGS
ksave:  lda (ptr1),y
        sta _picked,x
        inx
        iny
        cpy #TAGS+TAG_BYTES
        bne ksave
        beq knext               ; always taken
kgive:  pla
        cmp tag_print,y
        bne knext
        txa
        cmp tag_print+2,y
        bne knext
        ldx kept_at,y
        ldy #TAGS
kback:  lda _picked,x
        sta (ptr1),y
        inx
        iny
        cpy #TAGS+TAG_BYTES
        bne kback
knext:  ldx ptr3
        dex
        bpl kpanel
        rts
pan_lo:  .byte <_panels, <(_panels+PANEL_SIZE)
pan_hi:  .byte >_panels, >(_panels+PANEL_SIZE)
kept_at: .byte 0, TAG_BYTES

; unsigned char __fastcall__ dir_count_block(const unsigned char* entries);
;
; The thirteen 39-byte entries of a directory block (entries = the block
; + 4): how many are active (storage type, the high nibble of their first
; byte, not 0), or $FF when an active one has a zero name length. dir_next
; (a2fc.c) counts the blocks wholly before the window of a large directory
; this way instead of validating each name in C: 3,100 cycles an entry
; became about 1,800, the block read by ProDOS included
; (docs/PERFORMANCE-0.9.2.md, tools/test_dir_paging.py).
        .export _dir_count_block
_dir_count_block:
        sta ptr1
        stx ptr1+1
        lda #0
        sta tmp1                ; active entries
        ldx #13
dcount: ldy #0
        lda (ptr1),y
        cmp #$10
        bcc dnext               ; storage type 0: deleted
        and #$0F
        beq dbad                ; active, with no name
        inc tmp1
dnext:  lda ptr1
        clc
        adc #$27
        sta ptr1
        bcc :+
        inc ptr1+1
:       dex
        bne dcount
        lda tmp1
        rts                     ; X = 0
dbad:   lda #$FF
        ldx #0
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
