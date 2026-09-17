; fontview.s -- FONTVIEW: entry point, both font formats, the HGR page.
; Main bank only; no auxiliary memory or ProDOS RAM disk writes.
;
; fontview.c has the formats. The services are reached through the table
; as cc65 code would reach them, as in macpaint.s: arguments on the C
; stack, the last in A/X. Plain 6502 throughout.

        .export _plugin_entry
        .import pushax, jmpvec, _fv_ofs, _ferror
        .importzp ptr1, ptr2, ptr3
        .segment "CODE"

FO_FULL     = _fv_ofs+0
FO_BUF      = _fv_ofs+1
FO_NOTE     = _fv_ofs+2
FO_RESELECT = _fv_ofs+3
FO_SELECTED = _fv_ofs+4
FO_FOPEN    = _fv_ofs+5
FO_FREAD    = _fv_ofs+6
FO_FCLOSE   = _fv_ofs+7
FO_STRCPY   = _fv_ofs+8
FO_WAIT     = _fv_ofs+9
FO_TYPE     = _fv_ofs+10                ; within struct Entry
FO_SIZE     = _fv_ofs+11

; void plugin_entry(const struct A2fcApi* api)
_plugin_entry:
        sta     api
        stx     api+1
        ldy     FO_BUF
        jsr     field
        sta     buf
        stx     buf+1
        ldy     FO_SELECTED
        jsr     field
        sta     ent
        stx     ent+1
        sta     ptr1
        stx     ptr1+1
        ldy     FO_TYPE
        lda     (ptr1),y
        sta     ftype
        ldy     FO_SIZE                 ; the fsize: 16 bits, high byte $FF above
        lda     (ptr1),y
        sta     fsize
        iny
        lda     (ptr1),y
        sta     fsize+1
        iny
        lda     (ptr1),y
        iny
        ora     (ptr1),y
        beq     small
        lda     #$FF
        sta     fsize+1
small:  lda     #0
        sta     bad
        jsr     open
        bcc     head
        jmp     say_bad                 ; nothing opened, nothing to close
fail:   lda     #1                      ; within a branch of the checks
        sta     bad
        jmp     finish
goraw:  jmp     raw

; The header, read as MGTK's: cols, fn, fh, and whether it is one.
head:   lda     #3
        jsr     read_buf
        bcs     fail
        ldy     #0
        lda     (ptr3),y
        tax                             ; the flag
        ldy     #1
        lda     (ptr3),y
        clc
        adc     #1
        sta     fn                      ; last + 1, 0 when last was 255
        iny
        lda     (ptr3),y
        sta     fh
        lda     #1                      ; one column, or two when flag is $80
        cpx     #0
        beq     cols1
        cpx     #$80
        bne     notmg
        asl     a
cols1:  sta     cols
        lda     ftype
        cmp     #7
        bne     notmg
        lda     fn
        beq     notmg
        cmp     #129
        bcs     notmg
        lda     fh
        beq     notmg
        cmp     #23
        bcs     notmg
        lda     #1
        .byte   $2C                     ; BIT abs: skips the lda #0
notmg:  lda     #0
        sta     mgtk
        ; 768 or 1,024 bytes: a hi-res font, but for an MGTK font of
        ; exactly 768 bytes -- fn * (1 + fh * cols) = 765
        lda     fsize
        bne     mgtk_path
        lda     fsize+1
        cmp     #4
        beq     goraw
        cmp     #3
        bne     mgtk_path
        lda     mgtk
        beq     goraw
        lda     fh                      ; k = 1 + fh * cols
        ldx     cols
        dex
        beq     k1
        asl     a
k1:     clc
        adc     #1
        tax
        lda     #0
        sta     t
        sta     t+1
mul:    lda     t                       ; t = fn * k
        clc
        adc     fn
        sta     t
        bcc     mul2
        inc     t+1
mul2:   dex
        bne     mul
        lda     t
        cmp     #<765
        bne     raw
        lda     t+1
        cmp     #>765
        bne     raw

mgtk_path:
        lda     mgtk
        beq     fail2
        lda     fn                      ; the widths, at most cols * 7
        jsr     read_buf
        bcs     fail2
        lda     cols
        asl     a
        asl     a
        asl     a
        sec
        sbc     cols                    ; 7 * cols
        sta     t
        ldy     #0
width:  lda     (ptr3),y
        cmp     t
        beq     width2
        bcs     fail2
width2: iny
        cpy     fn
        bne     width
        jsr     hv_clear
        lda     #0
        sta     fr
rows:   lda     #0
        sta     fc
colsl:  lda     buf                     ; a plane at copy_buf + 128
        clc
        adc     #128
        tay
        lda     buf+1
        adc     #0
        tax
        tya
        ldy     fn
        jsr     read_at
        bcs     fail2
        jsr     font_draw
        inc     fc
        lda     fc
        cmp     cols
        bne     colsl
        inc     fr
        lda     fr
        cmp     fh
        bne     rows
        beq     finish

fail2:  jmp     fail

raw:    jsr     close                   ; back to the first byte
        jsr     open
        bcc     reopened
        jmp     say_bad
reopened:
        lda     fsize+1                  ; 96 or 128 glyphs
        asl     a
        asl     a
        asl     a
        asl     a
        asl     a
        sta     fn
        lda     #8
        sta     fh
        jsr     hv_clear
        lda     #0
        sta     g
