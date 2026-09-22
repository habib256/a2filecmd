; ui.s -- two panels, the keys, and the one loop that ties them together.
;
; Ported field for field from the C edition so the screens are the same
; ones: same headers, same 19-column panes either side of a colon, same
; inverse key blocks. Copy stays on those panels: footer prompt, then a
; progress bar, then COPIED. The POM2 benches assert on that text.
;
; Every local lives in BSS, never in a zero page temp: the screen
; routines below use t0 to t7 freely, and a value that had to survive a
; put() would be lost there.

        .include "mini.inc"
        .include "version.inc"  ; VERSION_STR, generated from A2FC_VERSION

        .export main, copy_progress
        .export activate, confirm, reload, keep_note, result_done
        .export result_kept
        .export say_protected, say_uncertain, say_unsupported
        .export print_name, print_name15, print_byte, tag_count, tag_test
        .export batch_number, batch_skipped, batch_done, foot_zone
        .export cf_ok, cf_marked, tg_n, brun_go

        .import present, at, put, inline_text, clear, zone
        .import number, hexbyte, filetype, keys_bar, keys_bar_inline
        .import key
        .import catalog, preview, load_file, load_count, load_more
        .import blank_scratch
        .import measure_text
        .import ent_ptr, ent_index, copy_side
        .import bit_masks, tags
        .import key_raw
        .import scratch
        .import copy_prepare, copy_execute, copy_cancel
        .import create_prepare, create_execute
        .import data_count, copy_done, copy_total
        .import delete_prepare, delete_execute, delete_cancel
        .import del_index, del_fault, del_audited
        .import lock_file, rename_file, format_file
        .import ask_name, edit_text, name_buf, ask_kind
        .import edit_len
        .import cp_index, cp_dest, verify, catalog_before
        .import cs_name, cs_type, cs_seclo, cs_sechi
        .import active, count, volume, drive, slot, selected, error
        .import live_panel
        .import buffer, prv_index
        .import ent_type, ent_seclo, ent_sechi
        .import pan_drive, pan_volume, pan_count, pan_selected, pan_error
        .import pan_top
        .import screen_image

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
; the name a reread keeps the selection by lives in the write engine's
; read-back page: a reread only reads, and no write runs during one
rl_name         = verify
rl_i:           .res 1
rl_mask:        .res 1          ; 0 = every panel (Ctrl-R)
rl_drive:       .res 1          ; written drive when rl_mask is set
ck:             .res 1          ; the key being acted on
cf_status:      .res 1          ; copy_file status
cf_marked:      .res 1          ; tagged files to copy, 0 = cursor only
cf_ok:          .res 1          ; how many of a batch landed
cf_full:        .res 1          ; a file of the batch did not fit: the batch's word
pg_acc:         .res 2          ; copy_progress: done * 32
pg_fill:        .res 1
pg_last:        .res 1          ; the bar as drawn: an unchanged bar is not redrawn
pg_i:           .res 1
have_note:      .res 1          ; last operation result, drawn on row 22 until the next key
brun_go:        .res 1          ; 1: page 3 holds the BRUN stub, start.s jumps there
br_idx:         .res 1          ; brun_file locals
br_last:        .res 1
br_i:           .res 1
; the result line kept for the next draw shares the write engines'
; catalog_before: that is written during an operation, this one at its
; end and read at the next draw, with only reads in between
note_line       = catalog_before

        .segment "RODATA"
; '1' to '7': Tab, Return, Copy, Drive, Reread, Help, Quit, the numbers
; documented since the first bars; the bar's labels changed since and
; the numbers deliberately did not.
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
;
; data.s keeps the five live values in one block, in the same order as
; the pan_* block, which is two bytes wide per field. So both are one
; loop: X walks the live block by one, Y walks pan_* by two from the
; active side. Naming the ten addresses twice cost thirty bytes more,
; and the asserts in data.s refuse a build where the orders drift.
; ---------------------------------------------------------------------
remember:
        ldy     active
        ldx     #0
@field:
        lda     live_panel,x
        sta     pan_drive,y
        iny
        iny
        inx
        cpx     #PANEL_FIELDS
        bcc     @field
        rts

activate:
        ldy     active
        ldx     #0
@field:
        lda     pan_drive,y
        sta     live_panel,x
        iny
        iny
        inx
        cpx     #PANEL_FIELDS
        bcc     @field
        rts

; ---------------------------------------------------------------------
; confirm -- carry set on Y. Nothing else answers, so a numeric bar key
; cannot confirm a write by accident.
; ---------------------------------------------------------------------
confirm:
        bit     KBDSTROBE       ; a key typed during the operation before
        KEYBAR  23, "Y Yes,N No,ESC Cancel"   ; this is not an answer to it
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
        bcc     @bar
@yes:
        sec
@bar:
        php                     ; the question is answered: the main keys
        jsr     main_bar        ; come back for the operation's duration,
        jsr     present         ; at once -- a Y/N bar left on through a
        plp                     ; long delete looked like an ignored Y
        rts

