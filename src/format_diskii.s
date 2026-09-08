; format_diskii.s -- le formatage physique d'une disquette 5,25 pouces
; (Disk II, 16 secteurs, volume 254), pour le formateur d'A2 File Cmd
; (touche F).
;
; Le coeur vient du « ProDOS Hyper-FORMAT » de Jerry Hewett (Living Legends
; Software, 1985, domaine public), repris par Gary Desrochers (1989), puis
; integre par David Schmidt dans ADTPro (GPL) ; la boucle d'ecriture d'une
; piste (Trans) vient de FASTDSK, via ADTPro. Ici : decoupe en trois appels
; C, une piste a la fois, pour afficher la progression, et sans le systeme
; de messages d'ADTPro. L'image de piste occupe $6500-$7FFF, hors de
; FORMAT.SYS qui tient sous $6400 : les seize secteurs sont a leur place
; d'origine ($6800-$7FFF), mais le GAP1 qui les precede est allonge de 512
; octets de synchro. Une piste ecrite plus longue qu'un tour de disque
; (6 862 octets, contre 6 250 a 6 400 selon la vitesse du lecteur, 6 656
; pour POM2) recouvre le debut du tour, c'est-a-dire ce GAP1 : rien de
; l'ancien contenu ne survit, et le champ d'adresse du secteur 0 reste hors
; de portee. Avec le GAP1 d'origine, un emulateur au tour long gardait un
; bout de l'ancienne piste, et le secteur 0 devenait illisible.
;
;   unsigned char __fastcall__ diskii_begin(unsigned char slotdrive);
;       slotdrive : $60 pour slot 6 lecteur 1, $E0 pour le lecteur 2.
;       Moteur en marche, tete en piste 0, image de piste construite. Rend 0.
;   unsigned char __fastcall__ diskii_track(unsigned char track);
;       Calcule les champs d'adresse, positionne la tete, ecrit la piste.
;       Rend 0 ou un code d'erreur ProDOS.
;   void diskii_end(void);   Moteur coupe.
;
; Les softswitches sont indexes par le slot x 16 (SlotF = $60 pour le slot
; 6) : Step0+SlotF = $C0E0, etc.

        .export _diskii_begin, _diskii_track, _diskii_end

Buffer  = $1D                   ; pointeur (2 octets), libre pour cc65 et ProDOS

Step0   = $C080
Step1   = $C081
Step2   = $C082
Step4   = $C084
Step6   = $C086
DiskOFF = $C088
DiskON  = $C089
Select  = $C08A
DiskRD  = $C08C
DiskWR  = $C08D
ModeRD  = $C08E
ModeWR  = $C08F

        .segment "BSS"
Slot:   .res 1                  ; slot x 16, bit 7 = lecteur 2
SlotF:  .res 1                  ; slot x 16 seul
LByte:  .res 1
Count:  .res 1
Track:  .res 1
Sector: .res 1
TRKcur: .res 1
TRKdes: .res 1
LInOut: .res 1

        .segment "RODATA"
LAddr:  .byte $D5,$AA,$96       ; en-tete d'adresse
        .byte $AA,$AA,$AA,$AA,$AA,$AA,$AA,$AA   ; volume, piste, secteur, somme (4&4)
        .byte $DE,$AA,$EB       ; fin d'adresse
        .byte $7F,$7F,$7F,$7F,$7F,$7F           ; GAP2
        .byte $D5,$AA,$AD       ; en-tete de donnees
        .byte $00
LData:  .byte $DE,$AA,$EB       ; fin de donnees
        .byte $7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F   ; GAP3
        .byte $00
LTable: .byte $02,$04,$06,$00   ; phases vers l'interieur
        .byte $06,$04,$02,$00   ; vers l'exterieur

        .segment "CODE"

; ── diskii_begin ──────────────────────────────────────────────────────────
_diskii_begin:
        sta Slot
        and #$70
        sta SlotF
        tax                     ; $60 : lecteur 1
        lda Slot
        bpl :+
        inx                     ; $61 : lecteur 2
:       lda Select,x            ; choisir le lecteur
        ldx SlotF
        lda DiskON,x            ; moteur
        lda ModeRD,x
        lda DiskRD,x
        ; la protection en ecriture se lit dans Trans, toutes phases
        ; coupees : la phase 1 encore alimentee la ferait croire protegee
        lda #$23                ; on suppose la tete en piste 35
        sta TRKcur
        lda #$00
        sta TRKdes
        jsr Seek                ; ... et on la ramene en piste 0
        ldx SlotF
        lda Step0,x             ; toutes les phases coupees
        lda Step2,x
        lda Step4,x
        lda Step6,x
        jsr Build
        lda #0
        ldx #0
        rts

; ── diskii_track ─────────────────────────────────────────────────────────
_diskii_track:
        sta Track
        sta TRKdes
        jsr Seek
        jsr Calc
        jsr Trans
        bcs @err
        lda #0
