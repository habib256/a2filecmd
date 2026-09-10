; Direct resident service calls; API copy occupies $3F9E-$3FFF.
.segment "CODE"
.export _f_message
_f_message: jmp ($3FAE)
.export _f_prompt
_f_prompt: jmp ($3FB2)
.export _f_keys_bar
_f_keys_bar: jmp ($3FB6)
.export _f_bar_begin
_f_bar_begin: jmp ($3FB8)
.export _f_dir_open
_f_dir_open: jmp ($3FC4)
.export _f_dir_next
_f_dir_next: jmp ($3FC6)
.export _f_dir_close
_f_dir_close: jmp ($3FC8)
.export _f_fopen
_f_fopen: jmp ($3FCC)
.export _f_fread
_f_fread: jmp ($3FCE)
.export _f_fclose
_f_fclose: jmp ($3FD2)
.export _f_cprintf
_f_cprintf: jmp ($3FD8)
.export _f_sprintf
_f_sprintf: jmp ($3FDA)
.export _f_cputs
_f_cputs: jmp ($3FDC)
.export _f_cputc
_f_cputc: jmp ($3FDE)
.export _f_gotoxy
_f_gotoxy: jmp ($3FE0)
.export _f_revers
_f_revers: jmp ($3FE2)
.export _f_clrscr
_f_clrscr: jmp ($3FE6)
.export _f_cgetc
_f_cgetc: jmp ($3FE8)
.export _f_memcpy
_f_memcpy: jmp ($3FEA)
.export _f_strcpy
_f_strcpy: jmp ($3FEE)
.export _f_strlen
_f_strlen: jmp ($3FF2)

; Parse two decimal digits, or return $FF. No software stack needed.
.importzp ptr1, tmp1
.export _pair
_pair:
    sta ptr1
    stx ptr1+1
    ldy #0
    lda (ptr1),y
    sec
    sbc #'0'
    cmp #10
    bcs bad_pair
    asl a
    sta tmp1
    asl a
    asl a
    adc tmp1
    sta tmp1
    iny
    lda (ptr1),y
    sec
    sbc #'0'
    cmp #10
    bcs bad_pair
    adc tmp1
    ldx #0
    rts
bad_pair:
    lda #$FF
    ldx #0
    rts