; main_bar -- the last row of the panels
main_bar:
        KEYBAR  23, "TAB Pan,C Copy,D Del,B Run,/ Drv,? Help,Q Quit"
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
        cpy     #21
        bcc     @divider
        lda     #0
        jsr     draw_panel
        lda     #1
        jsr     draw_panel
        jsr     foot_zone
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
        ldy     #22
        jsr     at_left
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
        beq     @notechk
        PRINT   "CATALOG ERROR - CTRL-R TO REREAD"
@notechk:
        lda     have_note
        beq     @keys
        ldx     #0
@note:
        lda     note_line,x
        sta     screen_image+22*40,x
        inx
        cpx     #40
        bne     @note
@keys:
        jsr     main_bar
        rts

; ---------------------------------------------------------------------
; have_entry -- Z set when the active panel holds nothing to act on:
; either it is empty, or its catalog did not read, and a command that
; needs a file must not run on a snapshot that is not there. Eight keys
; asked those two questions in line; asking them here costs five bytes
; per key instead of ten. The order of the two tests does not matter:
; both must hold, neither writes anything.
; ---------------------------------------------------------------------
have_entry:
        lda     error
        bne     @none
        lda     count
        rts
@none:
        lda     #0
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
        jsr     at_left
        PRINT   "~TAB~: PANEL   ~RET~: OPEN"
        ldy     #4
        jsr     at_left
        PRINT   "~CTRL-K/J~ OR ~I/K~: UP/DOWN"
        ldy     #6
        jsr     at_left
        PRINT   "~ARROWS~ OR ~-/+~: PAGE   ~[/]~: FIRST/LAST"
        ldy     #8
        jsr     at_left
        PRINT   "~/~: DRIVE   ~CTRL-R~: REREAD BOTH   ~Q~: QUIT"
        ldy     #10
        jsr     at_left
        PRINT   "~=~: SAME DISK IN THE OTHER PANEL"
        ldy     #12
        jsr     at_left
        PRINT   "~T/H/G~: VIEW   ~C~: COPY MARKED OR CURSOR"
        ldy     #14
        jsr     at_left
        PRINT   "~SPACE~: TAG  ~CTRL-T/N~: ALL/NONE ~*~: INVERT"
        ldy     #16
        jsr     at_left
        PRINT   "~N~: NEW  ~E~: EDIT  ~D~: DELETE  ~F~: FORMAT"
        ldy     #18
        jsr     at_left
        PRINT   "~L~: LOCK/UNLOCK  ~R~: RENAME  ~B~: BRUN"
        ldy     #20
        jsr     at_left
        PRINT   "~Y~ CONFIRMS A WRITE. UNLOCK TO DELETE."
        KEYBAR  23, "ESC Back"
        jsr     key
        rts

; ---------------------------------------------------------------------
; view -- A = 1 for hex, 0 for text, 4 for text after a binary's header. Shows the first stored sector and says so: it
; is not a claim to have read or checked the whole file.
; ---------------------------------------------------------------------
view:
        sta     vw_mode
        lda     selected
        sta     prv_index
        jsr     preview         ; read once; T and H only redraw it
; view_read -- A = preview status, vw_mode set: the sector is in buffer
view_read:
        sta     error
        beq     @render
        jsr     foot_zone
        lda     error
        cmp     #1
        bne     @nopreview
        PRINT   "READ ERROR"
        jmp     @noted
@nopreview:
        PRINT   "NO PREVIEW / INVALID T-S LIST"
@noted:
        lda     #0
        sta     error
        jmp     keep_note
@render:
        jsr     clear
        ldy     #0
        jsr     at_left
        lda     selected
        jsr     ent_index
        jsr     print_name
        ldy     #1
        jsr     at_left
        PRINT   "PREVIEW: FIRST SECTOR (256 BYTES)"
        lda     vw_mode
        cmp     #1
        bne     @text
        lda     #0
        sta     vw_i
@hexrow:
        lda     vw_i
        clc
        adc     #3
        tay
        jsr     at_left
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
        jsr     at_left
        lda     vw_mode         ; 0, or 4 past a binary's header
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
; copy_file -- tagged files of the active panel, or the cursor when
; nothing is marked. Stays on the two panels. One Y, then each file:
; exclusive create, readback, catalog last. An existing name is skipped
; so the rest of the batch can still land. An uncertain write stops it.
; ---------------------------------------------------------------------
copy_file:
        jsr     activate
        ldx     active
        lda     pan_drive,x
        sta     drive
        lda     selected
        sta     cp_index
        lda     active
        eor     #1
        tax
        lda     pan_drive,x
        sta     cp_dest
        lda     drive
        cmp     cp_dest
        bne     @drives
        lda     #COPY_SAME
        sta     cf_status
        jmp     cf_show
@drives:
        ldx     active
        jsr     tag_count
        sta     cf_marked
        bne     @batch
        jsr     copy_prepare
        sta     cf_status
        jne     cf_dest_show
        jsr     copy_ask_one
        bcs     @one
        jsr     copy_cancel
        jsr     activate
        rts
@one:
        jsr     copy_execute
        sta     cf_status
        jmp     cf_dest_show
@batch:
        jsr     copy_ask_many
        bcc     @out
        lda     #0
        sta     cf_ok
        sta     cf_full
        sta     tg_index