glyph:  lda     #8
        jsr     read_buf
        bcs     fail2
        lda     #0
        sta     fr
grow:   lda     g                       ; row (g / 16) * 10 + r
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     t
        asl     a
        asl     a
        adc     t
        asl     a
        adc     fr
        jsr     hv_row
        sta     ptr1
        stx     ptr1+1
        ldy     fr
        lda     (ptr3),y
        pha
        lda     g                       ; byte 4 + (g % 16) * 2
        and     #15
        asl     a
        adc     #4
        tay
        pla
        sta     (ptr1),y
        inc     fr
        lda     fr
        cmp     #8
        bne     grow
        inc     g
        lda     g
        cmp     fn
        bne     glyph

; The end of the file must come now; then the page on the air.
finish: lda     #1
        jsr     read_buf
        bcs     eof
        inc     bad                     ; bytes after the font
eof:    lda     ffile
        ldx     ffile+1
        jsr     _ferror
        stx     t
        ora     t
        beq     noerr
        inc     bad
noerr:  jsr     close
        stx     t
        ora     t
        beq     closed
        inc     bad
closed: lda     bad
        bne     done
        jsr     hv_show
        ldy     FO_WAIT
        jsr     call
done:   lda     ent
        ldx     ent+1
        ldy     FO_RESELECT
        jsr     strcpy
        lda     bad
        beq     out
say_bad:
        lda     #<m_bad
        ldx     #>m_bad
        ldy     FO_NOTE
; strcpy(the table's pointer at Y, A/X)
strcpy: pha
        txa
        pha
        jsr     field
        jsr     pushax
        pla
        tax
        pla
        ldy     FO_STRCPY
        jmp     call
out:    rts

open:   ldy     FO_FULL
        jsr     field
        jsr     pushax
        lda     #<rb
        ldx     #>rb
        ldy     FO_FOPEN
        jsr     call
        sta     ffile
        stx     ffile+1
        ora     ffile+1
        beq     nofile
        clc
        rts
nofile: sec                             ; nothing opened
        rts

close:  lda     ffile
        ldx     ffile+1
        ldy     FO_FCLOSE
        jmp     call

; A bytes into copy_buf; ptr3 = copy_buf after. Carry set when fewer came.
read_buf:
        tay
        lda     buf
        ldx     buf+1
; Y bytes at A/X.
read_at:
        sty     want
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     want
        ldx     #0
        jsr     pushax
        lda     ffile
        ldx     ffile+1
        ldy     FO_FREAD
        jsr     call
        pha
        lda     buf
        sta     ptr3
        lda     buf+1
        sta     ptr3+1
        pla
        cmp     want                    ; the count is at most want: carry clear if short
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

hv_clear:
        lda     #0
        sta     $C000
        sta     $C002
        sta     $C004
        sta     $C054
        sta     ptr1
        lda     #$20
        sta     ptr1+1
        ldy     #0
        lda     #0
@byte:  sta     (ptr1),y
        iny
        bne     @byte
        inc     ptr1+1
        ldx     ptr1+1
        cpx     #$40
        bne     @byte
        rts

; hv_row: A = the screen row; A/X its address.
hv_row: pha
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
        beq     @even
        lda     #$80
@even:  sta     ptr1
        pla
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        tax
        lda     offsets,x
        clc
        adc     ptr1
        ldx     ptr1+1
        rts

hv_show:
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

; The plane at ptr3 + 128 of row fr, column fc, the widths at ptr3.
font_draw:
        lda     ptr3
        sta     ptr2
        lda     ptr3+1
        sta     ptr2+1
        lda     #0
        sta     fg
        lda     fr
        sta     fy
@char:  lda     fy
        jsr     hv_row
        sta     ptr1
        stx     ptr1+1
        ldy     fg
        lda     (ptr2),y
        ldx     fc
        beq     @width
        sec
        sbc     #7
        bcs     @width
        lda     #0
@width: cmp     #8
        bcc     @mask
        lda     #7
@mask:  tax
        lda     fg
        ora     #$80
        tay
        lda     (ptr2),y
        and     masks,x
        pha
        lda     fg
        and     #15
        asl     a
        clc
        adc     #4
        adc     fc
        tay
        pla
        sta     (ptr1),y
        inc     fg
        lda     fg
        cmp     fn
        beq     @done
        and     #15
        bne     @char
        lda     fy
        clc
        adc     fh
        adc     #2
        sta     fy
        jmp     @char
@done:  rts

        .segment "RODATA"
offsets: .byte  0, 40, 80
masks:  .byte   0, 1, 3, 7, 15, 31, 63, 127
rb:     .asciiz "rb"
m_bad:  .asciiz "Bad data/I/O"

        .segment "BSS"
api:    .res    2
buf:    .res    2
ent:    .res    2
ffile:      .res    2
fsize:   .res    2
t:      .res    2
ftype:  .res    1
bad:    .res    1
mgtk:   .res    1
cols:   .res    1
fn:     .res    1
fh:     .res    1
fr:     .res    1
fc:     .res    1
fg:     .res    1
fy:     .res    1
g:      .res    1
want:   .res    1
