; screen.s -- compose in RAM, then touch only what changed.
;
; The 40-column page is never drawn into directly. Every frame is built in
; screen_image, and present() copies across only the cells whose byte
; differs, once each. That is what keeps a 1 MHz II+ quiet: a keystroke
; that changes nothing writes nothing, and the POM2 bench proves it with
; write watchpoints on all 960 cells.
;
; put() clobbers A, X and Y. Anything a caller needs across a put() goes
; in t1..t7 or in BSS, never in a register.

        .include "mini.inc"

        .export present, present_top, at, put, inline_text, clear, zone
        .export number, hexbyte, filetype, keys_bar, keys_bar_inline
        .export save_holes, restore_holes

        .import screen_image, slot

        .segment "BSS"
digits:         .res 5          ; a 16-bit value never needs more
hole_save:      .res 8          ; $0478+slot through $07F8+slot, one every $80

        .segment "RODATA"

; screen_image + row*40
img_lo:
        .repeat 24, r
        .byte   <(screen_image + r*40)
        .endrep
img_hi:
        .repeat 24, r
        .byte   >(screen_image + r*40)
        .endrep

; the physical page: $400 + (row & 7)*128 + (row >> 3)*40
scr_lo:
        .repeat 24, r
        .byte   <(SCREEN + (r & 7)*128 + (r >> 3)*40)
        .endrep
scr_hi:
        .repeat 24, r
        .byte   >(SCREEN + (r & 7)*128 + (r >> 3)*40)
        .endrep

hex_digits:
        .byte   "0123456789ABCDEF"
type_codes:
        .byte   0, 1, 2, 4, 8, 16
type_letters:
        .byte   "TIABSR"

        .segment "CODE"

; ---------------------------------------------------------------------
; present -- the composed image reaches the screen here, and only here.
; ---------------------------------------------------------------------
present:
        ldx     #0
@row:
        lda     scr_lo,x
        sta     ptr
        lda     scr_hi,x
        sta     ptr+1
        lda     img_lo,x
        sta     ptr2
        lda     img_hi,x
        sta     ptr2+1
        ldy     #39
@cell:
        lda     (ptr2),y
        cmp     (ptr),y
        beq     @same
        sta     (ptr),y
@same:
        dey
        bpl     @cell
        inx
        cpx     #24
        bcc     @row
        rts

; Only the four banner rows. The Disk II current-track bytes sit in $400
; where a full present() would overwrite them; the first catalog still
; needs those values.
present_top:
        ldx     #0
@row:
        lda     scr_lo,x
        sta     ptr
        lda     scr_hi,x
        sta     ptr+1
        lda     img_lo,x
        sta     ptr2
        lda     img_hi,x
        sta     ptr2+1
        ldy     #39
@cell:
        lda     (ptr2),y
        sta     (ptr),y
        dey
        bpl     @cell
        inx
        cpx     #4
        bcc     @row
        rts

; The slot's screen holes: $0478+slot, then the same offset every $80
; bytes through $07F8+slot, the 8 bytes of each $80 block no row shows.
; DOS 3.3 RWTS keeps the current track of drive 1 at $0478+slot and of
; drive 2 at $04F8+slot: it turns IBSLOT (slot*16) into the slot number
; (TXA, four LSRs, TAY) before indexing them. They were once taken at
; $0478+slot*16, which are visible cells (slot 6: column 8 of rows 5,
; 8, 11, 14, 17, 20 and 23): every RWTS call then put stale characters
; back on the screen.
hole_ptr:
        lda     slot
        clc
        adc     #$78
        sta     ptr
        lda     #$04
        adc     #0
        sta     ptr+1
        rts

save_holes:
        jsr     hole_ptr
        ldx     #0
@one:
        ldy     #0
        lda     (ptr),y
        sta     hole_save,x
        lda     ptr
        clc
        adc     #$80
        sta     ptr
        bcc     @noc
        inc     ptr+1
@noc:
        inx
        cpx     #8
        bcc     @one
        rts

restore_holes:
        jsr     hole_ptr
        ldx     #0
@one:
        lda     hole_save,x
        ldy     #0
        sta     (ptr),y
        lda     ptr
        clc
        adc     #$80
        sta     ptr
        bcc     @noc
        inc     ptr+1
@noc:
        inx
        cpx     #8
        bcc     @one
        rts

; ---------------------------------------------------------------------
; at -- Y = row, X = column
; ---------------------------------------------------------------------
at:
        sty     row
        stx     col
        rts

; ---------------------------------------------------------------------
; put -- A = character. Off-screen positions are dropped, not wrapped,
; so a long name cannot run into the next row.
; ---------------------------------------------------------------------
put:
        sta     t0
        lda     col
        cmp     #40
        bcs     @out
        ldx     row
        cpx     #24
        bcs     @out
        clc
        adc     img_lo,x
        sta     ptr
        lda     img_hi,x
        adc     #0
        sta     ptr+1
        lda     t0
        cmp     #'a'
        bcc     @upper
        cmp     #'z'+1
        bcs     @upper
        and     #$DF            ; the II+ has no lower case
@upper:
        ldy     inverse
        beq     @normal
        and     #$3F
        jmp     @store
@normal:
        ora     #$80
@store:
        ldy     #0
        sta     (ptr),y
        inc     col
@out:
        rts

; ---------------------------------------------------------------------
; inline_text -- prints the NUL-terminated string that follows the call
; and resumes after it. Saves the address setup at every message site.
; ---------------------------------------------------------------------
inline_text:
        pla
        sta     w0
        pla
        sta     w0+1            ; w0 = address of the byte before the text
        ldy     #1