@each:
        lda     tg_index
        cmp     count
        bcs     @done
        lda     tg_index
        ldx     active
        jsr     tag_test
        beq     @next
        lda     tg_index
        sta     cp_index
        jsr     one_copy
        beq     @landed
        cmp     #COPY_EXISTS
        beq     @next
        cmp     #COPY_FULL      ; nothing written: a smaller file may still fit
        bne     @stop
        sta     cf_full
        beq     @next           ; always: the cmp matched
@stop:
        sta     cf_status
        jmp     cf_dest_show
@landed:
        inc     cf_ok
@next:
        inc     tg_index
        jmp     @each
@done:
        lda     #COPY_EXISTS
        ldx     cf_ok
        beq     @none
        lda     #COPY_OK
@none:
        ldx     cf_full         ; one file did not fit: say so, whatever landed
        beq     @say
        lda     #COPY_FULL
@say:
        sta     cf_status
        jmp     cf_dest_show
@out:
        rts

copy_ask_one:
        jsr     copy_banner
        PRINT   "?"
        jmp     copy_ask_bar

copy_ask_many:
        jsr     foot_zone
        PRINT   "COPY "
        lda     cf_marked
        jsr     print_byte
        PRINT   " MARKED?"
copy_ask_bar:
        lda     #0
        sta     inverse
        KEYBAR  22, ""
        jmp     confirm

; copy_banner -- inverse "COPY " and the first 15 name characters
copy_banner:
        jsr     foot_zone
        PRINT   "COPY "
        ldy     #0
@name:
        sty     t1
        lda     cs_name,y
        jsr     put
        ldy     t1
        iny
        cpy     #15
        bcc     @name
        rts

; one_copy -- prepare and write cp_index to cp_dest. Drive is restored
; to the source panel: execute leaves it on the target.
one_copy:
        jsr     activate
        ldx     active
        lda     pan_drive,x
        sta     drive
        jsr     copy_prepare
        bne     @ret
        jsr     copy_banner
        jsr     copy_execute
@ret:
        rts

; cf_dest_show -- a disk copy writes only cp_dest, but a failure on the
; source side (a tagged file that no longer maps, a batch read) leaves
; `drive` on the source after files already landed: reread the
; destination, not wherever the last read happened to be.
cf_dest_show:
        lda     cp_dest
        sta     drive
cf_show:
        jsr     foot_zone
        lda     cf_status
        bne     @notok
        PRINT   "COPIED"
        jmp     result_done
@notok:
        cmp     #COPY_READ
        bne     @notread
        PRINT   "READ ERROR - COPY REFUSED"
        jmp     result_done
@notread:
        cmp     #COPY_EXISTS
        bne     @notexists
        PRINT   "NAME EXISTS - NO OVERWRITE"
        jmp     result_done
@notexists:
        cmp     #COPY_FULL
        bne     @notfull
        PRINT   "DISK OR CATALOG FULL"
        jmp     result_done
@notfull:
        cmp     #COPY_SAME
        bne     @notsame
        PRINT   "SELECT TWO DIFFERENT DRIVES"
        jmp     keep_note       ; nothing was tried: no reread, marks stay
@notsame:
        cmp     #COPY_PROTECTED
        bne     @notprot
        jsr     say_protected
        jmp     result_done
@notprot:
        cmp     #COPY_CHANGED
        bne     @notchanged
        PRINT   "DISK CHANGED - COPY REFUSED"
        jmp     result_done
@notchanged:
        cmp     #COPY_UNCERTAIN
        bne     say_unsupported
        ; fall through: the copy engine latched already, once more is harmless

; say_uncertain -- one copy for copy, delete and format: the result,
; the latch so nothing writes again this run, then the reread.
say_uncertain:
        PRINT   "UNCERTAIN WRITE - STOP"
        lda     #1
        sta     del_fault
        jmp     result_done

say_unsupported:
        PRINT   "UNSUPPORTED / INVALID DOS STRUCTURE"
        jmp     result_done

; say_protected -- the one copy of the message for copy, delete, lock,
; rename and format. RWTS refused before writing: the disk is unchanged.
say_protected:
        PRINT   "DISK IS WRITE PROTECTED"
        rts

; copy_progress -- [********----] on the footer, 32 stars or dashes
; in normal video, as copy_done / copy_total. The panels stay put.
; Drawn only when a cell changes: presenting the screen costs about
; 31 000 cycles, more than the gap before the next sector passes under
; the head, so a redraw at every sector would lose a turn each time.
copy_progress:
        ldy     #22
        jsr     at_left
        lda     #0
        sta     inverse
        lda     copy_total
        ora     copy_total+1
        jeq     @present
        lda     copy_done
        sta     pg_acc
        lda     copy_done+1
        sta     pg_acc+1
        ldx     #5
@times:
        asl     pg_acc
        rol     pg_acc+1
        dex
        bne     @times
        lda     #0
        sta     pg_fill
@div:
        lda     pg_acc
        cmp     copy_total
        lda     pg_acc+1
        sbc     copy_total+1
        bcc     @have
        lda     pg_acc
        sec
        sbc     copy_total
        sta     pg_acc
        lda     pg_acc+1
        sbc     copy_total+1
        sta     pg_acc+1
        inc     pg_fill
        lda     pg_fill
        cmp     #32
        bcc     @div
