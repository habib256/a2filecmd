; open.s -- OPEN's classifier: which viewer opens a file (Return, I, and the
; media browser's neighbour scan).
;
;   unsigned char __fastcall__ file_viewer(const struct Entry* e,
;                                          unsigned char pictures);
;
; 0 means the probe could not read the file (an error, never a fallback);
; otherwise a viewer ID of viewer_ids.h. `pictures` is 0 for Return, 1 for
; I, and 2 to 4 for the album scans (music, PT3, Duet) that only ask
; whether a neighbour is of the same kind.
;
; It was C, and 893 bytes of the 1,280 OPEN has on the 6502: every new
; format paid 15 to 30 bytes of that window, and the last ones had to be
; bought back byte by byte. The rules are unchanged, in the same order;
; tools/test_file_viewers.py keeps the C text they were written in and
; checks that this code answers exactly as it does, on both processors.
; The tables and the IDs stay in a2fc.c (fv_*), next to viewer_ids.h.
;
; Reads: the entry, the file's first 8 bytes into copy_buf (main RAM, by
; fopen/fread: never a graphics or AUX bank). Writes nothing else.
; Plain 6502 throughout: both editions assemble this file.

        .macpack longbranch             ; jne & co: a branch, or a jmp if far
        .export _file_viewer
        .import popax, pushax, _fopen, _fread, _ferror, _fclose
        .import _image_kind, _full, _copy_buf
        .import _fv_ext, _fv_ids, _fv_types, _fv_tids, _image_viewers, _fv_v
        .importzp ptr1

; Entry fields (a2fc_plugin.h ABI, NAME_LEN 17).
E_TYPE  = 17
E_AUX   = 19
E_SIZE  = 23

; The IDs this code needs, in the order of fv_v[] in a2fc.c.
V_HEX   = _fv_v+0
V_FONT  = _fv_v+1
V_LZ    = _fv_v+2
V_PS    = _fv_v+3
V_RUN   = _fv_v+4
V_DUET  = _fv_v+5
V_PT3   = _fv_v+6
V_RAW   = _fv_v+7
V_UNWRAP= _fv_v+8
N_TYPES = _fv_v+9                       ; entries in fv_types

        .segment "OPEN"

; The state, in the overlay itself: it lives as long as a classification.
e:      .res    2
pics:   .res    1
kind:   .res    1
type:   .res    1
auxl:   .res    1
auxh:   .res    1
len:    .res    1
cand:   .res    1
named:  .res    1
music:  .res    1
fh:     .res    2
n:      .res    1
bad:    .res    1
idx:    .res    1
k:      .res    1
at:     .res    1
nxt:    .res    1

_file_viewer:
        sta     pics
        jsr     popax
        sta     e
        stx     e+1
        jsr     _image_kind             ; A/X = e
        sta     kind
        jsr     eptr
        ldy     #E_TYPE
        lda     (ptr1),y
        sta     type
        ldy     #E_AUX
        lda     (ptr1),y
        sta     auxl
        iny
        lda     (ptr1),y
        sta     auxh
        ldy     #0                      ; the name's length
@len:   lda     (ptr1),y
        beq     @lend
        iny
        bne     @len
@lend:  sty     len
        lda     #0                      ; a Duet candidate: BIN named M.x
        sta     cand
        lda     type
        cmp     #$06
        bne     @nc
        ldy     #0
        lda     (ptr1),y
        cmp     #'M'
        bne     @nc
        iny
        lda     (ptr1),y
        cmp     #'.'
        bne     @nc
        inc     cand
@nc:    jsr     by_suffix
        sta     named
        cmp     V_DUET                  ; the music the suffix names
        beq     @m
        bcc     @m
        lda     #0
@m:     sta     music
        lda     type                    ; an Electric Duet song: $D5/$D0E7
        cmp     #$D5
        bne     @nd
        lda     auxl
        cmp     #$E7
        bne     @nd
        lda     auxh
        cmp     #$D0
        bne     @nd
        lda     V_DUET
        sta     music
