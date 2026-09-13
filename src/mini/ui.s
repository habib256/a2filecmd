; ui.s -- two panels, the keys, and the one loop that ties them together.
;
; Ported field for field from the C edition so the screens are the same
; ones: same headers, same 19-column panes either side of a colon, same
; inverse key blocks, same messages, same answers accepted. The POM2
; benches assert on that text, and they are not being relaxed.
;
; Every local lives in BSS, never in a zero page temp: the screen
; routines below use t0 to t7 freely, and a value that had to survive a
; put() would be lost there.

        .include "mini.inc"

        .export main

        .import present, at, put, inline_text, clear, zone
        .import number, hexbyte, filetype, keys_bar, keys_bar_inline
        .import key
        .import catalog, preview, load_file, load_count, blank_scratch
        .import ent_ptr, ent_index
        .import bit_masks, tags
        .import key_raw
        .import scratch
        .import copy_prepare, copy_execute, copy_cancel
        .import create_prepare, create_execute
        .import ram_source, data_count
        .import delete_prepare, delete_execute, delete_cancel
        .import del_index, del_fault
        .import ask_name, edit_text, edit_len, name_buf
        .import copy_from, copy_to, copy_src_volume, copy_dst_volume
        .import cp_index, cp_dest
        .import cs_name, cs_type, cs_seclo, cs_sechi
        .import active, count, volume, drive, slot, selected, error
        .import buffer, prv_index
        .import ent_track, ent_sector, ent_type, ent_seclo, ent_sechi
        .import ent_name
        .import pan_drive, pan_volume, pan_count, pan_selected, pan_error
        .import pan_top

        .segment "BSS"
dp_side:        .res 1          ; draw_panel locals
dp_x:           .res 1
dp_i:           .res 1
dp_row:         .res 1
dp_idx:         .res 1          ; index into the shared entry arrays
dp_rel:         .res 1          ; index within the panel, which marks use
tg_index:       .res 1          ; tag_bit arguments
tg_side:        .res 1
tg_n:           .res 1          ; tag_count workings
tg_bits:        .res 1
tg_left:        .res 1
hg_status:      .res 1          ; hi-res viewer
vw_mode:        .res 1          ; view locals
vw_i:           .res 1
vw_prev:        .res 1
rl_home:        .res 1          ; reload locals
rl_have:        .res 1
rl_name:        .res NAME_LEN
rl_i:           .res 1
ck:             .res 1          ; the key being acted on
cf_status:      .res 1          ; copy_file status

        .segment "RODATA"
; '1' to '7' stand in for the seven buttons on the bottom bars.
digit_keys:
        .byte   9, 13, 'C', '/', 18, '?', 'Q'

        .segment "CODE"

; ---------------------------------------------------------------------
; print_byte / print_word -- number() reads a 16-bit value from num
; ---------------------------------------------------------------------
print_byte:
        sta     num
        lda     #0
        sta     num+1
        jmp     number

; print_name -- A = array index, writes its 30 DOS characters
print_name:
        jsr     ent_ptr
        lda     ptr
        sta     w0
        lda     ptr+1
        sta     w0+1
        ldy     #0
@char:
        sty     t1
        lda     (w0),y
        jsr     put
        ldy     t1
        iny
        cpy     #NAME_LEN
        bcc     @char
        rts

; ---------------------------------------------------------------------
; Marks.
;
; One bit per entry per panel. A mark refers to a position in a catalog
; snapshot, so tags_clear runs on every reread: otherwise a mark could
; survive onto a different file than the one it was put on, and marks are
; what the destructive commands act on.
; ---------------------------------------------------------------------

; tag_bit -- A = index within the panel, X = side. bidx/bmsk select its
; bit in tags.
tag_bit:
        sta     tg_index
        stx     tg_side
        lsr     a
        lsr     a
        lsr     a
        sta     bidx
        lda     tg_side
        beq     @left
        lda     bidx
        clc
        adc     #TAG_BYTES
        sta     bidx
@left:
        lda     tg_index
        and     #7
        tax
        lda     bit_masks,x
        sta     bmsk
        rts

; tag_test -- A = index, X = side. Z clear when the entry is marked.
tag_test:
        jsr     tag_bit
        ldx     bidx
        lda     tags,x
        and     bmsk
        rts

; tag_toggle -- the selected entry of the active panel
tag_toggle:
        lda     count
        bne     @go
        rts
@go:
        lda     selected
        ldx     active
        jsr     tag_bit
        ldx     bidx
        lda     tags,x
        eor     bmsk
        sta     tags,x
        rts

; tag_all / tag_none -- every entry of the active panel, or none
tag_all:
        lda     #0
        sta     tg_index
@each:
        lda     tg_index
        cmp     count
        bcs     @done
        ldx     active
        jsr     tag_bit
        ldx     bidx
        lda     tags,x
        ora     bmsk
        sta     tags,x
        inc     tg_index
        jmp     @each
@done:
        rts

tag_none:
        ldx     active
        jmp     tags_clear

tag_invert:
        lda     #0
        sta     tg_index
@each:
        lda     tg_index
        cmp     count
        bcs     @done
        ldx     active
        jsr     tag_bit
        ldx     bidx
        lda     tags,x
        eor     bmsk
        sta     tags,x
        inc     tg_index
        jmp     @each
@done:
        rts

; tags_clear -- X = side. Called wherever a panel is read again.
tags_clear:
        cpx     #0
        beq     @left
        ldx     #TAG_BYTES
        jmp     @wipe
@left:
        ldx     #0