@have:
        lda     copy_done
        ora     copy_done+1
        beq     @fresh          ; the empty bar at the start is always drawn
        lda     pg_fill
        cmp     pg_last
        jeq     @same
@fresh:
        lda     pg_fill
        sta     pg_last
        lda     #'['
        jsr     put
        lda     #0
        sta     pg_i
@cell:
        lda     pg_i
        cmp     pg_fill
        bcc     @fill
        lda     #'-'
        jmp     @put
@fill:
        lda     #'*'
@put:
        jsr     put
        inc     pg_i
        lda     pg_i
        cmp     #32
        bcc     @cell
        lda     #']'
        jsr     put
@present:
        jmp     present
@same:
        rts

; ---------------------------------------------------------------------
; reload -- read both panels again, keeping each selection by name.
; Two panels on the same drive share one catalog: copy_side fills the
; other, including ent_slot, so '=' and this path never write from a
; half-copied snapshot.
; ---------------------------------------------------------------------
reload:
        lda     #0
        sta     rl_mask
        jmp     reload_go

; reload_written -- after a disk write, reread only panels whose drive
; is the one just written (`drive`). The other snapshot stays; its marks
; were already cleared. Same drive on both sides still costs one catalog.
reload_written:
        lda     drive
        sta     rl_drive
        lda     #1
        sta     rl_mask
reload_go:
        lda     active
        sta     rl_home
        lda     rl_mask
        bne     @filt
        lda     pan_drive
        cmp     pan_drive+1
        jeq     reload_grouped
        jmp     reload_sides
@filt:
        lda     pan_drive
        cmp     rl_drive
        jne     reload_sides
        lda     pan_drive+1
        cmp     rl_drive
        jeq     reload_grouped
reload_sides:
        lda     #0
        sta     active
@side:
        ldx     active
        lda     rl_mask
        beq     @do
        lda     pan_drive,x
        cmp     rl_drive
        bne     @next
@do:
        jsr     activate
        jsr     reload_keep
        lda     #0
        sta     volume
        jsr     catalog
        sta     error
        ldx     active
        jsr     tags_clear
        jsr     reload_restore
        jsr     remember
@next:
        inc     active
        lda     active
        cmp     #2
        jcc     @side
reload_home:
        lda     rl_home
        sta     active
        jmp     activate

reload_grouped:
        lda     #0
        sta     active
        jsr     activate
        jsr     reload_keep
        lda     pan_drive
        sta     drive
        lda     #0
        sta     volume
        jsr     catalog
        sta     error
        ldx     #0
        jsr     tags_clear
        ldx     #1
        jsr     tags_clear
        jsr     reload_restore
        jsr     remember
        lda     #1
        sta     active
        jsr     activate
        jsr     reload_keep
        ldx     #0
        ldy     #1
        jsr     copy_side
        lda     pan_volume
        sta     pan_volume+1
        lda     pan_count
        sta     pan_count+1
        lda     pan_error
        sta     pan_error+1
        lda     pan_drive
        sta     pan_drive+1
        jsr     activate
        jsr     reload_restore
        jsr     remember
        jmp     reload_home

reload_keep:
        lda     #0
        sta     rl_have
        lda     count
        beq     @out
        lda     #1
        sta     rl_have
        lda     selected
        jsr     ent_index
        jsr     ent_ptr
        ldy     #0
@copy:
        lda     (ptr),y
        sta     rl_name,y
        iny
        cpy     #NAME_LEN
        bcc     @copy
@out:
        rts

; reload_restore -- put the cursor back on rl_name when it is still in
; the catalog, else clamp it.
reload_restore:
        lda     rl_have
        beq     @clamp
        lda     #<rl_name
        sta     ptr2
        lda     #>rl_name
        sta     ptr2+1
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
        cmp     (ptr2),y
        bne     @nextentry
        iny
        cpy     #NAME_LEN
        bcc     @compare
        lda     rl_i
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
        jmp     land

; splash -- the same centered layout HELLO prints: title at the top,
; credits and the wait line at the bottom. A2FILECMD is written once.
; It runs from the working area: nothing owns that yet, and the bytes
; are not wanted in the resident afterwards.
        .segment "INIT"
splash:
        jsr     clear
        ldy     #0
        ldx     #15
        jsr     at
        PRINT   "A2FILECMD"
        ldy     #1
        ldx     #14
        jsr     at
        PRINT   "MINI DOS 3.3"
        ldy     #2
        ldx     #17
        jsr     at
        PRINT   VERSION_STR
        ldy     #11
        ldx     #5
        jsr     at
        PRINT   "LOADING .... PLEASE WAIT ...."
        ldy     #13
        ldx     #9
        jsr     at
        PRINT   "CAPS LOCK ON IS NEEDED"
        ldy     #23
        ldx     #10
        jsr     at
        PRINT   "GPL3 VERHILLE ARNAUD"
        jmp     present
        .segment "CODE"

; ---------------------------------------------------------------------
; main -- the set-up runs once, from the working area like the splash;
; the key loop is resident.
; ---------------------------------------------------------------------
        .segment "INIT"
