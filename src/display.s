; Resident presentation helpers, same cc65 ABI on both CPUs. Only MAIN
; scratch and the conio text screen (MAIN/AUX $0400-$07FF) are written.
; No file I/O, overlay loads or AUX /RAM storage. Conio may clobber ptr1:
; reload it before each access, keeping the parser state in resident BSS.
        .export _keys_bar, _hex_value
        .import _gotoxy, _revers, _cputc, popa, pusha
        .importzp ptr1, ptr2
        .bss
kb_ptr: .res 2
kb_len: .res 1
kb_i:   .res 1
        .code
_keys_bar:
        sta kb_ptr
        stx kb_ptr+1
        jsr popa                ; x, the first argument
        jsr pusha
        lda #23
        jsr _gotoxy
kb_item:
        jsr kb_peek
        bne kb_scan
        rts
kb_scan:
        cmp #' '
        beq kb_key
        iny
        lda (ptr1),y
        bne kb_scan
kb_key:
        sty kb_len
        lda #1
        jsr _revers
        lda kb_len
        cmp #1
        bne kb_three
        lda #' '
        jsr _cputc
        jsr kb_peek
        jsr _cputc
        lda #' '
        jsr _cputc
        jmp kb_label
kb_three:
        lda #0
        sta kb_i
kb_char:
        jsr kb_peek
        ldy kb_i
        cpy kb_len
        lda #' '
        bcs kb_put
        lda (ptr1),y
kb_put:
        jsr _cputc
        inc kb_i
        lda kb_i
        cmp #3
        bne kb_char
kb_label:
        lda #0
        jsr _revers
        lda kb_ptr
        clc
        adc kb_len
        sta kb_ptr
        bcc :+
        inc kb_ptr+1
:       jsr kb_peek
        cmp #' '
        bne kb_text
        jsr kb_next
kb_text:
        jsr kb_peek
        beq kb_done
        cmp #','
        beq kb_separator
        jsr _cputc
        jsr kb_next
        jmp kb_text
kb_separator:
        lda #' '
        jsr _cputc
        jsr kb_next
        jmp kb_item
kb_done:
        rts
kb_peek:
        lda kb_ptr
        sta ptr1
        lda kb_ptr+1
        sta ptr1+1
        ldy #0
        lda (ptr1),y
        rts
kb_next:
        inc kb_ptr
        bne :+
        inc kb_ptr+1
:       rts

; prompt() supplies only uppercase hex digits, at most four per call.
; Return the same low 16 bits as the original C; no library calls.
        .segment "LC"
_hex_value:
        sta ptr1
        stx ptr1+1
        lda #0
        sta ptr2
        sta ptr2+1
        tay
hv_next:
        lda (ptr1),y
        beq hv_done
        cmp #'9'+1
        bcc :+
        adc #8                  ; carry set: low nibble A..F becomes 10..15
:       and #$0F
        ldx #4
hv_shift:
        asl ptr2
        rol ptr2+1
        dex
        bne hv_shift
        ora ptr2
        sta ptr2
        iny
        bne hv_next
hv_done:
        lda ptr2
        ldx ptr2+1
        rts

; A heartbeat at row 21, column 79: odd columns of the 80-column display
; are MAIN RAM ($06F7). No conio state, soft switch, AUX or file is touched.
; CODE is permanently resident and covered by the normal layout checks.
        .export _activity_tick
        .bss
activity_phase: .res 1
        .code
_activity_tick:
        inc activity_phase
        lda activity_phase
        and #3
        tax
        lda activity_chars,x
        sta $06F7
        rts
activity_chars:
        .byte $FC, $AF, $AD, $DC  ; normal-video | / - backslash

; Temporary phase on the information row. Result/error row 22 is preserved.
; The panels redraw row 21 when the operation returns. No disk or AUX above
; the normal text page is used; the conio helpers select their text bank.
        .export _activity_begin
        .import _cclearxy, _cputsxy
        .code
_activity_begin:
        pha
        txa
        pha
        lda #0
        jsr pusha
        lda #21
        jsr pusha
        lda #79
        jsr _cclearxy
        lda #0
        jsr pusha
        lda #21
        jsr pusha
        pla
        tax
        pla
        jmp _cputsxy

; Exactly 38 cells, clipped and padded, with the caller's inverse state.
; Shared scratch with keys_bar; neither calls the other or runs in an IRQ.
        .export _panel_label
        .code
_panel_label:
        sta kb_ptr
        stx kb_ptr+1
        lda #38
        sta kb_len
@cell:  jsr kb_peek
        beq @space
        pha
        jsr kb_next
        pla
        jmp @put
@space: lda #' '
@put:   jsr _cputc
        dec kb_len
        bne @cell
        rts

; Minimum width 15, like %-15s: a 15-character directory plus slash
; occupies 16 cells. Input names are bounded by the directory reader.
        .export _entry_label
_entry_label:
        sta kb_ptr
        stx kb_ptr+1
        lda #15
        sta kb_len
@char:  jsr kb_peek
        beq @pad
        jsr _cputc
        jsr kb_next
        lda kb_len
        beq @char
        dec kb_len
        jmp @char
@pad:   lda kb_len
        beq @done
        lda #' '
        jsr _cputc
        dec kb_len
        bne @pad
@done:  rts

; Count marks in one pass without repeatedly computing index/8 and bit
; shifts in C. Ignore unused trailing bits, as the old per-entry loop did.
; Panel.count is at 64 and Panel.tags at 76 (a2fc_plugin.h ABI).
        .export _tag_count
        .importzp tmp1, tmp2, tmp3
_tag_count:
        sta ptr1
        stx ptr1+1
        ldy #64
        lda (ptr1),y
        tax
        lda #0
        sta tmp1
        cpx #0
        beq @done
        ldy #76
@byte:  lda (ptr1),y
        sta tmp2
        lda #8
        sta tmp3
@bit:   lsr tmp2
        bcc :+
        inc tmp1
:       dex
        beq @done
        dec tmp3
        bne @bit
        iny
        bne @byte
@done:  lda tmp1
        ldx #0
        rts
