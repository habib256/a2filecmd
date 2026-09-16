; edit.s -- a one-buffer text editor in the working area, and a name field.
;
; The buffer is scratch, 8191 bytes plus a trailing NUL. Saving goes
; through the exclusive-create engine: a new name only.

        .include "mini.inc"

        .export ask_name, edit_text, ask_kind
        .export _ask_name, _edit_text, _ask_kind
        .import name_buf

        .import present, at, put, inline_text, clear, zone
        .import keys_bar_inline
        .import key
        .import scratch
        .import edit_len

        .segment "BSS"
ask_kind:       .res 1          ; 0 new text, 1 rename, 2 the name exists: another
_ask_kind       = ask_kind
nm_len:         .res 1
ed_len          = edit_len
ed_cur:         .res 2
ed_done:        .res 1
ed_k:           .res 1
ed_off:         .res 2
ed_left:        .res 2
ed_lines:       .res 1
ed_high:        .res 1          ; $80 or 0: bit 7 of every typed character

.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"
.endif

; =====================================================================
ask_name:
_ask_name:
        ldx     #NAME_LEN-1
        lda     #' '
@pad:
        sta     name_buf,x
        dex
        bpl     @pad
        lda     #0
        sta     nm_len
@draw:
        ldy     #21
        ldx     #0
        lda     #40
        jsr     zone
        lda     ask_kind
        bne     @ren
        PRINT   "NEW: "
        jmp     @field
@ren:
        cmp     #1
        bne     @taken
        PRINT   "RENAME: "
        jmp     @field
@taken:
        PRINT   "EXISTS: "       ; 8 columns: the 30-character field must fit the row
@field:
        ldx     #0
@ch:
        stx     t1              ; put clobbers X (it becomes the row)
        lda     name_buf,x
        jsr     put
        ldx     t1
        inx
        cpx     #NAME_LEN
        bcc     @ch
        KEYBAR  23, "RET Accept,ESC Cancel"
        jsr     key
        cmp     #27
        beq     @no
        cmp     #13
        beq     @try
        cmp     #8
        beq     @bk
        cmp     #127
        beq     @bk
        jsr     name_char
        jcc     @draw
        lda     nm_len
        cmp     #NAME_LEN
        jcs     @draw
        tax
        lda     t0
        sta     name_buf,x
        inc     nm_len
        jmp     @draw
@bk:
        lda     nm_len
        jeq     @draw
        dec     nm_len
        ldx     nm_len
        lda     #' '
        sta     name_buf,x
        jmp     @draw
@try:
        lda     nm_len
        jeq     @draw
        lda     name_buf
        cmp     #'A'
        jcc     @draw
        cmp     #'Z'+1
        jcs     @draw
        sec
        rts
@no:
        clc
        rts

name_char:
        cmp     #'a'
        bcc     @up
        cmp     #'z'+1
        bcs     @up
        sec
        sbc     #32
@up:
        sta     t0
        cmp     #'A'
        bcc     @d
        cmp     #'Z'+1
        bcc     @yes
@d:
        cmp     #'0'
        bcc     @dot
        cmp     #'9'+1
        bcc     @yes
@dot:
        cmp     #'.'
        bne     @no
@yes:
        sec
        rts
@no:
        clc
        rts

; =====================================================================
edit_text:
_edit_text:
        lda     #0
        sta     ed_cur
        sta     ed_cur+1
        jsr     cap_len
        lda     scratch         ; the file's own convention: DOS writes
        ldx     ed_len          ; text with bit 7 set, CR as $8D. Typed
        bne     @have           ; characters follow the first byte, so a
        ldx     ed_len+1        ; file never mixes $0D and $8D; a new
        bne     @have           ; file follows DOS
        lda     #$80
@have:
        and     #$80
        sta     ed_high
@loop:
        jsr     draw_edit
        jsr     key
        sta     ed_k
        cmp     #27
        bne     @ne
        jsr     ask_leave
        bcc     @loop
        lda     ed_done
        cmp     #1
        beq     @sv
        clc
        rts
@ne:
        lda     ed_k
        cmp     #19
        bne     @ns
@sv:
        lda     ed_len
        ora     ed_len+1
        beq     @loop
        jsr     cap_len
        sec
        rts