@wipe:
        lda     #0
        ldy     #TAG_BYTES
@byte:
        sta     tags,x
        inx
        dey
        bne     @byte
        rts

; tag_count -- X = side, returns how many marks it holds
tag_count:
        lda     #0
        sta     tg_n
        cpx     #0
        beq     @left
        ldx     #TAG_BYTES
        jmp     @scan
@left:
        ldx     #0
@scan:
        ldy     #TAG_BYTES
@byte:
        lda     tags,x
        beq     @next
        sta     tg_bits
        lda     #8
        sta     tg_left
@bit:
        lsr     tg_bits
        bcc     @nobit
        inc     tg_n
@nobit:
        dec     tg_left
        bne     @bit
@next:
        inx
        dey
        bne     @byte
        lda     tg_n
        rts

; ---------------------------------------------------------------------
; remember / activate -- the panels keep their own drive, volume, count,
; selection and error; only one set is live at a time.
; ---------------------------------------------------------------------
remember:
        ldx     active
        lda     drive
        sta     pan_drive,x
        lda     volume
        sta     pan_volume,x
        lda     count
        sta     pan_count,x
        lda     selected
        sta     pan_selected,x
        lda     error
        sta     pan_error,x
        rts

activate:
        ldx     active
        lda     pan_drive,x
        sta     drive
        lda     pan_volume,x
        sta     volume
        lda     pan_count,x
        sta     count
        lda     pan_selected,x
        sta     selected
        lda     pan_error,x
        sta     error
        rts

; ---------------------------------------------------------------------
; confirm -- carry set on Y. Nothing else answers, so a numeric bar key
; cannot confirm a write by accident.
; ---------------------------------------------------------------------
confirm:
        KEYBAR  23, "Y Yes,N No,ESC Cancel"
@ask:
        jsr     key
        cmp     #'Y'
        beq     @yes
        cmp     #'N'
        beq     @no
        cmp     #27
        bne     @ask
@no:
        clc
        rts
@yes:
        sec
        rts

; ---------------------------------------------------------------------
; draw_panel -- A = side
; ---------------------------------------------------------------------
draw_panel:
        sta     dp_side
        asl     a
        asl     a
        asl     a
        asl     a
        sta     dp_x            ; side * 16
        lda     dp_side
        asl     a
        asl     a
        clc
        adc     dp_x
        sta     dp_x            ; + side * 4 = side * 20
        lda     dp_side
        cmp     active
        bne     @plain
        ldy     #0
        ldx     dp_x
        lda     #19
        jsr     zone
        jmp     @header
@plain:
        ldy     #0
        ldx     dp_x
        jsr     at
@header:
        PRINT   "S"
        lda     slot
        jsr     print_byte
        PRINT   ",D"
        ldx     dp_side
        lda     pan_drive,x
        jsr     print_byte
        ldx     dp_side
        lda     pan_error,x
        bne     @novolume
        PRINT   " / V"
        ldx     dp_side
        lda     pan_volume,x
        jsr     print_byte
@novolume:
        lda     #0
        sta     inverse
        ldy     #1
        ldx     dp_x
        jsr     at
        PRINT   "NAME            T L"
        lda     #0
        sta     dp_i
@rows:
        ldx     dp_side         ; stop at 18 rows or at the last entry
        lda     pan_top,x
        clc
        adc     dp_i
        sta     dp_idx
        cmp     pan_count,x
        jcs     @tail
        lda     dp_i
        cmp     #PANEL_ROWS
        jcs     @tail
        lda     dp_side         ; inverse only on the active selection
        cmp     active
        bne     @normal
        ldx     dp_side
        lda     dp_idx
        cmp     pan_selected,x
        bne     @normal
        lda     #1
        jmp     @setinverse
@normal:
        lda     #0
@setinverse:
        sta     inverse
        lda     dp_i
        clc
        adc     #2
        sta     dp_row
        tay
        ldx     dp_x
        jsr     at
        lda     dp_idx
        sta     dp_rel          ; panel-relative, which is what marks use
        lda     dp_side         ; the entry's index in the shared arrays
        beq     @left
        lda     dp_idx
        clc
        adc     #SIDE_STRIDE
        jmp     @haveindex
@left:
        lda     dp_idx
@haveindex:
        sta     dp_idx
        jsr     ent_ptr
        lda     ptr
        sta     w0
        lda     ptr+1
        sta     w0+1
        ldy     #0
@fifteen:
        sty     t1
        lda     (w0),y
        jsr     put
        ldy     t1
        iny
        cpy     #15
        bcc     @fifteen
@shortened:
        sty     t1              ; anything past 15 characters shows a '+'
        lda     (w0),y
        cmp     #' '
        beq     @nextchar
        lda     dp_x
        clc
        adc     #14             ; the '+' takes the fifteenth column
        tax
        ldy     dp_row
        jsr     at
        lda     #'+'
        jsr     put
        jmp     @attributes
@nextchar:
        ldy     t1
        iny
        cpy     #NAME_LEN
        bcc     @shortened
@attributes:
        lda     dp_x
        clc
        adc     #15
        tax
        ldy     dp_row
        jsr     at
        lda     dp_rel
        ldx     dp_side
        jsr     tag_test
        beq     @unmarked
        lda     #'*'
        jmp     @mark
@unmarked:
        lda     #' '
@mark:
        jsr     put
        ldy     dp_idx
        lda     ent_type,y
        jsr     filetype
        jsr     put
        lda     #' '
        jsr     put
        ldy     dp_idx
        lda     ent_type,y
        and     #$80
        beq     @unlocked
        lda     #'L'
        jmp     @lockdone
