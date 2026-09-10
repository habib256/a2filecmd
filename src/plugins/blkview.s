; Direct service calls through the reserved even API table at $3F9E.
.segment "CODE"
.export _v_cprintf
_v_cprintf: jmp ($3FD8)
.export _v_sprintf
_v_sprintf: jmp ($3FDA)
.export _v_cputs
_v_cputs: jmp ($3FDC)
.export _v_cputc
_v_cputc: jmp ($3FDE)
.export _v_gotoxy
_v_gotoxy: jmp ($3FE0)
.export _v_clrscr
_v_clrscr: jmp ($3FE6)
.export _v_cgetc
_v_cgetc: jmp ($3FE8)
.export _v_message
_v_message: jmp ($3FAE)
.export _v_prompt
_v_prompt: jmp ($3FB2)
.export _v_memcpy
_v_memcpy: jmp ($3FEA)
.export _v_strcpy
_v_strcpy: jmp ($3FEE)
.export _v_strcmp
_v_strcmp: jmp ($3FF0)
.export _v_strlen
_v_strlen: jmp ($3FF2)
.export _v_fopen
_v_fopen: jmp ($3FCC)
.export _v_fwrite
_v_fwrite: jmp ($3FD0)
.export _v_fclose
_v_fclose: jmp ($3FD2)
