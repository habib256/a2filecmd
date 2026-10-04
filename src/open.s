; open.s -- OPEN's classifier: which viewer opens a file (Return, I, and the
; media browser's neighbour scan).
;
;   unsigned char __fastcall__ file_viewer(const struct Entry* e,
;                                          unsigned char pictures);
;   void __fastcall__ open_entry(const struct A2fcApi* a);   (OPEN's entry)
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
; fopen/fread: never a graphics or AUX bank). Writes nothing else but its
; own state, kept in copy_buf too (from copy_buf + 64), and, for
; open_entry, the viewer's name into input.
; Plain 6502 throughout: both editions assemble this file.

        .macpack longbranch             ; jne & co: a branch, or a jmp if far
        .export _file_viewer, _open_entry
        .import popax, pushax, pusha0, _fopen, _fread, _ferror, _fclose
        .import _image_kind, _full, _copy_buf
        .import _input, _selected, _media_names, _strcpy, _report_error
        .import _fv_ext, _fv_ids, _fv_types, _fv_tids, _image_viewers, _fv_v
        .importzp ptr1, tmp1, tmp2

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

; The state lives as long as a classification: in copy_buf, past the
; bytes the probe reads (it cost 17 bytes of the overlay itself).
ST      = _copy_buf + 64
e       = ST+0                          ; 2 bytes
pics    = ST+2
kind    = ST+3
type    = ST+4
auxl    = ST+5
auxh    = ST+6
len     = ST+7
cand    = ST+8
named   = ST+9
music   = ST+10
fh      = ST+11                         ; 2 bytes
n       = ST+13
bad     = ST+14
idx     = ST+15
at      = ST+17
nxt     = ST+18
; From file_viewer's start to the probe, ptr1 = e: nothing in between
; calls C (by_suffix, binsize, printshop and the rules read it as it is).

        .segment "OPEN"

; void open_entry(const struct A2fcApi* a): the viewer of the selection,
; its overlay's name into input; input stays "" for a directory, an empty
; panel or a path too long, and after a probe error, which is reported.
_open_entry:
        sta     ptr1
        stx     ptr1+1
        lda     #0
        sta     _input
        lda     _selected               ; name[0]
        beq     @r
        lda     _selected+E_TYPE        ; not a directory
        cmp     #$0F
        beq     @r
        lda     _full
        beq     @r
        lda     #<_selected
        ldx     #>_selected
        jsr     pushax                  ; (ptr1 kept)
        ldy     #1                      ; a->arg: pictures
        lda     (ptr1),y
        jsr     _file_viewer
        asl     a                       ; the ID x 2 (IDs < 128); 0: an error
        beq     @err
        pha
        lda     #<_input
        ldx     #>_input
        jsr     pushax
        pla
        tay
        lda     _media_names,y
        ldx     _media_names+1,y
        jmp     _strcpy
@err:   lda     #<_selected
        ldx     #>_selected
        jmp     _report_error
@r:     rts

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
        cmp     V_FONT                  ; .SET / .FONT: a hi-res (HRCG) font
        bne     @ns                     ; only for a BIN of 768 or 1,024
        jsr     binsize                 ; bytes; otherwise no suffix
        bcs     @nfn
        sbc     #2                      ; carry clear: bits 8-15 - 3
        cmp     #2
        bcs     @nfn
        lda     (ptr1),y                ; bits 0-7
        bne     @nfn
        lda     V_FONT
        .byte   $2C                     ; BIT abs: skips the lda #0
@nfn:   lda     #0
@ns:    sta     named
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
        bne     @hx
        lda     cand
        bne     @same
@hx:    jmp     hex
@same:  lda     #0
        sta     pics

@rules: lda     type
        cmp     #$07
        bne     @nf
        lda     V_FONT
        bne     @retm                   ; (never 0)
@nf:    cmp     #$08                    ; LZ4FH: $08/$8066
        bne     @nl
        lda     auxl
        cmp     #$66
        bne     @nl
        lda     auxh
        cmp     #$80
        bne     @nl
        lda     V_LZ
        bne     @retm                   ; (never 0)
@nl:    jsr     printshop
        bcs     @np
        lda     V_PS
        bne     @retm                   ; (never 0)
@np:    lda     pics
        bne     @nr
        lda     type
        cmp     #$FA
        beq     @run
        cmp     #$06                    ; a Take 1 movie MV.x: BIN $8029
        bne     @nr                     ; once extracted, aux 0 in a DOS
        lda     auxl                    ; 3.3 catalog
        ldx     auxh
        beq     @t1z
        cpx     #$80
        bne     @nr
        cmp     #$29
        bne     @nr
        beq     @t1n
@t1z:   tay
        bne     @nr
@t1n:   ldy     #2
@t1c:   lda     (ptr1),y
        cmp     s_mv,y
        bne     @nr
        dey
        bpl     @t1c
@run:   lda     V_RUN
@retm:  ldx     #0                      ; ret, for the rules above and below
        rts