@ns:
        lda     ed_k
        cmp     #8
        beq     @bk
        cmp     #127
        beq     @bk
        cmp     #21
        beq     @rt
        cmp     #10
        beq     @dn
        cmp     #11
        beq     @up
        cmp     #13
        beq     @put
        cmp     #32
        bcc     @loop
        cmp     #127
        bcs     @loop
@put:
        jsr     insert
        jmp     @loop
@bk:
        jsr     backspace
        jmp     @loop
@lf:
        jsr     step_left
        jmp     @loop
@rt:
        jsr     step_right
        jmp     @loop
@up:
        jsr     step_up
        jmp     @loop
@dn:
        jsr     step_down
        jmp     @loop

cap_len:
        lda     #>(SCRATCH_SIZE-1)
        cmp     ed_len+1
        bcc     @max
        bne     @ok
        lda     #<(SCRATCH_SIZE-1)
        cmp     ed_len
        bcs     @ok
@max:
        lda     #<(SCRATCH_SIZE-1)
        sta     ed_len
        lda     #>(SCRATCH_SIZE-1)
        sta     ed_len+1
@ok:
        jmp     poke_nul

at_off:
        lda     #<scratch
        clc
        adc     ed_off
        sta     ptr
        lda     #>scratch
        adc     ed_off+1
        sta     ptr+1
        rts

at_cur:
        lda     ed_cur
        sta     ed_off
        lda     ed_cur+1
        sta     ed_off+1
        jmp     at_off

at_len:
        lda     ed_len
        sta     ed_off
        lda     ed_len+1
        sta     ed_off+1
        jmp     at_off

poke_nul:
        jsr     at_len
        lda     #0
        tay
        sta     (ptr),y
        rts

cmp_cur_len:
        lda     ed_cur
        cmp     ed_len
        bne     @d
        lda     ed_cur+1
        cmp     ed_len+1
@d:
        rts

insert:
        lda     ed_len+1
        cmp     #>(SCRATCH_SIZE-1)
        bcc     @ok
        bne     @full
        lda     ed_len
        cmp     #<(SCRATCH_SIZE-1)
        bcs     @full
@ok:
        jsr     tail
        jsr     at_cur
        lda     ptr
        clc
        adc     #1
        sta     ptr2
        lda     ptr+1
        adc     #0
        sta     ptr2+1
        jsr     copy_down
        jsr     at_cur
        lda     ed_k
        ora     ed_high
        ldy     #0
        sta     (ptr),y
        inc     ed_len
        bne     @i
        inc     ed_len+1
@i:
        jsr     step_right
        jmp     poke_nul
@full:
        rts

backspace:
        lda     ed_cur
        ora     ed_cur+1
        beq     @done
        jsr     step_left
        jsr     tail
        jsr     at_cur
        lda     ptr
        sta     ptr2
        lda     ptr+1
        sta     ptr2+1
        inc     ptr
        bne     @s
        inc     ptr+1
@s:
        jsr     copy_up
        lda     ed_len
        bne     @d
        dec     ed_len+1
@d:
        dec     ed_len
        jmp     poke_nul
@done:
        rts

tail:
        lda     ed_len
        sec
        sbc     ed_cur
        sta     ed_left
        lda     ed_len+1
        sbc     ed_cur+1
        sta     ed_left+1
        rts

; ptr = end of source, ptr2 = end of dest; copy ed_left bytes downward
copy_down:
        lda     ptr
        clc
        adc     ed_left
        sta     ptr
        lda     ptr+1
        adc     ed_left+1
        sta     ptr+1
        lda     ptr2
        clc
        adc     ed_left
        sta     ptr2
        lda     ptr2+1
        adc     ed_left+1
        sta     ptr2+1
@lp:
        lda     ed_left
        ora     ed_left+1
        beq     @d
        jsr     dec_ptr
        jsr     dec_ptr2
        ldy     #0
        lda     (ptr),y
        sta     (ptr2),y
        jsr     dec_left
        jmp     @lp
@d:
        rts

copy_up:
@lp:
        lda     ed_left
        ora     ed_left+1
        beq     @d
        ldy     #0
        lda     (ptr),y
        sta     (ptr2),y
        inc     ptr
        bne     @a
        inc     ptr+1
@a:
        inc     ptr2
        bne     @b
        inc     ptr2+1
@b:
        jsr     dec_left
        jmp     @lp
@d:
        rts

dec_ptr:
        lda     ptr
        bne     @a
        dec     ptr+1