main:
        sta     CLR80STORE      ; IIe: writes must hit main $400, not AUX
        sta     CLR80VID        ; IIe: 40 columns; a leftover 80-column
        sta     ALTCHAROFF      ; card shows a blank or doubled screen
        sta     TXTSET          ; text, page one, lo-res: leftover HGR
        sta     MIXCLR          ; is also a black screen that looks dead
        sta     LOWSCR
        sta     LORES
        jsr     splash
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
        jmp     @loop

        .segment "CODE"
@loop:
        jsr     draw
        lda     #0              ; the result is drawn once: the next key
        sta     have_note       ; gives its row back to the name
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
        jsr     foot_zone
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
        jsr     have_entry
        beq     @notview
        lda     ck
        cmp     #13
        bne     @explicit
        jsr     smart_open      ; RETURN looks inside; carry set: BRUN
        bcc     @notview
        jmp     @leave
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
        jsr     have_entry
        beq     @notcopy
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
        jsr     have_entry
        beq     @nothgr
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
        jsr     have_entry
        beq     @notedit
        jsr     edit_file
@notedit:
        lda     ck
        cmp     #'D'
        bne     @notdel
        jsr     have_entry
        beq     @notdel
        jsr     delete_file
@notdel:
        lda     ck
        cmp     #'L'
        bne     @notlock
        jsr     have_entry
        beq     @notlock
        jsr     lock_file
@notlock:
        lda     ck
        cmp     #'R'
        bne     @notren
        jsr     have_entry
        beq     @notren
        jsr     rename_file
@notren:
        lda     ck
        cmp     #'F'
        bne     @notformat
        jsr     format_file
@notformat:
        lda     ck
        cmp     #'B'
        bne     @notbrun
        jsr     have_entry
        beq     @notbrun
        jsr     brun_file
        bcc     @notbrun
        jmp     @leave
@notbrun:
        jmp     @loop
@leave:
        jsr     clear
        ldy     #0
        jsr     at_left
        PRINT   "A2FC MINI - BACK TO DOS 3.3"
        jmp     present

; ---------------------------------------------------------------------
; mirror_panel -- '=' shows the active panel's disk on the other side,
; entries included, without touching the drive
; ---------------------------------------------------------------------
; The six fields are one block of two-byte pairs (data.s), so the six
; named copies are one loop stepping both indices by two. X starts on
; the active side and Y on the other, exactly as the named copies did.
mirror_panel:
        ldx     active
        txa
        eor     #1
        tay
@field:
        lda     pan_drive,x
        sta     pan_drive,y
        inx
        inx
        iny
        iny
        cpx     #PAN_BYTES      ; 12 from side 0, 13 from side 1: both stop
        bcc     @field          ; after the sixth pair
        jsr     copy_tags
        ldx     active          ; the entries the same way round
        txa
        eor     #1
        tay
        jmp     copy_side

; copy_tags -- the active side's marks onto the other side's. '=' is its
; only caller, so the sides are read from `active` here rather than
; passed in registers: the two blocks are TAG_BYTES apart, so one EOR
; turns the source offset into the destination's.
copy_tags:
        lda     #0
        ldx     active
        beq     @fromleft
        lda     #TAG_BYTES
@fromleft:
        sta     t2
        eor     #TAG_BYTES
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
        ldy     #1
        jmp     copy_side

; ---------------------------------------------------------------------
; brun_file -- B, or RETURN on a binary that is not a picture. Carry set
; once Y was answered: brun_cmd then holds the command DOS runs after A2FC
; Mini has left (start.s), on the slot and the active panel's drive. A
; name DOS could not read back from a typed line -- a comma, or a
; character the catalog could not print (shown as ?) -- is refused.
; ---------------------------------------------------------------------
.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"
.endif
; result_kept -- like result_done when the panel already shows what was
; written (lock and rename patch their entry): no catalog reread, unless
; the other panel is on the same drive, which then reads it once. In the
; low code: entered by jmp from fileops.s, and the resident is full.
result_kept:
        lda     pan_drive
        cmp     pan_drive+1
        jeq     result_done
        jsr     keep_note
        jsr     present
        ldx     #0
        jsr     tags_clear
        ldx     #1
        jmp     tags_clear

brun_file:
        jsr     activate
        jsr     foot_zone
        lda     selected
        jsr     ent_index
        sta     br_idx
        tay
        lda     ent_type,y
        and     #$7F
        cmp     #TYPE_BINARY
        beq     @binary
        PRINT   "BRUN IS FOR BINARY FILES"
        jmp     @refused
@binary:
        lda     br_idx
        jsr     ent_ptr         ; the 30 name characters, as the panel shows them
        ldy     #NAME_LEN
@trim:
        dey
        jmi     @bad            ; all spaces
        lda     (ptr),y
        cmp     #' '
        beq     @trim
        sty     br_last
@scan:
        lda     (ptr),y
        cmp     #','
        jeq     @bad
        cmp     #'?'
        jeq     @bad
        dey
        bpl     @scan
        PRINT   "BRUN "
        lda     br_idx
        jsr     print_name15
        PRINT   "?"
        lda     #0
        sta     inverse
        jsr     confirm
        jcc     @no
        ldx     #BRUN_STUB_LEN-1 ; the stub, then the command after it
