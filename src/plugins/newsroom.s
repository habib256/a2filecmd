; newsroom.s -- the Newsroom viewer: the checks, the drawing and the screen.
;
; A photo or a banner (docs/NEWSROOM-FORMAT.md) is a six-byte frame -- L,
; the bitmap's length on 16 bits, then y1, y2, x1, x2 -- the clip history,
; $FF, and the bitmap: (x2 - x1) div 7 + 1 bytes a row, y2 - y1 + 1 rows.
; The history may hold $FF bytes of its own, so the bitmap is found from
; the end: it is the last L bytes of the file, and the byte before them
; must be $FF. Every check is made before the page is touched; a read
; error is never taken for the end of the file (ferror).
;
; Main bank only: hi-res page 1, no auxiliary memory, no disk writes.
; Plain 6502 throughout: the 6502 edition assembles this file too.
;
; The entry point reaches the program through the service table the way
; cc65 code would: arguments pushed on the C stack, the last one in A/X.
; tools/test_newsroom.py runs all of it under sim65, on both processors.

        .macpack longbranch             ; jcs & co: a branch, or a jmp if far
        .export _plugin_entry, _hv_clear, _hv_show, _hv_row
        .import pushax, jmpvec, _ferror
        .import _nr_ofs                 ; newsroom.c: the table offsets
        .importzp ptr1, ptr2, tmp1

NRO_FULL    = _nr_ofs+0
NRO_NOTE    = _nr_ofs+1
NRO_RESELECT= _nr_ofs+2
NRO_SELECTED= _nr_ofs+3
NRO_FOPEN   = _nr_ofs+4
NRO_FREAD   = _nr_ofs+5
NRO_FCLOSE  = _nr_ofs+6
NRO_STRCPY  = _nr_ofs+7
NRO_MWAIT   = _nr_ofs+8
NRO_ETYPE   = _nr_ofs+9
NRO_ESIZE   = _nr_ofs+10

        .segment "BSS"
api:    .res    2
sel:    .res    2
in:     .res    2
bad:    .res    1
want:   .res    1
wb:     .res    1                       ; bytes a row, 1 to 37
h:      .res    1                       ; rows, 1 to 192
row:    .res    1
left:   .res    1
n:      .res    2                       ; wb * h
skip:   .res    2
buf:    .res    64

        .segment "CODE"

; void plugin_entry(const struct A2fcApi* api)
_plugin_entry:
        sta     api
        stx     api+1
        lda     #1
        sta     bad
        ldy     NRO_SELECTED
        jsr     field
        sta     sel
        stx     sel+1
        jsr     selp
        ldy     NRO_ETYPE
        lda     (ptr1),y
        cmp     #6                      ; BIN
        jne     note
        ldy     NRO_FULL
        jsr     field
        jsr     pushax
        lda     #<rb
        ldx     #>rb
        ldy     NRO_FOPEN
        jsr     call
        sta     in
        stx     in+1
        ora     in+1
        jeq     note                    ; nothing opened, nothing to close

        ; The frame: y1 <= y2 < y1 + 192 and x1 <= x2, so that a row is
        ; 37 bytes at most and the picture fits the page.
        lda     #6
        jsr     readn
        jcs     fin
        lda     buf+3
        sec
        sbc     buf+2
        jcc     fin
        cmp     #192
        jcs     fin
        sta     h
        inc     h
        lda     buf+5
        sec
        sbc     buf+4
        jcc     fin
        ldx     #1                      ; wb = (x2 - x1) div 7 + 1
div7:   cmp     #7
        bcc     div7e
        sbc     #7
        inx
        bne     div7                    ; always
div7e:  stx     wb
        lda     #0                      ; n = wb * h, which L must be
        sta     n
        sta     n+1
        ldx     h
mul:    lda     n
        clc
        adc     wb
        sta     n
        bcc     mul1
        inc     n+1
mul1:   dex
        bne     mul
        lda     n
        cmp     buf
        jne     fin
        lda     n+1
        cmp     buf+1
        jne     fin

        ; The size holds the frame, the history's count byte, the $FF and
        ; the bitmap, and is below 64 KB: skip = size - L - 6, at least 2.
        jsr     selp
        lda     NRO_ESIZE
        clc
        adc     #3
        tay
        lda     (ptr1),y
        dey
        ora     (ptr1),y
        jne     fin
        dey
        dey
        lda     (ptr1),y
        sec
        sbc     n
        sta     skip
        iny
        lda     (ptr1),y
        sbc     n+1
        sta     skip+1
        jcc     fin
        lda     skip
        sbc     #6                      ; carry set
        sta     skip
        lda     skip+1
        sbc     #0
        sta     skip+1
        jcc     fin                     ; below 6: not even the frame
        bne     skl
        lda     skip
        cmp     #2
        jcc     fin

        ; The history, 64 bytes at a time; the last byte read is the $FF.
skl:    lda     skip
        ldx     skip+1
        bne     s64
        cmp     #64
        bcc     take