@unlocked:
        lda     #' '
@lockdone:
        jsr     put
        inc     dp_i
        jmp     @rows
@tail:
        lda     #0
        sta     inverse
        ldx     dp_side
        lda     pan_error,x
        beq     @maybeempty
        ldy     #3
        ldx     dp_x
        jsr     at
        ldx     dp_side
        lda     pan_error,x
        cmp     #1
        bne     @badcatalog
        PRINT   "READ ERROR"
        jmp     @reread
@badcatalog:
        PRINT   "INVALID CATALOG"
@reread:
        ldy     #5
        ldx     dp_x
        jsr     at
        PRINT   "CTRL-R: REREAD"
        rts
@maybeempty:
        ldx     dp_side
        lda     pan_count,x
        bne     @done
        ldy     #3
        ldx     dp_x
        jsr     at
        PRINT   "EMPTY DISK"
@done:
        rts

; ---------------------------------------------------------------------
; draw -- the whole screen, composed then presented by the next key wait
; ---------------------------------------------------------------------
draw:
        jsr     clear
        ldy     #0
@divider:
        sty     t2
        ldx     #19
        jsr     at
        lda     #':'
        jsr     put
        ldy     t2
        iny
        cpy     #20
        bcc     @divider
        lda     #0
        jsr     draw_panel
        lda     #1
        jsr     draw_panel
        ldy     #20
        ldx     #0
        lda     #40
        jsr     zone
        PRINT   "A2FC MINI DOS 3.3  "
        lda     count
        jsr     print_byte
        PRINT   " FILES"
        ldx     active
        jsr     tag_count
        beq     @nomarks
        sta     tg_n
        PRINT   "  "
        lda     tg_n
        jsr     print_byte
        PRINT   " MARKED"
@nomarks:
        lda     #0
        sta     inverse
        ldy     #21
        ldx     #0
        jsr     at
        lda     count
        beq     @noinfo
        lda     error
        bne     @noinfo
        lda     selected
        jsr     ent_index
        sta     dp_idx
        jsr     print_name
        lda     #' '
        jsr     put
        ldy     dp_idx
        lda     ent_seclo,y
        sta     num
        lda     ent_sechi,y
        sta     num+1
        jsr     number
        PRINT   " S"
@noinfo:
        lda     error
        beq     @bars
        PRINT   "CATALOG ERROR - CTRL-R TO REREAD"
@bars:
        KEYBAR  22, "TAB Panel,RET Open,C Copy"
        KEYBAR  23, "/ Drive,^R Reread,? Help,Q DOS"
        rts

; ---------------------------------------------------------------------
; land -- put the cursor on A, scrolling the window as little as needed
; ---------------------------------------------------------------------
land:
        sta     selected
        ldx     active
        sta     pan_selected,x
        cmp     pan_top,x
        bcs     @notabove
        sta     pan_top,x
        rts
@notabove:
        sec
        sbc     pan_top,x
        cmp     #PANEL_ROWS
        bcc     @done
        lda     selected        ; keep the cursor on the last row
        sec
        sbc     #PANEL_ROWS-1
        sta     pan_top,x
@done:
        rts

; ---------------------------------------------------------------------
; move -- A = signed delta, clamped to the catalog
; ---------------------------------------------------------------------
move:
        sta     t2
        lda     count
        bne     @go
        rts
@go:
        lda     t2
        bmi     @back
        clc
        adc     selected
        bcs     @last
        cmp     count
        bcc     land
@last:
        lda     count
        sec
        sbc     #1
        jmp     land
@back:
        clc
        adc     selected
        bcs     land
        lda     #0
        jmp     land

; ---------------------------------------------------------------------
; help
; ---------------------------------------------------------------------
help:
        jsr     clear
        ldy     #0
        ldx     #0
        lda     #40
        jsr     zone
        PRINT   "A2FC MINI - COMMANDS"
        lda     #0
        sta     inverse
        ldy     #2
        ldx     #0
        jsr     at
        PRINT   "TAB: PANEL   RET: OPEN"
        ldy     #4
        ldx     #0
        jsr     at
        PRINT   "CTRL-K/J OR I/K: UP/DOWN"
        ldy     #6
        ldx     #0
        jsr     at
        PRINT   "ARROWS OR -/+: PAGE   [/]: FIRST/LAST"
        ldy     #8
        ldx     #0
        jsr     at
        PRINT   "/: DRIVE   CTRL-R: REREAD BOTH"
        ldy     #10
        ldx     #0
        jsr     at
        PRINT   "=: SAME DISK IN THE OTHER PANEL"
        ldy     #12
        ldx     #0
        jsr     at
        PRINT   "T: TEXT  H: HEX  G: HI-RES  C: COPY"
        ldy     #14
        ldx     #0
        jsr     at
        PRINT   "SPACE: TAG  CTRL-T/N: ALL/NONE  *: INVERT"
        ldy     #16
        ldx     #0
        jsr     at
        PRINT   "N: NEW TXT  E: EDIT  D: DELETE"
        ldy     #18
        ldx     #0
        jsr     at
        PRINT   "Y CONFIRMS A WRITE. LOCKED FILES: NO DELETE."
        KEYBAR  23, "ESC Back"
        jsr     key
        rts

