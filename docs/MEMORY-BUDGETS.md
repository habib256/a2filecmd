# Consolidation : budgets mémoire

## État actuel (7 octobre 2026, sources b4cd129, candidat 0.9.6)

Le seul tableau à jour de ce document. Relevé sur une construction neuve des
deux éditions (`make ARCH=enh`, `make ARCH=6502`, puis `make mini`) :
65C02 avec cc65 V2.18 (Homebrew), 6502 avec cc65 V2.19 Git e11fb5c
(`~/opt/cc65-head`). Octets libres ; les zones se recouvrent, **rien ne
s'additionne**. Les réserves du résident et de ses surcouches sont la
ligne « reserves » que `tools/check_layout.py` imprime à chaque lien ; celles
des surcouches à table de services sont calculées depuis leur `.map` :
fin de la fenêtre moins fin du dernier segment (code, données et BSS).
Tout ce qui suit cette section est un **journal**, globalement du plus
récent au plus ancien : ses chiffres valent pour leur date. Pour le
relevé suivant, relire la sortie du lien plutôt que recopier ce tableau.

**Pourquoi ces plafonds.** `A2FILE.CODE` doit finir sous `$BEE0` : le
lanceur garde sa pile C sous `$BF00` et charge le fichier jusqu'à sa fin,
il lui faut ces 32 octets (`check_layout`). La carte langage exécute en
banque 2 de `$D400` à `$DFFF`. La BSS basse tient dans `$1000-$1AFF`.
Toutes les surcouches se chargent en `$1B00` : une petite s'arrête à
`$1FFF` (1 280 octets, la page graphique commence en `$2000`) ; une grande
(`OVERLAY_BIG`) va jusqu'à `$3FFF` (`__OVLSIZE__` `$2500`, 9 472 octets),
moins ce qu'elle garde pour elle : brouillon `$3000-$3FFF` (groupe
`XPLUGINS_SCRATCH` ; FIND à partir de `$3100`), `$3D60` pour DOCVIEW,
`$3F9E` pour VOLINFO, BLKVIEW, BLKEDIT, FIXIT et REPAIR (leur copie de 98
octets de la table de services), `$2400` pour DUET (la chanson), `$2000`
pour le code des visionneuses HGR (`XPLUGINS_HGR`, la page qu'elles
dessinent). VERIFY garde sa copie de la table à `$1FC2`. FIND, PT3,
NIBCOPY, NRCLIP, VISICALC et GMAGIC ont leur propre `sdk/*.cfg`. Les
plafonds des surcouches liées au résident sont dans `OVERLAYS` de
`tools/check_layout.py` (la page graphique, ou ce que la surcouche y
garde ; `--big BINARY2` porte BINARY2 à `$2800`). Aucun de ces contrôles ne
doit être relâché pour faire passer un lien.

| Zone : plafond et raison | 65C02 | 6502 |
| --- | ---: | ---: |
| MAIN — résident, jusqu’à `$BEE0` : le lanceur garde sa pile C à `$BF00` et charge `A2FILE.CODE` jusqu’à sa fin ; 32 octets de marge | 9 | 389 |
| LC — carte langage, banque 2 `$D400-$DFFF`, derrière le code QUIT de ProDOS ; image de 3 Ko posée en `$1000` par le lanceur | 13 | 11 |
| LOWRAM — BSS basse `$1000-$1AFF`, entre le tampon d’E/S ProDOS et la fenêtre des surcouches | 84 | 109 |
| STACK GAP — entre la fin du code persistant (sans ONCE) et la pile C de 192 octets sous `$BF00` ; ne mesure pas la consommation de la pile | 26 | 595 |
| FORMAT BSS — état de FORMAT jusqu’au tampon `$3E00` | 98 | 98 |

| Surcouche liée au résident (`$1B00`, plafond) | 65C02 | 6502 |
| --- | ---: | ---: |
| BATCH (`$3000`) | 2 759 | 2 773 |
| NAV (`$2000`) | 142 | 208 |
| CATALOG (`$2000`) | 221 | 205 |
| OPEN (`$2000`) | 11 | 11 |
| COPY (`$2000`) | 13 | 10 |
| FORMAT (`$3C00`) | 49 | 49 |
| IMAGE (`$2000`) | 22 | 24 |
| TEXT (`$2000`) | 49 | 19 |
| HEX (`$2000`) | 74 | 67 |
| DELETE (`$2000`) | 287 | 297 |
| HELP (`$2000`) | 394 | 369 |
| RUN (`$3000`) | 259 | 260 |
| ATTR (`$2000`) | 153 | 150 |
| EDIT (`$2C00`) | 53 | 36 |
| MENU (`$2A00`) | 203 | 152 |
| DISKIMG (`$3700`) | 206 | 161 |
| IMGFS (`$2800`) | 1 315 | 1 327 |
| DOSGET (`$2800`) | 1 217 | 1 213 |
| UNSHRINK (`$3C00`) | 901 | 888 |
| BASLIST (`$2800`) | 752 | 743 |
| COMPARE (`$2000`) | 59 | 83 |
| SEARCH (`$2000`) | 191 | 207 |
| BINARY2 (`$2800`) | 953 | 973 |
| AWP (`$2000`) | 144 | 121 |

DISKIMG : le dernier correctif (`b4cd129`) a déplacé ses trois blocs de
transfert en `$3700-$3CFF`, le bloc d’identité en `$3D00-$3EFF` et son
état, désormais limité à une page, en `$3F00-$3FFF`. Sa fenêtre de code
finit donc à `$3700` au lieu de `$3600` ; le lien et `check_layout.py`
contrôlent cette limite avant les tampons, sans chevauchement.

| Surcouche à table de services | Fenêtre (code + BSS) | Fichier 65C02 / 6502 | Libres 65C02 / 6502 |
| --- | --- | ---: | ---: |
| ARLEQUIN (big) | `$1B00-$1FFF` | 1 154 / 1 171 | 99 / 82 |
| AWDATA (big) | `$1B00-$3FFF` | 7 985 / 8 164 | 205 / 26 |
| BLKEDIT (big) | `$1B00-$3F9D` | 8 261 / 8 228 | 359 / 391 |
| BLKVIEW (big) | `$1B00-$3F9D` | 8 990 / 8 978 | 31 / 43 |
| BOOTBLK (big) | `$1B00-$2FFF` | 2 415 / 2 412 | 1 809 / 1 812 |
| CPM (big) | `$1B00-$3FFF` | 8 076 / 8 046 | 286 / 315 |
| CPMW (big) | `$1B00-$3FFF` | 7 280 / 7 242 | 1 352 / 1 389 |
| CRC (small) | `$1B00-$1FFF` | 1 152 / 1 161 | 13 / 4 |
| DATE (small) | `$1B00-$1FFF` | 1 227 / 1 228 | 8 / 7 |
| DGRVIEW (big) | `$1B00-$2FFF` | 3 753 / 3 844 | 1 555 / 1 464 |
| DISASM (big) | `$1B00-$3FFF` | 7 940 / 7 935 | 885 / 890 |
| DISKCMP (big) | `$1B00-$3FFF` | 6 940 / 6 905 | 854 / 889 |
| DOCVIEW (big) | `$1B00-$3D5F` | 8 404 / 8 405 | 42 / 41 |
| DOS33W (big) | `$1B00-$3FFF` | 4 922 / 4 987 | 3 117 / 3 052 |
| DOSIMAGE (big) | `$1B00-$3FFF` | 7 337 / 7 467 | 1 474 / 1 343 |
| DOSPUT (big) | `$1B00-$3FFF` | 7 346 / 7 431 | 372 / 286 |
| DOSREPL (big) | `$1B00-$3FFF` | 7 520 / 7 618 | 127 / 28 |
| DOSWRITE (big) | `$1B00-$3FFF` | 7 265 / 7 348 | 463 / 379 |
| DUET (big) | `$1B00-$23FF` | 2 193 / 2 193 | 81 / 80 |
| EXTASIE (big) | `$1B00-$1FFF` | 1 201 / 1 227 | 64 / 38 |
| FIND (big) | `$1B00-$30FF`, SETUP `$3100-$38FF` | 6 818 / 6 847 | 341 + 862 / 392 + 833 |
| FIXIT (big) | `$1B00-$3F9D` | 7 566 / 7 599 | 276 / 243 |
| FIXTYPES (big) | `$1B00-$2FFF` | 3 823 / 3 765 | 1 189 / 1 246 |
| FONTVIEW (big) | `$1B00-$1FFF` | 1 121 / 1 127 | 133 / 126 |
| GMAGIC (big) | `$1B00-$1FFF`, HGR `$2000-$3FFF`, LOW `$0C00-$0FFF` | 4 109 / 4 109 | 9 + 6 314 + 12 / 6 + 6 314 + 12 |
| GOTO (big) | `$1B00-$2FFF` | 5 073 / 5 046 | 29 / 55 |
| IDENT (big) | `$1B00-$3FFF` | 6 267 / 6 315 | 3 134 / 3 085 |
| IMGCONV (big) | `$1B00-$3FFF` | 8 777 / 8 943 | 205 / 38 |
| IMGPUT (big) | `$1B00-$3FFF` | 8 025 / 7 977 | 28 / 75 |
| INTBASIC (big) | `$1B00-$3FFF` | 3 863 / 3 906 | 5 182 / 5 139 |
| LZ4FH (big) | `$1B00-$1FFF` | 1 255 / 1 219 | 8 / 43 |
| MACPAINT (big) | `$1B00-$1FFF` | 1 111 / 1 114 | 46 / 43 |
| MDVIEW (big) | `$1B00-$2FFF` | 4 729 / 4 707 | 463 / 485 |
| MKIMAGE (big) | `$1B00-$3FFF` | 4 019 / 4 097 | 5 157 / 5 079 |
| MOVE (big) | `$1B00-$3FFF` | 8 344 / 8 364 | 321 / 300 |
| MUSIC (big) | `$1B00-$2FFF` | 2 752 / 2 713 | 2 551 / 2 589 |
| NEWSROOM (big) | `$1B00-$1FFF` | 948 / 954 | 250 / 243 |
| NIBCOPY (big) | `$1B00-$3FFF` | 7 443 / 7 474 | 1 053 / 1 022 |
| NRCLIP (big) | `$1B00-$1FFF`, HGR `$2000-$3FFF`, LOW `$0C00-$0FFF` | 2 681 / 2 681 | 85 + 7 583 + 101 / 82 + 7 583 + 101 |
| PACKFOT (big) | `$1B00-$1FFF` | 1 218 / 1 249 | 43 / 12 |
| PAINT816 (big) | `$1B00-$1FFF` | 1 204 / 1 215 | 48 / 37 |
| PASCAL (big) | `$1B00-$3FFF` | 7 019 / 7 003 | 1 664 / 1 679 |
| PASCALW (big) | `$1B00-$3FFF` | 7 236 / 7 242 | 1 358 / 1 351 |
| PRINTSHOP (big) | `$1B00-$1FFF` | 1 000 / 1 022 | 265 / 242 |
| PT3 (big) | `$1B00-$36FF`, PG `$3B00-$3FBF` | 9 264 / 9 264 | 86 + 131 / 20 + 131 |
| PURPLE (big) | `$1B00-$1FFF` | 1 261 / 1 265 | 8 / 3 |
| RENAME (small) | `$1B00-$1FFF` | 1 208 / 1 223 | 18 / 3 |
| REPAIR (big) | `$1B00-$3F9D` | 7 820 / 7 884 | 77 / 13 |
| RESCUE (big) | `$1B00-$3FFF` | 6 607 / 6 682 | 2 395 / 2 319 |
| SCIIBIN (big) | `$1B00-$3FFF` | 6 415 / 6 417 | 160 / 158 |
| SHAPES (big) | `$1B00-$1FFF` | 1 236 / 1 239 | 3 / 0 |
| SYNC (big) | `$1B00-$3FFF` | 6 981 / 7 008 | 745 / 717 |
| TAGPAT (small) | `$1B00-$1FFF` | 1 228 / 1 228 | 6 / 6 |
| TREE (big) | `$1B00-$3FFF` | 4 979 / 5 002 | 3 362 / 3 339 |
| TXTCONV (big) | `$1B00-$3FFF` | 6 096 / 6 134 | 2 782 / 2 743 |
| UNDELETE (big) | `$1B00-$3FFF` | 6 909 / 6 924 | 48 / 33 |
| UNSQ (big) | `$1B00-$3FFF` | 6 056 / 6 127 | 1 329 / 1 257 |
| UNWRAP (big) | `$1B00-$3FFF` | 6 657 / 6 662 | 1 314 / 1 308 |
| VERIFY (small) | `$1B00-$1FC1` | 1 114 / 1 129 | 55 / 40 |
| VISICALC (big) | fixe `$1B00-$25FF`, phases `$2600-$35FF`, BSS `$3600-$3FFF` | 4 216 / 4 216 | 156 (VCB 13) / 153 (VCB 13) |
| VOLINFO (big) | `$1B00-$3F9D` | 7 711 / 7 653 | 208 / 266 |
| VOLNAME (small) | `$1B00-$1FFF` | 1 156 / 1 139 | 14 / 31 |
| WIPE (big) | `$1B00-$2FFF` | 5 159 / 5 130 | 50 / 79 |

