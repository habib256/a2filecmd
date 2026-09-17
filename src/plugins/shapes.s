; shapes.s -- the SHAPES viewer: entry point, shape tracer and dot plotter.
;
; tools/shapes_ref.py is the reference: the vectors, the 7 x 4 cells of 40
; dots, the centring, the clipping, the dot a byte holds. Each shape is
; traced twice from the file -- once for the bounding box of its plotted
; dots, once to plot them -- through a 255-byte window, after a seek to its
; offset. Coordinates are bytes from 128, compared as unsigned.
;
; The services are reached through the table as cc65 code would reach
; them, as in macpaint.s: arguments on the C stack, the last in A/X.
; Plain 6502 throughout.

        .export _plugin_entry
        .import pushax, pusha, pusheax, jmpvec, _sh_ofs
        .importzp ptr1, ptr2, ptr3, sreg
        .segment "CODE"

SO_FULL     = _sh_ofs+0
SO_BUF      = _sh_ofs+1
SO_NOTE     = _sh_ofs+2
SO_RESELECT = _sh_ofs+3
SO_SELECTED = _sh_ofs+4
SO_FOPEN    = _sh_ofs+5
SO_FREAD    = _sh_ofs+6
SO_FSEEK    = _sh_ofs+7
SO_FCLOSE   = _sh_ofs+8
SO_STRCPY   = _sh_ofs+9
SO_CGETC    = _sh_ofs+10
SO_MEMSET   = _sh_ofs+11
SO_GOTOXY   = _sh_ofs+12
SO_CPUTS    = _sh_ofs+13
SO_CLRSCR   = _sh_ofs+14
SO_KEYS     = _sh_ofs+15
SO_SET      = _sh_ofs+16

; void plugin_entry(const struct A2fcApi* api)
_plugin_entry:
        sta     api
        stx     api+1
        ldy     SO_BUF
        jsr     field
        sta     buf
        stx     buf+1
        ldy     SO_SELECTED
        jsr     field
        sta     ent
        stx     ent+1
        ldy     SO_FULL
        jsr     field
        jsr     pushax
        lda     #<rb
        ldx     #>rb
        ldy     SO_FOPEN
        jsr     call
        sta     in
        stx     in+1
        ora     in+1
        bne     opened
        jmp     bad
opened: lda     #0                      ; the count, and room for its offsets
        tax
        jsr     seek
        bcs     badc
        jsr     getb
        bcs     badc
        sta     count
        tax
        beq     badc
        asl     a                       ; the offsets' last byte, 2n + 1, is there
        ora     #1
        tay
        lda     #0
        rol     a
        tax
        tya
        jsr     seek
        bcs     badc
        jsr     getb
        bcc     valid
badc:   jsr     close
        jmp     bad

valid:  ldy     SO_CLRSCR
        jsr     call
        sta     $C050                   ; graphics
        sta     $C053                   ; mixed: four text rows below
        sta     $C054                   ; page 1
        sta     $C057                   ; hi-res
        sta     $C05F                   ; double hi-res off
        lda     #1
        sta     first
page:   jsr     draw_page
        jsr     status
wait:   ldy     SO_CGETC
        jsr     call
        and     #$7F
        cmp     #27
        beq     quit
        cmp     #' '
        beq     next
        cmp     #10                     ; Down
        beq     next
        cmp     #11                     ; Up
        beq     prev
        ora     #$20
        cmp     #'b'
        bne     wait
prev:   lda     first
        cmp     #2
        bcc     wait
        sbc     #24
        sta     first
        jmp     page
next:   lda     first                   ; another page when first + 24 <= count
        clc
        adc     #24
        bcs     wait
        cmp     count
        beq     go
        bcs     wait
go:     sta     first
        jmp     page
quit:   jsr     close                   ; the core puts the text back
        lda     ent
        ldx     ent+1
        ldy     SO_RESELECT
        bne     strcpy                  ; always

bad:    lda     #<m_bad
        ldx     #>m_bad
        ldy     SO_NOTE
