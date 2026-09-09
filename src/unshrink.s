; unshrink.s -- the core of A2FILE/UNSHRINK.PLG: the two ShrinkIt LZWs
; (LZW/1 of ProDOS 8 ShrinkIt, LZW/2 of GS/ShrinkIt) and their RLE, one
; 4096-byte chunk per call. After nufxlib (Lzw.c: Nu_ExpandLZW1/2,
; Nu_ExpandRLE, Nu_LZWGetCode), verified against tools/mkshk.py, itself
; verified byte for byte against nulib2.
;
; The overlay is loaded at $1B00; this core is its head, and the C driver
; (a2fc.c, unshrink_entry) copies it to AUX at the same address before any
; call (aux_copy). _us_chunk switches RAMRD and RAMWRT to AUX: from then on
; the 6502 EXECUTES the AUX copy, and reads and writes AUX, where the
; dictionary, the decode stack, the input window and the output chunk
; live. The zero page and the 6502 stack ($0000-$01FF) do not change
; bank: the parameters go through them (cc65's ptr1..ptr4, tmp1..tmp4, which
; the callee is allowed to clobber). The LZW state (entry, old, final, fresh,
; the bit buffer) lives in the variables of this file -- in the AUX copy,
; the only one the core touches -- and survives from one chunk to the next,
; as LZW/2 requires. No interrupts meanwhile (sei): the Mockingboard must be
; stopped beforehand (music_stop), and the mouse reader has none.
;
;   void __fastcall__ us_init(unsigned int fmt_esc);
;       A = format (2 LZW/1, 3 LZW/2), X = the RLE escape byte, read by
;       the driver from the stream header. To be called AFTER the copy to
;       AUX: writes only to AUX (RAMWRT), execution stays in MAIN.
;   unsigned int __fastcall__ us_chunk(unsigned int in_addr);
;       Decodes ONE chunk whose header is at in_addr, in the AUX input
;       window that the driver keeps filled with at least one whole chunk
;       (at most 4096 + 4 bytes), and puts its 4096 bytes in OUTBUF (AUX).
;       Returns the number of input bytes consumed, header included. The
;       driver copies OUTBUF back to MAIN with aux_copy and writes it to the
;       file, truncating the last chunk at thread_eof.
;
; Map of AUX (the C driver repeats these addresses):
;   PREFIX $2000-$3FFF  prefix[code], 2 bytes, at PREFIX + code*2
;   SUFFIX $4000-$4FFF  suffix[code], 1 byte
;   STACK  $5000-$5FFF  the decode stack (4096 at worst)
;   INBUF  $6000-$7FFF  the input window, 8 KB
;   OUTBUF $8000-$8FFF  the decoded chunk, 4096 bytes
;   TMPBUF $9000-$9FFF  the LZW output when RLE follows
;
; The chunk: rlelen(2) [lzw(1) in LZW/1 | bit 15 of rlelen = LZW, and 2
; bytes of length to skip, in LZW/2] then the data. rlelen = 4096: no
; RLE. Input -> [LZW -> rlelen bytes] -> [RLE -> 4096]; neither one nor
; the other: 4096 raw bytes. LZW/1 starts from an empty table on each chunk;
; LZW/2 keeps its own, clears it on code $100, and starts afresh on a
; chunk without LZW. Codes of 9 to 12 bits, low-order bits first, the width
; of the NEXT code according to entry: 9 up to $1FE, 10 up to $3FE, 11 up to
; $7FE, 12 beyond. Each chunk starts on a byte boundary: the leftover bits
; are discarded, and the input consumed is exactly the bytes read.

        .export         _us_init, _us_chunk
        .importzp       ptr1, ptr2, ptr3, ptr4, tmp1, tmp2, tmp3, tmp4
        .segment        "UNSHRINK"

PREFIX  = $2000
SUFFIX  = $4000
STACK   = $5000
OUTBUF  = $8000
TMPBUF  = $9000
CHUNK   = 4096
CLEAR   = $100
FIRST   = $101

RDMAIN  = $C002
RDAUX   = $C003
WRMAIN  = $C004
WRAUX   = $C005

