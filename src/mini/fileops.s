; fileops.s -- lock, unlock and rename on the two panels. LOWCODE.
; Prompts and results stay on the footer (rows 20-23), like copy.

        .include "mini.inc"

        .export lock_file, rename_file

        .import at, put, inline_text, zone
        .import activate, confirm, keep_note, result_done
        .import print_name, print_byte, tag_count, tag_test
        .import lock_prepare, lock_execute, rename_prepare, rename_execute
        .import del_index, del_fault, lock_op, ren_name
        .import ask_name, name_buf, ask_kind
        .import ent_index, ent_ptr, ent_type
        .import active, count, selected

        .segment "BSS"
fo_n:           .res 1
fo_i:           .res 1
fo_st:          .res 1

.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"
.endif

foot_ask:
        ldy     #20
        ldx     #0
        lda     #40
        jsr     zone
        rts

foot_bar:
        lda     #0
        sta     inverse
        jmp     confirm

foot_done:
        jmp     result_done

short15:
        jsr     ent_ptr
        ldy     #0
@ch:
        sty     t1
        lda     (ptr),y
        jsr     put
        ldy     t1
        iny
        cpy     #15
        bcc     @ch
        rts

; ---------------------------------------------------------------------
lock_file:
        jsr     activate
        ldx     active
        jsr     tag_count
        sta     fo_n
        lda     #0
        sta     lock_op
        lda     fo_n
        beq     @ask
        jsr     tagged_locked
        beq     @all_free
        lda     #1
        sta     lock_op
        jmp     @ask
@all_free:
        lda     #2
        sta     lock_op
@ask:
        jsr     foot_ask
        lda     fo_n
        bne     @many
        lda     selected
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$80
        bne     @unl
        PRINT   "LOCK "
        jmp     @nm
@unl:
        PRINT   "UNLOCK "
@nm:
        lda     selected
        jsr     ent_index
        jsr     short15
        PRINT   "?"
        jmp     @go
@many:
        lda     lock_op
        cmp     #1
        beq     @unlmany
        PRINT   "LOCK "
        jmp     @nfiles
@unlmany:
        PRINT   "UNLOCK "
@nfiles:
        lda     fo_n
        jsr     print_byte
        PRINT   " MARKED?"
@go:
        jsr     foot_bar
        bcc     @out
        lda     #DEL_OK
        sta     fo_st
        lda     fo_n
        bne     @tagged
        lda     selected
        sta     del_index
        jsr     one_lock
        sta     fo_st
        jmp     @show
@tagged:
        lda     #0
        sta     fo_i
@each:
        lda     fo_i
        cmp     count
        bcs     @show
        lda     fo_i
        ldx     active
        jsr     tag_test
        beq     @next
        lda     fo_i
        sta     del_index
        jsr     one_lock
        sta     fo_st
        cmp     #DEL_OK
        beq     @next
        cmp     #DEL_LOCKED
        beq     @next
        jmp     @show
@next:
        inc     fo_i
        jmp     @each
@show:
        jsr     lock_show
        jmp     foot_done
@out:
        rts

tagged_locked:
        lda     #0
        sta     fo_i
@lp:
        lda     fo_i
        cmp     count
        bcs     @no
        lda     fo_i
        ldx     active
        jsr     tag_test
        beq     @n
        lda     fo_i
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$80
        bne     @yes
@n:
        inc     fo_i
        jmp     @lp
@yes:
        lda     #1
        rts
@no:
        lda     #0
        rts

one_lock:
        jsr     lock_prepare
        bne     @out
        jsr     lock_execute
@out:
        rts

lock_show:
        jsr     foot_ask
        lda     fo_st
        bne     @notok
        lda     lock_op
        beq     @togmsg
        cmp     #1
        beq     @saidun
        PRINT   "LOCKED"
        rts
@togmsg:
        lda     del_index
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$80
        bne     @saidun
        PRINT   "LOCKED"
        rts
@saidun:
        PRINT   "UNLOCKED"
        rts
@notok:
        cmp     #DEL_LOCKED
        bne     @notsame
        PRINT   "ALREADY SET"
        rts
@notsame:
        cmp     #DEL_CHANGED
        bne     @notchg
        PRINT   "DISK CHANGED - LOCK REFUSED"
        rts
@notchg:
        cmp     #DEL_READ
        bne     @notread
        PRINT   "READ ERROR - LOCK REFUSED"
        rts
@notread:
        cmp     #DEL_UNCERTAIN
        bne     @bad
        PRINT   "UNCERTAIN WRITE - STOP"
        lda     #1
        sta     del_fault
        rts
@bad:
        PRINT   "UNSUPPORTED / INVALID DOS STRUCTURE"
        rts

; ---------------------------------------------------------------------
rename_file:
        jsr     activate
        lda     selected
        jsr     ent_index
        tay
        lda     ent_type,y
        and     #$80
        beq     @open
        jsr     foot_ask
        PRINT   "LOCKED - UNLOCK FIRST"
        jmp     keep_note
@open:
        lda     #1
        sta     ask_kind
        jsr     ask_name
        jcc     @out
        ldy     #0
@copy:
        lda     name_buf,y
        sta     ren_name,y
        iny
        cpy     #NAME_LEN
        bcc     @copy
        lda     selected
        sta     del_index
        jsr     rename_prepare
        sta     fo_st
        bne     @show
        jsr     rename_execute
        sta     fo_st
@show:
        jsr     foot_ask
        lda     fo_st
        bne     @notok
        PRINT   "RENAMED"
        jmp     foot_done
@notok:
        cmp     #REN_EXISTS
        bne     @notex
        PRINT   "NAME EXISTS - NO OVERWRITE"
        jmp     foot_done
@notex:
        cmp     #DEL_LOCKED
        bne     @notlk
        PRINT   "LOCKED - UNLOCK FIRST"
        jmp     foot_done
@notlk:
        cmp     #DEL_CHANGED
        bne     @notchg
        PRINT   "DISK CHANGED - RENAME REFUSED"
        jmp     foot_done
@notchg:
        cmp     #DEL_READ
        bne     @notrd
        PRINT   "READ ERROR - RENAME REFUSED"
        jmp     foot_done
@notrd:
        cmp     #DEL_UNCERTAIN
        bne     @bad
        PRINT   "UNCERTAIN WRITE - STOP"
        lda     #1
        sta     del_fault
        jmp     foot_done
@bad:
        PRINT   "UNSUPPORTED / INVALID DOS STRUCTURE"
        jmp     foot_done
@out:
        rts