; ---------------------------------------------------------------------
; view -- A = 1 for hex. Shows the first stored sector and says so: it
; is not a claim to have read or checked the whole file.
; ---------------------------------------------------------------------
view:
        sta     vw_mode
        lda     selected
        sta     prv_index
        jsr     preview         ; read once; T and H only redraw it
        sta     error
        beq     @render
        jsr     clear
        ldy     #3
        ldx     #0
        jsr     at
        lda     error
        cmp     #1
        bne     @nopreview
        PRINT   "READ ERROR"
        jmp     @anykey
@nopreview:
        PRINT   "NO PREVIEW / INVALID T-S LIST"
@anykey:
        ldy     #23
        ldx     #0
        jsr     at
        PRINT   "ANY KEY: BACK"
        jsr     key
        lda     #0
        sta     error
        rts
@render:
        jsr     clear
        ldy     #0
        ldx     #0
        jsr     at
        lda     selected
        jsr     ent_index
        jsr     print_name
        ldy     #1
        ldx     #0
        jsr     at
        PRINT   "PREVIEW: FIRST SECTOR (256 BYTES)"
        lda     vw_mode
        beq     @text
        lda     #0
        sta     vw_i
@hexrow:
        lda     vw_i
        clc
        adc     #3
        tay
        ldx     #0
        jsr     at
        lda     vw_i
        asl     a
        asl     a
        asl     a
        asl     a
        jsr     hexbyte
        lda     #':'
        jsr     put
        lda     #' '
        jsr     put
        lda     vw_i
        asl     a
        asl     a
        asl     a
        asl     a
        sta     vw_prev         ; the row's first byte
        ldx     #0
@bytes:
        stx     t2
        txa
        clc
        adc     vw_prev
        tax
        lda     buffer,x
        jsr     hexbyte
        ldx     t2
        inx
        cpx     #16
        bcc     @bytes
        inc     vw_i
        lda     vw_i
        cmp     #16
        bcc     @hexrow
        jmp     @keys
@text:
        ldy     #3
        ldx     #0
        jsr     at
        lda     #0
        sta     vw_i
@char:
        lda     row             ; the text stops at the bars
        cmp     #21
        bcs     @keys
        ldx     vw_i
        lda     buffer,x
        and     #$7F
        beq     @keys           ; a NUL ends the text
        cmp     #13
        beq     @newline
        cmp     #10
        bne     @printable
        lda     vw_i            ; an LF just after a CR is the same break
        beq     @newline
        tax
        dex
        lda     buffer,x
        and     #$7F
        cmp     #13
        beq     @nextchar
@newline:
        inc     row
        lda     #0
        sta     col
        jmp     @nextchar
@printable:
        cmp     #32
        bcc     @dot
        cmp     #127
        bcc     @emit
@dot:
        lda     #'.'
@emit:
        jsr     put
        lda     col
        cmp     #40
        bcc     @nextchar
        lda     #0
        sta     col
        inc     row
@nextchar:
        inc     vw_i
        lda     vw_i
        bne     @char
@keys:
        KEYBAR  23, "T Text,H Hex,ESC Back"
        jsr     key
        cmp     #'H'
        bne     @nothex
        lda     #1
        sta     vw_mode
        jmp     @render
@nothex:
        cmp     #'T'
        bne     @leave
        lda     #0
        sta     vw_mode
        jmp     @render
@leave:
        rts

; ---------------------------------------------------------------------
; copy_file -- checks, then one confirmation, then the writing
; ---------------------------------------------------------------------
copy_file:
        jsr     clear
        ldy     #2
        ldx     #0
        jsr     at
        PRINT   "CHECKING BOTH DISKS..."
        jsr     present
        lda     selected
        sta     cp_index
        lda     active
        eor     #1
        tax
        lda     pan_drive,x
        sta     cp_dest
        jsr     copy_prepare
        sta     cf_status
        jne     cf_show
        jsr     clear
        ldy     #0
        ldx     #0
        lda     #40
        jsr     zone
        PRINT   "COPY TO THE OTHER PANEL"
        lda     #0
        sta     inverse
        ldy     #2
        ldx     #0
        jsr     at
        ldy     #0
@name:
        sty     t1
        lda     cs_name,y
        jsr     put
        ldy     t1
        iny
        cpy     #NAME_LEN
        bcc     @name
        ldy     #4
        ldx     #0
        jsr     at
        PRINT   "SOURCE S"
        lda     slot
        jsr     print_byte
        PRINT   " D"
        lda     copy_from
        jsr     print_byte
        PRINT   " V"
        lda     copy_src_volume
        jsr     print_byte
        ldy     #5
        ldx     #0
        jsr     at
        PRINT   "TARGET S"
        lda     slot
        jsr     print_byte
        PRINT   " D"
        lda     copy_to
        jsr     print_byte
        PRINT   " V"
        lda     copy_dst_volume
        jsr     print_byte
        ldy     #7
        ldx     #0
        jsr     at
        lda     cs_seclo
        sta     num
        lda     cs_sechi
        sta     num+1
        jsr     number
        PRINT   " SECTORS - NEW FILE"
        ldy     #9
        ldx     #0
        jsr     at
        PRINT   "DO NOT CHANGE DISKS"
        jsr     confirm
        bcs     @go
        jsr     copy_cancel     ; the plan dies with the refusal
        jmp     activate
@go:
        jsr     clear
        ldy     #2
        ldx     #0
        jsr     at
        PRINT   "COPYING AND VERIFYING..."
        jsr     present
        jsr     copy_execute
        sta     cf_status
cf_show:
        jsr     clear
        ldy     #2
        ldx     #0
        jsr     at
        lda     cf_status
        bne     @notok
        PRINT   "COPY VERIFIED"
        jmp     @anykey