@err:   ldx #0
        rts

; ── diskii_end ───────────────────────────────────────────────────────────
_diskii_end:
        ldx SlotF
        lda DiskOFF,x
        rts

; ── Build : GAP1 puis 16 images de secteur entre $6700 et $8000 ───────────
Build:
        lda #$10
        ldx #$65
        sta Buffer
        stx Buffer+1
        ldy #$00
        lda #$7F
        sta LByte
        ldx #$F0                ; GAP1 : $2F0 octets de synchro ($7F) --
        jsr LFill               ; LFill rend X = 0 : les deux suivants font 256
        jsr LFill
        jsr LFill
        lda #$10
        sta Count
LImage:
        ldx #$00
ELoop:  lda LAddr,x
        beq LInfo
        sta (Buffer),y
        jsr LInc
        inx
        bne ELoop
LInfo:  ldx #$AB                ; 343 octets de donnees a $96 (zero en 6&2)
        lda #$96
        sta LByte
        jsr LFill
        ldx #$AC
        jsr LFill
        ldx #$00
YLoop:  lda LData,x
        beq LDecCnt
        sta (Buffer),y
        jsr LInc
        inx
        bne YLoop
LDecCnt:
        dec Count
        bne LImage
        rts
LFill:  lda LByte
        sta (Buffer),y
        jsr LInc
        dex
        bne LFill
        rts
LInc:   inc Buffer
        bne :+
        inc Buffer+1
:       rts

; ── Calc : volume, piste, secteur, somme en 4&4 dans les 16 en-tetes ──────
Calc:
        lda #$03
        ldx #$68
        sta Buffer
        stx Buffer+1
        lda #$00
        sta Sector
ZLoop:  ldy #$00
        lda #$FE                ; volume 254
        jsr LEncode
        lda Track
        jsr LEncode
        lda Sector
        jsr LEncode
        lda #$FE
        eor Track
        eor Sector
        jsr LEncode
        clc                     ; secteur suivant : + 385
        lda Buffer
        adc #$81
        sta Buffer
        lda Buffer+1
        adc #$01
        sta Buffer+1
        inc Sector
        lda Sector
        cmp #$10
        bcc ZLoop
        rts
LEncode:
        pha
        lsr a
        ora #$AA
        sta (Buffer),y
        iny
        pla
        ora #$AA
        sta (Buffer),y
        iny
        rts

; ── Seek : deplacer la tete de TRKcur a TRKdes ────────────────────────────
Seek:
        lda #$00
        sta LInOut
        lda TRKcur
        sec
        sbc TRKdes
        beq LExit
        bcs LMove
        eor #$FF
        adc #$01
LMove:  sta Count
        rol LInOut
        lsr TRKcur
        rol LInOut
        asl LInOut
        ldy LInOut
ALoop:  lda LTable,y
        jsr Phase
        lda LTable+1,y
        jsr Phase
        tya
        eor #$02
        tay
        dec Count
        bne ALoop
        lda TRKdes
        sta TRKcur
LExit:  rts

Phase:  ora SlotF
        tax
        lda Step1,x             ; phase active
        jsr Wait20              ; 20 ms
        lda Step0,x             ; phase coupee
        rts

; 20 ms sans la ROM : cc65 laisse la carte langage en lecture, et $FCA8 y
; tombe dans ProDOS, pas dans le moniteur. 15 x 256 x 5 cycles = 19 200.
; A, X et Y sont preserves : Phase coupe la phase avec X juste apres, et
; une phase 1 restee alimentee se lit comme une disquette protegee.
Wait20: pha
        txa
        pha
        tya
        pha
        ldy #15
@outer: ldx #0
@inner: dex
        bne @inner
        dey
        bne @outer
        pla
        tay
        pla
        tax
        pla
        rts

; ── Trans : ecrire l'image de piste sur le disque ─────────────────────────
; La boucle est calibree au cycle pres : elle doit tenir dans une page,
; d'ou l'alignement. Rend C=1 et A=$2B si la disquette est protegee.
        .align 256
Trans:
        lda #$00
        ldx #$65
        sta Buffer
        stx Buffer+1
        ldy #$32
        ldx SlotF
        sec
        lda DiskWR,x
        lda ModeRD,x
        bmi LWRprot
        lda #$FF
        sta ModeWR,x
        cmp DiskRD,x
        nop
        jmp LSync2
LSync1: eor #$80
        nop
        nop
        jmp MStore
LSync2: pha
        pla
LSync3: lda (Buffer),y
        cmp #$80
        bcc LSync1
        nop
MStore: sta DiskWR,x
        cmp DiskRD,x
        iny
        bne LSync2
        inc Buffer+1
        bpl LSync3              ; jusqu'a $8000
        lda ModeRD,x
        lda DiskRD,x
        clc
        rts
LWRprot:
        lda #$2B
        sec
        rts