; ---- the state: in the AUX copy, the only one the core reads and writes ----
fmt:    .byte   0
esc:    .byte   0
entry:  .word   0               ; the next free entry of the table
old:    .word   0               ; the previous code
final:  .byte   0               ; the first byte of the previous string
fresh:  .byte   0               ; 1: empty table, the next code is a byte
bb:     .res    3               ; the bit buffer, low-order bits first
bc:     .byte   0               ; bits present in bb
tsh2:   .byte   0               ; byte 2 of the shift temporary
rlelen: .word   0
lzwon:  .byte   0
instart: .word  0
outcnt: .word   0
code:   .word   0
width:  .byte   0
hmask:  .byte   $01, $03, $07, $0F   ; high byte of a 9, 10, 11, 12-bit code

; ---- us_init: format and escape, empty table, empty bit buffer ----
_us_init:
        sei
        sta     tmp1
        stx     tmp2
        sta     WRAUX           ; writes go to AUX, execution stays in MAIN
        lda     tmp1
        sta     fmt
        lda     tmp2
        sta     esc
        jsr     reset_table
        lda     #0
        sta     bc
        sta     WRMAIN
        cli
        rts

reset_table:
        lda     #<FIRST
        sta     entry
        lda     #>FIRST
        sta     entry+1
        lda     #1
        sta     fresh
        rts

; ---- us_chunk: one chunk, from the header at (A/X) to OUTBUF ----
_us_chunk:
        sta     ptr1
        stx     ptr1+1
        sei
        sta     WRAUX
        sta     RDAUX           ; from here on, the AUX copy is what executes
        lda     ptr1
        sta     instart
        lda     ptr1+1
        sta     instart+1
        lda     #0
        sta     bc
        sta     lzwon
        jsr     getb            ; rlelen
        sta     rlelen
        jsr     getb
        sta     rlelen+1
        lda     fmt
        cmp     #3
        beq     @h2
        jsr     getb            ; LZW/1: the LZW flag, and a fresh table
        sta     lzwon
        jsr     reset_table
        jmp     @hdone
@h2:    lda     rlelen+1        ; LZW/2: bit 15 = LZW, rlelen on 13 bits
        and     #$80
        sta     lzwon
        lda     rlelen+1
        and     #$1F
        sta     rlelen+1
        lda     lzwon
        beq     @h2none
        jsr     getb            ; the compressed length: unneeded, the stream ends by itself
        jsr     getb
        jmp     @hdone
@h2none: jsr    reset_table     ; a chunk without LZW starts afresh
@hdone: lda     rlelen          ; RLE in use if rlelen != 4096
        bne     @rle
        lda     rlelen+1
        cmp     #>CHUNK
        bne     @rle
        lda     lzwon           ; --- no RLE ---
        beq     @raw
        lda     #<OUTBUF        ; LZW alone: straight into OUTBUF
        ldx     #>OUTBUF
        jsr     lzw
        jsr     byte_align
        jmp     @done
@raw:   jsr     copy_raw        ; neither one nor the other: 4096 bytes as they are
        jmp     @done
@rle:   lda     lzwon           ; --- RLE ---
        beq     @rleonly
        lda     #<TMPBUF        ; LZW to TMPBUF, then RLE from TMPBUF to OUTBUF
        ldx     #>TMPBUF
        jsr     lzw
        jsr     byte_align
        lda     #<TMPBUF
        ldx     #>TMPBUF
        jsr     rle
        jmp     @done
@rleonly:
        lda     ptr1            ; RLE from the input itself
        ldx     ptr1+1
        jsr     rle
        lda     ptr3            ; what the RLE read is the input consumed
        sta     ptr1
        lda     ptr3+1
        sta     ptr1+1
@done:  sec                     ; consumed = ptr1 - instart, computed BEFORE
        lda     ptr1            ; going back to MAIN: instart exists only in AUX
        sbc     instart
        sta     ptr4
        lda     ptr1+1
        sbc     instart+1
        sta     ptr4+1
        sta     RDMAIN
        sta     WRMAIN
        cli
        lda     ptr4
        ldx     ptr4+1
        rts

; ---- the bytes ----
getb:   ldy     #0              ; A = the next input byte
        lda     (ptr1),y
        inc     ptr1
        bne     :+
        inc     ptr1+1
:       rts