@stub:
        lda     brun_stub,x
        sta     BRUN_PAGE,x
        dex
        bpl     @stub
        ldx     #0
@head:
        lda     brun_head,x
        beq     @name
        sta     BRUN_TEXT,x
        inx
        bne     @head
@name:
        stx     br_i
        lda     br_idx
        jsr     ent_ptr         ; again: the prompt used ptr
        ldy     #0
@char:
        lda     (ptr),y
        ora     #$80
        ldx     br_i
        sta     BRUN_TEXT,x
        inc     br_i
        cpy     br_last
        beq     @tail
        iny
        bne     @char
@tail:
        ldx     br_i
        lda     #','|$80
        sta     BRUN_TEXT,x
        inx
        lda     #'S'|$80
        sta     BRUN_TEXT,x
        inx
        lda     slot
        ora     #'0'|$80
        sta     BRUN_TEXT,x
        inx
        lda     #','|$80
        sta     BRUN_TEXT,x
        inx
        lda     #'D'|$80
        sta     BRUN_TEXT,x
        inx
        ldy     active
        lda     pan_drive,y
        ora     #'0'|$80
        sta     BRUN_TEXT,x
        inx
        lda     #$8D
        sta     BRUN_TEXT,x
        inx
        lda     #0
        sta     BRUN_TEXT,x
        lda     #1
        sta     brun_go
        sec
        rts
@bad:
        PRINT   "NAME HAS , OR ? - CANNOT BRUN"
@refused:
        jsr     keep_note
@no:
        clc
        rts

; The page-3 stub (start.s jumps to it once A2FC Mini has left): nothing
; of A2FC Mini runs after the program, which may load over it. It prints
; the command through COUT, where DOS takes a line starting with Ctrl-D.
; DOS reads such lines only from a running program, so CURLIN's high byte
; is cleared first, which also covers a start from the DOS prompt. A
; program that returns lands on DOS's warm start.
brun_stub:
        .byte   $A9, $00                ; LDA #0
        .byte   $85, CURLIN_HI          ; STA CURLIN+1
        .byte   $A2, $00                ; LDX #0
        .byte   $BD, <BRUN_TEXT, >BRUN_TEXT ; LDA text,X
        .byte   $F0, $06                ; BEQ to the JMP
        .byte   $20, <COUT, >COUT       ; JSR COUT
        .byte   $E8                     ; INX
        .byte   $D0, $F5                ; BNE to the LDA
        .byte   $4C, <DOS_WARM, >DOS_WARM ; JMP DOS warm start
BRUN_STUB_LEN   = * - brun_stub
BRUN_TEXT       = BRUN_PAGE + BRUN_STUB_LEN
        .assert BRUN_TEXT + 48 <= DOS_WARM, error, "BRUN stub and command reach the DOS vectors"
; the start of the command, high ASCII as DOS reads a typed line
brun_head:
        .byte   $8D, $84, 'B'|$80, 'R'|$80, 'U'|$80, 'N'|$80, ' '|$80, 0
        .segment "CODE"

; ---------------------------------------------------------------------
; smart_open -- RETURN. Reads the first data sector once, writes nothing,
; and picks the view from what the file holds:
;   T: text, or hex when the bytes are not text;
;   B whose DOS header matches its size: hi-res for an 8 KB load at $2000
;     or $4000; hex when it cannot run (empty, below $0800, reaching DOS's
;     buffers at $9600); text when the bytes are text; else BRUN after Y;
;   B without a matching header: a raw hi-res page at 32-34 sectors, else
;     hex; anything else: hex.
; Carry set when brun_file leaves for DOS.
; ---------------------------------------------------------------------
smart_open:
        lda     #1              ; a failed read shows as hex, which reports it
        sta     vw_mode
        lda     selected
        sta     prv_index
        jsr     preview
        bne     @show
        lda     selected
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$7F
        sta     t2              ; 0 for T: a NUL ends the text
        bne     @nottext
        ldx     #255
        ldy     #0
        jsr     looks_text
        bcs     @text
@hex:
        lda     #1
        .byte   $2C             ; BIT abs: skips the LDA #0
@text:
        lda     #0
@mode:
        sta     vw_mode
        lda     #CAT_OK
@show:
        jsr     view_read
        clc
        rts
@hgr:
        jsr     show_hgr
        clc
        rts
@raw:
        lda     ent_sechi,y     ; no DOS header: a raw hi-res page by size
        bne     @hex
        lda     ent_seclo,y
        cmp     #32
        bcc     @hex
        cmp     #35
        bcc     @hgr
        bcs     @hex
@nottext:
        cmp     #TYPE_BINARY
        bne     @hex
        clc                     ; data sectors the header asks for:
        lda     buffer+2        ; (length + 4 + 255) / 256
        adc     #$03
        lda     buffer+3
        adc     #$01
        bcs     @raw
        sta     t3
        lda     ent_sechi,y
        bne     @raw
        lda     ent_seclo,y     ; the catalog adds 1 to 3 T/S lists
        sec
        sbc     t3
        bcc     @raw
        sbc     #1
        cmp     #3
        bcs     @raw
        lda     buffer          ; an 8 KB load at $2000 or $4000
        bne     @code
        lda     buffer+1
        cmp     #$20
        beq     @page
        cmp     #$40
        bne     @code