@nr:    lda     V_DUET                  ; a suffix beyond the music
        cmp     named
        bcs     @nn
        lda     named
        bne     @retm                   ; (never 0)
@nn:    lda     pics
        bne     @probe
        lda     music
        cmp     V_PT3
        bcs     @retm

; Probe only in main-RAM copy_buf, never in a graphics/AUX bank.
@probe: lda     kind
        cmp     #2
        jcs     @kinded
        jsr     probe
        bcc     @read
        lda     #0                      ; unreadable: no viewer, an error
        beq     @retm                   ; always
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
        ldx     #5
        bne     @dx                     ; always
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
        ldx     #6
        bne     @dx                     ; always
@rle:   lda     n                       ; HGRR / DHRR version 1 headers
        cmp     #8
        bne     @doc
        ldx     #0
        jsr     cmp8
        beq     @raw
        ldx     #8
        jsr     cmp8
        bne     @doc
@raw:   ldx     #1
        bne     @dx                     ; always
@doc:   lda     type                    ; Epistole `_`, Papyrus/HomeWord $FF:
        cmp     #$04                    ; OR $A0 makes both $FF (DEL and a
        bne     @bsw                    ; high-bit _ too, which no text starts
        ldx     n                       ; with). An empty file is TEXT's:
        beq     @lores                  ; copy_buf[0] is then a stale byte (a
        lda     _copy_buf               ; VisiCalc `>` VISICALC read there)
        ora     #$A0
        ldx     #9                      ; A VisiCalc worksheet's `>`, either
        cmp     #$FF                    ; form, is $BE: kind 10 (VISICALC
        beq     @dx                     ; checks the rest, and points to T)
        inx
        cmp     #$BE
        bne     @lores
@dx:    txa
        bne     @tos                    ; (to @set: too far for one branch)
@bsw:   ldx     pics                    ; Return only: I keeps a high-bit
        bne     @lores                  ; sprite or lo-res pixmap a picture
        ldx     kind                    ; and a page-sized BIN (or .RLE) is
        bne     @lores                  ; one (its top row may be all $80+):
        cmp     #$06                    ; Bank Street Writer: BIN at $0840,
        bne     @lores                  ; $63D0 or 0, high-bit text from its
        lda     auxl                    ; first byte
        ldx     auxh
        beq     @bz
        cpx     #$08
        bne     @b63
        cmp     #$40
        beq     @bt
        bne     @lores
@b63:   cpx     #$63
        bne     @lores
        cmp     #$D0
        bne     @lores
        beq     @bt
@bz:    tay
        bne     @lores
@bt:    ldx     n
        beq     @lores
@bl:    lda     _copy_buf-1,x
        bpl     @lores
        dex
        bne     @bl
        lda     #9
        bne     @tos                    ; (to @set)
@lores: lda     kind                    ; I on a small unmarked BIN or FOT:
        bne     @kd                 ; a lo-res screen or pixmap
        lda     pics
        beq     @gm
        lda     type
        cmp     #$06
        beq     @small
        cmp     #$08
        bne     @kd
@small: jsr     eptr                    ; size 1 to 2,048
        ldy     #E_SIZE+3
        lda     (ptr1),y
        dey
        ora     (ptr1),y
        bne     @kd
        dey
        lda     (ptr1),y                ; bits 8-15
        tax
        dey
        ora     (ptr1),y
        beq     @kd                 ; 0 bytes
        cpx     #8
        bcc     @lo
        bne     @kd
        lda     (ptr1),y                ; $08xx: $0800 only
        bne     @kd
@lo:    lda     #5
@tos:   bne     @set                    ; always
@kd:    jmp     @kinded                 ; (for the branches above: too far)

; Return on a Graphics Magician picture (docs/GRAPHICS-MAGICIAN-FORMAT.md,
; section 3): a BIN whose first command is $2x/$4x/$6x/$8x/$Ax and whose
; commands starting in the bytes read are commands, their argument nibble
; within its limit. A picture that ends in them (its end byte $00 before
; the end of the bytes read; a short file must end) is held to rules 4
; and 5: it draws (a command $Ax/$Cx/$Ex: the highest nibble seen is $A
; or more) and, when its only drawing is lines, has a line start ($8x).
; One that goes on past byte 8 must not open on its first three bytes
; repeated at once (a command written twice in a row, or a run of the
; same 1-byte command): filled tables, data and text do that ($80 x 8,
; 80 FF 00 80 FF 00, spaces), no picture of the corpus or of Appendix B
; does. Real programs start like pictures (LDY #0 / LDA abs,Y is A0 00
; B9 00, a line then the end byte): on 10,594 DOS 3.3 B files, Return
; sent 295 programs and data files and 131 pictures here before these
; rules, 49 and the same 131 since. GMAGIC checks the whole file; kind 11.
@gm:    lda     type
        cmp     #$06
        bne     @kinded
        lda     _copy_buf               ; $20-$AF, an even high nibble
        sec
        sbc     #$20
        cmp     #$90
        bcs     @kinded
        and     #$10
        bne     @kinded
        tax                             ; (0)
        stx     tmp1                    ; the highest command nibble seen
        stx     tmp2                    ; a line start seen