@nd:    lda     pics                    ; album scans reject unrelated names
        cmp     #2
        bcc     @rules
        sbc     #1                      ; carry set
        cmp     music
        beq     @same
        lda     pics
        cmp     #4
        jne     hex
        lda     cand
        jeq     hex
@same:  lda     #0
        sta     pics

@rules: lda     type
        cmp     #$07
        bne     @nf
        lda     V_FONT
        jmp     ret
@nf:    cmp     #$08                    ; LZ4FH: $08/$8066
        bne     @nl
        lda     auxl
        cmp     #$66
        bne     @nl
        lda     auxh
        cmp     #$80
        bne     @nl
        lda     V_LZ
        jmp     ret
@nl:    jsr     printshop
        bcc     @np
        lda     V_PS
        jmp     ret
@np:    lda     pics
        bne     @nr
        lda     type
        cmp     #$FA
        bne     @nr
        lda     V_RUN
        jmp     ret
@nr:    lda     V_DUET                  ; a suffix beyond the music
        cmp     named
        bcs     @nn
        lda     named
        jmp     ret
@nn:    lda     pics
        bne     @probe
        lda     music
        cmp     V_PT3
        bcc     @probe
        jmp     ret

; Probe only in main-RAM copy_buf, never in a graphics/AUX bank.
@probe: lda     kind
        cmp     #2
        jcs     @kinded
        jsr     probe
        bcc     @read
        lda     #0                      ; unreadable: no viewer, an error
        jmp     ret
@read:  lda     cand                    ; a Duet song: 8 bytes, 1st and 4th set
        beq     @dgr
        lda     n
        cmp     #8
        bne     @dgr
        lda     _copy_buf
        beq     @dgr
        lda     _copy_buf+3
        beq     @dgr
        lda     V_DUET
        sta     music
@dgr:   lda     n                       ; "DGR": DGRVIEW's to validate
        cmp     #3
        bcc     @arl
        ldx     #2
@dg:    lda     _copy_buf,x
        cmp     s_dgr,x
        bne     @arl
        dex
        bpl     @dg
        lda     #5
        jne     @set                    ; always
@arl:   lda     type                    ; Arlequin: $F8 and "gs" after its size
        cmp     #$F8
        bne     @rle
        lda     n
        cmp     #4
        bcc     @rle
        lda     _copy_buf+2
        cmp     #'g'
        bne     @rle
        lda     _copy_buf+3
        cmp     #'s'
        bne     @rle
        lda     #6
        bne     @set
@rle:   lda     n                       ; HGRR / DHRR version 1 headers
        cmp     #8
        bne     @doc
        ldx     #0
        jsr     cmp8
        beq     @raw
        ldx     #8
        jsr     cmp8
        bne     @doc
@raw:   lda     #1
        bne     @set
@doc:   lda     type                    ; Epistole `_`, Papyrus/HomeWord $FF:
        cmp     #$04                    ; OR $A0 makes both $FF (DEL and a
        bne     @lores                  ; high-bit _ too, which no text starts
        lda     _copy_buf               ; with). No test of n: an empty file
        ora     #$A0                    ; can only show DOCVIEW's empty page.
        cmp     #$FF
        bne     @lores
        lda     #9
        bne     @set
@lores: lda     kind                    ; I on a small unmarked BIN or FOT:
        bne     @kinded                 ; a lo-res screen or pixmap
        lda     pics
        beq     @kinded
        lda     type
        cmp     #$06
        beq     @small
        cmp     #$08
        bne     @kinded
@small: jsr     eptr                    ; size 1 to 2,048
        ldy     #E_SIZE+3
        lda     (ptr1),y
        dey
        ora     (ptr1),y
        bne     @kinded
        dey
        lda     (ptr1),y                ; bits 8-15
        tax
        dey
        ora     (ptr1),y
        beq     @kinded                 ; 0 bytes
        cpx     #8
        bcc     @lo
        bne     @kinded
        lda     (ptr1),y                ; $08xx: $0800 only
        bne     @kinded
@lo:    lda     #5
@set:   sta     kind

@kinded:
        ldx     kind
        beq     @nokind
        lda     _image_viewers,x
        jmp     ret