getsrc: ldy     #0              ; A = the next byte of the RLE source
        lda     (ptr3),y
        inc     ptr3
        bne     :+
        inc     ptr3+1
:       rts

out:    ldy     #0              ; the byte A to the output; outcnt++
        sta     (ptr2),y
        inc     ptr2
        bne     :+
        inc     ptr2+1
:       inc     outcnt
        bne     :+
        inc     outcnt+1
:       rts

push:   ldy     #0
        sta     (ptr3),y
        inc     ptr3
        bne     :+
        inc     ptr3+1
:       rts

pop:    lda     ptr3
        bne     :+
        dec     ptr3+1
:       dec     ptr3
        ldy     #0
        lda     (ptr3),y
        rts

; ---- 4096 raw bytes, from the input to OUTBUF ----
copy_raw:
        lda     #<OUTBUF
        sta     ptr2
        lda     #>OUTBUF
        sta     ptr2+1
        lda     #0
        sta     outcnt
        sta     outcnt+1
@l:     lda     outcnt+1
        cmp     #>CHUNK
        beq     @e
        jsr     getb
        jsr     out
        jmp     @l
@e:     rts

; ---- RLE: from the source (A/X) to OUTBUF, 4096 bytes ----
; esc val cnt: val repeated cnt+1 times; any other byte, as it is.
rle:    sta     ptr3
        stx     ptr3+1
        lda     #<OUTBUF
        sta     ptr2
        lda     #>OUTBUF
        sta     ptr2+1
        lda     #0
        sta     outcnt
        sta     outcnt+1
@loop:  lda     outcnt+1
        cmp     #>CHUNK
        beq     @end
        jsr     getsrc
        cmp     esc
        beq     @run
        jsr     out
        jmp     @loop
@run:   jsr     getsrc
        sta     tmp3            ; the value
        jsr     getsrc
        sta     tmp4            ; the count minus one
@rep:   lda     tmp3
        jsr     out
        dec     tmp4
        bpl     @rep
        jmp     @loop
@end:   rts

; ---- LZW: rlelen bytes to (A/X) ----
lzw:    sta     ptr2
        stx     ptr2+1
        lda     #0
        sta     outcnt
        sta     outcnt+1
@loop:  lda     outcnt+1        ; done when outcnt >= rlelen
        cmp     rlelen+1
        bcc     @more
        bne     @fin
        lda     outcnt
        cmp     rlelen
        bcc     @more
@fin:   jmp     @end            ; @end is too far for a branch
@more:  jsr     getcode
        lda     fmt
        cmp     #3
        bne     @nclr
        lda     code            ; LZW/2: $100 clears the table
        bne     @nclr
        lda     code+1
        cmp     #>CLEAR
        bne     @nclr
        jsr     reset_table
        jmp     @loop
@nclr:  lda     fresh
        beq     @norm
        lda     code            ; the first code of a fresh table: a byte
        jsr     out
        lda     code
        sta     old
        sta     final
        lda     code+1
        sta     old+1
        lda     #0
        sta     fresh
        jmp     @loop
@norm:  lda     code            ; p = code, empty stack
        sta     tmp1
        lda     code+1
        sta     tmp2
        lda     #<STACK
        sta     ptr3
        lda     #>STACK
        sta     ptr3+1
        lda     tmp2            ; p >= entry: KwKwK -> push final, p = old
        cmp     entry+1
        bcc     @walk
        bne     @kwk
        lda     tmp1
        cmp     entry
        bcc     @walk
@kwk:   lda     final
        jsr     push
        lda     old
        sta     tmp1
        lda     old+1
        sta     tmp2
@walk:  lda     tmp2            ; while p > $FF: push suffix[p], p = prefix[p]
        beq     @leaf
        clc
        lda     tmp1
        adc     #<SUFFIX
        sta     ptr4
        lda     tmp2
        adc     #>SUFFIX
        sta     ptr4+1
        ldy     #0
        lda     (ptr4),y
        jsr     push
        lda     tmp1            ; prefix[p] at PREFIX + p*2
        asl     a
        sta     ptr4
        lda     tmp2
        rol     a
        clc
        adc     #>PREFIX
        sta     ptr4+1
        ldy     #0
        lda     (ptr4),y
        sta     tmp1
        iny
        lda     (ptr4),y
        sta     tmp2
        jmp     @walk
