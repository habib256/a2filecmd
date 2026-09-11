; Direct service calls through the reserved even API table at $3F9E.
; The editor's own set: BLKVIEW next door keeps a different one, and each
; overlay carries only the thunks it calls.
.segment "CODE"
.export _v_cprintf
_v_cprintf: jmp ($3FD8)
.export _v_cputs
_v_cputs: jmp ($3FDC)
.export _v_cputc
_v_cputc: jmp ($3FDE)
.export _v_gotoxy
_v_gotoxy: jmp ($3FE0)
.export _v_revers
_v_revers: jmp ($3FE2)
.export _v_clrscr
_v_clrscr: jmp ($3FE6)
.export _v_cgetc
_v_cgetc: jmp ($3FE8)
.export _v_message
_v_message: jmp ($3FAE)
.export _v_confirm
_v_confirm: jmp ($3FB0)
.export _v_prompt
_v_prompt: jmp ($3FB2)
.export _v_strcpy
_v_strcpy: jmp ($3FEE)
.export _v_strcmp
_v_strcmp: jmp ($3FF0)