@nokind:
        lda     pics
        beq     @nopic
        lda     V_RAW                   ; I may explicitly try a raw file
        jmp     ret
@nopic: lda     music
        bne     ret
        lda     type                    ; AppleSingle: $E0/$0001
        cmp     #$E0
        bne     @types
        lda     auxl
        cmp     #1
        bne     @types
        lda     auxh
        bne     @types
        lda     V_UNWRAP
        jmp     ret
@types: ldx     N_TYPES                 ; the types that name a viewer alone
@t:     dex
        bmi     hex
        lda     _fv_types,x
        cmp     type
        bne     @t
        lda     _fv_tids,x
        jmp     ret
hex:    lda     V_HEX
ret:    ldx     #0
        rts

; ptr1 = e
eptr:   lda     e
        sta     ptr1
        lda     e+1
        sta     ptr1+1
        rts

; Carry set for Print Shop clip art: BIN, aux $4800/$5800/$6800/$7800,
; 572 or 576 bytes.
printshop:
        lda     type
        cmp     #$06
        bne     @no
        lda     auxl
        bne     @no
        lda     auxh
        and     #$CF
        cmp     #$48
        bne     @no
        jsr     eptr
        ldy     #E_SIZE+3
        lda     (ptr1),y
        dey
        ora     (ptr1),y
        bne     @no
        dey
        lda     (ptr1),y
        cmp     #$02
        bne     @no
        dey
        lda     (ptr1),y
        cmp     #$3C                    ; 572
        beq     @yes
        cmp     #$40                    ; 576
        bne     @no
@yes:   sec
        rts
@no:    clc
        rts

; The viewer the name's suffix gives (fv_ext/fv_ids), with something
; before the suffix; 0 if none. ptr1 = e (the name is at offset 0).
by_suffix:
        jsr     eptr
        lda     #0
        sta     idx
        tax
@next:  lda     _fv_ext,x
        beq     @none                   ; the table's end
        stx     at
        ldy     #0
@k:     lda     _fv_ext,x               ; k = the suffix's length
        beq     @kend
        inx
        iny
        bne     @k
@kend:  sty     k
        inx
        stx     nxt
        lda     len                     ; the name must be longer
        cmp     k
        beq     @skip
        bcc     @skip
        sbc     k                       ; carry set
        tay
        ldx     at
@c:     lda     _fv_ext,x
        beq     @hit                    ; the whole suffix matched to the name's end
        cmp     (ptr1),y
        bne     @skip
        inx
        iny
        bne     @c
@hit:   ldx     idx
        lda     _fv_ids,x
        rts
@skip:  ldx     nxt
        inc     idx
        bne     @next                   ; always
@none:  lda     #0
        rts

; fopen(full, "rb"), fread(copy_buf, 1, 8), ferror, fclose. Carry set if
; the file could not be opened, read or closed; n = the bytes read.
probe:  lda     #<_full
        ldx     #>_full
        jsr     pushax
        lda     #<s_rb
        ldx     #>s_rb
        jsr     _fopen
        sta     fh
        stx     fh+1
        ora     fh+1
        bne     @open
        sec
        rts
@open:  lda     #<_copy_buf
        ldx     #>_copy_buf
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     #8
        ldx     #0
        jsr     pushax
        lda     fh
        ldx     fh+1
        jsr     _fread
        sta     n
        lda     fh
        ldx     fh+1
        jsr     _ferror
        stx     bad
        ora     bad
        sta     bad
        lda     fh
        ldx     fh+1
        jsr     _fclose
        stx     k
        ora     k
        ora     bad
        cmp     #1                      ; carry: something failed
        rts

; Z set when copy_buf[0..7] equals s_rle+X (8 bytes).
cmp8:   ldy     #0
@b:     lda     _copy_buf,y
        cmp     s_rle,x
        bne     @r
        inx
        iny
        cpy     #8
        bne     @b
@r:     rts

        .segment "OPENRO"
s_dgr:  .byte   "DGR"
s_rb:   .asciiz "rb"
s_rle:  .byte   "HGRR", 1, 0, 0, $20, "DHRR", 1, 0, 0, $40