Mini (`tools/check_mini_layout.py`, correction PCS du 10 octobre 2026) :
résident jusqu'à `$9600` exclus, **0** octet libre sous DOS ; zone basse
jusqu'à `$2000` exclus, **0** octet libre ;
moteur de formatage 459 octets en `$0200`, 5 octets sous les vecteurs DOS
`$03D0`.

## VISICALC : quatre morceaux et une table (4 octobre 2026)

Tout en assembleur (`src/plugins/visicalc.s`, le C ne porte que l'en-tête
et les décalages des services) : en C, la seule partie fichiers/écran
faisait 6,4 Ko. Même ainsi, 9,4 Ko de code ne tiennent pas avec une table
dans `$1B00-$3FFF` : `sdk/visicalc.cfg` coupe le code en une partie qui
reste (`$1B00-$25FF`, en-tête, lecteur de fichier, accès à la table,
nombres littéraux, chargeur de phases) et trois phases au même endroit
(`$2600-$35FF`) : lecture (VCA, dans VISICALC.PLG), recalcul (VCB) et
affichage (VCC), ces deux-là dans `A2FILE/VISICALC.BIN`, chacune marquée
de l'identité du lien (VISICALC.BIN d'une autre construction est refusé).
Libres (mesurés sur les cartes du lien, 6502/65C02) : partie fixe
**151/154**, VCA 2 696, VCB **13**, VCC 1 428 ; BSS `$3600-$3873`. Avant
Échap pendant le recalcul (2026-10-06) : 63/66, 2 905, 16, 1 428. Échap
coûte 23 octets de partie fixe (`poll`, `ppeek`), « Stopped. » 9, et 3 de
VCB (`jsr poll` dans `rnext`) ; ils sont payés, et au-delà, par le message
« Sheet too big » et ses chaînes, passés de la partie fixe à VCA (la phase
de lecture est encore là quand la table est refusée). Les tables fixes
(débuts de rangée, ligne lue, colonnes) occupent `$0C00-$0FFF`, le second
tampon ProDOS (un seul fichier ouvert à la fois) ; la sauvegarde de la page
zéro pour la ROM, `copy_buf + 256`.

La table (8 octets par valeur : la rangée, la valeur tassée) va de la fin
de la BSS à `$3FFF` : **241 valeurs**. Au-delà, la mémoire auxiliaire
`$4000-$BEFF` (4 064 valeurs), avec `aux_consent` (API 6 : pas de question
si /RAM est vide), MACHID 128 Ko vérifié, puis `ram_format` et la note
« /RAM rebuilt. » ; `leave`, qui appelle `ram_format`, est en tête du code,
sous `$2000` que `ram_format` écrase. Les accès à la table passent tous par
six petites routines qui basculent RAMRD/RAMWRT autour d'un seul accès,
interruptions coupées ; celles de lecture sont recopiées en mémoire
auxiliaire à la même adresse (le processeur y lit ses instructions tant que
RAMRD est mis) ; en mémoire principale, leurs STA $C00x deviennent BIT.