@page:
        lda     buffer+3
        cmp     #$1F
        beq     @hgr
        cmp     #$20
        beq     @hgr
@code:
        lda     buffer+2
        ora     buffer+3
        beq     @farhex         ; nothing to run
        lda     buffer+1
        cmp     #$08            ; pages 0-7: stack, DOS vectors, screen
        bcc     @farhex
        clc
        lda     buffer
        adc     buffer+2
        lda     buffer+1
        adc     buffer+3
        bcs     @farhex
        cmp     #DOS_BUFFERS_HI
        bcs     @farhex
        ldx     buffer+2        ; the bytes after the header, up to its length
        lda     buffer+3
        beq     @scan
        ldx     #252
@scan:
        ldy     #4
        jsr     looks_text
        bcc     @run
        lda     #4              ; text, after the header
        jmp     @mode
@farhex:
        jmp     @hex
@run:
        jmp     brun_file

; looks_text -- X bytes (1-255) of buffer from Y; t2 = 0 stops at a NUL,
; where a T file ends. Carry set when at most one byte in 16 of those
; looked at is neither printable nor a RETURN.
looks_text:
        lda     #0
        sta     t3              ; bytes looked at
        sta     t4              ; bytes that are not text
@byte:
        lda     buffer,y
        bne     @some
        lda     t2
        beq     @done           ; T: the text ends here
        bne     @bad
@some:
        and     #$7F
        cmp     #$0D
        beq     @ok
        cmp     #$20
        bcs     @ok
@bad:
        inc     t4
@ok:
        inc     t3
        iny
        beq     @done           ; the sector ends
        dex
        bne     @byte
@done:
        lda     t3
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        cmp     t4
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
        sta     CLR80STORE      ; IIe: $2000 is main, 40 columns
        sta     CLR80VID
        lda     TXTCLR          ; any access trips these switches
        lda     MIXCLR
        lda     LOWSCR
        lda     HIRES
        jsr     key_raw
        sta     CLR80STORE
        sta     CLR80VID
        lda     TXTSET
        lda     LORES
        lda     LOWSCR
        rts
@fail:
        jsr     foot_zone
        lda     hg_status
        cmp     #1
        bne     @bad
        PRINT   "READ ERROR"
        jmp     keep_note
@bad:
        PRINT   "NOT A PICTURE / INVALID T-S LIST"
        jmp     keep_note

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
        lda     #0
        sta     ask_kind
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
        jsr     activate
        lda     selected
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$7F
        cmp     #TYPE_TEXT
        beq     @text
        jsr     foot_zone
        PRINT   "EDIT IS FOR TEXT FILES"
        jmp     keep_note
@text:
        lda     selected
        jsr     ent_index
        tay
        lda     ent_sechi,y
        jne     @big
        lda     ent_seclo,y
        cmp     #34             ; 32 data sectors plus one T/S list
        jcs     @big
        lda     selected
        sta     prv_index
        jsr     load_file
        sta     hg_status
        bne     @fail
        lda     load_more       ; the catalog count lied: a 33rd data
        jne     @big            ; sector exists, never save it truncated
        jsr     measure_text    ; carry: 8 KB of text leave no room for
        jcs     @big            ; the NUL, and the last byte would be cut
        jsr     edit_text
        jcc     @out
        lda     #0
        sta     ask_kind
        jsr     ask_name
        bcc     @out
        jsr     name_to_cs
        jmp     save_new
@fail:
        jsr     foot_zone
        lda     hg_status
        cmp     #CAT_READ
        bne     @notread
        PRINT   "READ ERROR - NOT LOADED"
        jmp     keep_note
@notread:
        PRINT   "INVALID T-S LIST - NOT LOADED"
        jmp     keep_note
@big:
        jsr     foot_zone
        PRINT   "FILE TOO LARGE TO EDIT"
        jmp     keep_note
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

save_new:
        jsr     sectors_from_len
        jsr     clear
        ldy     #2
        jsr     at_left
        PRINT   "CHECKING DISK..."
        jsr     present
        jsr     create_prepare
        sta     cf_status
        beq     @planned
        cmp     #COPY_EXISTS    ; the text is still in the working area:
        jne     copy_report     ; ask for another name rather than lose it
        lda     #2
        sta     ask_kind
        jsr     ask_name
        bcc     @out            ; Escape gives the text up
        jsr     name_to_cs
        jmp     save_new
@planned:
        jsr     clear
        ldy     #0
        ldx     #0
        lda     #40
        jsr     zone
        PRINT   "CREATE TEXT FILE"
        lda     #0
        sta     inverse
        ldy     #2
        jsr     at_left
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
        jsr     at_left
        lda     data_count
        jsr     print_byte
        PRINT   " SECTORS - NEW FILE ONLY"
        jsr     confirm
        bcs     @go
        jsr     copy_cancel
@out:
        rts