; strcpy(the table's pointer at Y, A/X)
strcpy: pha
        txa
        pha
        jsr     field
        jsr     pushax
        pla
        tax
        pla
        ldy     SO_STRCPY
        jmp     call

; The page: the screen cleared, shapes first to first + 23 drawn.
draw_page:
        lda     #$00
        ldx     #$20
        jsr     pushax
        lda     #0
        tax
        jsr     pushax
        lda     #$00
        ldx     #$20
        ldy     SO_MEMSET
        jsr     call
        lda     #0
        sta     cell
cloop:  lda     first
        clc
        adc     cell
        bcs     cdone
        sta     k
        lda     count
        cmp     k
        bcc     cdone
        jsr     draw_k
        inc     cell
        lda     cell
        cmp     #24
        bne     cloop
cdone:  rts

; Shape k in cell `cell`: its bounding box, then its dots.
draw_k: jsr     seek_k
        bcs     dret
        lda     #$FF
        sta     minx
        sta     miny
        lda     #0
        sta     maxx
        sta     maxy
        lda     #1                      ; the bounding box
        sta     mode
        jsr     trace
        bcs     dret
        lda     maxx                    ; no dot: the box is still upside down
        cmp     minx
        bcc     dret
        sec
        sbc     minx
        jsr     padding
        sta     padx
        lda     maxy
        sec
        sbc     miny
        jsr     padding
        sta     pady
        lda     cell                    ; the cell: column in A, row in X
        ldx     #0
div7:   cmp     #6
        bcc     cxy
        sbc     #6
        inx
        bne     div7
cxy:    jsr     times40
        sta     cellx
        txa
        jsr     times40
        sta     celly
        jsr     seek_k
        bcs     dret
        lda     #2                      ; the dots
        sta     mode
        jsr     trace
dret:   rts

; A = width - 1: the gap before the shape, (40 - width) / 2, or 0.
padding:
        cmp     #39
        bcs     nopad
        sta     t
        lda     #39
        sec
        sbc     t
        lsr     a
        rts
nopad:  lda     #0
        rts

; A times 40, A at most 6.
times40:
        asl     a
        asl     a
        asl     a
        sta     t
        asl     a
        asl     a
        adc     t
        rts

; The file at the offset of shape k. Carry set on a failure.
seek_k: lda     k
        asl     a
        sta     t
        lda     #0
        rol     a
        tax
        lda     t
        jsr     seek
        bcs     sret
        jsr     getb
        bcs     sret
        sta     t
        jsr     getb
        bcs     sret
        tax
        lda     t
        jmp     seek
sret:   rts

; One shape from the file position: carry clear at its zero byte, set when
; the file ends first. Each plotted vector goes to dot.
trace:  lda     #$80
        sta     xx
        sta     yy
tloop:  jsr     getb
        bcs     tret
        sta     vb
        tax
        bne     tvec
        clc
tret:   rts
tvec:   and     #7                      ; A
        jsr     vec
        lda     vb
        lsr     a
        lsr     a
        lsr     a
        beq     tloop                   ; B and C both zero: skipped
        and     #7                      ; B
        jsr     vec
        lda     vb
        asl     a
        rol     a
        rol     a
        and     #3                      ; C: bits 7-6, never a plot
        beq     tloop
        jsr     vec
        jmp     tloop

vec:    sta     vv
        and     #4
        beq     move
        jsr     dot
move:   lda     vv
        and     #3
        beq     up
        cmp     #2
        beq     down
        bcs     left
        inc     xx
        rts
up:     dec     yy
        rts
down:   inc     yy
        rts
left:   dec     xx
        rts

; The dot at xx, yy: mode 0 nothing, 1 the bounding box, 2 the screen.
dot:    lda     mode
        beq     dret2
        lsr     a
        bne     plot
        lda     xx
        cmp     minx
        bcs     b1
        sta     minx
b1:     cmp     maxx
        bcc     b2
        sta     maxx
b2:     lda     yy
        cmp     miny
        bcs     b3
        sta     miny
b3:     cmp     maxy
        bcc     dret2
        sta     maxy
dret2:  rts

plot:   lda     yy                      ; the row, or nothing past the cell
        sec
        sbc     miny
        clc
        adc     pady
        bcs     dret2
        cmp     #40
        bcs     dret2
        adc     celly
        jsr     setrow
        lda     xx
        sec
        sbc     minx
        clc
        adc     padx
        bcs     dret2
        cmp     #40
        bcs     dret2
        adc     cellx                   ; carry clear: the screen x, 0 to 239
        ldy     #0                      ; x / 7 in Y, x % 7 in X
div:    cmp     #7
        bcc     divd
        sbc     #7
        iny
        bne     div
divd:   tax
        lda     (ptr2),y
        ora     bits,x
        sta     (ptr2),y
        rts

; setrow: A = the screen row; ptr2 its address. A hi-res row is $2000 +
; (y AND 7) * $400 + ((y / 8) MOD 8) * $80 + (y / 64) * $28.
setrow: pha
        lsr     a
        lsr     a
        lsr     a
        tay                             ; y / 8
        and     #7
        lsr     a                       ; carry: an odd text row, + $80
        sta     t
        lda     #0
        bcc     even
        lda     #$80
even:   sta     ptr2
        tya
        lsr     a
        lsr     a
        lsr     a
        tay                             ; y / 64
        beq     third
tl:     lda     ptr2
        clc
        adc     #$28
        sta     ptr2
        dey
        bne     tl
third:  pla
        and     #7
        asl     a
        asl     a
        clc
        adc     t
        adc     #$20
        sta     ptr2+1
        rts

; The status row: "SHAPES FFF-LLL/NNN", the numbers 3 wide.
status: lda     #0
        jsr     pusha                   ; gotoxy(0, 21)
        lda     #21
        ldy     SO_GOTOXY
        jsr     call
        lda     #<s_shapes
        ldx     #>s_shapes
        ldy     SO_CPUTS
        jsr     call
        ldx     #0
        lda     first
        jsr     num
        lda     #'-'
        sta     st,x
        inx
        lda     first                   ; the last: first + 23, or the count
        clc
        adc     #23
        bcs     slast
        cmp     count
        bcc     slast2
slast:  lda     count
slast2: jsr     num
        lda     #'/'
        sta     st,x
        inx
        lda     count
        jsr     num
        lda     #0
        sta     st,x
        lda     #<st
        ldx     #>st
        ldy     SO_CPUTS
        jmp     call

; A in decimal at st,x, 3 wide, leading zeros as spaces; X moves on.
num:    ldy     #' '
        sty     lead                    ; a space until the first digit
        ldy     #100
        jsr     digit
        ldy     #10
        jsr     digit
        ora     #'0'
        sta     st,x
        inx
        rts
digit:  sty     t                       ; A div t as a character, A mod t left
        ldy     #'0'-1
dig:    iny
        sec
        sbc     t
        bcs     dig
        adc     t
        cpy     #'0'
        bne     nz
        ldy     lead                    ; a zero: a space before the first digit
        bne     put                     ; always
nz:     pha
        lda     #'0'                    ; from here on zeros show
        sta     lead
        pla
put:    pha
        tya
        sta     st,x
        pla
        inx
        rts

; fseek(in, A/X, SEEK_SET); the window emptied. Carry set on a failure.
seek:   pha
        txa
        pha
        lda     #0
        sta     at
        sta     have
        sta     sreg
        sta     sreg+1
        lda     in
        ldx     in+1
        jsr     pushax
        pla
        tax
        pla
        jsr     pusheax
        lda     SO_SET
        ldx     #0
        ldy     SO_FSEEK
        jsr     call
        stx     t
        ora     t
        cmp     #1
        rts

; The next byte of the file, carry clear; carry set at the end.
getb:   ldy     at
        cpy     have
        bne     fetch
        lda     buf
        ldx     buf+1
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     #255
        ldx     #0
        jsr     pushax
        lda     in
        ldx     in+1
        ldy     SO_FREAD
        jsr     call
        sta     have
        ldy     #0
        sty     at
        tax
        beq     geof
        lda     buf                     ; after the call: it may use the zero page
        sta     ptr3
        lda     buf+1
        sta     ptr3+1
fetch:  lda     (ptr3),y
        inc     at
        clc
        rts
geof:   sec
        rts

close:  lda     in
        ldx     in+1
        ldy     SO_FCLOSE
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

        .segment "RODATA"
rb:     .asciiz "rb"
bits:   .byte   1, 2, 4, 8, 16, 32, 64
s_shapes: .asciiz "SHAPES "
m_bad:  .asciiz "Not a shape table."

        .segment "BSS"
api:    .res    2
buf:    .res    2
ent:    .res    2
in:     .res    2
t:      .res    1
count:  .res    1
first:  .res    1
k:      .res    1
cell:   .res    1
mode:   .res    1
at:     .res    1
have:   .res    1
xx:     .res    1
yy:     .res    1
vb:     .res    1
vv:     .res    1
minx:   .res    1
maxx:   .res    1
miny:   .res    1
maxy:   .res    1
padx:   .res    1
pady:   .res    1
cellx:  .res    1
celly:  .res    1
lead:   .res    1
st:     .res    12
