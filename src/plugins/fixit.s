; Direct service calls. Fixed even API copy at $3F9E; see fixit.c.
.segment "CODE"
.export _v_mli
_v_mli: jmp ($3FCA)
.export _v_cputs
_v_cputs: jmp ($3FDC)
.export _v_cprintf
_v_cprintf: jmp ($3FD8)
.export _v_sprintf
_v_sprintf: jmp ($3FDA)
.export _v_gotoxy
_v_gotoxy: jmp ($3FE0)
.export _v_clrscr
_v_clrscr: jmp ($3FE6)
.export _v_memcpy
_v_memcpy: jmp ($3FEA)
.export _v_cgetc
_v_cgetc: jmp ($3FE8)
.export _v_memset
_v_memset: jmp ($3FEC)
.export _v_strcpy
_v_strcpy: jmp ($3FEE)
.export _v_strcmp
_v_strcmp: jmp ($3FF0)
