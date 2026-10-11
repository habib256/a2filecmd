; Bounded, forward ZX02 for both NMOS 6502 and 65C02.
; Default Elias polarity, initial distance 1; algorithm by Daniel Serpell.
; Own implementation, including CRC-16/CCITT-FALSE and stream bounds.
;
; MAIN only: output $1000-$1BFF then $4000-$BEDF. No AUX switches.
; Every run is reserved against the exact output extent before its first
; write. References must already exist. Input is refilled through C only
; after exhaustion; failed/short/error reads unwind without executing output.
; ptr1..4, tmp1..2 and sreg are runtime scratch. Live state is saved over
; C refills; ptr4 is exhausted before each refill and receives its result.
; The C stack pointer is never borrowed.
        .macpack longbranch
        .export _zx_decode, _zx_pos, _zx_input_left
        .import _zx_buffer, _zx_refill, popax
        .importzp ptr1, ptr2, ptr3, ptr4, tmp1, tmp2, sreg
bits = tmp1
count = tmp2
crc = sreg
input_left = ptr4
.ifdef ZX02_TEST_LINEAR
        .import _zx_test_output
.endif

        .bss
_zx_pos:        .res 2
_zx_input_left: .res 2
out_left:       .res 2
expected:       .res 2
saved_crc:      .res 2
distance:       .res 2
length:         .res 2
saved_bits:     .res 1
extra:          .res 1
state:          .res 1
saved_count:    .res 1
entry_sp:       .res 1
bit_y:          .res 1
saved_ptrs:     .res 4

        .code
; Inline the per-byte work. Slow C refills remain a shared bounded path.
        .macro read_byte
        .local present, low_ready, done
        lda input_left
        ora input_left+1
        bne present
        jsr refill_input
present:
        lda input_left
        bne low_ready
        dec input_left+1
low_ready:
        dec input_left
        ldy #0
        lda (ptr3),y
        inc ptr3
        bne done
        inc ptr3+1
done:
        .endmacro

        .macro write_byte
        .local done
        ldy #0
        sta (ptr1),y
        eor crc+1
        tax
        lda crc
        eor crc_hi,x
        sta crc+1
        lda crc_lo,x
        sta crc
        inc ptr1
        bne done
        inc ptr1+1
.ifndef ZX02_TEST_LINEAR
        lda ptr1+1
        cmp #$1C
        bne done
        lda #$40
        sta ptr1+1
.endif
done:
        .endmacro

; __fastcall__: expected CRC in A/X, size on the software stack.
_zx_decode:
        sta expected
        stx expected+1
        jsr popax
        sta out_left
        stx out_left+1
        tsx
        stx entry_sp
        ; Independent limit even if called outside the C launcher.
        lda out_left+1
        cmp #$0C
        jcc fail
        bne :+
        lda out_left
        jeq fail
:       lda out_left+1
        cmp #$8A
        bcc :+
        jne fail
        lda out_left
        cmp #$E1
        jcs fail
:       lda #0
        sta _zx_pos
        sta _zx_pos+1
        sta _zx_input_left
        sta _zx_input_left+1
        sta input_left
        sta input_left+1
        sta extra
        sta state
        sta distance+1
        lda #1
        sta distance
        lda #$80
        sta bits
        lda #$FF
        sta crc
        sta crc+1
.ifdef ZX02_TEST_LINEAR
        lda _zx_test_output
        sta ptr1
        lda _zx_test_output+1
.else
        lda #0
        sta ptr1
        lda #$10
.endif
        sta ptr1+1
dispatch:
        lda state
        beq literals
        cmp #2
        beq new_offset
        jmp match_length

literals:
        jsr elias
        jsr reserve
literal_loop:
        read_byte
        write_byte
        dec count
        bne literal_loop
        jsr advance
        jsr get_bit
        lda #1
        jcc set_state
        lda #2
set_state:
        sta state
        jmp dispatch

new_offset:
        jsr elias
        lda length+1
        jne finished            ; Elias 256 is the sole end marker.
        lda length
        sec
        sbc #1
        lsr a
        sta distance+1
        lda #0
        ror a
        sta distance
        read_byte
        lsr a
        pha
        lda #2
        adc #0
        sta extra
        pla
        ora distance
        sta distance
        inc distance
        bne match_length
        inc distance+1