@go:
        jsr     clear
        ldy     #2
        jsr     at_left
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
; Stays on the two panels. Footer prompt, then each file.
; ---------------------------------------------------------------------
delete_file:
        jsr     activate
        lda     #0
        sta     del_audited     ; one whole-disk audit per batch
        ldx     active
        jsr     tag_count
        sta     tg_n
        jsr     foot_zone
        lda     tg_n
        bne     @many
        PRINT   "DELETE "
        lda     selected
        jsr     ent_index
        jsr     print_name15
        PRINT   "?"
        jmp     @ask
@many:
        PRINT   "DELETE "
        lda     tg_n
        jsr     print_byte
        PRINT   " MARKED?"
@ask:
        lda     #0
        sta     inverse
        jsr     confirm
        bcc     @out
        lda     #DEL_OK
        sta     hg_status
        lda     tg_n
        bne     @tagged
        lda     selected
        sta     del_index
        jsr     one_delete
        sta     hg_status
        jmp     @show
@tagged:
        lda     #0
        sta     tg_index
        sta     cf_ok           ; deleted
        sta     cf_marked       ; refused as locked
@each:
        lda     tg_index
        cmp     count
        bcs     @summary
        lda     tg_index
        ldx     active
        jsr     tag_test
        beq     @next
        lda     tg_index
        sta     del_index
        jsr     one_delete
        sta     hg_status
        bne     @notdone
        inc     cf_ok
        bne     @next           ; always: 105 at most
@notdone:
        cmp     #DEL_LOCKED
        bne     @show           ; anything else stops the batch
        inc     cf_marked
@next:
        inc     tg_index
        jmp     @each
@show:
        jmp     del_show
@summary:
        jsr     batch_count     ; "3 DELETED, 1 LOCKED": every file counted
        PRINT   "DELETED"
        jsr     batch_skipped
        beq     @said
        PRINT   "LOCKED"
@said:
        jmp     result_done
@out:
        rts

; batch_count -- a tagged batch ran to its end: the footer, then cf_ok
; and a space. batch_skipped then adds ", n " when cf_marked files were
; refused without a write, Z clear so the caller names why.
batch_count:
        jsr     foot_zone
        lda     cf_ok
batch_number:
        jsr     print_byte
        lda     #' '
        jmp     put

batch_skipped:
        lda     cf_marked
        beq     @none
        PRINT   ", "
        lda     cf_marked
        jsr     batch_number
        lda     #1              ; Z clear
@none:
        rts

; batch_done -- a batch stopped by a refusal: "n DONE, " first when
; files were already changed, so the refusal never reads as nothing
batch_done:
        lda     tg_n
        beq     @none
        lda     cf_ok
        beq     @none
        jsr     print_byte
        PRINT   " DONE, "
@none:
        rts

foot_zone:
        ldy     #21
        ldx     #0
        lda     #40
        jmp     zone

; at_left -- Y = row, cursor at column 0
at_left:
        ldx     #0
        jmp     at

; print_name15 -- A = array index: the first 15 name characters, for the
; DELETE / LOCK / UNLOCK prompts. put builds its own screen pointer in
; ptr, so the name is read through ptr2 or only its first letter shows.
print_name15:
        jsr     ent_ptr
        lda     ptr
        sta     ptr2
        lda     ptr+1
        sta     ptr2+1
        ldy     #0
@ch:
        sty     t1
        lda     (ptr2),y
        jsr     put
        ldy     t1
        iny
        cpy     #15
        bcc     @ch
        rts

one_delete:
        jsr     delete_prepare
        bne     @out
        jsr     delete_execute
@out:
        rts

; del_show -- the result of one delete on the footer, then result_done:
; entered by jmp, never by jsr, because the shared say_uncertain and
; say_unsupported end at result_done themselves.
del_show:
        jsr     foot_zone
        jsr     batch_done
        lda     hg_status
        bne     @notok
        PRINT   "DELETED"
        jmp     result_done
@notok:
        cmp     #DEL_LOCKED
        bne     @notlock
        PRINT   "LOCKED - NOT DELETED"
        jmp     result_done
@notlock:
        cmp     #DEL_CHANGED
        bne     @notchg
        PRINT   "DISK CHANGED - DELETE REFUSED"
        jmp     result_done
@notchg:
        cmp     #DEL_READ
        bne     @notread
        PRINT   "READ ERROR - DELETE REFUSED"
        jmp     result_done
@notread:
        cmp     #DEL_PROTECTED
        bne     @notprot
        jsr     say_protected
        jmp     result_done
@notprot:
        cmp     #DEL_UNCERTAIN
        bne     @bad
        jmp     say_uncertain
@bad:
        jmp     say_unsupported

; keep_note -- remember row 21, the question and result line. The next
; draw shows the two panels with that result on row 22 until a key.
keep_note:
        ldx     #0
@copy:
        lda     screen_image+21*40,x
        sta     note_line,x
        inx
        cpx     #40
        bne     @copy
        lda     #1
        sta     have_note
        rts

; result_done -- show the result, reread the written disk, return to
; the panels. Marks on both sides are consumed: a tagged copy must not
; leave the source marked for a second pass. Ctrl-R still reads both.
result_done:
        jsr     keep_note
        jsr     present
        ldx     #0
        jsr     tags_clear
        ldx     #1
        jsr     tags_clear
        jmp     reload_written


