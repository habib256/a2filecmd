; driver.s -- the main-memory side of GROUiK / French Touch's PT3 engine
; (ppt3.s, wrapped by engine.s). Included by pt3.s, in the PG segments: the
; part of PT3.PLG's file that loads at $3B00-$3FFF (sdk/pt3.cfg). pt3_lib
; uses those pages as cache and tables once IT starts, so nothing here runs
; after pt3_lib's initialisation; when GROUiK plays, those pages are never
; touched and this code stays in place until the plugin returns.
;
; The auxiliary bank holds the ProDOS /RAM disk. Nothing is written there
; before api->aux_consent() answers yes -- it asks "ALL /RAM files will be
; LOST" unless /RAM is on line and empty, or was already accepted while
; leafing through this media folder. From the first AUX write on, _aux is
; set: pt3.c then calls pg_end on the way out, which rebuilds /RAM and says
; so, whatever happened, and pg_setup never hands over to pt3_lib again.
;
; AUX map (abi.inc): $2000-$3AFF the engine image (A2FILE/PPT3.BIN) and the
; tables and variables its INIT builds; the trampoline's mirror at its own
; address ($3Bxx, pg_call); $4000-$BFFF the module, whole (32 KB at most).
; $0800-$1FFF (/RAM's own blocks) is never written.
; Main: pt3.c's SECOND page pair ($3900-$3AFF, a TurboSound pair's second
; header, unused for a single module) stages every 512-byte transfer -- NOT
; api->copy_buf, which aux_consent overwrites (ram_empty reads /RAM's
; directory block there: the first chunk of the engine, read before the
; question, would have been replaced by it).
;
; unsigned char pg_setup(void): 0 = not used, play with pt3_lib, AUX
;   untouched (API older than v6, module over 32 KB, no consent, engine file
;   missing, short or not of this ABI); 1 = ready, the engine has run INIT,
;   the source file is closed (_source = 0) and row 3 of music_info's
;   screen names GROUiK's player; 2 = stop, with _io_bad set
;   (an engine or module read error after the consent, a short or long
;   stream, a close error, a module that changed between the two passes)
;   or _r = 1 (a guard trip in INIT).
; void pg_end(void): rebuild /RAM (keeping main $2000-$21FF, which the
;   /RAM driver's FORMAT overwrites); if it was rebuilt, append
;   " /RAM rebuilt." to api->note (after any message pt3.c has put there).

        .import _A, _n, _source, _io_bad, _r, _aux
        .import _ferror, _feof, pushax, pusha
        .importzp ptr1, ptr2, ptr3, tmp1, tmp2

API_FOPEN       = 46            ; struct A2fcApi offsets (tools/test_ppt3_driver.py
                                ; checks them against src/a2fc_plugin.h)
API_FREAD       = 48
API_FCLOSE      = 52
API_FSEEK       = 54
API_CPUTS       = 62
API_GOTOXY      = 66
API_NOTE        = 92
API_CFG_PATH    = 96
API_RAM_FORMAT  = 98
API_AUX_CONSENT = 106
PG_SONG         = $3700         ; pt3.c SONG: the first 512 bytes the scan read
PG_STAGE        = $3900         ; pt3.c SECOND: the staging buffer
CC65_SEEK_SET   = 2             ; cc65's stdio.h: SEEK_CUR 0, SEEK_END 1, SEEK_SET 2

        .macpack longbranch
        .segment "PGCODE"

_pg_setup:
        jsr     api_ptr
        ldy     #0
        lda     (ptr1),y                ; api->version
        cmp     #6
        jcc     no
        lda     #<PPT3_MODMAX           ; n > 32 KB: pt3_lib
        cmp     _n
        lda     #>PPT3_MODMAX
        sbc     _n+1
        jcc     no
        ; <directory of A2FILE.CFG>/PPT3.BIN
        ldy     #API_CFG_PATH
        jsr     api_word
        sta     ptr2
        stx     ptr2+1
        jsr     b_ptr3
        ldy     #0
        ldx     #0                      ; just past the last '/'
@path:  lda     (ptr2),y
        sta     (ptr3),y
        beq     @name
        iny
        jmi     no                      ; longer than PATH_LEN: impossible
        cmp     #'/'
        bne     @path
        tya
        tax
        bne     @path                   ; always
@name:  txa
        clc
        adc     ptr3
        sta     ptr3
        bcc     :+
        inc     ptr3+1
:       ldy     #8
@app:   lda     pg_name,y
        sta     (ptr3),y
        dey
        bpl     @app
        ; fopen(path, "rb")
        lda     #<PG_STAGE
        ldx     #>PG_STAGE
        jsr     pushax
        lda     #<pg_rb
        ldx     #>pg_rb
        ldy     #API_FOPEN
        jsr     api_call
        sta     pg_f
        stx     pg_f+1
        txa
        ora     pg_f
        jeq     no
        ; its first chunk: this ABI's header, read BEFORE any question
        jsr     pg_read
        sta     pg_total
        stx     pg_total+1
        jsr     f_error
        jne     close_no
        lda     pg_total+1
        bne     :+
        lda     pg_total
        cmp     #26
        jcc     close_no
:       jsr     b_ptr3
        ldy     #4
@magic: lda     (ptr3),y
        cmp     pg_magic,y
        jne     close_no
        dey
        bpl     @magic
        ldy     #24                     ; PPT3_LEN: the image's own size
        lda     (ptr3),y
        sta     pg_len
        iny
        lda     (ptr3),y
        sta     pg_len+1
        ldy     #API_AUX_CONSENT
        jsr     api_call
        tax
        bne     yes
close_no:
        jsr     f_close
no:     lda     #0
        tax
        rts

        ; From the first AUX write on, never back to pt3_lib.
yes:    lda     #1
        sta     _aux
        jsr     b_ptr1                  ; the first chunk
        lda     #<PPT3_BASE
        ldx     #>PPT3_BASE
        ldy     pg_total
        sty     tmp1
        ldy     pg_total+1
        sty     tmp2
        jsr     put_at
        lda     #<pg_tramp              ; the trampoline's mirror
        sta     ptr1
        ldx     #>pg_tramp
        stx     ptr1+1
        ldy     #pg_tramp_end-pg_tramp
        sty     tmp1
        ldy     #0
        sty     tmp2
        jsr     put_at
        lda     #<PPT3_BASE             ; the rest of the image
        ldx     #>PPT3_BASE
        ldy     #>(PPT3_LIMIT-PPT3_BASE)
        jsr     pg_stream
        bne     :+
        inc     _io_bad
:       jsr     f_close
        beq     :+
        inc     _io_bad
:       ; the module again, whole, into AUX; then the source is closed
        lda     _source
        sta     pg_f
        lda     _source+1
        sta     pg_f+1
        lda     #0
        sta     _source
        sta     _source+1
        sta     pg_total
        sta     pg_total+1
        lda     _n
        sta     pg_len
        lda     _n+1
        sta     pg_len+1
        lda     _io_bad
        bne     @close
        lda     pg_f                    ; fseek(source, 0L, SEEK_SET)
        ldx     pg_f+1
        jsr     pushax
        lda     #0
        tax
        jsr     pushax
        jsr     pushax
        lda     #CC65_SEEK_SET          ; X = 0
        ldy     #API_FSEEK
        jsr     api_call
        stx     tmp1
        ora     tmp1
        bne     @bad
        lda     #<PPT3_MODULE
        ldx     #>PPT3_MODULE
        ldy     #>PPT3_MODMAX
        jsr     pg_stream
        bne     @close
@bad:   inc     _io_bad
@close: jsr     f_close
        beq     :+
        inc     _io_bad
:       lda     _io_bad
        bne     @stop
        clc                             ; the module's end, for the guards
        lda     pg_len
        sta     pg_hi
        lda     pg_len+1
        adc     #>PPT3_MODULE
        sta     pg_hi+1
        lda     #<pg_hi
        sta     ptr1
        lda     #>pg_hi
        sta     ptr1+1
        lda     #2
        sta     tmp1
        lda     #0
        sta     tmp2
        lda     #<PPT3_MODHI
        ldx     #>PPT3_MODHI
        jsr     put_at
        lda     #0
        jsr     _pg_call                ; INIT
        tax
        jeq     pg_credit
        lda     #1
        sta     _r
@stop:  lda     #2
        ldx     #0
        rts

; Copies pg_f, from where it stands to its end, into AUX at A/X +
; pg_total, at most Y pages in all. Z clear (A = 1) when exactly pg_len
; bytes came, with no read error, a real EOF and, for the module, a first
; chunk equal to the header the scan read: the file may not change
; between the two passes. Z set (A = 0) otherwise.
pg_stream:
        sta     pg_dst
        stx     pg_dst+1
        sty     pg_max
@loop:  lda     #$AF                    ; the activity cell, as in the scan
        cmp     $06F7
        bne     :+
        lda     #$DC
:       sta     $06F7
        jsr     pg_read
        sta     pg_c
        stx     pg_c+1
        jsr     f_error
        jne     @fail
        lda     pg_c                    ; total + c > max pages: too long
        clc
        adc     pg_total
        tay
        lda     pg_c+1
        adc     pg_total+1
        jcs     @fail
        cmp     pg_max
        bcc     :+
        jne     @fail
        cpy     #0
        jne     @fail
:
        lda     pg_c
        ora     pg_c+1
        beq     @eof
        lda     pg_total
        ora     pg_total+1
        bne     @put
        lda     pg_dst+1
        cmp     #>PPT3_MODULE
        bne     @put
        jsr     b_ptr3                  ; first module chunk vs SONG
        lda     #<PG_SONG
        sta     ptr2
        lda     #>PG_SONG
        sta     ptr2+1
        ldx     pg_c+1                  ; 0, 1 or 2 whole pages, then the rest
        ldy     #0
@cmp:   cpx     #0
        bne     :+
        cpy     pg_c
        beq     @put
:       lda     (ptr3),y
        cmp     (ptr2),y
        jne     @fail
        iny
        bne     @cmp
        inc     ptr3+1
        inc     ptr2+1
        dex
        jmp     @cmp
@put:   jsr     b_ptr1
        lda     pg_c
        sta     tmp1
        lda     pg_c+1
        sta     tmp2
        clc
        lda     pg_dst
        adc     pg_total
        pha
        lda     pg_dst+1
        adc     pg_total+1
        tax
        pla
        jsr     put_at
        clc
        lda     pg_total
        adc     pg_c
        sta     pg_total
        lda     pg_total+1
        adc     pg_c+1
        sta     pg_total+1
        jmp     @loop
@eof:   lda     pg_f
        ldx     pg_f+1
        jsr     _feof
        stx     tmp1
        ora     tmp1
        jeq     @fail
        lda     pg_total
        cmp     pg_len
        jne     @fail
        lda     pg_total+1
        cmp     pg_len+1
        jne     @fail
        lda     #1
        rts
@fail:  lda     #0
        rts

; fread(PG_STAGE, 1, 512, pg_f) -> A/X
pg_read:
        lda     #<PG_STAGE
        ldx     #>PG_STAGE
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     #0
        ldx     #2
        jsr     pushax
        lda     pg_f
        ldx     pg_f+1
        ldy     #API_FREAD
        jmp     api_call

; Z clear when pg_f has its error flag.
f_error:
        lda     pg_f
        ldx     pg_f+1
        jsr     _ferror
        stx     tmp1
        ora     tmp1
        rts

; fclose(pg_f); Z clear on an error.
f_close:
        lda     pg_f
        ldx     pg_f+1
        ldy     #API_FCLOSE
        jsr     api_call
        stx     tmp1
        ora     tmp1
        rts

b_ptr1: lda     #<PG_STAGE
        sta     ptr1
        lda     #>PG_STAGE
        sta     ptr1+1
        rts
b_ptr3: lda     #<PG_STAGE
        sta     ptr3
        lda     #>PG_STAGE
        sta     ptr3+1
        rts

; tmp1/tmp2 bytes from ptr1 (main) to A/X (AUX).
put_at: sta     ptr2
        stx     ptr2+1
        jmp     pg_put

api_ptr:
        lda     _A
        sta     ptr1
        lda     _A+1
        sta     ptr1+1
        rts
; Y = an offset in the service table: its word in A/X.
api_word:
        jsr     api_ptr
        lda     (ptr1),y
        pha
        iny
        lda     (ptr1),y
        tax
        pla
        rts
; Calls the service at offset Y with A/X its last (fastcall) argument.
api_call:
        sta     tmp1
        stx     tmp2
        jsr     api_word
        sta     pg_vec+1
        stx     pg_vec+2
        lda     tmp1
        ldx     tmp2
pg_vec: jmp     $FFFF                   ; patched just above

; Ready: music_info credits pt3_lib's author on row 3; name the player
; that really plays, and answer 1.
pg_credit:
        lda     #0
        jsr     pusha
        lda     #3
        ldy     #API_GOTOXY
        jsr     api_call
        lda     #<pg_player
        ldx     #>pg_player
        ldy     #API_CPUTS
        jsr     api_call
        lda     #1
        ldx     #0
        rts

; ram_format hands the /RAM driver a FORMAT with $2000 as its buffer, and
; that driver writes a block there: main $2000-$21FF, which is PT3.PLG's own
; code (plugin_entry returns through it). Measured 2026-10-03 on POM2: the
; return from this routine landed on overwritten code and dropped to the
; monitor. The block is kept in SONG (unused by now) and put back.
_pg_end:
        ldx     #0
@save:  lda     $2000,x
        sta     PG_SONG,x
        lda     $2100,x
        sta     PG_SONG+$100,x
        inx
        bne     @save
        ldy     #API_RAM_FORMAT
        jsr     api_call
        pha
        ldx     #0
@back:  lda     PG_SONG,x
        sta     $2000,x
        lda     PG_SONG+$100,x
        sta     $2100,x
        inx
        bne     @back
        pla
        beq     @done
        ldy     #API_NOTE
        jsr     api_word
        sta     ptr1
        stx     ptr1+1
        ldy     #0
@end:   lda     (ptr1),y
        beq     @app
        iny
        bne     @end
@app:   ldx     #0
        cpy     #0                      ; an empty note: no leading space
        bne     @copy
        inx
@copy:  lda     pg_ram,x
        sta     (ptr1),y
        beq     @done
        iny
        inx
        bne     @copy
@done:  rts

        .segment "PGRODATA"
pg_name:   .byte "PPT3.BIN", 0
pg_rb:     .byte "rb", 0
pg_magic:  .byte "PPT3", PPT3_ABI
pg_player: .byte "Player: GROUiK/French Touch, after S.V. Bulba - A2FC adapter", 0
pg_ram:    .byte " /RAM rebuilt.", 0

        .segment "PGBSS"
pg_f:      .res 2               ; the FILE being streamed
pg_total:  .res 2               ; bytes already in AUX
pg_len:    .res 2               ; bytes expected in all
pg_c:      .res 2               ; the last chunk
pg_dst:    .res 2
pg_max:    .res 1               ; pages
pg_hi:     .res 2               ; PPT3_MODULE + n