@notok:
        cmp     #COPY_READ
        bne     @notread
        PRINT   "READ ERROR - COPY REFUSED"
        jmp     @anykey
@notread:
        cmp     #COPY_EXISTS
        bne     @notexists
        PRINT   "NAME EXISTS - NO OVERWRITE"
        jmp     @anykey
@notexists:
        cmp     #COPY_FULL
        bne     @notfull
        PRINT   "DISK OR CATALOG FULL"
        jmp     @anykey
@notfull:
        cmp     #COPY_SAME
        bne     @notsame
        PRINT   "SELECT TWO DIFFERENT DRIVES"
        jmp     @anykey
@notsame:
        cmp     #COPY_PROTECTED
        bne     @notprot
        PRINT   "DISK IS WRITE PROTECTED"
        jmp     @anykey
@notprot:
        cmp     #COPY_CHANGED
        bne     @notchanged
        PRINT   "DISK CHANGED - COPY REFUSED"
        jmp     @anykey
@notchanged:
        cmp     #COPY_UNCERTAIN
        bne     @unsupported
        PRINT   "UNCERTAIN WRITE - STOP"
        ldy     #4
        ldx     #0
        jsr     at
        PRINT   "TARGET DISK MUST BE CHECKED"
        ldy     #6
        ldx     #0
        jsr     at
        PRINT   "DO NOT WRITE TO THIS DISK"
        jmp     @anykey
@unsupported:
        PRINT   "UNSUPPORTED / INVALID DOS STRUCTURE"
@anykey:
        ldy     #23
        ldx     #0
        jsr     at
        PRINT   "ANY KEY: BACK"
        jsr     key
        jmp     reload

; ---------------------------------------------------------------------
; reload -- read both panels again, keeping each selection by name
; ---------------------------------------------------------------------
reload:
        lda     active
        sta     rl_home
        lda     #0
        sta     active
@side:
        jsr     activate
        lda     #0
        sta     rl_have
        lda     count
        beq     @read
        lda     #1
        sta     rl_have
        lda     selected
        jsr     ent_index
        jsr     ent_ptr
        ldy     #0
@keep:
        lda     (ptr),y
        sta     rl_name,y
        iny
        cpy     #NAME_LEN
        bcc     @keep
@read:
        lda     #0
        sta     volume
        jsr     catalog
        sta     error
        ldx     active
        jsr     tags_clear
        lda     rl_have
        beq     @clamp
        lda     #0
        sta     rl_i
@search:
        lda     rl_i
        cmp     count
        bcs     @clamp
        lda     rl_i
        jsr     ent_index
        jsr     ent_ptr
        ldy     #0
@compare:
        lda     (ptr),y
        cmp     rl_name,y
        bne     @nextentry
        iny
        cpy     #NAME_LEN
        bcc     @compare
        lda     rl_i            ; found it again, by name
        sta     selected
        jmp     @clamp
@nextentry:
        inc     rl_i
        jmp     @search
@clamp:
        lda     selected
        cmp     count
        bcc     @place
        lda     count
        beq     @zero
        sec
        sbc     #1
        jmp     @setsel
@zero:
        lda     #0
@setsel:
        sta     selected
@place:
        lda     selected
        jsr     land
        jsr     remember
        inc     active
        lda     active
        cmp     #2
        jcc     @side
        lda     rl_home
        sta     active
        jmp     activate

; ---------------------------------------------------------------------
; main
; ---------------------------------------------------------------------
main:
        lda     #0
        sta     TXTSET          ; text, page one, as the C edition did
        sta     LOWSCR
        jsr     catalog
        sta     error
        ldx     #0
        jsr     tags_clear
        jsr     remember
        lda     pan_drive       ; both panels start on the boot disk, so
        sta     pan_drive+1     ; the second one costs no second read
        lda     pan_volume
        sta     pan_volume+1
        lda     pan_count
        sta     pan_count+1
        lda     pan_selected
        sta     pan_selected+1
        lda     pan_error
        sta     pan_error+1
        lda     pan_top
        sta     pan_top+1
        jsr     copy_entries_to_right
@loop:
        jsr     draw
        jsr     key
        sta     ck
        cmp     #'1'
        bcc     @notdigit
        cmp     #'8'
        bcs     @notdigit
        sec
        sbc     #'1'
        tax
        lda     digit_keys,x
        sta     ck
@notdigit:
        lda     ck
        cmp     #'Q'
        bne     @notquit
        ldy     #22
        ldx     #0
        lda     #40
        jsr     zone
        PRINT   "QUIT TO DOS 3.3?"
        lda     #0
        sta     inverse
        jsr     confirm
        bcc     @notquit
        jmp     @leave
@notquit:
        lda     ck
        cmp     #9
        bne     @nottab
        lda     active
        eor     #1
        sta     active
        jsr     activate
@nottab:
        lda     ck
        cmp     #'K'
        beq     @down
        cmp     #10
        bne     @notdown
@down:
        lda     #1
        jsr     move
@notdown:
        lda     ck
        cmp     #'I'
        beq     @up
        cmp     #11
        bne     @notup
@up:
        lda     #$FF
        jsr     move
@notup:
        lda     ck
        cmp     #8
        beq     @pageup
        cmp     #'-'
        beq     @pageup
        cmp     #'<'
        bne     @notpageup
@pageup:
        lda     #256-PANEL_ROWS
        jsr     move
@notpageup:
        lda     ck
        cmp     #21
        beq     @pagedown
        cmp     #'+'
        beq     @pagedown
        cmp     #'>'
        bne     @notpagedown