match_length:
        jsr elias
        lda state
        cmp #2
        bne :+
        ; New-offset length is (Elias+1), with 257 encoded as 1.
        inc length
        bne :+
        inc length+1
:       jsr reserve
        ; Reference index = produced - distance; a borrow rejects it.
        lda _zx_pos
        sec
        sbc distance
        sta ptr2
        lda _zx_pos+1
        sbc distance+1
        jcc fail
        sta ptr2+1
.ifdef ZX02_TEST_LINEAR
        lda ptr2
        clc
        adc _zx_test_output
        sta ptr2
        lda ptr2+1
        adc _zx_test_output+1
.else
        cmp #$0C
        bcs :+
        clc
        adc #$10
        bne :++
:       clc
        adc #$34
:
.endif
        sta ptr2+1
match_loop:
        ldy #0
        lda (ptr2),y
        write_byte
        inc ptr2
        bne :+
        inc ptr2+1
.ifndef ZX02_TEST_LINEAR
        lda ptr2+1
        cmp #$1C
        bne :+
        lda #$40
        sta ptr2+1
.endif
:       dec count
        bne match_loop
        jsr advance
        jsr get_bit
        lda #0
        jcc set_state
        lda #2
        jne set_state

finished:
        ; Publish scratch state before returning to the C runtime.
        lda input_left
        sta _zx_input_left
        lda input_left+1
        sta _zx_input_left+1
        lda out_left
        ora out_left+1
        jne fail
        lda crc
        cmp expected
        jne fail
        lda crc+1
        cmp expected+1
        jne fail
        lda #1
        ldx #0
        rts
fail:
        ; All paths have popped the size argument. Discard only internal
        ; hardware return addresses, keeping the caller's return address.
        ldx entry_sp
        txs
        lda #0
        tax
        rts

; Elias 1..256, rejecting continuations/low bits that exceed 256.
elias:
        ldy #1
        ; Only a new offset injects its low bit, once at Elias entry.
        lda extra
        beq elias_loop
        lsr a
        lda #0
        sta extra
        bcc elias_done
        bcs elias_data
elias_loop:
        asl bits
        bne :+
        jsr bit_refill
:       bcc elias_done
elias_data:
        asl bits
        bne :+
        jsr bit_refill
:       tya
        rol a
        tay
        bcc elias_loop
        ; Overflow is legal only for 256, followed by its terminator.
        tya
        jne fail
        jsr get_bit
        jcs fail
        lda #1
        bne elias_store
elias_done:
        lda #0
elias_store:
        sta length+1
        sty length
        rts

; Reserve a full 1..256-byte run. length $0101 wraps to 1 as in ZX02.
reserve:
        lda length+1
        beq :+
        lda length
        beq :+
        lda #0
        sta length+1
:       lda length
        sta count               ; zero means 256 iterations
        lda out_left
        sec
        sbc length
        sta out_left
        lda out_left+1
        sbc length+1
        jcc fail
        sta out_left+1
        rts
advance:
        lda _zx_pos
        clc
        adc length
        sta _zx_pos
        lda _zx_pos+1
        adc length+1
        sta _zx_pos+1
        rts

get_bit:
        asl bits
        bne bit_ready
bit_refill:
        sty bit_y
        read_byte
        ldy bit_y
        sec
        rol a
        sta bits
bit_ready:
        rts

refill_input:
        ; C fread/runtime uses ptr1..3; retain all live codec pointers.
        lda ptr1
        sta saved_ptrs
        lda ptr1+1
        sta saved_ptrs+1
        lda ptr2
        sta saved_ptrs+2
        lda ptr2+1
        sta saved_ptrs+3
        lda bits
        sta saved_bits
        lda count
        sta saved_count
        lda crc
        sta saved_crc
        lda crc+1
        sta saved_crc+1
        jsr _zx_refill
        sta input_left
        stx input_left+1
        lda saved_ptrs
        sta ptr1
        lda saved_ptrs+1
        sta ptr1+1
        lda saved_ptrs+2
        sta ptr2
        lda saved_ptrs+3
        sta ptr2+1
        lda saved_bits
        sta bits
        lda saved_count
        sta count
        lda saved_crc
        sta crc
        lda saved_crc+1
        sta crc+1
        lda input_left
        ora input_left+1
        jeq fail
        lda #<_zx_buffer
        sta ptr3
        lda #>_zx_buffer
        sta ptr3+1
        rts

        .rodata
        .include "zx02_crc.inc"