Cœur OPEN : la règle `>` (6 octets) et l'entrée d'`image_viewers` ont été
payées par quatre `jmp ret` devenus `bne ret` (A n'y vaut jamais 0) : OPEN
**4/9** octets libres (65C02/6502). Le nom « VISICALC » est en carte langage
(MAIN n'avait pas ses 9 octets) : MAIN **8/420**, LC **37/28**.

## DOCVIEW : calculs, en-têtes et bas de page d'Epistole (29 septembre 2026)

DOCVIEW quitte le groupe des surcouches à brouillon `$3000` : code et BSS
dans `$1B00-$3D5F` (`__OVLSIZE__` `$2260`, cas à part dans le Makefile),
brouillon `$3D60-$3FFF` (table des pages 16 × 14, copie de la table de
services 112 octets, ligne et attributs, état, tampon de lecture 112
octets). Libres sous `$3D60` : **51** (6502) / **59** (65C02) ; 6 / 40
avant les corrections du 2026-10-06, qui ont pourtant ajouté du code
(garde de rangée dans `emit`, blocs `_DB`/`_EN` sans récursion, numéro de
page sur trois chiffres) : le centrage calculé en octets (`emit`, −25
sur 6502) et les deux lettres de `show_def` passées en un entier au lieu
d'une chaîne (la fonction ne grossit que de 4 octets avec ses trois
chiffres, et `asrax1` et `ldptr1sp` quittent le lien : 22 octets) ont
payé. Le saut de
page en attente a son octet dans `struct Layout` (10 octets, 14 par début
de page) : les 16 octets de la table viennent du tampon de lecture. La copie
de la page zéro `$50-$FF` pendant un calcul (176 octets), l'état des
variables au début de la page (144) et le champ lu (64) vivent dans le
`copy_buf` de la table de services.

Ce qui a payé : l'évaluateur en assembleur (`docview.s`, ~1,9 Ko de code ;
en C, cc65 en faisait 3,7 Ko), les positions sur 16 bits (plus
d'arithmétique `long`), 16 pages d'historique au lieu de 64, le tampon de
lecture de 2 Ko à 128 octets, `epistole()` par table. `--codesize` plus
bas grossit le code (5074 → 6421 octets à 10) : ne pas y compter.

## Page de titre : ni effacée, ni escamotée (29 septembre 2026)

MAIN **57/469** (93/503 avant) : `key_wait` (display.s), la boucle
d'attente du diaporama devenue sous-programme, et son appel dans `main`
(26 octets) ; le test de RD80VID/RD80STORE qui évite l'appel de
`videomode` quand le lanceur a déjà mis le 80 colonnes (10 octets).

## Diaporama des visionneuses et suite des films Fantavision (29 septembre 2026)

Réserves au lien, 65C02/6502 : MAIN **93/503** (203/609 avant), écart
avant la pile 121/720 (231/826), carte langage 62/53 et LOWRAM 91/116
(inchangées à l'octet près pour LC ; LOWRAM −2 : `slideshow`). Sous
l'objectif de 256 octets MAIN sur 65C02, déjà manqué avant (203) par les
formats non publiés ; aucun contrôle de disposition n'a été relâché.

Ce qui coûte 110 octets : `slide_getc` en assembleur (display.s, 58
octets ; la même en C en prenait 95), le tour de l'album dans
`media_prepare` (+31) et `view_image` (+11), la portée du diaporama dans
`overlay_run` (+11). La carte langage (62/53) ne pouvait pas recevoir
`slide_getc` sur 6502.

FANTA.SYSTEM (hors résident) : programme `$A400-$BEDD`, 34 octets libres
sous `$BF00` ; `cmdbuf` (85 octets) en tête, sous `$BB00` que le tampon du
thunk de retour recouvre ; LOW 52 octets libres ; page zéro jusqu'à `$D9`.
Le chargeur (`LOADER`, `$2000-$2672`) porte la lecture du répertoire.

## 4 octobre 2026 : écrans texte et polices HRCG

OPEN : 63/68 → **15/20** octets (65C02/6502) pour la règle `.SET`/`.FONT`
+ BIN de 768/1 024 octets (suffixes dans `fv_ext`, test de taille partagé
avec Print Shop par `binsize` dans `src/open.s`). DGRVIEW (fenêtre de
5 376 octets jusqu'à `$3000`) : 2 999/3 058 → 3 753/3 844 octets avec la
lecture texte, T/A et l'écriture des seuls octets visibles. MAIN et LC
inchangés.

## Préparation 1.0 : l'audit des signes rend des octets (26 septembre 2026)

Réserves au lien après `rm -rf build build-6502`, 65C02/6502 : MAIN
**415/821** (413/805 avant), écart avant la pile 443/1038 (441/1022),
carte langage 78/69, LOWRAM 82/107 et NAV 142/208 inchangées. Surcouches :
RUN 1700/1708 (1691/1696), DELETE 286/296 (286/291) ; AWDATA 8 034/8 181
octets (8 040/8 195), DGRVIEW 2 999/3 058 (2 999/3 082) ; IDENT, MDVIEW et
DISASM gardent leur taille.

Rien n'a coûté : les sites de `tools/sign_compare.py` prouvés non négatifs
reçoivent un transtypage vers le type que cc65 2.19 employait déjà (code
65C02 identique ou plus court), et la comparaison non signée du 6502 est
plus courte que la signée. `addr_len <= 18 + 40` compare un octet au lieu
d'un mot. Le transtypage `(unsigned char)` des chiffres hexadécimaux de
DISASM coûtait 2 octets dans les deux éditions : la ligne est annotée à la
place.

## Préparation 1.0 : les grands catalogues comptés, pas indexés (26 septembre 2026)

Réserves au lien après `rm -rf build build-6502`, 65C02/6502 : MAIN
**413/805** (494/885 avant), carte langage 77/68, LOWRAM 82/107 et NAV
142/208 inchangées, écart avant la pile 441/1022. L'objectif de 256 octets
MAIN sur 65C02 reste tenu, avec 157 octets de marge.

Ce qui coûte 81/80 octets : `dir_count_block` (a2fc_mli.s, une quarantaine
d'octets) compte les entrées actives d'un bloc de répertoire entièrement
situé avant la fenêtre ; la boucle qui l'appelle dans `dir_next` ; et
`move_cursor` réordonné (le signe testé d'abord : cc65 2.19 compilait
`target >= pan->count` comme une comparaison non signée, et Haut ou Gauche
près du haut de toute fenêtre sauf la dernière chargeait la suivante sur
65C02). Aucune BSS : rien n'est retenu d'une page à l'autre.

L'index de points de reprise demandé par la piste 4 a été prototypé et
mesuré, puis écarté. En C, il coûtait 658 octets MAIN en 6502 ; réécrit en
assembleur (table de 4 fenêtres par panneau, somme du bloc d'en-tête et du
bloc repris, SET_MARK et READ directs), encore 488 octets en 65C02, soit
**6 octets** libres : sous l'objectif de 256, et 56 octets de LOWRAM en plus.
Et il ne supprimait pas la lecture : SET_MARK sur un fichier répertoire fait
parcourir la chaîne des blocs à ProDOS (environ 6 500 cycles par bloc sur la
carte HDV de POM2), si bien qu'une fenêtre sautée coûtait encore ~70 000
cycles (prototype C mesuré en 6502) contre ~247 000 avec le comptage et
~431 000 avant. Le comptage garde un peu plus de la moitié du gain du
prototype sur la dernière page d'un catalogue de 700 ou 1 500 entrées, sans
aucun état à invalider après un changement de disque ou une écriture. Les
chiffres sont dans
[les mesures](PERFORMANCE-0.9.2.md#pagination-des-grands-catalogues-10).

## Préparation 1.0 : 412 octets rendus par `pan_at` (25 septembre 2026)

L'objectif MAIN de 256 octets sur 65C02 est atteint. Réserves au lien
après `rm -rf build build-6502`, 65C02/6502 : MAIN **494/885** (82/485
avant), carte langage **77/68** (66/57), LOWRAM 82/107 inchangée, écart
avant la pile 522/1102 (110/702).

Ce qui a payé : une seule réécriture mécanique. cc65 calcule
`&panels[active]`, `&panels[!active]` et `panels[p].champ` en multipliant
l'indice par 98 (`sizeof(struct Panel)`) avec `tosmula0` : une vingtaine
d'octets par site, et il y en avait 35 dans le seul segment résident.
`pan_at(p)` (`__fastcall__`, 21 octets, dans CODE, hors de tout bloc
`code-name`) rend `panels + 1` ou `panels`, et chaque site coûte cinq
octets. `p` vaut toujours 0 ou 1 : `active` n'est écrit que par
`active = !active` et par `cfg_parse`, qui refuse tout autre chiffre que
0 ou 1. Les indices constants (`panels[0]`, `panels[1]`) et les `sizeof`
restent tels quels : cc65 les résout au lien. Les surcouches liées avec le
résident appellent la même fonction, d'où leurs gains :

| Surcouche | 65C02 avant → après | 6502 avant → après |
| --- | ---: | ---: |
| ATTR | 19 → **153** | 20 → **150** |
| TEXT | 44 → 120 | 16 → 94 |
| COMPARE | 17 → 59 | 41 → 83 |
| EDIT | 19 → 30 | 5 → 16 |
| DISKIMG | 57 → 68 | 9 → 20 |
| HEX | 49 → 74 | 42 → 67 |
| DELETE | 261 → 286 | 266 → 291 |
| SEARCH | 177 → 191 | 193 → 207 |
| BATCH, RUN, IMGFS, DOSGET, UNSHRINK, BINARY2 | +14 à +117 | +14 à +117 |

NAV, CATALOG, OPEN, COPY, FORMAT, IMAGE, HELP, MENU, BASLIST et AWP ne
changent pas : leur code n'avait aucun de ces sites. Disquettes : la 140K
passe de 22 à 24 blocs libres, la 800K de 608 à 610, les deux XL gagnent
deux blocs.

Les harnais hôtes qui découpent `a2fc.c` ou incluent `batch.h`,
`config.h`, `launch.h` et `media.h` déclarent leurs propres `panels` : ils
reçoivent `#define pan_at(p) (&panels[p])`, la même adresse. La fonction
est placée après `batch_state_fits`, hors de la tranche `#define
POOL_SIZE` que découpe `test_tree_walk.py`.

À ne pas refaire à la main : la même multiplication existe pour
`pan->e[i]` (29 octets par entrée, 26 sites résidents). Une aide à deux
paramètres coûte plus cher à l'appel ; ne l'essayer que si la réserve
redescend, en mesurant au lien.

## Mini : l'aperçu hexadécimal lisible payé par la page d'aide (25 septembre 2026)

L'aperçu hexadécimal passe de 16 lignes de 32 chiffres collés à huit
octets espacés par ligne suivis de leurs caractères, en deux moitiés de
128 octets que gauche/droite (`-`/`+`, `<`/`>`) choisissent. Mesuré au
lien : le code et les données restent à 15 659 octets, le BSS passe
de 11 203 à 11 202 ; le résident finit à **$95D5, 43 octets libres**
sous `$9600` (42 avant). LOW (1) et FORMAT (5) inchangés.

- **−66** : la fonctionnalité. `hex_rows` (dans `screen.s`, pour que le
  banc sim65 l'exécute sans `ui.s`) remplace la boucle hexadécimale de
  `view` ; `put_char`, le « caractère ou point » que l'aperçu texte
  faisait en ligne, sert aux deux ; les touches de moitié sont une table
  de six octets parcourue par `dex`, et la moitié vit dans le bit 7 de
  `vw_mode` (1 ou $81), lu par `lsr`/`asl`. Le texte `PREVIEW: FIRST
  SECTOR` est commun, le suffixe dépend du mode.
- **+66** : la page d'aide. `inline_text` comprend `|` (deux lignes plus
  bas, colonne 0, 14 octets) ; les dix couples `ldy`/`jsr at_left`,
  neuf `PRINT` sur onze et le `lda #0`/`sta inverse` après le titre
  disparaissent (un `~` éteint l'inverse). Deux textes et non un : un
  `PRINT` s'arrête à 255 octets. `jsr key`/`rts` devient `jmp key`.
- **+1** de BSS : `vw_prev`, qui ne servait qu'à l'ancienne boucle.

Ce que cela ne change pas : l'écran d'aide, vérifié cellule par cellule
dans `bench/mini33.py`, l'aperçu texte, aucune écriture disque.

## Mini : le signe de vie dans les relectures RWTS (25 septembre 2026)

Le crochet de `format.s` (`fmt_hook`, `fmt_on`, `fmt_off`, `fmt_ticking`,
`fm_sig`, 64 octets) laisse la place à un seul mécanisme dans `rwts.s`,
qui prête le JSR de RDADR16 (`$BDC4`) pendant une lecture et celui de la
recherche de piste (`$BED6`) pendant un formatage : une table de deux
sites et de deux signatures indexée par commande, un crochet commun
(`lend_hook`, qui rappelle la routine de DOS par un JSR recopié de la
signature) et une restauration sans condition après l'appel : quand
rien n'est prêté, `iob` pointe sur `lend_call` lui-même, que la boucle
réécrit avec ses propres octets. L'adresse de l'IOB est redemandée à
`RWTS_LOCATE_IOB` (un octet de moins que `lda`/`ldy`), ce qui libère
`iob` pour désigner le site. Au lien : **+23 octets**, le résident finit
à **$95ED, 19 octets libres** sous `$9600` (42 avant). FORMAT à `$0200`
inchangé (459 octets, 5 libres) : l'appel y reste `jsr rwts_format`.

Ce que cela ne change pas : `bench/mini33_lend.py` compare 749 appels
RWTS avec et sans prêt (retenue, code, octets lus) et les deux disquettes
octet pour octet ; `bench/mini33_time.py` donne 25 275 341 cycles contre
25 275 251, toujours 1,11 tour par secteur.

## Mini : 92 octets rendus pour le signe de vie du formatage (22 septembre 2026)

Le crochet posé sur la boucle par piste de RWTS FORMAT (`fmt_hook`,
`fmt_on`, `fmt_off`) faisait passer le résident 50 octets sous DOS. Trois
réécritures à comportement identique l'ont payé, mesurées au lien : le
résident finit à **$95D6, 42 octets libres** sous `$9600`.

- **+30** : les cinq valeurs vivantes d'un panneau (`drive`, `volume`,
  `count`, `selected`, `error`) sont un bloc de `data.s` dans l'ordre du
  bloc `pan_*`, qui est le même à deux octets par champ. `remember` et
  `activate` parcourent les deux blocs avec un index chacun. Des
  `.assert` dans `data.s` refusent une construction où les deux ordres
  divergeraient.
- **+34** : `mirror_panel` copie les six paires du bloc `pan_*` en
  boucle, `copy_tags` lit les côtés dans `active` (« = » est son seul
  appelant) et passe de la source à la destination par un
  `eor #TAG_BYTES`, et `copy_entries_to_left` disparaît avec lui.
- **+28** : `have_entry`, les deux questions — panneau vide, catalogue
  illisible — que huit touches de la boucle principale posaient en ligne.

Ce que cela ne change pas : aucune écriture, aucun ordre d'écriture,
aucun texte d'écran. `bench/mini33_time.py` donne 1,11 tour de disque par
secteur avant comme après (25 274 290 contre 25 275 251 cycles au total).

## Préparation 0.9.2 : progression visible (22 septembre 2026)

Réserves après les barres et les signes d'activité, 65C02/6502 : MAIN
**82/485** (83/491 avant), carte langage **66/57** inchangée, LOWRAM
82/107, écart avant la pile 110/702. Surcouches du cœur : DELETE 261/266,
IMGFS 1287/1299, DOSGET 1195/1191, BINARY2 967/987, SEARCH 177/193,
COMPARE **17/41**, MENU 260/209, UNSHRINK 904/896, **DISKIMG 57/9**
(la barre de pré-remplissage coûte 42 octets en 6502), FORMAT 269/269.

Ce qui l'a payé : la remise à zéro des compteurs « n/m » avant chaque
surcouche (14 octets MAIN) et le parcours d'album (8) sont compensés par la
sauvegarde des compteurs déplacée de `copy_or_move` vers DELETE
(`moved_tree_delete`, en assembleur : la pile 6502 garde les compteurs ;
en C, ses variables statiques faisaient passer DELETE à trois blocs et la
disquette de banc à zéro bloc libre, où la configuration ne s'écrit plus). `activity_tick` lit RDTEXT ($C01A) et n'écrit plus
sur une image lo-res. Dans FORMAT, le code Disk II est aligné sur 256
octets : la réécriture rapide du bitmap faisait passer la partie C sur la
page suivante (269 → 13) ; seul un signe d'activité par page a été gardé.

Surcouches de service les plus serrées après ce travail : `crc` 13/4
(la copie `buf` de `copy_buf` retirée pour payer le signe), `date` 8/7
(mois par `ror`, table des dizaines remplacée par des décalages),
`rename` 18/3, `verify` 55/40, `fixit` 3 (description du menu
raccourcie), `dosrepl` 1 en 6502 (réservation VTOC en assembleur),
`undelete` 25/21, `paint816` (refus regroupés). Mini : 19 octets sous
DOS (34 avant) pour le signe RWTS et la barre principale après Y.

## Préparation 0.9.2 : optimisation et récupération

Après compilation des deux architectures, réserves 65C02/6502 : MAIN
**83/491**, carte langage **66/57**, LOWRAM **82/107**, écart avant la
pile **111/708**, HELP **395/369**, IMGFS **1295/1306**, DOSGET **1218/1218**.
COPY reste à **13/10**. Aucun plafond ni contrôle de disposition modifié.
L’objectif MAIN 65C02 de 256 octets reste ouvert. Le prototype de cache
des informations de volume a été écarté pour son coût résident.

## État au 20 septembre 2026 (0.9.1 publiée, historique)

Réserves au lien, en octets, 65C02/6502 ; ce ne sont pas des sommes. Le
tableau est celui que `tools/check_layout.py` imprime à chaque lien
(« reserves ») : le relire après chaque relink plutôt que le recopier.

| Zone | 65C02 | 6502 | Objectif |
| --- | ---: | ---: | --- |
| MAIN (résident, plafond `$BEE0`) | **203** | 609 | 256 sur 65C02 : à rétablir avant enrichissement |
| Carte langage | 66 | 57 | ne pas descendre |
| CATALOG (catalogues DOS 3.3 et images) | 221 | 205 | surcouche de lecture, pas à enrichir |
| LOWRAM | 98 | 123 | — |
| Écart avant la pile C de 192 octets | 119 | 711 | — |
| NAV | 142 | 208 | — |
| DELETE | 304 | 309 | libéré par le parcours résident |
| OPEN | 168 | 173 | classifieur en assembleur (`src/open.s`) depuis le 26 septembre ; une règle coûte 10 à 20 octets |
| IMGFS (grande depuis le 14 septembre) | 1 286 | 1 310 | — |
| UNSHRINK (code jusqu’à `$3BFF`) | 907 | 899 | — |
| ATTR | 19 | 20 | idem |
| EDIT | 19 | **5** | — |
| COMPARE | 23 | 47 | — |
| COPY | 13 | 10 | — |
| Mini (sous DOS à `$9600`) | **9** | — | 270 : `copy_side` et la relecture groupée |

26 septembre 2026 : **OPEN desserré**. Newsroom, Movie Maker, Fantavision
et DOCVIEW avaient ramené OPEN à 20/4 octets ; le classifieur `file_viewer`
occupait à lui seul 893 des 1 280 octets de la fenêtre en 6502. Il est passé
en assembleur (`src/open.s`), mêmes règles dans le même ordre, tables et
identifiants restés en C à côté de `viewer_ids.h`. OPEN : 168/173 octets
libres, LOWRAM +16 (les statiques du C). La version C est gardée comme
spécification (`tools/file_viewer_ref.c`) : `tools/test_file_viewers.py`
exécute l'assembleur sous sim65 sur les deux processeurs et exige la même
réponse que la référence sur toutes les attentes et sur 300 cas tirés au
hasard (noms, types, aux, tailles, contenus, `pictures`, pannes d'E/S).

20 septembre 2026 : réveil de la Mockingboard 4c sur //c uniquement, avec
exposition temporaire de la ROM puis restauration de la carte langage.
La souris est désactivée si la carte masque sa ROM sur //c. Coût résident :
33 octets enhanced, 21 octets 6502 ; aucune écriture AUX ou disque.

19 septembre 2026 : phases et activité visibles, contrôles de disposition
inchangés et valides sur les deux architectures. La réserve MAIN 65C02 est
sous l'objectif de confort de 256 octets : ne pas ajouter de fonctions avant
de la reconstituer. Le compteur d'activité occupe un octet de BSS ; sa seule
écriture d'écran directe est `$06F7` (MAIN, ligne 21, colonne 79). Les phases
utilisent la ligne d'information, sans effacer le résultat ou l'erreur ligne 22.
Le banc POM2 `memory:stack` mesure 145 octets de pile utilisés sur 192
(47 de marge) pour ses parcours de visionneuses et de copie récursive ;
ce résultat ne couvre pas tous les chemins possibles.

19 septembre 2026, **ce qu'`audit()` ne rend pas**. Quatre tentatives
mesurées au lien, toutes perdantes : le parcours des paires de la liste
T/S au pointeur (+26), `claim()` avec `free_sector` et `mask` inlinés
(+41), `claim(piste, secteur)` au lieu d'un numéro 0-559 (+22 en 6502).
Gardée malgré son coût : le contrôle des pistes réservées lu directement
dans le bitmap, deux octets par piste au lieu de 560 tours avec deux
divisions — **+3** octets pour une boucle 140 fois plus courte, sur un
chemin que toute écriture DOS 3.3 emprunte deux fois. `audit()` reste à
826 octets en 65C02, dans trois surcouches. Ne pas refaire ces passes.

18 septembre 2026, deux corrections qui *rendent* des octets : la ligne
d'un dossier qui n'affichait pas ses marques (les deux formats partagent
leur tête, le `sprintf` qui posait la barre oblique disparaît : **+27** de
MAIN) et l'écran d'attente du visionneur d'images, `loading_screen`, une
seule fonction pour l'entrée dans l'album et pour ses transitions, posée
dans MAIN et non dans la carte langage — la carte remonte de 60 à 73
(51 à 64 en 6502), MAIN de 457 à 465 après que `overlay_run` a étendu le
même écran d'attente aux dix visionneurs spécialisés.

18 septembre 2026, **la place prise dans OPEN** pour le routage Retour
des `.QQ`, `.ACU` et `.BA3` : la surcouche la plus serrée passe de 4 à 28
octets libres en 6502 (26 à 43 en 65C02), les trois suffixes, le type
`$09` et deux entrées de `media_names` déjà payés. Deux formes :

- `ends` fondu dans `by_suffix` : séparées, la longueur de chaque suffixe
  était mesurée deux fois, une par fonction (**+26**) ;
- la queue de `file_viewer`, les types ProDOS qui nomment une surcouche à
  eux seuls (`$04`, `$09`, `$19`, `$1A`, `$1B`, `$FC`, `$FF`), devient deux
  tables lues dans une boucle : quatorze octets de code par type contre
  deux de données, et un type de plus ne coûte plus que ces deux octets.

Ce qui n’a pas payé : lire `e->size` comme deux mots (l’idiome de
`page_size`) pour les deux comparaisons longues de `file_viewer`. La
fonction y gagne 24 octets, l’aide résidente en coûte 43 : une comparaison
longue ne se paie qu'à partir de trois mentions. MAIN perd 9 octets, les
deux noms ajoutés à `media_names` (`UNSQ`, `BASLIST`).

18 septembre 2026, **+190 octets de MAIN en 65C02 (+188 en 6502)**, sans
changement de comportement : MAIN passe de 276 à 466 (6502 : 677 à 865),
la carte langage de 34 à 60, CATALOG de 30 à 224. Quatre formes écrites
plusieurs fois deviennent une fonction, et la répartition des touches du
menu principal devient une table :

- `empty_panel` et `fill_entry` (les trois vidages de panneau et les deux
  remplissages d'entrée de `read_panel`, `read_image_dir` et
  `read_dos33_panel`) : CATALOG passe de 30 à 224 octets libres, MAIN y
  perd les 172 octets des deux fonctions et en regagne autant en appels ;
- `ov_keys` / `ov_names` : les dix lettres qui ne font qu'ouvrir une
  surcouche en lui passant leur propre lettre (M, S, X, F, E, W, puis R, K,
  A, L pour ATTR) quittent le `switch` de `main` pour une table lue dans le
  `default` : **+115**, `main` de 1 980 à 1 680 octets ;
- `file_at_cursor` (le fichier sous le curseur, `full` construit), partagé
  par T et H : **+37** ;
- `open_row22` (la ligne de message effacée et prête, sept appelants) :
  **+36** ; `reread_both` (les deux panneaux relus et redessinés, trois
  appelants) : **+11**.

Piège rencontré en chemin : posées juste avant `read_dos33_panel`,
`empty_panel` et `fill_entry` tombaient **dans le segment CATALOG** (le
`#pragma code-name (push, "CATALOG")` les précède), et `read_panel`, qui
est résident, les appelait dans la fenêtre d'une surcouche. Le lien
passait, la réserve MAIN annonçait 638 octets — 172 de trop, la taille
exacte des deux fonctions — et le programme n'aurait marché que tant que
CATALOG était chargée. Une fonction partagée par le résident et une
surcouche se pose **hors** des blocs `code-name` ; ici, juste après
`add_entry`. Vérifier avec `ca65 -l` dans quel segment chaque `.proc`
tombe, la réserve seule ne le dit pas.

Mesure : `cc65` vers `.s`, `ca65 -l`, somme des `.proc`/`.endproc` par
segment — les fonctions statiques ne sont pas dans `a2fc.lbl`. Ce qui n'a
rien donné : `--codesize` (80 comme 125 débordent, 100 est un optimum
local) ; les chaînes dupliquées (cc65 les fusionne déjà : 5 octets en tout).
Ce qui reste, par ordre de taille : la famille `printf` de la bibliothèque
cc65 (1 292 octets pour 84 appels), et sortir du résident la liste des
volumes (`read_volumes` + `ask_disk`, ~720 octets) dans une petite
surcouche, comme CATALOG l'a fait — au prix d'un bloc de la disquette BOOT.

6 octobre 2026 : REPAIR n'écrit plus que là où un pointeur abîmé ne peut pas expliquer ce qu'il voit (docs/FIXIT.md §5, « Ce que REPAIR refuse de croire ») ; les trois règles ont été payées par la fusion des deux boucles de l'écran de plan et la chute du masque `on`. Réserves au lien : REPAIR **61** octets en 65C02 (50 avant), **36** en 6502 (30 avant) ; FIXIT 3 et 3, inchangé à l'octet du masque `ENT_ACCESS` près. Le journal des formes est dans docs/FIXIT.md §4.

17 septembre 2026 : FIXIT et REPAIR gardent leurs réclamations en AUX au-delà de 4 096 blocs (`src/plugins/fixit_bits.inc`) et ne parcourent l'arbre qu'une fois ; FIXIT gagne le contrôle rapide. Réserves au lien, après l'acquittement d'Échap par écriture de `$C010` : FIXIT **1** octet sur les deux processeurs, REPAIR 62 (42). Le journal des formes est dans docs/FIXIT.md §4, « Un seul parcours ». VOLINFO et FIND ne copient plus que 98 octets de la table de services : même taille.

16 septembre 2026 : `mn_group3` nomme FIXIT et REPAIR (catégorie « Disks ») ; ces chaînes vivent dans la surcouche MENU, dont la réserve passe de 1 846 à 1 833 octets en 65C02 (1 794 à 1 781 en 6502), MAIN inchangé (361 et 790 au lien du jour).

Au lien de la 0.8.5, MAIN 65C02 ne gardait que 23 octets (518 sur 6502) :
DUET, DOSGET, IDENT/FIXTYPES et la sonde DUET du routage avaient consommé
la réserve retrouvée au neuvième incrément du chantier 1. Le reste de ce
document est le journal chronologique de la consolidation, le plus récent
en premier.

Relectures IMGFS et UNSHRINK (chantier 3), 14 septembre 2026 : les deux
surcouches n’avaient plus que 5 et 9 octets. IMGFS devient une grande
surcouche (plafond `$2800`) : ses entrées viennent de l’instantané `$3000`
comme DOSGET, le bloc d’index et le bloc relu occupent `$2800` et `$2A00`,
et la marque « surcouche grande » ne coûte qu’un bloc de plus sur BOOT
(3 libres). UNSHRINK garde son cœur assembleur en tête et son pilote C
jusqu’à `$3BFF` ; l’état passe de `$3000` à `$3E00` (la place de DISKIMG,
jamais chargée en même temps) et le tampon relu à `$3C00`. Leçon : ce
tampon d’abord posé à `$3000` a été recouvert par le code dès que la
surcouche a dépassé son ancien plafond — un tampon à adresse fixe se place
au-dessus du plafond de `check_layout`, jamais dedans. L’enrobage
`new_output`, sans appelant, quitte le résident : MAIN 65C02 passe de 299
à 429 octets (6502 : 742 à 873). IMGFS 1 520/1 530, UNSHRINK 2 727/2 739.

Dossiers marqués (chantier 4), 14 septembre 2026 : Espace et Ctrl-T
marquent un dossier ; BATCH accepte l’enregistrement (type de stockage `$D`
vérifié à la relecture) ; MOVE réécrit l’entrée d’un dossier sur le même
volume comme pour un fichier ; vers un autre volume, MOVE, qui connaît les
unités ProDOS, rend la main avec une note commençant par l’octet 2, et le
résident (`move_tree_across`) pose le curseur sur le dossier, efface les
marques et appelle `copy_or_move(1)` : l’arbre est compté, copié, relu
fichier par fichier et sa source effacée seulement si tout est arrivé ; la
réussite se constate par la disparition de la source. Quatre formes
mesurées : dupliquer la logique de V dans le résident et comparer les
volumes par nom coûtait 582 octets (MAIN 8) ; réutiliser `copy_or_move`
ramène l’aide à 205 octets ; la comparaison de volumes coûtait 131 octets
où qu’elle soit (résident ou BATCH, où elle faisait franchir un bloc à
BATCH.PLG et déborder la disquette BOOT) ; la remise par MOVE la supprime.
`move_marked` reste en carte langage, sa chaîne d’annulation passe au
résident. Le moteur de copie et l’état du lot empruntent tous deux
`text_starts` (207 et 279 octets sur 320) : après un déplacement d’arbre,
une phase `X` de BATCH reconstruit les trois chemins depuis les panneaux
(les compteurs, au-delà des 207 octets, survivent) — reconstruire dans le
résident coûtait 70 octets de plus. BATCH.PLG 6502 passe à 2 659 octets,
un bloc de plus sur BOOT ; MENU.PLG rend ce bloc en raccourcissant un
message (3 591 → 3 582 octets, sous 3 584). Réserves : MAIN 335/779, LC
34/26, LOWRAM 129/154, écart avant pile 363/996 ; BOOT à 0 bloc libre.

Lanceur, 14 septembre 2026 : RUN.PLG 6502 passe à 3 734 octets (neuf blocs)
pour épeler la commande de retour ; le lanceur disquette rend le bloc en
tombant à 6 134 octets (douze blocs, dix octets de marge) : noms de mois
abrégés, ligne descriptive retirée sur disquette seulement, deux notes
raccourcies. VOLNAME passe ensuite sur DISKTOOLS : BOOT retrouve 4 blocs
libres. Les tailles encore au bord d’un bloc sont RUN.PLG (3 734/4 096),
MENU.PLG (3 582/3 584), BATCH.PLG (2 659/3 072) et le lanceur (6 134/6 144). Test hôte `tools/test_batch.py` (un dossier traverse le manifeste,
relu comme `$D`), banc `bench/roi.py` (dossier marqué à deux niveaux sur le
même volume puis vers l’autre disque, arbres relus, sources parties).

Parcours d’arbres itératif (chantier 2), 14 septembre 2026 : `count_tree`,
`copy_tree` et `delete_tree` récursifs sont remplacés par un moteur unique
`walk_tree(mode)` dans `src/tree_walk.h`, résident, avec un cadre de trois
octets par niveau dans trois tableaux `lv_base/lv_n/lv_i[TREE_DEPTH]`
(32 niveaux, ce qu’un chemin ProDOS de 64 caractères ne peut dépasser) et
les entrées de chaque niveau empilées dans la réserve de 213 entrées comme
avant. Budget mesuré : quatre formes essayées. Un moteur unique avec les
cadres adressés par pointeur de structure coûtait 423 octets de résident ;
une instance par mode depuis l’en-tête (mode en constante) faisait déborder
DELETE de 268 octets, et les trois instances résidentes ramenaient MAIN à
11 octets — cc65 produit ~450 à 600 octets par copie de la boucle. La forme
retenue (moteur unique, cadres en tableaux d’octets indexés par la
profondeur, aides communes `push_paths`/`pop_paths`) coûte 257 octets de
code et 99 de BSS ; DELETE ne garde que l’appel et gagne 405 octets.
Réserves : MAIN 590/1 037, LOWRAM 131/156, écart avant pile 618/1 254,
DELETE 409/405. Test hôte `tools/test_tree_walk.py` (ordre, bornes,
arrêts sur erreur, dix scénarios sur un système de fichiers simulé) et banc
`bench/tree_safety.py` réécrit : un arbre de 18 niveaux se copie, un arbre
de 20 niveaux s’efface mais sa copie s’arrête proprement (le nom temporaire
`A2FC.COPY` dans le dossier cible dépasse 64 caractères), un chemin de 221
entrées est refusé avant toute écriture.

CATALOG, 14 septembre 2026 : le lecteur de catalogue DOS 3.3
(`read_dos33_panel`, `dos33_type`, 707 + 40 octets de code) puis le parcours
d’un répertoire ProDOS dans une image (`read_image_dir`, `dir_open_image`)
quittent le résident pour une petite surcouche CATALOG, sur BOOT et XL,
chargée à chaque lecture d’un panneau étranger (disque DOS 3.3 réel, image
en ordre DOS, image ProDOS ouverte comme dossier) et mise en cache comme les
autres. `img_open`, `img_read_block` et `dos_read_sector` restent résidents :
IMGFS et DOSGET s’en servent depuis leur propre fenêtre. Quand une image en
ordre DOS n’a pas de répertoire ProDOS à sa racine, la surcouche répond 2
et le résident, seul autorisé à recharger la fenêtre, tente le lecteur
DOS 3.3 ; l’image est fermée par le résident dans tous les cas. Ce que la surcouche ne peut pas faire : être chargée
pendant qu’une autre surcouche a encore du code sur la pile de retour — HELP
relit les deux panneaux, le tri S hébergé par TEXT relit le sien, et un
plugin SDK relit par `api->read_panel` le panneau DOS qu’il vient d’écrire
(DOSWRITE). `load_overlay` pose donc `in_overlay` à chaque chargement ou
succès de cache ; `read_dos33_overlay` diffère alors la lecture (panneau
vide, bit dans `panel_stale`) et `settle_panels`, appelé en tête de la boucle
principale, relit et redessine ce seul panneau — relire l’autre lui ferait
perdre ses marques. `overlay_run` remet `in_overlay` à zéro dès que le point
d’entrée a rendu la main. NAV relit un panneau puis y cherche le dossier quitté
(`nav_select`) : quand cette lecture est différée, le nom est confié à
`reselect` et `settle_panels` le sélectionne après la relecture, sinon Échap
depuis un sous-dossier d’image perdait sa sélection (vu au banc). Coût
résident : 3 octets de BSS, 46/64 octets de code pour ce report, +8 octets
dans MENU pour la liste des surcouches cachées. Gain MAIN net 824/782
octets ;
CATALOG garde 15/36 octets libres, ce qui suffit à une surcouche de lecture
qui n’a pas vocation à grossir. Test hôte `tools/test_catalog_overlay.py`
(différé, direct, chargement refusé, catalogue refusé, « pas un répertoire »
transmis) et banc `bench/catalog_overlay.py` (aide et tri depuis un panneau
DOS puis depuis une image ProDOS et son sous-dossier, octets de l’image
conservés, deux CPU). Les bancs DOSWRITE, DOSIMAGE, catalogues
malformés, smoke et XL passent sur les deux CPU.


UNSHRINK, 13 septembre 2026 : réservation possédée, nettoyage contrôlé,
lectures exactes des threads ignorés, erreurs de flux/fermeture et annulation.
Les opérations de comparaison et lecture des entiers réutilisent les fonctions
`memcmp`/`memcpy` déjà résidentes pour tenir dans la fenêtre inchangée.
UNSHRINK occupe 5 367/5 347 octets (65C02/6502), soit 9/29 octets libres
sous `$3000`. Aucun BSS ajouté ; l'état à `$3000` est borné à 512 octets
par une assertion de compilation. MAIN garde 60/546 octets, LC 31/24,
LOWRAM 277/302, écart avant pile 88/763 ; pile C toujours de 192 octets.
Le résident 6502 prend 12 octets supplémentaires, le 65C02 est inchangé.
Tous les contrôles de disposition restent actifs.

Audit des chaînes DOS, 13 septembre 2026 : ajout du numéro logique attendu
pour les listes T/S, soit deux octets de BSS par moteur. DOSWRITE : fichiers
7 142/7 219, BSS 1 994/1 995, réserves 336/258 octets (65C02/6502).
DOSPUT : fichiers 7 175/7 265, BSS 1 754/1 755, réserves 543/452 octets.
Pas de nouveau tampon, d'AUX ni de récursion ; pile et plafonds inchangés.
Le vrai moteur compilé pour les deux CPU refuse les chaînes malformées sous
sim65 sans écrire de bloc et accepte un fichier existant sur plusieurs listes.

Erreurs de flux en écriture, 13 septembre 2026 : COPY et EDIT vérifient
`ferror` avant de fermer le temporaire, même après un compte d'octets complet.
Réserves COPY 54/51 et EDIT 97/75 octets (65C02/6502). Aucun BSS ajouté ;
réserves résidentes et pile de 192 octets inchangées par cette correction.

Chargeur de surcouches, 13 septembre 2026 : lecture et fermeture contrôlées,
refus des corps vides ou trop grands, restauration des panneaux après échec
d'un grand chargement. Le menu vide son résultat avant chargement pour éviter
la réexécution d'une ancienne commande. Réserves finales 65C02/6502 : MAIN
128/627, LC 38/31, LOWRAM 281/306, écart avant pile 156/844. La pile reste à
192 octets et aucun plafond n'est changé. Le contrôle de fin utilise `fread`
déjà résident. POM2 : 6/6 contrôles sur chaque CPU, dont le motif sous la pile,
la mémoire auxiliaire et l'intégralité du volume jetable après sauvegarde.

Écriture DOS physique et images, 13 septembre 2026 : DOSWRITE utilise le
slot Disk II sélectionné, avec signature ROM et protection matérielle.
DOSIMAGE prépare/installe le temporaire ; DOSPUT partage le moteur DOS.
Appels successifs, sans chargement imbriqué ni AUX, avec fichiers fermés
entre phases. L'allocation est un bitmap de 70 octets au lieu de 260 mots.
La préparation conserve offset, résultat, CRC-32 et longueur dans 12 octets
du tampon `input` résident ; le chemin est reconstruit après chaque chargement.

| Surcouche | Fichier 65C02/6502 | BSS 65C02/6502 | Libre sous `$4000` |
| --- | ---: | ---: | ---: |
| DOSWRITE | 7 114 / 7 192 | 1 992 / 1 993 | 366 / 287 |
| DOSPUT | 7 147 / 7 238 | 1 752 / 1 753 | 573 / 481 |
| DOSIMAGE | 6 954 / 7 087 | 653 / 654 | 1 865 / 1 731 |

Réserves résidentes : MAIN 266/769, LC 38/31, LOWRAM 282/307, écart avant
pile 294/986 ; pile inchangée à 192 octets. Les textes privés IMAGE et
UNSHRINK sont dans leurs surcouches ; le message RAM reste en LC permanente.
IMAGE garde 66/69 octets, UNSHRINK 52/67, MENU 2 111/2 054. Aucun plafond ni
contrôle de disposition n'est désactivé. LC reste sous la réserve de travail
visée et ne doit pas accueillir une nouvelle fonctionnalité sans libération.
Le banc DOS protège aussi la zone sous la pile par un motif contrôlé après
copie. Le CRC-32 de l'image d'origine utilise une table de 1 Ko pour éviter
huit décalages C 32 bits par octet sur 6502.
Le contrôle final compare aussi les octets hors secteurs modifiés à l'original.
Les diagnostics transitoires du moteur interne sont portés par son résultat,
puis affichés par DOSIMAGE. Celui-ci conserve les 64 octets de l'en-tête 2MG
validé pour détecter une modification pendant la confirmation.


Finalisation DISKIMG, 13 septembre 2026 : la réservation exclusive directe
et la finalisation commune aux modes R/W/O rendent 50/39 octets à DISKIMG
(65C02/6502), réserves 369/313. `DiskImg` occupe 200 octets à `$3E00`, avec
assertion sur les 512 disponibles ; son nouveau champ de propriété n'ajoute
pas de BSS résident. MAIN 272/782, LC 80/73, LOWRAM 282/307 et écart avant
pile 300/999 inchangés. Le helper de finalisation garde un octet de résultat
pendant les fermetures/nettoyages ; pas de récursion ni de chargement imbriqué.
Les deux liens gardent leurs plafonds et la pile de 192 octets. Validation :
32 tests ciblés et sept images ProDOS contrôlés.

DOSWRITE et retour aux volumes, 13 septembre 2026 : surcouche 6 773/6 838
octets (65C02/6502), BSS 2 433/2 434, fin `$3EF5`/`$3F37`, soit 266/200
octets libres sous `$4000`. Locaux statiques, aucune récursion ni AUX ;
appels API par trampoline sans chargement imbriqué. La pile reste à 192 octets.
Le routage C et la remise à zéro du mode DOS coûtent du résident ; des
textes privés déplacés dans leurs surcouches et deux noms/diagnostics placés
en LC maintiennent MAIN à 272/782 octets libres. LC 80/73, LOWRAM 282/307,
écart avant pile 300/999 ; COPY 69/66, EDIT 116/96, DISKIMG 319/274,
MENU 2 181/2 124. Aucun plafond relevé, deux architectures compilées.
Validation : 102 tests ciblés, 15 contrôles POM2 par CPU et sept images
ProDOS contrôlées.

Extraction Binary II contrôlée, 13 septembre 2026 : coût BINARY2 238/247
octets (65C02/6502), réserves 1 694/1 709. MAIN 281/791, LC 117/110,
LOWRAM 282/307 et écart avant pile 309/1 008 inchangés. Les locaux restent
sur la pile : suppression du compteur de lecture et réduction du remplissage
à un octet compensent le pointeur de diagnostic, la propriété et le compteur
d'extraits élargi. Aucun BSS supplémentaire, récursion ou chargement imbriqué.
Pile de 192 octets et plafonds conservés aux deux liens. Validation :
56 tests ciblés et reconstruction/contrôle des sept images ProDOS.

Transaction commune EDIT, 13 septembre 2026 : coût EDIT 110/116 octets
(65C02/6502), réserves 138/118. MAIN 281/791, LC 117/110, LOWRAM 282/307,
écart avant pile 309/1 008 et COPY 79/76 inchangés. La transaction est
compilée dans EDIT ; ses sept octets d'arguments restent empilés pendant
les renommages, sans récursion ni chargement imbriqué. Aucun BSS ajouté,
plafonds et pile de 192 octets inchangés. Les deux liens, 48 tests ciblés
et les sept images ProDOS sont validés.

Nettoyage contrôlé EDIT, 13 septembre 2026 : EDIT coûte 62/64 octets
(65C02/6502) et conserve 248/234 octets libres. Le remplacement du diagnostic
littéral « Save » libère cinq octets MAIN : réserves 281/791, écart avant
pile 309/1 008. LC 117/110, LOWRAM 282/307 et COPY 79/76 inchangés.
Le helper EDIT garde deux octets d'argument pendant suppression/diagnostic,
sans récursion ni nouveau local statique. Les deux liens conservent tous
les plafonds et la pile de 192 octets ; 42 tests ciblés et sept images
ProDOS contrôlés.

Localisation des textes de surcouches, 13 septembre 2026 : neuf tableaux
nommés dans EDITRO, MENURO, BINARY2RO et UNSHRINKRO remplacent des littéraux
que cc65 plaçait dans RODATA résident. Gain MAIN de 127 octets sur chaque
CPU : réserves 276/786 octets (65C02/6502), objectif de 256 retrouvé.
Écart avant pile 304/1 003 ; LC 117/110 et LOWRAM 282/307 inchangés.
Réserves des surcouches concernées : EDIT 310/298, MENU 2 190/2 133,
BINARY2 1 932/1 956 et UNSHRINK 86/101. COPY reste à 79/76.
Les textes sont consommés pendant leur surcouche ou copiés dans `note`
avant son déchargement ; aucun pointeur ne lui survit. Aucun appel ni
local supplémentaire, aucune écriture AUX et aucun changement du protocole
de fichiers. Les contrôles des deux liens gardent tous les plafonds et
la pile de 192 octets. Validation : 24 tests C de copie/édition, 15 tests
du contrôle de disposition et reconstruction/contrôle des sept images ProDOS.

Publication COPY par temporaire, 13 septembre 2026 : réserves COPY 79/76
octets, MAIN 149/659, LC 117/110, LOWRAM 282/307, écart avant pile 177/876
(65C02/6502). MAIN coûte 107 octets sur chaque CPU et le BSS un octet ;
le chemin temporaire supplémentaire tient dans `CopyState` (204 octets sur
les 320 de `text_starts`). La variante de transaction liée à CP évite ses
sept octets d'arguments empilés ; la profondeur des appels reste bornée,
sans récursion ni chargement imbriqué. Les deux liens passent sans relever
les plafonds ni réduire la pile de 192 octets. La réserve MAIN 65C02 est
cependant sous l'objectif de 256 : marge à regagner avant d'enrichir encore.

Finalisation COPY résidente, 13 septembre 2026 : COPY passe de 1 247/1 255
à 1 164/1 169 octets (65C02/6502), soit 116/111 octets libres dans sa fenêtre
de 1 280. Le résident absorbe nettoyage, restauration et compteurs : MAIN
conserve 256/766 octets (coût net 79/84), écart avant pile 284/983. LC et BSS
sont inchangés ; LOWRAM conserve 283/308 octets. La finalisation remplace
la vérification dans la chaîne d'appels, sans ajouter de niveau récursif ;
la réservation directe retire le détour par `new_output`. Pile de 192 octets
et plafonds de toutes les surcouches conservés sur les deux liens.

Réservation résidente/BATCH commune, 13 septembre 2026 : CODE résident
+30/+35 octets (65C02/6502), BATCH -20/-20 et LOWBSS -2/-2. Il s'agit d'un
contrat de résultat supplémentaire ; le résident ne gagne pas de code dans
cet incrément. Réserves après lien : MAIN 335/850, LC 117/110, LOWRAM 283/308,
écart avant pile 363/1 067, BATCH 2 817/2 834. COPY conserve 33/25 octets de
marge et demande toujours un chantier séparé. La nouvelle fonction résidente
garde deux octets d'argument pendant `open`/`close`, sans récursivité ni
chargement de surcouche. Les plafonds et la pile de 192 octets sont inchangés.

Migration GOTO vers l'installation commune, 13 septembre 2026 : fichier
4 969/4 953 octets (+157/+164), BSS 262/263 octets (+1), fin
`$2F6E`/`$2F5F` (65C02/6502). Réserve 145/160 octets sous `$3000`, sans
empiéter sur LIST (`$3000`) ou TEXT (`$3400`). La transaction commune garde
sept octets d'arguments pendant le renommage, sans récursivité ni chargement
imbriqué. Les deux liens respectent les limites d'origine et la pile de
192 octets ; les autres plugins restent identiques octet pour octet.

Installation commune SYNC/conversions, 13 septembre 2026 : les appels API
compacts de SYNC compensent l'ajout des diagnostics et de l'arrêt de
récupération. Le premier essai dépassait la fenêtre de 45 octets sur 65C02 ;
aucun plafond n'a été relevé. Bilan final (65C02/6502) : SYNC 6 732/6 755
octets, soit -730/-728 ; BSS 1 746/1 747 (+1 pour l'indicateur), fin
`$3C1D`/`$3C35`, réserve 994/970 octets sous `$4000`. TXTCONV ajoute 66/79
octets (6 017/6 036), IMGCONV 57/71 (6 814/6 916), leurs BSS inchangés.
La fonction d'installation garde sept octets d'arguments sur la pile pendant
le transport de renommage ; elle est non récursive. Les contrôles natifs des
deux éditions conservent la pile de 192 octets et toutes les limites de lien.
Les autres plugins sont identiques octet pour octet.

Nettoyage et restauration des conversions, 13 septembre 2026 : TXTCONV ajoute
243/237 octets et IMGCONV 190/184 octets (65C02/6502), messages compris.
Leurs fichiers occupent désormais 5 951/5 957 et 6 757/6 845 octets.
Le BSS reste inchangé : 592/593 et 730/731 octets ; fins respectives
`$348E`/`$3495` et `$383E`/`$3897`, sous `$4000`. Le nettoyage ajoute un
argument de deux octets sur la pile pendant l'appel, sans récursivité ;
la chaîne de restauration reste de même profondeur. Les autres plugins
sont identiques octet pour octet. Les plafonds et la pile de 192 octets
restent en vigueur sur les deux constructions.

Extraction CREATE des plugins, 13 septembre 2026 : TXTCONV passe de
5 673 à 5 708 octets sur 65C02 et de 5 687 à 5 720 sur 6502. BSS inchangé
(592/593 octets), fin BSS `$339B`/`$33A8`, soit 3 172/3 159 octets libres
avant `$4000`. Le nouvel appel garde six octets d'arguments sur la pile C
pendant CREATE ; il n'est pas récursif et ne charge aucune surcouche.
Les autres plugins restent identiques octet pour octet, comme le résident
et ses budgets. Aucun plafond ni réserve de pile n'est modifié.

Premier relevé du 12 septembre 2026, code natif de `af84617`, après reconstruction
forcée des deux architectures. `tools/check_layout.py` affiche maintenant les
réserves à chaque lien réussi, en complément des contrôles bloquants existants.
Les chiffres ci-dessous sont un point de départ, pas des constantes à recopier
dans un futur rapport de qualification.

## Mesures et objectifs du premier chantier (12 septembre 2026)

Les réserves sont en octets. Les objectifs sont des seuils de travail proposés,
pas des garanties déjà obtenues ni des plafonds assouplis.

| Zone | 65C02 | 6502 | Réserve visée sur chaque architecture |
| --- | ---: | ---: | ---: |
| MAIN, jusqu'à `$BEE0` | 5 | 542 | ≥ 256 |
| Carte langage, jusqu'à `$E000` | 0 | 4 | ≥ 128 |
| LOWRAM, BSS compris, jusqu'à `$1B00` | 290 | 315 | ≥ 256 |
| Espace entre code persistant et pile C | 33 | 759 | ≥ 128 |
| BSS FORMAT, jusqu'au tampon `$3E00` | 147 | 147 | ≥ 128 |

La pile C réserve 192 octets : l'espace avant la pile ne mesure **pas** sa
consommation dynamique et ne justifie pas de réduire sa taille. MAIN contient
aussi le code ONCE jetable ; ses octets libres ne s'ajoutent pas à cet espace.
Les surcouches se recouvrent et leurs réserves ne s'additionnent pas non plus.

| Surcouche liée au résident | 65C02 | 6502 |
| --- | ---: | ---: |
| BATCH | 2797 | 2814 |
| NAV | 230 | 296 |
| OPEN | 74 | 110 |
| COPY | 33 | 25 |
| FORMAT | 428 | 428 |
| IMAGE | 113 | 116 |
| TEXT | 61 | 33 |
| HEX | 49 | 42 |
| DELETE | 4 | 3 |
| HELP | 219 | 183 |
| RUN | 2190 | 2202 |
| ATTR | 26 | 26 |
| EDIT | 370 | 358 |
| MENU | 2241 | 2184 |
| DISKIMG | 328 | 283 |
| IMGFS | 1520 | 1530 |
| DOS33 | 59 | 84 |
| UNSHRINK | 2727 | 2739 |
| BASLIST | 1863 | 1856 |
| COMPARE | 86 | 111 |
| SEARCH | 335 | 338 |
| BINARY2 | 1968 | 1992 |
| AWP | 216 | 197 |

Viser au moins 64 octets dans chaque petite surcouche modifiée ; traiter
OPEN, COPY et ATTR en priorité avant de les enrichir. Les plugins SDK liés
séparément ne figurent pas dans ce relevé : leurs limites code/BSS et tampons
restent imposées par leurs configurations de lien, à contrôler aussi lors des
extractions. BINARY2 utilise ici sa grande fenêtre sur les deux architectures.

## Premier gain : diagnostics résidents (12 septembre 2026)

Les diagnostics ProDOS sont extraits dans `src/errors.h`, toujours en carte
langage. Une table de douze codes remplace le switch, et le diagnostic n'est
recherché qu'une fois par affichage. Le message sans appelant de l'ancien
lecteur Mockingboard est retiré ; le message « SYS, BIN or BAS only. » rejoint
RUNRO, dont RUN est l'unique utilisateur, sans chargement supplémentaire.

| Zone après modification | 65C02 | 6502 | Évolution |
| --- | ---: | ---: | --- |
| MAIN | 27 | 564 | +22 sur les deux |
| Carte langage | 71 | 74 | +71 / +70 |
| LOWRAM | 287 | 312 | −3 sur les deux |
| Espace avant pile C | 55 | 781 | +22 sur les deux |
| RUN | 2168 | 2180 | −22 sur les deux |

Les trois octets LOWRAM servent à l'indice et au pointeur de diagnostic
(locaux statiques cc65). Les autres surcouches et la réserve BSS FORMAT gardent
leurs marges initiales. Les objectifs MAIN, LC et espace avant pile ne sont
**pas encore atteints** sur 65C02 ; LC reste également sous l'objectif sur 6502.

Le service n'écrit aucun fichier ni volume. Il modifie le compteur d'erreurs
en RAM principale, ses locaux statiques, et l'écran texte 80 colonnes
MAIN/AUX `$0400-$07FF` via conio, sans toucher le stockage du disque `/RAM`.
Le message déplacé reste disponible pendant tout son affichage : `message()`
est résident et ne remplace pas la surcouche RUN.

Les tests exécutent le vrai C pour les 256 valeurs de code ProDOS : douze
messages connus, repli numérique pour tous les autres, contenu exact de la
ligne, compteur et conservation de `_oserror`/`errno`.

Validation locale du lot : `make test`, les deux liens et leurs contrôles,
construction des sept supports puis `tools/check_images.py` passent. POM2
valide l'amorçage BOOT sur 6502, les 11 contrôles XL sur 65C02 et mesure
92 octets de pile utilisés sur les 192 réservés dans `bench/memory.py`.
Ces scénarios ne prouvent pas une borne exhaustive pour tous les parcours.

### Après l'extension du lanceur à Integer BASIC

Le chantier demandé ensuite ajoute `src/launch.h`, toujours dans RUN, et
`INTBASIC.SYSTEM` sur DEVTOOLS/XL. Les chemins de lancement vivent à
`$3400-$347F`, séparés du tampon de configuration `$3000-$33FF` ; des contrôles
de taille à la compilation empêchent leur recouvrement. Aucun plafond n'est
relevé. Deux messages de sélection et deux libellés d'erreur sont placés en LC
pour garder RUN dans sept blocs sur la disquette BOOT 6502.

| Réserve du lien après extension | 65C02 | 6502 |
| --- | ---: | ---: |
| MAIN | 62 | 593 |
| Carte langage | 8 | 11 |
| LOWRAM | 280 | 305 |
| Espace avant pile C | 90 | 810 |
| RUN | 1781 | 1795 |
| OPEN | 83 | 119 |

BOOT occupe les 280 blocs : l'échec de sauvegarde d'une nouvelle configuration
y reste signalé avant de proposer de lancer quand même le programme. Les
objectifs de réserve restent ouverts, particulièrement la carte langage.

## Deuxième lot : affichage et saisie (12 septembre 2026)

Le lot suivant part de `68c39f5`. Une table compacte remplace le `switch` des
types de fichiers. Un seul en-tête sert aux trois tris ; l'étoile est ajoutée
à sa colonne d'origine. La ligne d'information partage son préfixe entre
fichiers ProDOS et fichiers dans une image. Les questions utilisent `cputs`
et `cputc` pour leur texte fixe, avec les mêmes réponses admises.

`src/display.s` remplace le parseur de barre de touches et la conversion
hexadécimale : mêmes conventions cc65 sur 6502/65C02 et même interface pour
les plugins. Le parseur recharge ses pointeurs après les appels conio ; ses
quatre octets d'état restent résidents. Aucune nouvelle surcouche n'est chargée.

| Réserve après ce lot | 65C02 | 6502 | Gain 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| MAIN | 290 | 835 | +228 / +242 |
| Carte langage | 172 | 169 | +164 / +158 |
| LOWRAM | 281 | 306 | +1 / +1 |
| Espace avant pile C | 318 | 1052 | +228 / +242 |
| BSS FORMAT | 147 | 147 | inchangé |

Les objectifs initiaux sont atteints sur les deux architectures. Les plafonds,
la réserve de pile de 192 octets et les fenêtres des surcouches restent
inchangés. Les réserves de ces dernières n'évoluent pas. BOOT gagne un bloc
libre, et la disquette de banc enhanced passe de huit à neuf blocs libres.

### Écritures et qualification

Ces services ne font aucune opération de fichier ou de volume. Ils écrivent
leurs variables en MAIN, les registres temporaires cc65 en page zéro et
l'écran texte MAIN/AUX `$0400-$07FF`. La saisie écrit dans `input`, comme avant.
La ligne d'information utilise `copy_buf` en MAIN, désormais aussi pour les
fichiers dans une image : ses appelants ont terminé la lecture des répertoires
avant l'affichage. Le préfixe fait au plus 66 caractères, le texte complet
84 avant troncature à 79 ; le tampon en contient 512. Le disque `/RAM` n'est
pas utilisé comme réserve de mémoire par ces services.

`tools/test_display.py` exécute le C réel pour les 256 types, les trois tris
sur les deux panneaux, les attributs maximaux, les limites de ligne/tampon,
les saisies et les 256 touches de confirmation (seuls Y/y, N/n et Échap
terminent la question). Le test de style des questions reste dans
`tools/test_ui.py`. Sur sim65, le véritable assembleur est comparé à l'ancien
parseur C, texte et vidéo inverse compris, avec passage de page et appel par
le pointeur de fonction des plugins. Les 65 536 valeurs hexadécimales sont
vérifiées sur chacun des deux processeurs.

Validation locale : `make test`, les deux constructions natives et la relecture
des sept supports passent. POM2 valide les 11 contrôles XL sur 6502. Le parcours
`bench/memory.py` sur enhanced (visionneuses, édition abandonnée, copie
récursive sur volumes jetables) mesure toujours 92 octets de pile utilisés
sur 192. Cette mesure n'est pas une borne exhaustive pour tous les parcours.

## Suite de la consolidation (12 septembre 2026)

Poursuivre avec les contrats de buffers et les services de fichiers sûrs,
en mesurant séparément le gain MAIN et carte langage. Déplacer un service dans
une surcouche demande de vérifier tous ses appelants : charger cette surcouche
peut écraser celle qui appelle le service. Une réserve dans MENU ou BATCH n'est
donc pas automatiquement disponible pour un service partagé.

Avant toute modification native, établir les fichiers, volumes, buffers et
banques écrits par les fonctions concernées et leurs appels. Conserver les
garanties de création exclusive, copie vérifiée et remplacement récupérable.
Ne pas emprunter AUX pour gagner de la place sans le consentement préalable
requis pour la destruction de `/RAM`.

L'outil de mesure lit les symboles et tailles des fichiers construits sans
modifier les volumes ProDOS ni les banques mémoire.

## Reproduire

```sh
make -B all ARCH=enh
make -B all ARCH=6502
python3 tools/check_layout.py --big BINARY2
python3 tools/check_layout.py --lbl build-6502/a2fc.lbl --bin build-6502/A2FILE.CODE.BIN --big BINARY2
make test
```

Outils observés : `cc65 V2.18 - N/A` pour enhanced et `cc65 V2.19 - Git e11fb5c`
pour 6502. Relever les versions réellement utilisées plutôt que déduire leur
version des commentaires du Makefile. Ce relevé local ne constitue pas un test
sur émulateur ou matériel.

## PT3 : le lecteur de GROUiK (3 octobre 2026)

Moteur principal pour un module simple de 32 Ko au plus, en mémoire
auxiliaire après `aux_consent` : AUX `$2000–$32CC` image `A2FILE/PPT3.BIN`
(4 813 octets dont les 7 tables de notes ZX, mêmes octets pour les deux
éditions), `$32CD–$3531` ses variables et tables, `$3B00–$3B25` le miroir du trampoline, `$4000–$BFFF`
le module ; AUX `$0800–$1FFF` (bitmap et répertoire de `/RAM`) n'est jamais
écrite. Dans PT3.PLG, le pilote (hook.s + driver.s) est lié à
`$3B00–$3F3C` : le fichier porte la fenêtre et les pages d'en-tête en
remplissage, 9 264 octets (limite 9 472). La fenêtre de code garde
94 / 28 octets (65C02/6502) avant `$3700`, après la conversion exacte vers
1,0227 MHz (`conv_mb`, 1181/2048) et les corrections de pt3_lib, grâce au
déplacement de ses copies de page zéro en `$3FC0–$3FFF` (64 octets) ; les
62 octets de NOP qui alignaient le code d'initialisation de pt3_lib ne
servent plus. Le service
`aux_consent` coûte 2 octets de MAIN résidente (reste 10 octets en 65C02).

## PT3 : grands modules et TurboSound (12 septembre 2026)

Le lecteur accepte 65 535 octets, conteneur TurboSound compris, sans AUX.
La fenêtre BIG reste `$1B00–$3FFF` et les bornes de lien sont conservées.

| Zone PT3 | Adresses | Taille |
| --- | --- | ---: |
| Code, données, BSS | `$1B00–$36FF` | 7 168 |
| Deux en-têtes | `$3700–$3AFF` | 1 024 |
| Cache initial | `$3B00–$3DFF` | 768 |
| Tables du second module | `$3E00–$3FBF` | 448 |

Les premières tables empruntent 448 octets de `copy_buf`. Après initialisation,
deux pages entières de code devenu mort sont réutilisées ; une assertion de
lien vérifie leurs bornes. Les pages d'en-tête inutilisées peuvent aussi être
récupérées : cinq à huit pages de cache. Les opérandes d'initialisation ne
sont plus modifiés ensuite, ce que vérifie un test avec pages empoisonnées.
Le cache donne une seconde chance aux pages de samples et d'ornements ;
les lectures de patterns ne promeuvent pas les pages froides. Le bit 6 de la
table des pages porte cette référence et est masqué avant tout accès mémoire.
Le BSS PT3 finit à `$36AB` / `$36ED` (65C02/6502), laissant
84 / 18 octets avant les en-têtes.
Aucune donnée AUX, pile ou zone résidente n'est utilisée comme cache.

PURPLE reste sous `$2000` (fenêtre de 1 280 octets), ses lectures vont dans
MAIN `$2000–$3FFF`, puis AUXMOVE copie la première page vers AUX pour les
modes étendus. Le consentement précède le chargement ; toute sortie après
AUXMOVE reconstruit `/RAM`, y compris en cas d'erreur de lecture/fermeture.

Après intégration Purplesoft, les réserves résidentes sont : MAIN 145/682,
LC 168/163, LOWRAM 278/303, espace avant pile C 173/899, OPEN 4/42 octets
(65C02/6502). La pile C réservée reste de 192 octets. MAIN enhanced demeure
sous la réserve de travail visée de 256 octets ; OPEN enhanced est presque
plein. Les contrôles de disposition restent obligatoires.

Les bancs PT3 vérifient le plancher de pile, la mémoire AUX hors écran texte
(pour pt3_lib) et le volume source octet par octet sur des images jetables. Le lecteur
Purplesoft vérifie ses deux plans, les sorties et le consentement par session
sur les deux architectures. Ce sont des validations en émulation, pas des
mesures sur matériel physique.


## Consolidation du routage média (12 septembre 2026)

La correction des transitions ajoute un écran `Loading <cible>` préparé dans
MAIN/AUX `$0400–$07FF` dès la flèche, avant le nettoyage du lecteur. La relecture
des tables de panneaux attend son retour : elles partagent sa mémoire. Aucun
fichier ni octet AUX à partir de `$0800` n'est écrit par cette coordination.
Le parcours HGR/DHGR brut utilise la même annonce et redessine les panneaux
après relecture ; il n'a plus besoin des anciennes empreintes d'écran.
Les réserves après cette correction sont MAIN 365/885, LC 117/110,
LOWRAM 281/306 et espace avant pile C 393/1102 octets (65C02/6502),
avec une pile C réservée de 192 octets et les mêmes plafonds.

Les identifiants de `src/viewer_ids.h` indexent une seule table résidente de
noms. OPEN renvoie un octet plutôt qu'un pointeur vers ses propres chaînes ;
le feuilletage compare cet identifiant. Zéro reste une erreur de sonde et ne
sélectionne jamais un lecteur de repli. Les suffixes musicaux ne sont évalués
qu'une fois par candidat. La priorité des types explicites est conservée.

Le contrôle de taille HGR/DHGR regroupe les tailles exactes et leurs variantes
sans les huit derniers octets invisibles. Un test du vrai C couvre les 65 536
valeurs du mot bas, avec mot haut nul et non nul (393 216 vérifications pour
les deux configurations). Il conserve exactement 8 184, 8 192, 16 376 et
16 384 octets et refuse les tailles plus grandes ayant le même mot bas.

| Réserve | 65C02 avant → après | 6502 avant → après |
| --- | ---: | ---: |
| MAIN | 145 → 259 | 682 → 779 |
| OPEN | 4 → 185 | 42 → 215 |
| LC | 168 → 168 | 163 → 163 |
| LOWRAM | 278 → 277 | 303 → 302 |
| Espace avant pile C | 173 → 287 | 899 → 996 |

La réserve de travail MAIN de 256 octets est de nouveau atteinte sur 65C02.
Aucune limite de lien, taille de pile, API de plugin ou autorisation AUX n'est
modifiée. Les sondes n'écrivent que le buffer principal de lecture ; les
lecteurs conservent leur contrôle de consentement avant toute utilisation AUX.

Validation : 428 tests automatisés, compilations et limites des deux CPU ;
109 contrôles POM2 par architecture (`open_images.py`, `media.py`, `purple.py`),
avec écrans relus octet par octet, flèches, Échap, refus AUX et conservation du
volume source. Les essais utilisent uniquement des images jetables.

## Extraction des services de fichiers, 13 septembre 2026

Mesure sur l'arbre de travail courant, qui comprend les modifications en cours
de NIBCOPY et du routage. `file_output.h` et `file_copy.h` conservent leur
position dans l'unité de compilation ; aucun nouveau chargement ni appel
n'est ajouté. Tous les `.BIN` et `.PLG` existants sont identiques octet pour
octet avant/après sur les deux CPU (SHA-256), ainsi que les symboles `.lbl`.
Le contrôle de capacité de `CopyState` ne produit pas de code.

| Réserve, octets | 65C02 avant/après | 6502 avant/après |
| --- | ---: | ---: |
| MAIN | 365 / 365 | 885 / 885 |
| Carte langage | 117 / 117 | 110 / 110 |
| LOWRAM, BSS compris | 281 / 281 | 306 / 306 |
| Espace avant pile C | 393 / 393 | 1102 / 1102 |
| COPY | 33 / 33 | 25 / 25 |
| FORMAT BSS | 147 / 147 | 147 / 147 |

Les contrôles de disposition passent pour les deux architectures, avec la
pile C de 192 octets et tous les plafonds inchangés. Aucune modification du
graphe d'appels ni des binaires : consommation dynamique de pile inchangée,
sans nouvelle mesure sur émulateur. COPY reste sous l'objectif de 64 octets,
et la carte langage sous celui de 128 ; l'extraction ne revendique aucun gain
mémoire. Les autres surcouches gardent exactement leurs réserves.

### DOSGET, IDENT et FIXTYPES — 13 septembre 2026

DOSGET remplace la petite surcouche DOS33 par une grande surcouche explicitement
signalée BIG. Son plafond de code est `$2800` ; le bitmap de 70 octets est à
`$2800`, la copie T/S de 244 octets à `$2F00`. Le snapshot des 140 entrées
actives occupe `$3000-$3FDB`. FIXTYPES utilise le même snapshot, avec code et
BSS obligatoirement sous `$3000` (fin BSS `$2B5A` / `$2B21`). Le chargeur fait
un memmove avant de charger une grande surcouche ; BATCH réutilise ce service.
Aucun de ces nouveaux espaces n'utilise AUX. L'API passe à v5 sans déplacer
les services ; FIXTYPES refuse une ancienne API avant toute modification.

| Réserve en octets | 65C02 | 6502 |
| --- | ---: | ---: |
| MAIN | 23 | 518 |
| Carte langage | 14 | 6 |
| LOWRAM avec BSS | 245 | 270 |
| Espace avant pile C | 51 | 735 |
| OPEN | 11 | 43 |
| DOSGET avant `$2800` | 1547 | 1528 |
| FIXTYPES BSS avant `$3000` | 1189 | 1246 |

La pile reste à 192 octets et les contrôles de disposition sont actifs sur
les deux architectures. DOSGET ne tient plus dans le budget disque de BOOT :
il est distribué sur FILES/XL, sans agrandir les disquettes de 280 blocs.
Le banc formats passe 13 contrôles par CPU, dont le garde de pile, AUX intact
et la comparaison intégrale des fichiers sur une disquette jetable relue
après flush. FIXTYPES passe également 17 contrôles par CPU.

## 9 octobre 2026 — visionneuses DOS et import MCS

Le routage des touches DOS 3.3 réside en assembleur dans MAIN, avec les
petites tables en carte langage. Les contrôles de disposition restent
actifs et la pile C conserve 192 octets. Les marges suivantes ne sont pas
additionnables.

| Réserve en octets | 65C02 | 6502 |
| --- | ---: | ---: |
| MAIN | 1 | 382 |
| Carte langage | 3 | 1 |
| LOWRAM avec BSS | 84 | 109 |
| Espace avant pile C | 18 | 588 |
| DOSVIEW code + BSS avant `$4000` | 65 | 56 |
| MCS code + BSS avant `$3680` | 422 | 304 |
| DOSMCS code/données avant `$3700` | 210 | 191 |
| DOSMCS handoff + BSS avant `$1000` | 26 | 25 |
| MCSIMPORT code/données avant `$3700` | 369 | 249 |
| MCSIMPORT handoff + BSS avant `$1000` | 71 | 70 |
| MCSPLAY code + BSS avant `$3700` | 4501 | 4466 |
| DOSINT code + BSS avant `$4000` | 301 | 307 |
| DOSBAS code + BSS avant `$4000` | 397 | 402 |

DOSVIEW occupe 7523/7532 octets de fichier et 1884 octets de BSS.
Son chargeur HGR et son état se terminent à `$1DFC` : une assertion de lien
impose leur maintien sous `$2000`. Une fois le catalogue et les listes
T/S validés, leur mémoire sert aux positions des pages texte ou aux
quelques pointeurs lo-res, ce qui évite un nouveau tampon. Le chargeur
ne rappelle aucun code ou auxiliaire cc65 recouvert par la page HGR.
MCS occupe 6278/6395 octets de fichier et 340/341 octets de BSS. Son tampon
de musique de 2304 octets passe à `$3680-$3F7F` : la limite de lien spécifique
`__OVLSIZE__=$1B80` protège ce tampon, y compris contre la croissance du BSS.
Ces lecteurs utilisent MAIN ; aucun tampon AUX ni fichier temporaire.

DOSMCS occupe 6958/6977 octets de fichier et 623/624 de BSS. Il valide
les cartes des deux fichiers, puis conserve les pointeurs/tailles dans
64 octets de `other_full` (81 octets disponibles). MCSIMPORT occupe
6799/6919 octets de fichier et 578/579 de BSS ; MCSPLAY 2584/2619 et 83.
Le résultat canonique est MAIN `$3700-$3FFF`, protégé par la limite
`__OVLSIZE__=$1C00` des trois étapes. La carte accepte 13 secteurs par
partition et limite toujours les exports à 10 : aucune allocation excessive
n'est tronquée.

DOSMCS/MCSIMPORT placent leur BSS après le handoff `$0C00-$0D76`, dans
la réserve du second FILE ProDOS. Le lien refuse un dépassement de `$1000`.
Les services de répertoire sont fermés et jamais deux FILEs ne restent
ouverts : l'unique source/étape utilise le buffer `$0800`. Le C revient
avant copie du handoff ; celui-ci n'exécute aucun auxiliaire du code
recouvert et ferme l'étape avant son saut. Taille scellée, EOF, erreurs,
version/CPU et adresse d'entrée sont contrôlés. Aucun changement d'ABI.

DOSINT occupe 8012/8006 octets de fichier et 1159 de BSS. Les 257 mots
maximaux de carte T/S restent sous `$4000`, et les métadonnées retirées
hébergent l'anneau de 64 positions de page. `copy_buf` sert au secteur
courant ; aucun tampon AUX, temporaire ou second FILE ProDOS. L'EOF de
65535 octets et son préfixe traversent correctement la limite de 64K dans
les tests C compilés pour les deux CPU.

DOSBAS réemploie le même lecteur et l'anneau : 7912/7907 octets de fichier
et 1163 de BSS, sous `$4000` avec 397/402 octets de réserve. La table des
107 mots-clés Applesoft est partagée au niveau source avec BASLIST et
reste dans le segment propre à chaque surcouche. Les wrappers DOSINT,
DOSBAS et MCSPLAY dépendent explicitement des fichiers C inclus afin que
la validation porte sur les objets reconstruits.

## 10 octobre 2026 — IDENT et Newsroom

Mesures du lien final (65C02 / 6502), sans diminuer les contrôles : MAIN
9 / 397, LC 3 / 1, LOWRAM 84 / 109, espace avant pile C 26 / 603 octets.
Ces marges ne sont pas additionnables. Les courts messages résidents ont été
raccourcis pour conserver le repli OPEN/DOSVIEW des installations incomplètes.
La 140K ProDOS est retirée de la distribution ; BOOT est une fixture interne.

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| DOSVIEW | 7521 / 7530 | 1884 | 67 / 58 |
| DOSNEWS | 6632 / 6606 | 1014 | 1826 / 1852 |
| NEWSPAN | 6539 / 6551 | 1149 | 1784 / 1772 |
| NEWSPAGE | 6617 / 6626 | 1228 | 1627 / 1618 |
| IDENT | 8836 / 9003 | 120 | 516 / 349 |
| IDREAD | 6509 / 6622 | 1610 | 1353 / 1240 |
| IDFORMATS | 9133 / 9390 | 69 | 270 / 13 |
| SCASM | 6492 / 6482 | 1391 | 1589 / 1599 |

DOSNEWS garde tout son rendu/état sous $1E7A, protégé par l'assertion $2000.
Le C revient avant que HGR recouvre sa zone ; le chargeur n'appelle aucun
auxiliaire recouvert, ferme la source avant affichage et ne touche pas AUX.

Les trois phases IDENT se chargent à $1B00 avec une limite de $4000. Leur
handoff relocalisé est borné par le lien à $0C00-$0DFF et laisse intact
l'échantillon de 512 octets à $0E00-$0FFF. Ils empruntent le buffer d'un
second FILE ProDOS ; les répertoires sont fermés et un seul FILE reste
ouvert, à $0800. Le handoff vérifie longueur scellée, EOF, erreurs de lecture
et fermeture, CPU et entrée avant de sauter. Les tests exécutent les trois
chargeurs natifs sur les deux CPU et contrôlent chaque octet conservé.

MultiScribe/Apple Writer (2026-10-10), sans AUX ni espace de travail HGR :

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| MULTISCR | 2358 / 2388 | 147 | 6967 / 6937 |
| APPLEWR | 7289 / 7474 | 1382 | 801 / 616 |

MENU conserve 58/7 octets ; MAIN, LC, LOWRAM et pile inchangés. Les deux
builds complets et les contrôles de disposition passent.

Print Shop BIN (2026-10-10), MAIN uniquement :

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| PSBORDER | 6436 / 6437 | 1270 | 1766 / 1765 |
| PSFONT | 7303 / 7476 | 1780 | 389 / 216 |

MAIN, LC, LOWRAM et pile restent aux marges ci-dessus. Les descriptions
courtes du MENU compensent les deux nouvelles entrées ; aucun plafond levé.

Magic Window / LISA v3 (2026-10-10), MAIN uniquement :

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| MAGWIN | 6085 / 6075 | 1119 | 2268 / 2278 |
| LISAV3 | 4896 / 5023 | 3372 | 1204 / 1077 |

LISAV3 garde 3072 octets de symboles compactés et un seul enregistrement
borné à 126 octets ; aucune allocation en AUX. Le MENU garde 58/7 octets
après raccourcissement de ses descriptions. MAIN, LC, LOWRAM et pile
inchangés ; aucun contrôle désactivé. IDFORMATS 6502 ne garde que 13 octets :
la prochaine extension exigera de récupérer de la place ou de scinder ce code.


DOSREC et Print Shop ProDOS $F5 (2026-10-10), MAIN uniquement :

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| DOSREC | 7400 / 7387 | 1967 | 105 / 118 |
| PSBORDER | 6730 / 6709 | 1003 | 1739 / 1760 |
| PSFONT | 7583 / 7748 | 1546 | 343 / 178 |
| IDFORMATS | 9076 / 9335 | 69 | 327 / 68 |

Le tableau DOS des lecteurs Print Shop est borné à 65 secteurs : assez pour
le maximum accepté de 16 KiB plus l’en-tête BIN. DOSREC conserve 560 entrées
et 288 octets de page avec un bitmap de trous. Les descriptions IDENT
raccourcies signalent les candidatures par `?`. MENU garde 54/3 octets ;
MAIN 9/397, LC 3/1, LOWRAM 84/109 et écart de pile 26/603 inchangés.
Aucun plafond relevé ni contrôle désactivé.


LISA 8/16 v4/v5 (2026-10-10), MAIN uniquement :

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| LISAV4 | 6036 / 6301 | 3133 | 303 / 38 |
| IDENT | 9098 / 9294 | 120 | 254 / 58 |
| IDFORMATS | 9097 / 9356 | 69 | 306 / 47 |

LISAV4 conserve 2816 octets de symboles encodés ; leurs références sur
16 bits sont retrouvées dans cette table sans tableau d’offsets ni AUX.
La règle de candidature LISA 8/16 est dans IDENT, puis sa route dans
IDFORMATS : chaque phase reste bornée par son lien et son handoff scellé.
MENU garde 52/1 octets. MAIN 9/397, LC 3/1, LOWRAM 84/109 et écart de pile
26/603 inchangés. Builds complets et contrôles de disposition réussis.


PFS:Write (2026-10-10), buffers MAIN, aucune reconstruction AUX /RAM :

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| PFSWRITE | 2048 / 2101 | 135 | 7289 / 7236 |
| IDENT | 9113 / 9305 | 120 | 239 / 47 |
| IDFORMATS | 9120 / 9379 | 69 | 283 / 24 |

PFSWRITE utilise `copy_buf` pour lire 512 octets à la fois. Aucun tableau
de document entier ni allocation AUX. La candidature $16/$0002 est dans
IDENT, sa route dans IDFORMATS. Des descriptions IDENT/MENU sont
raccourcies pour respecter les plafonds existants ; MENU garde 59/8 octets.
MAIN 9/397, LC 3/1, LOWRAM 84/109 et écart de pile 26/603 inchangés.
Les deux builds complets et leurs contrôles de disposition passent.


PFS:File (2026-10-10), buffers MAIN et lecture seule :

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| PFSFILE | 4832 / 4838 | 2589 | 2051 / 2045 |
| IDENT | 9148 / 9340 | 120 | 204 / 12 |
| IDFORMATS | 9141 / 9400 | 69 | 262 / 3 |

PFSFILE garde deux buffers de 1024 octets pour le formulaire et la fiche,
un bitmap de 256 octets pour l’appartenance des cellules et 32 offsets de
libellés. Le chargement accepte huit cellules (1008 octets utiles) au plus ;
les zones libres/index restent opaques. Aucun buffer AUX ou reconstruction
RAM. Le routage File reste partagé entre IDENT et IDFORMATS ; descriptions
et catégories sont raccourcies sans relever les plafonds. MENU garde 60/9
octets. MAIN 9/397, LC 3/1, LOWRAM 84/109 et écart de pile 26/603 restent
inchangés. Les deux builds complets, les gardes de disposition et les bancs
natifs passent ; la réserve IDFORMATS 6502 reste très faible (3 octets).


PFS:Plan B00 (2026-10-10), MAIN et lecture seule :

| Surcouche | Fichier 65C02 / 6502 | BSS | Libre sous $4000, 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| PFSPLAN | 4897 / 4972 | 1345 | 3230 / 3155 |
| IDENT | 9134 / 9326 | 120 | 218 / 26 |
| IDFORMATS | 9123 / 9382 | 69 | 280 / 21 |

Deux blocs de 512 octets stockent les libellés, plus les offsets bornés
(32 lignes, 16 colonnes) ; les cellules restent lues en flux. La candidature
Plan est dans IDENT, la route dans IDFORMATS. Les descriptions visibles
sont raccourcies pour respecter les plafonds existants. MENU garde 52/1
octets (65C02/6502). MAIN 9/397, LC 3/1, LOWRAM 84/109 et écart de pile
26/603 restent inchangés. Les deux builds et les gardes de disposition
passent sans relever les limites ; les réserves MENU/IDENT/IDFORMATS 6502
restent faibles.

## Lecteurs 1.0

IDV1 ajoute un relais MAIN-only, scellé comme les autres étapes IDENT, sans
modifier les plafonds. WORDPERF/MOUSEWR/BSFILER/MULTPLAN utilisent le lecteur
texte MAIN. MVMOVIE conserve un aperçu lores de 1920 octets en BSS MAIN et
n’alloue pas AUX. DGMAGI/PCSVW ont une queue $1B00–$1C9F et une phase C
$1CA0–$3FFF ; la queue engage le bitmap seulement après retour du C. AUX
$4000–$7FFF est réservé après consentement, puis /RAM est reconstruit.
Les limites sont imposées par sdk/v1gfx.cfg et les deux linkers natifs.