@a:
        dec     ptr
        rts

dec_ptr2:
        lda     ptr2
        bne     @a
        dec     ptr2+1
@a:
        dec     ptr2
        rts

dec_left:
        lda     ed_left
        bne     @a
        dec     ed_left+1
@a:
        dec     ed_left
        rts

step_left:
        lda     ed_cur
        ora     ed_cur+1
        beq     @d
        lda     ed_cur
        bne     @a
        dec     ed_cur+1
@a:
        dec     ed_cur
@d:
        rts

step_right:
        jsr     cmp_cur_len
        beq     @d
        inc     ed_cur
        bne     @d
        inc     ed_cur+1
@d:
        rts

step_up:
        jsr     line_start
        lda     ed_off
        ora     ed_off+1
        beq     @d
        lda     ed_off
        sta     ed_cur
        lda     ed_off+1
        sta     ed_cur+1
        jsr     step_left
        jsr     line_start
        lda     ed_off
        sta     ed_cur
        lda     ed_off+1
        sta     ed_cur+1
@d:
        rts

step_down:
        jsr     line_start
@sc:
        jsr     cmp_off_len
        beq     @d
        jsr     at_off
        ldy     #0
        lda     (ptr),y
        jsr     bump_off
        and     #$7F            ; $0D and DOS's $8D both end a line
        cmp     #13
        bne     @sc
        lda     ed_off
        sta     ed_cur
        lda     ed_off+1
        sta     ed_cur+1
@d:
        rts

cmp_off_len:
        lda     ed_off
        cmp     ed_len
        bne     @x
        lda     ed_off+1
        cmp     ed_len+1
@x:
        rts

line_start:
        lda     ed_cur
        sta     ed_off
        lda     ed_cur+1
        sta     ed_off+1
@lp:
        lda     ed_off
        ora     ed_off+1
        beq     @d
        jsr     dec_off
        jsr     at_off
        ldy     #0
        lda     (ptr),y
        and     #$7F            ; $0D or $8D
        cmp     #13
        bne     @lp
        jmp     bump_off
@d:
        rts

bump_off:
        inc     ed_off
        bne     @d
        inc     ed_off+1
@d:
        rts

dec_off:
        lda     ed_off
        bne     @a
        dec     ed_off+1
@a:
        dec     ed_off
        rts

ask_leave:
        jsr     clear
        ldy     #2
        ldx     #0
        jsr     at
        PRINT   "SAVE THIS TEXT?"
        KEYBAR  23, "Y Save,N Abandon,ESC Back"
@a:
        jsr     key
        cmp     #'Y'
        beq     @y
        cmp     #'N'
        beq     @n
        cmp     #27
        bne     @a
        clc
        rts
@y:
        lda     #1
        sta     ed_done
        sec
        rts
@n:
        lda     #0
        sta     ed_done
        sec
        rts

; Draw from the start of the file. A basic editor: the first 21 lines.
draw_edit:
        lda     #0
        sta     ed_off
        sta     ed_off+1
        sta     ed_lines
        jsr     clear
@row:
        lda     ed_lines
        cmp     #21
        bcs     @bar
        tay
        ldx     #0
        jsr     at
@col:
        jsr     cmp_off_len
        beq     @eol
        lda     ed_off
        cmp     ed_cur
        bne     @ch
        lda     ed_off+1
        cmp     ed_cur+1
        bne     @ch
        lda     #1
        sta     inverse
@ch:
        jsr     at_off
        ldy     #0
        lda     (ptr),y
        jsr     bump_off
        and     #$7F            ; $8D is a line end too
        cmp     #13
        beq     @nl
        cmp     #32
        bcc     @dot
        cmp     #127
        bcc     @em
@dot:
        lda     #'.'
@em:
        jsr     put
        lda     #0
        sta     inverse
        lda     col
        cmp     #40
        bcc     @col
        inc     ed_lines
        jmp     @row
@nl:
        lda     #0
        sta     inverse
        inc     ed_lines
        jmp     @row
@eol:
        lda     ed_off
        cmp     ed_cur
        bne     @bar
        lda     ed_off+1
        cmp     ed_cur+1
        bne     @bar
        lda     #1
        sta     inverse
        lda     #' '
        jsr     put
        lda     #0
        sta     inverse
@bar:
        KEYBAR  23, "^S Save,ESC Leave,^K/^J Up/Dn"
        rts