@leaf:  lda     tmp1            ; final = p, output p, then the stack
        sta     final
        jsr     out
@pop:   lda     ptr3
        cmp     #<STACK
        bne     @popone
        lda     ptr3+1
        cmp     #>STACK
        beq     @add
@popone: jsr    pop
        jsr     out
        jmp     @pop
@add:   lda     entry+1         ; suffix[entry] = final, prefix[entry] = old, entry++
        cmp     #$10            ; (never reached: the compressor clears at $FFD)
        bcs     @setold
        clc
        lda     entry
        adc     #<SUFFIX
        sta     ptr4
        lda     entry+1
        adc     #>SUFFIX
        sta     ptr4+1
        lda     final
        ldy     #0
        sta     (ptr4),y
        lda     entry
        asl     a
        sta     ptr4
        lda     entry+1
        rol     a
        clc
        adc     #>PREFIX
        sta     ptr4+1
        lda     old
        ldy     #0
        sta     (ptr4),y
        lda     old+1
        iny
        sta     (ptr4),y
        inc     entry
        bne     @setold
        inc     entry+1
@setold: lda    code
        sta     old
        lda     code+1
        sta     old+1
        jmp     @loop
@end:   rts

; ptr1 -= bc>>3: getcode reads WHOLE bytes into its bit buffer but only
; consumes `width` of them: at the end of the chunk, ptr1 has read up to two
; bytes too many (the remainder of bb). Since a chunk's stream is aligned on
; a byte, we move ptr1 back by the whole bytes still buffered, otherwise the
; next chunk is read askew and the dictionary goes haywire.
byte_align:
        lda     bc
        lsr     a
        lsr     a
        lsr     a               ; A = bc >> 3, bytes read in excess
        beq     @z
        sta     tmp1
        lda     ptr1
        sec
        sbc     tmp1
        sta     ptr1
        lda     ptr1+1
        sbc     #0
        sta     ptr1+1
@z:     rts

; ---- one code: width according to entry, low-order bits first ----
getcode:
        ldx     #9              ; 9 up to $1FE, 10 up to $3FE, 11 up to $7FE, 12 beyond
        lda     entry+1
        cmp     #$01
        bcc     @w
        bne     @ge200
        lda     entry
        cmp     #$FF
        bcc     @w
        inx
        bne     @w
@ge200: inx
        lda     entry+1
        cmp     #$03
        bcc     @w
        bne     @ge400
        lda     entry
        cmp     #$FF
        bcc     @w
        inx
        bne     @w
@ge400: inx
        lda     entry+1
        cmp     #$07
        bcc     @w
        bne     @ge800
        lda     entry
        cmp     #$FF
        bcc     @w
        inx
        bne     @w
@ge800: inx
@w:     stx     width
@fill:  lda     bc              ; fill: bb |= byte << bc, bc += 8, while bc < width
        cmp     width
        bcs     @have
        jsr     getb
        sta     tmp3
        lda     #0
        sta     tmp4
        sta     tsh2
        ldx     bc
        beq     @orin
@sh:    asl     tmp3
        rol     tmp4
        rol     tsh2
        dex
        bne     @sh
@orin:  lda     bb
        ora     tmp3
        sta     bb
        lda     bb+1
        ora     tmp4
        sta     bb+1
        lda     bb+2
        ora     tsh2
        sta     bb+2
        lda     bc
        clc
        adc     #8
        sta     bc
        jmp     @fill
@have:  lda     bb              ; code = bb & mask(width)
        sta     code
        lda     bb+1
        ldx     width
        and     hmask-9,x
        sta     code+1
        ldx     width           ; bb >>= width, bc -= width
@shr:   lsr     bb+2
        ror     bb+1
        ror     bb
        dex
        bne     @shr
        lda     bc
        sec
        sbc     width
        sta     bc
        rts

us_end:
        .assert us_end <= $2000, error, "UNSHRINK core must end under $2000 (AUX mirror)"
        .assert (PREFIX & $FF) = 0 .and (SUFFIX & $FF) = 0, error, "PREFIX and SUFFIX must be page-aligned"
