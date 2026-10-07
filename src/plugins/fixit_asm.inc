; fixit_asm.inc -- two small routines of the FIXIT/REPAIR walker written in
; assembly for their size (fixit_walk.h, bug hunt 2): cc65 spent 110 bytes
; on the path loop and 100 on the 512-byte comparison, where each is some
; thirty here. The host harnesses (-DFIXIT_HOST) compile the C versions.
;
; void __fastcall__ first_part(char* dst, const char* path);
;   "/VOL": the first component of a ProDOS path -- the leading slash, then
;   everything up to the next slash or the end, NAME_LEN - 1 characters at
;   most, zero-terminated. Any first character is kept, as the C did.
;
; unsigned char __fastcall__ samebytes(const unsigned char* a, const unsigned char* b, unsigned int n);
;   1 when the first n bytes of the two buffers are the same, 0 otherwise
;   (REPAIR: the 512 bytes read back after a write, the 39 of the header).
;
; void __fastcall__ swap(unsigned char* p, unsigned char n);
;   exchanges n bytes (1 to 5) between p and nv[], the patch of a directory
;   correction: done once it puts the correction in, done again it is the
;   restore (REPAIR, fix()).

        .importzp ptr1, ptr2, tmp1, tmp2
        .import popax
        .export _first_part
.ifdef REPAIR_ASM
        .import _nu
        .export _samebytes, _swap
.endif

        .segment "CODE"

_first_part:
        sta     ptr1
        stx     ptr1+1          ; path
        jsr     popax
        sta     ptr2
        stx     ptr2+1          ; dst
        ldy     #0
@next:  lda     (ptr1),y
        beq     @end
        cpy     #0
        beq     @keep           ; the first character, whatever it is
        cmp     #'/'
        beq     @end
@keep:  sta     (ptr2),y
        iny
        cpy     #16             ; NAME_LEN - 1
        bne     @next
@end:   lda     #0
        sta     (ptr2),y
        rts

.ifdef REPAIR_ASM
_samebytes:
        sta     tmp1
        stx     tmp2            ; n, counted down
        jsr     popax
        sta     ptr2
        stx     ptr2+1          ; b
        jsr     popax
        sta     ptr1
        stx     ptr1+1          ; a
        ldy     #0
@cmp:   lda     tmp1
        ora     tmp2
        beq     @same           ; n bytes compared
        lda     (ptr1),y
        cmp     (ptr2),y
        bne     @differ
        iny
        bne     :+
        inc     ptr1+1
        inc     ptr2+1
:       lda     tmp1
        bne     :+
        dec     tmp2
:       dec     tmp1
        jmp     @cmp            ; the count is tested at the top
@same:  lda     #1
        .byte   $2C             ; BIT abs: skips the lda #0
@differ:
        lda     #0
        ldx     #0
        rts

_swap:
        sta     tmp1            ; n, 1 to 5 -- popax uses Y, so not kept there
        jsr     popax
        sta     ptr1
        stx     ptr1+1          ; p
        ldy     tmp1            ; swapped from the last byte down
        dey
@byte:  lda     (ptr1),y
        pha
        lda     _nu,y
        sta     (ptr1),y
        pla
        sta     _nu,y
        dey
        bpl     @byte
        rts
.endif
