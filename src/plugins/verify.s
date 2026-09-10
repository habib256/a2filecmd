; Direct service calls through the even table at $1FC2.
.segment "CODE"
.export _t_message
_t_message: jmp ($1FD2)
.export _t_mli
_t_mli: jmp ($1FEE)
.export _t_fclose
_t_fclose: jmp ($1FF6)
.export _t_fopen
_t_fopen: jmp ($1FF0)
.export _t_build_full
_t_build_full: jmp ($1FE6)
.export _t_fread
_t_fread: jmp ($1FF2)
.export _print
_print: jmp ($1FFE)