@pagedown:
        lda     #PANEL_ROWS
        jsr     move
@notpagedown:
        lda     ck
        cmp     #'['
        bne     @notfirst
        lda     #0
        jsr     land
@notfirst:
        lda     ck
        cmp     #']'
        bne     @notlast
        lda     count
        beq     @notlast
        sec
        sbc     #1
        jsr     land
@notlast:
        lda     ck
        cmp     #'/'
        bne     @notdrive
        lda     #3
        sec
        sbc     drive
        sta     drive
        lda     #0
        sta     selected
        ldx     active
        sta     pan_top,x
        sta     volume
        jsr     catalog
        sta     error
        ldx     active
        jsr     tags_clear
        jsr     remember
@notdrive:
        lda     ck
        cmp     #18
        bne     @notreread
        jsr     reload
@notreread:
        lda     ck
        cmp     #'='
        bne     @notsame
        jsr     mirror_panel
@notsame:
        lda     ck
        cmp     #13
        beq     @maybeview
        cmp     #'T'
        beq     @maybeview
        cmp     #'H'
        bne     @notview
@maybeview:
        lda     count
        beq     @notview
        lda     error
        bne     @notview
        lda     ck
        cmp     #13
        bne     @explicit
        jsr     looks_hgr
        bcc     @bytype
        jsr     show_hgr
        jmp     @notview
@bytype:
        lda     selected        ; RETURN picks by type: text reads as text
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$7F
        beq     @astext
        lda     #1
        jmp     @doview
@astext:
        lda     #0
        jmp     @doview
@explicit:
        lda     ck
        cmp     #'H'
        bne     @astext
        lda     #1
@doview:
        jsr     view
@notview:
        lda     ck
        cmp     #'C'
        bne     @notcopy
        lda     count
        beq     @notcopy
        lda     error
        bne     @notcopy
        jsr     copy_file
@notcopy:
        lda     ck
        cmp     #'?'
        bne     @nothelp
        jsr     help
@nothelp:
        lda     ck
        cmp     #' '
        bne     @nottag
        jsr     tag_toggle
@nottag:
        lda     ck
        cmp     #20             ; Ctrl-T
        bne     @notall
        jsr     tag_all
@notall:
        lda     ck
        cmp     #14             ; Ctrl-N
        bne     @notnone
        jsr     tag_none
@notnone:
        lda     ck
        cmp     #'*'
        bne     @notinv
        jsr     tag_invert
@notinv:
        lda     ck
        cmp     #'G'
        bne     @nothgr
        lda     count
        beq     @nothgr
        lda     error
        bne     @nothgr
        jsr     show_hgr
@nothgr:
        lda     ck
        cmp     #'N'
        bne     @notnew
        jsr     new_text
@notnew:
        lda     ck
        cmp     #'E'
        bne     @notedit
        lda     count
        beq     @notedit
        lda     error
        bne     @notedit
        jsr     edit_file
@notedit:
        lda     ck
        cmp     #'D'
        bne     @notdel
        lda     count
        beq     @notdel
        lda     error
        bne     @notdel
        jsr     delete_file
@notdel:
        jmp     @loop
@leave:
        jsr     clear
        ldy     #0
        ldx     #0
        jsr     at
        PRINT   "A2FC MINI - BACK TO DOS 3.3"
        jmp     present

; ---------------------------------------------------------------------
; mirror_panel -- '=' shows the active panel's disk on the other side,
; entries included, without touching the drive
; ---------------------------------------------------------------------
mirror_panel:
        ldx     active
        lda     active
        eor     #1
        tay
        lda     pan_drive,x
        sta     pan_drive,y
        lda     pan_volume,x
        sta     pan_volume,y
        lda     pan_count,x
        sta     pan_count,y
        lda     pan_selected,x
        sta     pan_selected,y
        lda     pan_error,x
        sta     pan_error,y
        lda     pan_top,x
        sta     pan_top,y
        jsr     copy_tags
        lda     active
        bne     copy_entries_to_left
        jmp     copy_entries_to_right

; copy_tags -- X = source side, Y = dest side
copy_tags:
        lda     #0
        cpx     #0
        beq     @fromleft
        lda     #TAG_BYTES
@fromleft:
        sta     t2
        lda     #0
        cpy     #0
        beq     @toleft
        lda     #TAG_BYTES
@toleft:
        sta     t3
        ldx     #0
@byte:
        ldy     t2
        lda     tags,y
        ldy     t3
        sta     tags,y
        inc     t2
        inc     t3
        inx
        cpx     #TAG_BYTES
        bcc     @byte
        rts

copy_entries_to_right:
        ldx     #0
@fields:
        lda     ent_track,x
        sta     ent_track+SIDE_STRIDE,x
        lda     ent_sector,x
        sta     ent_sector+SIDE_STRIDE,x
        lda     ent_type,x
        sta     ent_type+SIDE_STRIDE,x
        lda     ent_seclo,x
        sta     ent_seclo+SIDE_STRIDE,x
        lda     ent_sechi,x
        sta     ent_sechi+SIDE_STRIDE,x
        inx
        cpx     #SIDE_STRIDE
        bcc     @fields
        SETPTR  ptr, ent_name
        SETPTR  ptr2, ent_name+SIDE_STRIDE*NAME_STRIDE
        jmp     copy_names

copy_entries_to_left:
        ldx     #0