@loop:
        lda     (w0),y
        beq     @done
        sty     t1
        jsr     put
        ldy     t1
        iny
        bne     @loop
@done:
        tya                     ; Y indexes the NUL; resume just after it
        clc
        adc     w0
        sta     t1
        lda     w0+1
        adc     #0
        pha
        lda     t1
        pha
        rts

; ---------------------------------------------------------------------
; clear -- every cell becomes a normal-video space, inverse off
; ---------------------------------------------------------------------
clear:
        lda     #0
        sta     inverse
        lda     #$A0
        ldx     #0
@pages:
        sta     screen_image,x
        sta     screen_image+$100,x
        sta     screen_image+$200,x
        inx
        bne     @pages
        ldx     #SCREEN_CELLS-$300
@tail:
        dex
        sta     screen_image+$300,x
        bne     @tail
        rts

; ---------------------------------------------------------------------
; zone -- Y = row, X = column, A = width. Leaves inverse video ON and
; the cursor back at the start, ready for a title.
; ---------------------------------------------------------------------
zone:
        sty     t6
        stx     t7
        tax                     ; width
        ldy     t6
        sty     row
        lda     t7
        sta     col
        lda     #1
        sta     inverse
        cpx     #0
        beq     @back
@loop:
        stx     t5
        lda     #' '
        jsr     put
        ldx     t5
        dex
        bne     @loop
@back:
        ldy     t6
        ldx     t7
        jmp     at

; ---------------------------------------------------------------------
; number -- num holds a 16-bit value; prints it without leading zeros
; ---------------------------------------------------------------------
number:
        ldx     #0
@digit:
        stx     t3
        jsr     div10
        ora     #'0'
        ldx     t3
        sta     digits,x
        inx
        lda     num
        ora     num+1
        bne     @digit
@print:
        dex
        stx     t3
        lda     digits,x
        jsr     put
        ldx     t3
        bne     @print
        rts

; num /= 10, remainder in A
div10:
        lda     #0
        sta     t4
        ldx     #16
@bit:
        asl     num
        rol     num+1
        rol     t4
        lda     t4
        sec
        sbc     #10
        bcc     @keep
        sta     t4
        inc     num
@keep:
        dex
        bne     @bit
        lda     t4
        rts

; ---------------------------------------------------------------------
; hexbyte -- A = byte, printed as two upper-case digits
; ---------------------------------------------------------------------
hexbyte:
        pha
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        tax
        lda     hex_digits,x
        jsr     put
        pla
        and     #$0F
        tax
        lda     hex_digits,x
        jmp     put

; ---------------------------------------------------------------------
; filetype -- A = DOS type byte, returns its letter, '?' when unknown
; ---------------------------------------------------------------------
filetype:
        and     #$7F
        ldx     #5
@look:
        cmp     type_codes,x
        beq     @found
        dex
        bpl     @look
        lda     #'?'
        rts
@found:
        lda     type_letters,x
        rts

; ---------------------------------------------------------------------
; keys_bar -- A = row, w1 = spec address. On return t2 indexes the NUL.
;
; "TAB Panel,RET Open" becomes an inverse key block then a plain label.
; A one-character key is centred, so "C Copy" reads as " C  COPY".
; ---------------------------------------------------------------------
keys_bar:
        tax                     ; row
        lda     img_lo,x
        sta     ptr
        lda     img_hi,x
        sta     ptr+1
        lda     #$A0
        ldy     #39
@blank:
        sta     (ptr),y
        dey
        bpl     @blank
        stx     row
        ldy     #0
        sty     col
        sty     t2              ; index into the spec
@field:
        ldy     t2
        lda     (w1),y
        beq     @end
        lda     #1
        sta     inverse
        lda     col
        sta     t6              ; where this key block starts
        ldy     t2
        iny
        lda     (w1),y          ; a single-character key is padded left
        cmp     #' '
        bne     @keys
        lda     #' '
        jsr     put
@keys:
        ldy     t2
        lda     (w1),y
        beq     @pad
        cmp     #' '
        beq     @pad
        inc     t2
        jsr     put
        jmp     @keys
@pad:
        lda     t6
        clc
        adc     #3
        sta     t5
@padloop:
        lda     col
        cmp     t5
        bcs     @label
        lda     #' '
        jsr     put
        jmp     @padloop
@label:
        lda     #0
        sta     inverse
@labelloop:
        ldy     t2
        lda     (w1),y
        beq     @end
        cmp     #','
        beq     @comma
        inc     t2
        jsr     put
        jmp     @labelloop
@comma:
        inc     t2              ; step over the comma, space out the next
        lda     #' '
        jsr     put
        ldy     t2
        jmp     @field
@end:
        rts

; ---------------------------------------------------------------------
; keys_bar_inline -- A = row, spec follows the call. On return t2 indexes
; the terminating NUL, which is how the resume address is found.
; ---------------------------------------------------------------------
keys_bar_inline:
        tax                     ; keep the row
        pla
        sta     ptr2
        pla
        sta     ptr2+1          ; ptr2 = address of the byte before it
        lda     ptr2
        clc
        adc     #1
        sta     w1
        lda     ptr2+1
        adc     #0
        sta     w1+1
        txa
        jsr     keys_bar
        lda     w1
        clc
        adc     t2
        sta     ptr2
        lda     w1+1
        adc     #0
        pha
        lda     ptr2
        pha
        rts