@gl:    cpx     n
        bcs     @ge
        lda     _copy_buf,x
        beq     @gy                     ; the end byte
        pha
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        tay
        pla
        and     #$0F
        cmp     gm_lim,y
        bcs     @kinded
        cpy     tmp1
        bcc     @g1
        sty     tmp1
@g1:    cpy     #8
        bne     @g2
        sty     tmp2
@g2:    lda     gm_lim,y                ; its length: limit 8 one byte,
        and     #3                      ; 1 two, 2 three
        tay
@gi:    inx
        dey
        bpl     @gi
        bmi     @gl                     ; always
@ge:    lda     n                       ; all 8 read: as far as they go,
        cmp     #8                      ; bytes 0-2 not repeated at once
        bcc     @kinded
        ldx     #2
@gr:    lda     _copy_buf,x
        cmp     _copy_buf+3,x
        bne     @gk
        dex
        bpl     @gr
        bmi     @kinded                 ; always
@gy:    lda     tmp1                    ; the picture ends: it draws (rule
        cmp     #$0A                    ; 5), and lines alone need a line
        bcc     @kinded                 ; start (rule 4)
        bne     @gk
        lda     tmp2
        beq     @kinded
@gk:    lda     #11
@set:   sta     kind

@kinded:
        ldx     kind
        beq     @nokind
        lda     _image_viewers,x
        bne     ret                     ; (an ID, never 0)
@nokind:
        lda     pics
        beq     @nopic
        lda     V_RAW                   ; I may explicitly try a raw file
        bne     ret                     ; (never 0)
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
        bne     ret                     ; (never 0)
@types: ldx     N_TYPES                 ; the types that name a viewer alone
@t:     dex
        bmi     hex
        lda     _fv_types,x
        cmp     type
        bne     @t
        lda     _fv_tids,x
        bne     ret                     ; (never 0)
hex:    lda     V_HEX
ret:    ldx     #0
        rts

; ptr1 = e
eptr:   lda     e
        sta     ptr1
        lda     e+1
        sta     ptr1+1
        rts

; Carry clear for Print Shop clip art: BIN, aux $4800/$5800/$6800/$7800,
; 572 or 576 bytes; set otherwise.
printshop:
        lda     auxl
        bne     nobin
        lda     auxh
        and     #$CF
        cmp     #$48
        bne     nobin
        jsr     binsize
        bcs     @r
        cmp     #$02
        bne     nobin
        lda     (ptr1),y
        cmp     #$3C                    ; 572
        beq     @yes
        cmp     #$40                    ; 576
        bne     nobin
@yes:   clc
@r:     rts

; A BIN under 64 KB: carry clear, A = bits 8-15 of its size and Y =
; E_SIZE (bits 0-7 at (ptr1),y; ptr1 = e already). Carry set otherwise.
binsize:
        lda     type
        cmp     #$06
        bne     nobin
        ldy     #E_SIZE+3
        lda     (ptr1),y
        dey
        ora     (ptr1),y
        bne     nobin
        dey
        lda     (ptr1),y
        dey
        clc
        rts
nobin:  sec
        rts

; The viewer the name's suffix gives (fv_ext/fv_ids), with something
; before the suffix; 0 if none. ptr1 = e (the name is at offset 0). Each
; suffix is compared from its last character back to its first, against
; the name's end.
by_suffix:
        ldx     #0
        stx     idx
@next:  lda     _fv_ext,x
        beq     @none                   ; the table's end
        stx     at
@k:     inx                             ; to the suffix's 0
        lda     _fv_ext,x
        bne     @k
        stx     nxt
        ldy     len
@c:     dex
        dey
        bmi     @skip                   ; the name is shorter
        lda     _fv_ext,x
        cmp     (ptr1),y
        bne     @skip
        cpx     at
        bne     @c
        tya                             ; matched: something must come
        beq     @skip                   ; before the suffix
        ldx     idx
        lda     _fv_ids,x
        rts
@skip:  ldx     nxt
        inx
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
        jsr     pusha0
        lda     #8
        jsr     pusha0
        jsr     ldfh
        jsr     _fread
        sta     n
        jsr     ldfh
        jsr     _ferror                 ; 0, or _FERROR: A alone says it
        sta     bad
        jsr     ldfh
        jsr     _fclose                 ; 0, or -1 ($FF in A)
        ora     bad
        cmp     #1                      ; carry: something failed
        rts
ldfh:   lda     fh
        ldx     fh+1
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
; The argument nibble's limit + 1 by high nibble (0: no such command):
; GMAGIC's own table (src/plugins/gmagic.s, lim).
gm_lim: .byte   0, 2, 8, 1, 8, 1, 1, 0, 2, 0, 2, 0, 2, 0, 2, 0
s_dgr:  .byte   "DGR"
s_mv:   .byte   "MV."
s_rb:   .asciiz "rb"
s_rle:  .byte   "HGRR", 1, 0, 0, $20, "DHRR", 1, 0, 0, $40