@fields:
        lda     ent_track+SIDE_STRIDE,x
        sta     ent_track,x
        lda     ent_sector+SIDE_STRIDE,x
        sta     ent_sector,x
        lda     ent_type+SIDE_STRIDE,x
        sta     ent_type,x
        lda     ent_seclo+SIDE_STRIDE,x
        sta     ent_seclo,x
        lda     ent_sechi+SIDE_STRIDE,x
        sta     ent_sechi,x
        inx
        cpx     #SIDE_STRIDE
        bcc     @fields
        SETPTR  ptr, ent_name+SIDE_STRIDE*NAME_STRIDE
        SETPTR  ptr2, ent_name
        jmp     copy_names

; copy_names -- ptr to ptr2, one panel's worth of name storage
copy_names:
        lda     #>(SIDE_STRIDE*NAME_STRIDE)
        sta     t2
        ldy     #0
@page:
        lda     (ptr),y
        sta     (ptr2),y
        iny
        bne     @page
        inc     ptr+1
        inc     ptr2+1
        dec     t2
        bne     @page
        ldy     #0
@tail:
        cpy     #<(SIDE_STRIDE*NAME_STRIDE)
        bcs     @done
        lda     (ptr),y
        sta     (ptr2),y
        iny
        bne     @tail
@done:
        rts

; ---------------------------------------------------------------------
; looks_hgr -- carry set when the selected file is a binary of 32 to 34
; sectors, the usual size of a hi-res page with or without a BSAVE header.
; ---------------------------------------------------------------------
looks_hgr:
        lda     selected
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$7F
        cmp     #TYPE_BINARY
        bne     @no
        lda     ent_sechi,y
        bne     @no
        lda     ent_seclo,y
        cmp     #32
        bcc     @no
        cmp     #35
        bcs     @no
        sec
        rts
@no:
        clc
        rts

; ---------------------------------------------------------------------
; show_hgr -- load the selected file into the working area and put the
; machine in hi-res. The program lives above $4000, so the picture does
; not sit on top of the code that shows it. Any key returns to text.
; ---------------------------------------------------------------------
show_hgr:
        lda     selected
        sta     prv_index
        jsr     load_file
        sta     hg_status
        bne     @fail
        lda     load_count
        beq     @fail
        jsr     skip_bsave
        lda     TXTCLR
        lda     MIXCLR
        lda     LOWSCR
        lda     HIRES
        jsr     key_raw
        lda     TXTSET
        lda     LORES
        lda     LOWSCR
        rts
@fail:
        jsr     clear
        ldy     #3
        ldx     #0
        jsr     at
        lda     hg_status
        cmp     #1
        bne     @bad
        PRINT   "READ ERROR"
        jmp     @any
@bad:
        PRINT   "NOT A PICTURE / INVALID T-S LIST"
@any:
        jmp     any_back

; skip_bsave -- if the first four bytes are a DOS binary header pointing
; at a hi-res page, slide the picture down so it starts at scratch.
skip_bsave:
        lda     scratch+1
        cmp     #$20
        beq     @addr
        cmp     #$40
        bne     @done
@addr:
        lda     scratch
        bne     @done
        lda     scratch+3
        cmp     #$1F
        beq     @len
        cmp     #$20
        bne     @done
@len:
        lda     #<scratch
        sta     ptr
        lda     #>scratch
        sta     ptr+1
        lda     #<(scratch+4)
        sta     ptr2
        lda     #>(scratch+4)
        sta     ptr2+1
        lda     #<(SCRATCH_SIZE-4)
        sta     num
        lda     #>(SCRATCH_SIZE-4)
        sta     num+1
        ldy     #0
@copy:
        lda     (ptr2),y
        sta     (ptr),y
        inc     ptr
        bne     @a
        inc     ptr+1
@a:
        inc     ptr2
        bne     @b
        inc     ptr2+1
@b:
        lda     num
        bne     @c
        dec     num+1
@c:
        dec     num
        lda     num
        ora     num+1
        bne     @copy
@done:
        rts

; ---------------------------------------------------------------------
; new_text / edit_file -- exclusive create from the editor buffer.
; ---------------------------------------------------------------------
new_text:
        jsr     ask_name
        bcc     @out
        jsr     blank_scratch
        lda     #0
        sta     edit_len
        sta     edit_len+1
        jsr     edit_text
        bcc     @out
        jsr     name_to_cs
        jmp     save_new
@out:
        rts

edit_file:
        lda     selected
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$7F
        cmp     #TYPE_TEXT
        beq     @text
        jsr     clear
        ldy     #3
        ldx     #0
        jsr     at
        PRINT   "EDIT IS FOR TEXT FILES"
        jmp     any_back
@text:
        lda     selected
        sta     prv_index
        jsr     load_file
        sta     hg_status
        bne     @fail
        jsr     measure_text
        jsr     edit_text
        bcc     @out
        jsr     ask_name
        bcc     @out
        jsr     name_to_cs
        jmp     save_new
@fail:
        jsr     clear
        ldy     #3
        ldx     #0
        jsr     at
        PRINT   "READ ERROR - NOT LOADED"
        jmp     any_back
@out:
        rts

name_to_cs:
        ldy     #0
@copy:
        lda     name_buf,y
        sta     cs_name,y
        iny
        cpy     #NAME_LEN
        bcc     @copy
        lda     #TYPE_TEXT
        sta     cs_type
        rts

; measure_text -- ed_len = one past the last non-zero byte
measure_text:
        lda     load_count
        sta     edit_len+1
        lda     #0
        sta     edit_len
        lda     edit_len+1
        beq     @done