s64:    lda     #64
take:   jsr     readn
        jcs     fin
        lda     skip
        sec
        sbc     want
        sta     skip
        bcs     sk2
        dec     skip+1
sk2:    ora     skip+1
        bne     skl
        ldx     want
        lda     buf-1,x
        cmp     #$FF
        jne     fin

        ; The rows, centered on the black page.
        jsr     _hv_clear
        lda     #192
        sec
        sbc     h
        lsr     a
        sta     row
        lda     #40
        sec
        sbc     wb
        lsr     a
        sta     left
rows:   lda     wb
        jsr     readn
        jcs     fin
        lda     row
        jsr     _hv_row
        clc
        adc     left
        sta     ptr2
        txa
        adc     #0
        sta     ptr2+1
        ldy     #0
copy:   lda     buf,y
        and     #$7F
        sta     (ptr2),y
        iny
        cpy     wb
        bne     copy
        inc     row
        dec     h
        bne     rows

        ; Nothing may follow: the directory's size is the file's.
        lda     #1
        jsr     readn
        jcc     fin
        dec     bad

; The end, good or bad: a read error or a failed close is a refusal too.
fin:    lda     in
        ldx     in+1
        jsr     _ferror
        stx     tmp1
        ora     tmp1
        beq     fin1
        sta     bad
fin1:   lda     in
        ldx     in+1
        ldy     NRO_FCLOSE
        jsr     call
        stx     tmp1
        ora     tmp1
        beq     fin2
        sta     bad
fin2:   lda     bad
        bne     fin3
        jsr     _hv_show
        ldy     NRO_MWAIT
        jsr     call
fin3:   ldy     NRO_RESELECT            ; strcpy(api->reselect, selected->name)
        jsr     field
        jsr     pushax
        lda     sel
        ldx     sel+1
        ldy     NRO_STRCPY
        jsr     call
        lda     bad
        beq     out
note:   ldy     NRO_NOTE                ; strcpy(api->note, m_bad)
        jsr     field
        jsr     pushax
        lda     #<m_bad
        ldx     #>m_bad
        ldy     NRO_STRCPY
        jmp     call

; ptr1 = the selected entry.
selp:   lda     sel
        sta     ptr1
        lda     sel+1
        sta     ptr1+1
out:    rts

; fread(buf, 1, A, in), the count in A (1 to 64); carry clear when exactly
; that many bytes came. Every read turns the resident's activity cell
; ($06F7, row 21) between / and \ (see spin.h).
readn:  sta     want
        lda     #$AF
        cmp     $06F7
        bne     spun
        lda     #$DC
spun:   sta     $06F7
        lda     #<buf
        ldx     #>buf
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     want
        ldx     #0
        jsr     pushax
        lda     in
        ldx     in+1
        ldy     NRO_FREAD
        jsr     call
        cpx     #0
        bne     short
        cmp     want
        bne     short
        clc
        rts
short:  sec
        rts

; The service at offset Y of the table, A/X its last argument.
call:   pha
        txa
        pha
        jsr     field
        sta     jmpvec+1
        stx     jmpvec+2
        pla
        tax
        pla
        jmp     jmpvec

; A/X = the word at offset Y of the table.
field:  lda     api
        sta     ptr1
        lda     api+1
        sta     ptr1+1
        lda     (ptr1),y
        pha
        iny
        lda     (ptr1),y
        tax
        pla
        rts

; The whole of page 1 black, with the main bank's routing.
_hv_clear:
        lda     #0
        sta     $C000                   ; 80STORE off
        sta     $C002                   ; RAMRD main
        sta     $C004                   ; RAMWRT main
        sta     $C054                   ; PAGE2 off
        sta     ptr1
        lda     #$20
        sta     ptr1+1
        ldy     #0
        lda     #0
clr:    sta     (ptr1),y
        iny
        bne     clr
        inc     ptr1+1
        ldx     ptr1+1
        cpx     #$40
        bne     clr
        rts

; A/X = the address of hi-res row A (0-191) on page 1.
_hv_row:
        pha
        and     #7
        asl     a
        asl     a
        ora     #$20
        sta     ptr1+1
        pla
        pha
        and     #$38
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        ora     ptr1+1
        sta     ptr1+1
        pla
        pha
        and     #8
        beq     even
        lda     #$80
even:   sta     ptr1
        pla
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        tax
        lda     thirds,x
        clc
        adc     ptr1
        ldx     ptr1+1
        rts

; Full-screen hi-res page 1, forty columns, colour killer as the firmware
; leaves it: the page is shown only once whole.
_hv_show:
        lda     #0
        sta     $C000
        sta     $C00D
        sta     $C05E
        sta     $C05F
        sta     $C05E
        sta     $C05F
        sta     $C00C
        sta     $C057
        sta     $C054
        sta     $C052
        sta     $C050
        rts

        .segment "RODATA"
thirds: .byte   0, 40, 80
rb:     .asciiz "rb"
m_bad:  .asciiz "Not a whole Newsroom picture, or I/O error."