@scan:
        lda     edit_len
        bne     @dec
        dec     edit_len+1
        lda     edit_len+1
        bmi     @empty
@dec:
        dec     edit_len
        lda     #<scratch
        clc
        adc     edit_len
        sta     ptr
        lda     #>scratch
        adc     edit_len+1
        sta     ptr+1
        ldy     #0
        lda     (ptr),y
        beq     @scan
        inc     edit_len
        bne     @done
        inc     edit_len+1
        jmp     @done
@empty:
        lda     #0
        sta     edit_len
        sta     edit_len+1
@done:
        rts

save_new:
        jsr     sectors_from_len
        jsr     clear
        ldy     #2
        ldx     #0
        jsr     at
        PRINT   "CHECKING DISK..."
        jsr     present
        jsr     create_prepare
        sta     cf_status
        jne     copy_report
        jsr     clear
        ldy     #0
        ldx     #0
        lda     #40
        jsr     zone
        PRINT   "CREATE TEXT FILE"
        lda     #0
        sta     inverse
        ldy     #2
        ldx     #0
        jsr     at
        ldy     #0
@nm:
        sty     t1
        lda     cs_name,y
        jsr     put
        ldy     t1
        iny
        cpy     #NAME_LEN
        bcc     @nm
        ldy     #4
        ldx     #0
        jsr     at
        lda     data_count
        jsr     print_byte
        PRINT   " SECTORS - NEW FILE ONLY"
        jsr     confirm
        bcs     @go
        jsr     copy_cancel
        rts
@go:
        jsr     clear
        ldy     #2
        ldx     #0
        jsr     at
        PRINT   "WRITING AND VERIFYING..."
        jsr     present
        jsr     create_execute
        sta     cf_status
        jmp     copy_report

sectors_from_len:
        lda     edit_len
        sta     data_count
        lda     edit_len+1
        sta     data_count+1
        lda     data_count
        ora     data_count+1
        bne     @round
        lda     #1
        sta     data_count
        lda     #0
        sta     data_count+1
        rts
@round:
        lda     data_count
        beq     @even
        inc     data_count+1
        lda     #0
        sta     data_count
@even:
        lda     data_count+1
        sta     data_count
        lda     #0
        sta     data_count+1
        rts

; copy_report -- same messages as a disk-to-disk copy, then reread
copy_report:
        jmp     cf_show

; ---------------------------------------------------------------------
; delete_file -- tagged files, or the cursor when nothing is tagged.
; One confirmation, then each file: mark the catalog, then free sectors.
; ---------------------------------------------------------------------
delete_file:
        ldx     active
        jsr     tag_count
        sta     tg_n
        jsr     clear
        ldy     #0
        ldx     #0
        lda     #40
        jsr     zone
        lda     tg_n
        bne     @many
        PRINT   "DELETE THIS FILE"
        lda     #0
        sta     inverse
        ldy     #2
        ldx     #0
        jsr     at
        lda     selected
        jsr     ent_index
        jsr     print_name
        jmp     @ask
@many:
        PRINT   "DELETE MARKED FILES"
        lda     #0
        sta     inverse
        ldy     #2
        ldx     #0
        jsr     at
        lda     tg_n
        jsr     print_byte
        PRINT   " FILES - LOCKED FILES ARE SKIPPED"
@ask:
        ldy     #5
        ldx     #0
        jsr     at
        PRINT   "THIS CANNOT BE UNDONE FROM HERE"
        jsr     confirm
        bcc     @out
        lda     tg_n
        bne     @tagged
        lda     selected
        sta     del_index
        jsr     one_delete
        jmp     @finish
@tagged:
        lda     #0
        sta     tg_index
@each:
        lda     tg_index
        cmp     count
        bcs     @finish
        lda     tg_index
        ldx     active
        jsr     tag_test
        beq     @next
        lda     tg_index
        sta     del_index
        jsr     one_delete
        cmp     #DEL_UNCERTAIN
        beq     @finish
@next:
        inc     tg_index
        jmp     @each
@finish:
        jsr     any_back
        jmp     reload
@out:
        rts

one_delete:
        jsr     delete_prepare
        sta     hg_status
        bne     @rep
        jsr     delete_execute
        sta     hg_status
@rep:
        jsr     clear
        ldy     #2
        ldx     #0
        jsr     at
        lda     hg_status
        bne     @notok
        PRINT   "DELETED"
        lda     #DEL_OK
        rts
@notok:
        cmp     #DEL_LOCKED
        bne     @notlock
        PRINT   "LOCKED - NOT DELETED"
        lda     #DEL_LOCKED
        rts
@notlock:
        cmp     #DEL_CHANGED
        bne     @notchg
        PRINT   "DISK CHANGED - DELETE REFUSED"
        lda     #DEL_CHANGED
        rts
@notchg:
        cmp     #DEL_READ
        bne     @notread
        PRINT   "READ ERROR - DELETE REFUSED"
        lda     #DEL_READ
        rts
@notread:
        cmp     #DEL_UNCERTAIN
        bne     @bad
        PRINT   "UNCERTAIN WRITE - STOP"
        ldy     #4
        ldx     #0
        jsr     at
        PRINT   "TARGET DISK MUST BE CHECKED"
        lda     #1
        sta     del_fault
        lda     #DEL_UNCERTAIN
        rts
@bad:
        PRINT   "UNSUPPORTED / INVALID DOS STRUCTURE"
        lda     hg_status
        rts

any_back:
        ldy     #23
        ldx     #0
        jsr     at
        PRINT   "ANY KEY: BACK"
        jsr     key
        rts
