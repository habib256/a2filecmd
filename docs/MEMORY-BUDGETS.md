# Consolidation : budgets mémoire

## Relevé actuel (25 octobre 2026, sources 0.9.9)

Les constructions 6502 et 65C02 et leurs gardes de disposition passent.
Le relevé de `tools/check_layout.py` est le suivant, en octets libres :

| Réserve | 65C02 | 6502 |
| --- | ---: | ---: |
| MAIN | 1 | 388 |
| Carte langage | 8 | 6 |
| LOWRAM | 87 | 112 |
| Écart sous la pile C réservée | 18 | 594 |
| OPEN | 0 | 0 |
| COPY | 8 | 5 |

Ces zones se recouvrent et ne s'additionnent pas. L'écart sous la pile
réservée n'est pas une mesure de sa consommation. Le Mini conserve MAIN
et LOW pleins. Les corrections de l'hôte POM2 du même jour ne modifient
pas les binaires Apple II. Les tableaux détaillés ci-dessous restent des
relevés historiques, à ne pas substituer à une nouvelle sortie du lien.

## Relevé historique (7 octobre 2026, sources b4cd129, candidat 0.9.6)

Relevé historique sur une construction neuve des
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
| AWDATA (big) | `$1B00-$3FFF` | 7 993 / 8 172 | 197 / 18 |
| BLKEDIT (big) | `$1B00-$3F9D` | 8 261 / 8 228 | 359 / 391 |
| BLKVIEW (big) | `$1B00-$3F9D` | 8 990 / 8 978 | 31 / 43 |
| BOOTBLK (big) | `$1B00-$2FFF` | 2 415 / 2 412 | 1 809 / 1 812 |
| CPM (big) | `$1B00-$3FFF` | 8 076 / 8 046 | 286 / 315 |
| CPMW (big) | `$1B00-$3FFF` | 7 280 / 7 242 | 1 352 / 1 389 |
| CRC (small) | `$1B00-$1FFF` | 1 152 / 1 161 | 13 / 4 |
| DATE (small) | `$1B00-$1FFF` | 1 227 / 1 228 | 8 / 7 |
| DGRVIEW (big) | `$1B00-$2FFF` | 3 753 / 3 844 | 1 555 / 1 464 |
| DIRSORT (big) | `$1B00-$3FFF` | 6 685 / 6 827 | 147 / 5 |
| DISASM (big) | `$1B00-$3FFF` | 7 940 / 7 935 | 885 / 890 |
| DISKCMP (big) | `$1B00-$3FFF` | 6 940 / 6 905 | 854 / 889 |
| DOCVIEW (big) | `$1B00-$3D5F` | 8 429 / 8 432 | 17 / 14 |
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
| NEWSROOM (big) | `$1B00-$1FFF` | 1151 / 1157 | 47 / 40 |
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
| TREE (big) | `$1B00-$3FFF` | 5 764 / 5 809 | 2 568 / 2 522 |
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

## Favoris de programmes FAVRUN (10 octobre 2026)

FAVRUN partage le lecteur et la sauvegarde récupérable de GOTO. Code et
BSS restent sous `$3000` ; neuf chemins à `$3000`, chemin sélectionné à
`$3300`, sérialisation à `$3400`. Aucun accès AUX. Le retour demande RUN
avec une entrée explicite conservée dans le résident : aucun indice du
panneau ni appel imbriqué à une surcouche. RUN accepte cette entrée même
quand le panneau n'a plus de table, et conserve ses contrôles habituels.

Relevé des deux liens : FAVRUN 5 088 / 5 051 octets (65C02 / 6502),
code + BSS jusqu'à `$2FF2` / `$2FCE` inclus, donc 13 / 49 octets libres.
GOTO finit à `$2FFB` / `$2FE3` inclus (4 / 28 libres). Le résident a
4 / 389 octets de réserve MAIN, 13 / 11 en LC, 86 / 111 en LOWRAM ;
écart sous la pile C réservée 21 / 595, sans mesure de sa consommation.
RUN laisse 271 / 270 octets avant `$3000`, MENU 57 / 6 avant `$2A00`.
La chaîne « Loading » est partagée en LC pour conserver les plafonds.
Les contrôles du lieur et `check_layout.py` restent actifs.

Contrôle du fichier source BASIC dans RUN (10 octobre 2026) : la nouvelle
lecture des métadonnées précède la recherche de l'interpréteur et toute
sauvegarde. RUN atteint 5 178 / 5 164 octets, soit 198 / 212 octets libres
avant `$3000` (65C02 / 6502). Aucun nouveau buffer, accès AUX ou changement
des réserves du résident. Les deux builds et leurs gardes passent.

Sauvegarde de configuration, contrôle tardif du fichier remplacé
(10 octobre 2026) : les métadonnées d'A2FILE.CFG sont relues avant son
renommage. Le même contrôle de protections/type/stockage sert aux deux
étapes. RUN atteint 5 224 / 5 210 octets, soit 152 / 166 octets libres
avant `$3000` (65C02 / 6502). Aucun buffer supplémentaire ni accès AUX ;
réserves du résident inchangées, deux builds et gardes validés.

Copie principale, contrôles de destination (10 octobre 2026) : la même
validation des protections et du stockage standard (1–3) sert avant la
création du temporaire et avant le remplacement. La constante A2FC.COPY
rejoint COPYRO ; le chemin d'erreur de publication est partagé et son
message raccourci pour conserver les plafonds. COPY mesure 1 272 / 1 275
octets, soit 8 / 5 octets libres sous `$2000` (65C02 / 6502). MAIN garde
2 / 389 octets, LC 13 / 11, LOWRAM 87 / 112 ; écart sous la pile réservée
19 / 595, sans mesure de consommation. Aucun buffer ou accès AUX ajouté.
Les deux builds et leurs gardes passent sans relever les limites.

Éditeur, protection des fichiers étendus (10 octobre 2026) : le contrôle
avant remplacement refuse tout stockage hors 1–3, notamment un fichier
à fourche de ressources. EDIT atteint 4 303 / 4 320 octets, soit 49 / 32
octets libres avant `$2C00` (65C02 / 6502). Aucun buffer supplémentaire
ni accès AUX ; réserves du résident inchangées. Les deux builds et leurs
gardes passent. Le banc hôte fait suivre une fourche simulée lors des
renommages et destructions et vérifie ses octets conservés sur refus.

Extraction IMGFS, identité de l'entrée (10 octobre 2026) : la recherche
compare aussi le nom, le type et l'auxiliaire du panneau avant toute
réservation de sortie. IMGFS atteint 2 168 / 2 150 octets, soit 1 160 /
1 178 octets libres avant `$2800` (65C02 / 6502). Aucun buffer ou accès
AUX ajouté ; réserves du résident inchangées, deux builds et gardes
validés. Les 18 cas d'entrée périmée passent ; 100 cas de fuzz vérifient
595 sorties contre la référence, sans divergence.

Extraction CP/M et Pascal, erreurs de relecture (10 octobre 2026) : la
sonde EOF n'est acceptée que si le flux de sortie reste sans erreur.
CPM mesure 8 085 / 8 051 octets, BSS jusqu'à `$3EEA` / `$3EC9` inclus,
soit 277 / 310 octets libres sous `$4000` (65C02 / 6502). PASCAL mesure
7 028 / 7 008 octets, BSS jusqu'à `$3988` / `$3975` inclus, soit
1 655 / 1 674 octets libres. Aucun buffer ou accès AUX ajouté. Deux builds
et contrôles de disposition validés ; douze cas d'erreur vérifient les
octets conservés, y compris les sorties précédentes et un nettoyage refusé.

MKIMAGE, relecture du résultat (10 octobre 2026) : un buffer MAIN de
512 octets compare le fichier fermé à l'en-tête et aux blocs reconstruits,
avec contrôle du flux, de l'EOF et de la fermeture. MKIMAGE mesure
4 675 / 4 773 octets, BSS jusqu'à `$306D` / `$30D0` inclus, soit
3 986 / 3 887 octets libres sous `$4000` (65C02 / 6502). Aucun accès AUX
ni changement des réserves du résident. Les deux builds et leurs gardes
passent ; le banc couvre PO/2MG, plusieurs bitmaps, corruptions, erreurs
de flux, annulation, collisions et nettoyage refusé.

SCIIBIN, erreurs de flux (10 octobre 2026) : les flux source, destination
et relecture sont contrôlés avant fermeture ; la sonde EOF exige aussi
un flux sans erreur. La description d'en-tête passe à 22 octets pour
conserver les plafonds. SCIIBIN mesure 6 552 / 6 566 octets, BSS jusqu'à
`$3FEA` / `$3FF9` inclus, soit 21 / 6 octets libres sous `$4000`
(65C02 / 6502). Aucun buffer ni accès AUX ajouté, résident inchangé.
Les deux builds et gardes passent ; seize cas vérifient les erreurs de
flux/fermeture et les octets conservés en cas de nettoyage refusé.

DISASM, erreurs malgré un compte complet (10 octobre 2026) : le lecteur
de page et l'écrivain d'export contrôlent aussi l'état du flux. DISASM
mesure 8 056 / 8 058 octets, BSS jusqu'à `$3D00` / `$3D03` inclus,
soit 767 / 764 octets libres sous `$4000` (65C02 / 6502). Aucun nouveau
buffer ni accès AUX ; résident inchangé. Les deux builds et leurs gardes
passent. Sept cas de régression vérifient le refus d'export complet et
la conservation de la source, en plus de l'oracle assembleur des opcodes.

VOLINFO, erreurs de flux dans les rapports (10 octobre 2026) : toutes
les écritures vérifient le compte et `ferror`, avant la fermeture contrôlée.
Une erreur arrête le rapport sans altérer les résultats de l’audit.
VOLINFO mesure 7 773 / 7 726 octets, BSS jusqu’à `$3F0D` / `$3EDF`
inclus, soit 144 / 190 octets libres sous la table à `$3F9E`
(65C02 / 6502). Aucun buffer ni accès AUX ajouté, résident inchangé.
Les deux builds et gardes passent ; sept cas injectent un compte complet
avec erreur et vérifient les octets conservés du rapport et du volume.

BLKVIEW, erreur de flux en extraction (11 octobre 2026) : chaque bloc
écrit exige le compte complet et un flux sans erreur. Le fichier partiel
reste disponible ; aucun accès AUX ni écriture source n’est ajouté.
La description d’en-tête et quelques libellés sont raccourcis pour garder
les plafonds. BLKVIEW mesure 9 004 / 8 997 octets, BSS jusqu’à `$3F8E` /
`$3F88` inclus, soit 15 / 21 octets libres sous la table à `$3F9E`
(65C02 / 6502). Résident inchangé ; les deux builds et gardes passent.
Neuf cas injectent une erreur avec compte complet sur le premier, deuxième
ou dernier bloc extrait en PO, DO et 2MG, et contrôlent les octets du
fichier partiel ainsi que la conservation intégrale de l’image source.

DISKCMP, verdict et erreurs de flux (11 octobre 2026) : les lectures
d’images exigent un flux sans erreur, même avec un compte complet.
Les deux fermetures sont exécutées et contrôlées ; une erreur interdit
un verdict complet. DISKCMP mesure 7 181 / 7 154 octets, BSS jusqu’à
`$3D9D` / `$3D83` inclus, soit 610 / 636 octets libres sous `$4000`
(65C02 / 6502). Aucun tampon ni accès AUX ajouté, résident inchangé.
Les deux builds et gardes passent. Douze cas sur les deux images,
identiques ou différentes, injectent une erreur au premier/dernier bloc
ou à la fermeture, contrôlent les octets conservés et exigent la
fermeture des deux flux même après échec.

DISKCMP, taille périmée des images brutes (11 octobre 2026) : avant
un verdict complet, une sonde à la fin attendue des images PO/DO exige
un EOF réel sans erreur. Les données annexes des conteneurs 2MG restent
acceptées : la comparaison porte sur leur disque déclaré. DISKCMP mesure
7 457 / 7 425 octets, BSS jusqu’à `$3EB1` / `$3E92` inclus, soit
334 / 365 octets libres sous `$4000` (65C02 / 6502). Aucun tampon
ni accès AUX ajouté, résident inchangé. Les deux builds et gardes passent.
Douze cas de taille périmée sur PO/DO et quatre erreurs de sonde
(lecture/recherche) contrôlent les octets conservés ; des cas valides DO
et 2MG avec données annexes distinctes complètent les régressions.

DISKCMP, ne pas sauter un volume en erreur (11 octobre 2026) :
la recherche parmi des volumes homonymes s’arrête dès qu’une unité
est identifiée, même si son en-tête est illisible ou invalide. Elle
ne remplace plus ce disque par un autre pour obtenir un verdict.
DISKCMP mesure 7 482 / 7 450 octets, BSS jusqu’à `$3ECA` / `$3EAB`
inclus, soit 309 / 340 octets libres sous `$4000` (65C02 / 6502).
Aucun tampon ni accès AUX ajouté, résident inchangé ; les deux builds
et gardes passent. Huit cas sur la source ou la destination vérifient
les erreurs persistantes/transitoires, le type d’en-tête et la taille
invalide, l’absence de lecture du disque suivant et les octets conservés.

DISKCMP, validation après échange en lecteur unique (11 octobre 2026) :
chaque disque déjà ouvert est relu au bloc 2 avant la reprise. Un
en-tête invalide, une taille différente ou une erreur de lecture arrête
la comparaison avec un verdict incomplet. Le premier montage destination
reste suivi de son ouverture normale, sans taille BSS non initialisée.
DISKCMP mesure 7 662 / 7 630 octets, BSS jusqu’à `$3F7F` / `$3F60`
inclus, soit 128 / 159 octets libres sous `$4000` (65C02 / 6502).
Aucun tampon ni accès AUX ajouté, résident inchangé ; les deux builds
et gardes passent. Six cas sur source/destination vérifient l’arrêt
avant la reprise des blocs ; un échange valide et deux annulations
complètent les tests, qui contrôlent les octets conservés. Le nom et
la taille ne distinguent pas deux disques différents de même nom/taille.

DIRSCAN, erreurs de flux avant exposition des entrées (11 octobre 2026) :
le comptage des blocs racine et le chargement du cache contrôlent `ferror`
malgré un compte complet. Les entrées du bloc en erreur ne sont ni
mises en cache ni utilisées par SYNC pour remplacer des fichiers.
SYNC mesure 7 181 / 7 206 octets, BSS jusqu’à `$3DDF` / `$3DF9`
inclus, soit 544 / 518 octets libres sous `$4000` (65C02 / 6502).
TREE mesure 5 159 / 5 185 octets, BSS jusqu’à `$3394` / `$33AF`
inclus, soit 3 179 / 3 152 octets libres sous `$4000`. Aucun tampon
ni accès AUX ajouté, résident inchangé ; les deux builds et gardes passent.
Six cas d’itération et un cas exécutant SYNC vérifient les erreurs de flux,
les octets conservés et l’absence de temporaires ou de remplacements.

SYNC, champs de dates source malformés (11 octobre 2026) : les plages
des dates de création/modification et des heures sont contrôlées avant
toute création ou tout remplacement. Les dates nulles restent inconnues ;
ce contrôle de champs ne valide pas toutes les combinaisons calendaires
(par exemple le nombre de jours de février). SYNC mesure 7 346 /
7 378 octets, BSS jusqu’à `$3E85` / `$3EA6` inclus, soit 378 /
345 octets libres sous `$4000` (65C02 / 6502). Aucun tampon ni accès
AUX ajouté, résident inchangé ; les deux builds et gardes passent.
Quatorze cas avec cible existante ou absente contrôlent les octets
conservés, l’absence de temporaires et les erreurs de mois/jour/heure/
minute ; un cas valide au 31 décembre à 23:59 complète les régressions.

SYNC, date destination invalide (11 octobre 2026) : les champs de
modification destination sont validés avant de décider que la source
est plus récente et de nouveau après vérification de la copie, avant
le premier renommage. Un refus tardif conserve l’original et la copie
vérifiée A2FC.SYNC, sans toucher à une sauvegarde. SYNC mesure 7 407 /
7 436 octets, BSS jusqu’à `$3EC2` / `$3EE0` inclus, soit 317 /
287 octets libres sous `$4000` (65C02 / 6502). Aucun tampon ni accès
AUX ajouté, résident inchangé ; les deux builds et gardes passent.
Dix cas injectent des champs de mois/jour/heure/minute invalides au
départ ou au contrôle final et vérifient les octets des originaux,
de la source et, au refus tardif, de la copie conservée.

RESCUE, comptes complets avec erreur de flux (11 octobre 2026) :
les lectures de fichier contrôlent `ferror` pour déclencher les retries
et, après épuisement, la mise à zéro journalisée. Les écritures du
fichier récupéré et du journal contrôlent aussi le flux avant fermeture.
RESCUE mesure 6 836 / 6 904 octets, BSS jusqu’à `$378A` / `$37CF`
inclus, soit 2 165 / 2 096 octets libres sous `$4000` (65C02 / 6502).
Aucun tampon ni accès AUX ajouté, résident inchangé ; les deux builds
et gardes passent. Dix-sept cas contrôlent retries, zéros journalisés,
les octets partiels et la source intacte. Si l’écriture de COMPLETE
retourne un compte complet avec erreur, cette ligne peut être présente ;
le résultat reste incomplet et une ligne INCOMPLETE est tentée ensuite.
Une panne persistante du journal peut empêcher cette dernière écriture.

UNDELETE, erreurs malgré un compte complet (11 octobre 2026) :
les deux lectures de répertoire et chaque écriture de récupération
contrôlent `ferror`. Un bloc de métadonnées en erreur n’autorise aucune
création ; une écriture en erreur refuse le succès et ne nettoie que
l’output créé. En cas de nettoyage refusé, les octets partiels restent
disponibles. Description et libellés sont raccourcis pour garder les
plafonds. UNDELETE mesure 6 925 / 6 946 octets, BSS jusqu’à `$3FE1` /
`$3FF7` inclus, soit 30 / 8 octets libres sous `$4000` (65C02 / 6502).
Aucun tampon ni accès AUX ajouté, résident inchangé ; les deux builds
et gardes passent. Dix cas vérifient les erreurs de répertoire/écriture,
les octets conservés après nettoyage refusé et la source intacte.

UNDELETE, noms déclarés malformés (11 octobre 2026) : tous les
caractères de la longueur conservée doivent appartenir à un composant
ProDOS valide. L’inférence d’un préfixe valide reste réservée aux entrées
dont DESTROY a effacé la longueur. Un nom avec slash, NUL ou caractère
invalide est refusé avant CREATE ; deux libellés sont raccourcis pour
conserver les plafonds. UNDELETE mesure 6 929 / 6 952 octets, BSS
jusqu’à `$3FE5` / `$3FFD` inclus, soit 26 / 2 octets libres sous
`$4000` (65C02 / 6502). Aucun tampon ni accès AUX ajouté, résident
inchangé ; les deux builds et gardes passent. Huit noms invalides
n’atteignent jamais CREATE, les octets source et du sous-dossier restent
intacts ; huit cas valides vérifient aussi les longueurs inférées.

UNDELETE, erreurs de lecture et index ambigus (11 octobre 2026) :
une erreur de lecture du bitmap, d’un index ou d’un index maître est
mémorisée pendant la validation ; elle ne peut plus sélectionner l’autre
interprétation des moitiés d’index. La récupération est refusée avant
CREATE. Trois libellés sont raccourcis pour conserver les plafonds.
UNDELETE mesure 6 927 / 6 942 octets, BSS jusqu’à `$3FE5` / `$3FF5`
inclus, soit 26 / 10 octets libres sous `$4000` (65C02 / 6502).
Aucun accès AUX ni écriture source ajouté, résident inchangé ; les deux
builds et gardes passent. Huit injections dans les deux interprétations,
sur fichiers à index simple ou maître, vérifient zéro CREATE et les
octets source conservés sur des images jetables. Les 64 tests des six
plugins et les 15 tests des gardes passent.

RESCUE, stockage et permission de lecture (11 octobre 2026) : le mode
fichier exige désormais un stockage standard 1 à 3 et le bit d’accès
lecture avant de créer le journal ou la sortie. Un stockage nul ou une
lecture interdite ne peut plus produire une récupération annoncée comme
complète, éventuellement remplie de zéros après des ouvertures refusées.
Le libellé de refus est raccourci. RESCUE mesure 6 827 / 6 895 octets,
BSS jusqu’à `$3781` / `$37C6` inclus, soit 2 174 / 2 105 octets libres
sous `$4000` (65C02 / 6502). Aucun tampon ni accès AUX ajouté, résident
inchangé ; les deux builds et gardes passent. Le vrai point d’entrée C
est testé sur 33 combinaisons de métadonnées et tailles : refus sans
création, octets source et fichier existant conservés, récupération exacte
des stockages 1 à 3 avec permission de lecture seule. Les 9 tests RESCUE,
64 tests des six plugins et 15 tests des gardes passent.

RESCUE, étendue brute impossible (11 octobre 2026) : une taille de
volume déclarée de 0, 1 ou 2 blocs omettrait l’en-tête lu au bloc 2.
Ces tailles sont refusées avant CREATE, au lieu d’annoncer COMPLETE
pour une image vide ou tronquée. Ce contrôle de cohérence ne prouve
pas la géométrie physique du support ni la validité complète du système
de fichiers endommagé. RESCUE mesure 6 847 / 6 914 octets, BSS jusqu’à
`$3795` / `$37D9` inclus, soit 2 154 / 2 086 octets libres sous `$4000`
(65C02 / 6502). Aucun tampon ni accès AUX ajouté, résident inchangé ;
les deux builds et gardes passent. Huit cas exécutent le vrai point
d’entrée C sur des images jetables : tailles impossibles, lecture
d’en-tête refusée, mauvais stockage et copies exactes de 3, 7 et 280
blocs. Les octets source et du fichier existant sont conservés ; les
10 tests RESCUE, 64 tests des six plugins et 15 tests des gardes passent.

UNWRAP, taille de panneau périmée (11 octobre 2026) : la longueur du
wrapper est mesurée par les lectures réelles du flux avant de valider les
offsets AppleSingle et MacBinary. Une taille périmée ne peut plus accepter
un fork vide au-delà de la fin réelle ni refuser un wrapper valide. Une
erreur de lecture, de retour au début ou une annulation arrête avant CREATE.
Cela ajoute une lecture complète du wrapper ; aucun tampon ni accès AUX
ajouté. UNWRAP mesure 7 010 / 7 000 octets, BSS jusqu’à `$3C40` / `$3C37`
inclus, soit 959 / 968 octets libres sous `$4000` (65C02 / 6502).
Résident inchangé ; les deux builds et gardes passent. Les 23 nouveaux
cas exécutent le vrai C sur des fichiers jetables et contrôlent les octets
source et existants, les sorties exactes et le refus avant création.
Les 13 tests UNWRAP et 15 tests des gardes passent. La mesure préalable
ne garantit pas que le support ne changera pas pendant les lectures suivantes.

UNSQ, annulation pendant la vérification (11 octobre 2026) : la
relecture contrôle ESC avant son ouverture et après chaque bloc, y
compris le dernier. Un fichier dont la vérification a été interrompue
n’est plus compté comme extrait ; seul ce fichier créé exclusivement
est nettoyé, les sorties précédemment vérifiées sont conservées. Aucun
tampon ni accès AUX ajouté, résident inchangé. UNSQ mesure 6 894 /
6 970 octets, BSS jusqu’à `$3E19` / `$3E66` inclus, soit 486 / 409
octets libres sous `$4000` (65C02 / 6502). Les deux builds et gardes
passent. Quatre injections exécutent le vrai C sur une archive jetable :
annulation au premier et dernier bloc, avant une vérification vide, et
échec de nettoyage conservant tous les octets du fichier en cours. Les
tests contrôlent aussi l’arrêt des lectures, la fermeture de vérification
et les octets source/existants/précédemment vérifiés. Les 16 tests UNSQ
et 15 tests des gardes passent.

SCIIBIN, annulation pendant la vérification (11 octobre 2026) : ESC
est contrôlé avant chaque lecture de 48 octets et avant la sonde EOF,
y compris après le dernier affichage de progression. Une vérification
interrompue échoue et nettoie uniquement la sortie créée exclusivement ;
les sources et AUX restent intactes. Les branches d’échec de lecture et
de CRC partagent leur fermeture, ce qui économise du code sans changer
les contrôles. SCIIBIN mesure 6 524 / 6 540 octets, BSS jusqu’à `$3FCE`
/ `$3FDF` inclus, soit 49 / 32 octets libres sous `$4000` (65C02 / 6502).
Résident et tampons inchangés ; les deux builds et gardes passent. Quatre
injections exécutent le vrai C sur des fichiers jetables : annulation au
premier et dernier affichage de vérification, avant la première lecture,
et nettoyage refusé conservant exactement la sortie. Les tests contrôlent
aussi la fermeture unique, la position d’arrêt et les octets des sources
et fichiers existants. Les 10 tests SCIIBIN (dont les CRC sous sim65 pour
les deux processeurs) et 15 tests des gardes passent.

UNWRAP, annulation pendant les fermetures finales (11 octobre 2026) :
ESC est contrôlé avant chaque passe et après la fermeture finale du
flux source, avant d’annoncer la réussite. Un fork vide ne peut plus
éviter tous les contrôles d’annulation, et une annulation reçue pendant
la fermeture de la relecture ou de la source arrête aussi l’extraction.
Seule la sortie créée exclusivement est nettoyée ; aucun tampon ni
accès AUX ajouté, résident inchangé. UNWRAP mesure 7 022 / 7 015 octets,
BSS jusqu’à `$3C4C` / `$3C46` inclus, soit 947 / 953 octets libres sous
`$4000` (65C02 / 6502). Les deux builds et gardes passent. Seize cas
exécutent le vrai C sur des wrappers AppleSingle et MacBinary jetables,
avec fork vide ou non vide, annulation aux trois fermetures et nettoyage
refusé. Les sources et fichiers existants restent identiques ; le
nettoyage refusé conserve exactement les octets de la sortie. Les
14 tests UNWRAP et 15 tests des gardes passent.

UNWRAP, données AppleSingle dans l’en-tête (11 octobre 2026) : la
table entière des descripteurs doit tenir dans le flux source, et toute
entrée non vide doit commencer après cette table. Des octets d’en-tête
ne peuvent plus être extraits comme fork ni interprétés comme nom ou
métadonnées. Les entrées vides à offset zéro restent acceptées. Ce
contrôle suit la disposition en-tête/descripteurs/données décrite dans
[RFC 1740, annexe A](https://www.rfc-editor.org/rfc/rfc1740.html#appendix-A).
La référence Python applique aussi ce contrôle. UNWRAP mesure 7 160 /
7 153 octets, BSS jusqu’à `$3CDA` / `$3CD4` inclus, soit 805 / 811
octets libres sous `$4000` (65C02 / 6502). Aucun tampon ni accès AUX
ajouté, résident inchangé ; les deux builds et gardes passent. Les 48
cas malformés des versions 1 et 2, pour six types d’entrées dont un ID
privé, sont refusés avant CREATE. Six cas valides contrôlent les entrées
vides et la frontière exacte de table. Le vrai C est exécuté sur des
fichiers jetables, dont les octets source et existants restent conservés.
Les 16 tests UNWRAP et 15 tests des gardes passent. Les chevauchements
entre deux zones de données ne sont pas contrôlés par cette correction.

UNWRAP, repli de format après rejet AppleSingle (11 octobre 2026) :
la signature AppleSingle choisit exclusivement son parseur. Un en-tête
rejeté ne peut plus contourner les contrôles d’offset/table/version par
une seconde interprétation MacBinary I. La référence Python suit aussi
ce choix. Aucun tampon ni accès AUX ajouté, résident inchangé ; seuls
les fichiers de sortie créés exclusivement peuvent être écrits/nettoyés.
UNWRAP mesure 7 178 / 7 174 octets, BSS jusqu’à `$3CEC` / `$3CE9`
inclus, soit 787 / 790 octets libres sous `$4000` (65C02 / 6502).
Les deux builds et gardes passent. Seize en-têtes jetables satisfaisant
les contrôles MacBinary I mais portant la signature AppleSingle sont
refusés avant CREATE : chevauchement d’en-tête, version invalide, offset
hors fichier ou table tronquée, avec sorties vides/non vides. Les six
cas MacBinary I/II/III valides restent extraits exactement. Le vrai C
contrôle aussi les octets source et existants conservés ; les 18 tests
UNWRAP et 15 tests des gardes passent.

CPM, lecture de répertoire pendant la mesure (11 octobre 2026) : une
erreur de lecture dans measure() marque l’extraction en échec, et le
parcours s’arrête avant de traiter le fichier comme vide. Elle ne peut
plus augmenter le compteur des fichiers ignorés puis annoncer une
extraction terminée. Les sorties précédemment vérifiées sont conservées ;
image source et AUX restent intactes. Aucun tampon ajouté, résident
inchangé. CPM mesure 8 099 / 8 064 octets, BSS jusqu’à `$3EF8` / `$3ED6`
inclus, soit 263 / 297 octets libres sous `$4000` (65C02 / 6502).
Les deux builds et gardes passent. Quatorze erreurs de lecture exécutent
le vrai C sur une image jetable, pendant la mesure du premier fichier
ou après une première sortie vérifiée. Les octets source/existants et
de la sortie conservée sont contrôlés, sans création pour le fichier
illisible. Un vrai fichier à zéro enregistrement reste ignoré sans
erreur. Les 12 tests CPM et 15 tests des gardes passent.

CPM, erreur du flux source à la fin (11 octobre 2026) : après le
parcours, l’extracteur contrôle ferror() et le résultat de fermeture
du fichier image avant d’annoncer une extraction terminée. Le flux
est fermé une seule fois même s’il porte déjà une erreur, puis son
pointeur est effacé. Les sorties déjà vérifiées restent conservées ;
source et AUX ne sont pas écrits. Aucun tampon ajouté, résident
inchangé. CPM mesure 8 138 / 8 105 octets, BSS jusqu’à `$3F1F` /
`$3EFF` inclus, soit 224 / 256 octets libres sous `$4000` (65C02 /
6502). Les deux builds et gardes passent. Quatre injections exécutent
le vrai C sur les deux ordres de secteurs d’images jetables : échec
de fermeture source et indicateur d’erreur tardif. Elles contrôlent
la fermeture unique, les octets source/existants et chaque sortie
vérifiée conservée exactement. Les 13 tests CPM et 15 tests des
gardes passent.

PASCAL, erreur du flux source à la fin (11 octobre 2026) : après le
parcours, ferror() et le résultat de fermeture du fichier image sont
contrôlés avant l’annonce de réussite, y compris pour un répertoire
vide. Le flux est fermé une seule fois même s’il porte une erreur,
puis son pointeur est effacé. Les sorties déjà vérifiées restent
conservées ; source et AUX ne sont pas écrits. Aucun tampon ajouté,
résident inchangé. PASCAL mesure 7 067 / 7 049 octets, BSS jusqu’à
`$39AF` / `$399E` inclus, soit 1 616 / 1 633 octets libres sous `$4000`
(65C02 / 6502). Les deux builds et gardes passent. Quatre cas exécutent
le vrai C sur des images jetables : fermeture source refusée après les
copies, indicateur d’erreur tardif, fermeture refusée d’une image vide,
et image vide sans erreur. Ils contrôlent la fermeture unique, les
octets source/existants et chaque sortie vérifiée conservée exactement.
Les 10 tests PASCAL et 15 tests des gardes passent.

PASCAL, erreurs source malgré un compte complet (11 octobre 2026) :
les lectures normalisées propres à l’extracteur contrôlent maintenant
ferror() avant de valider une entrée de répertoire ou un bloc de données.
Une lecture signalée en erreur ne peut plus conserver la sortie comme
vérifiée malgré un compte complet. Le lecteur partagé imageio et le
writer Pascal restent inchangés ; seuls les appels de cet extracteur
utilisent ce contrôle. Aucun tampon ni accès AUX ajouté, résident
inchangé. PASCAL mesure 7 119 / 7 103 octets, BSS jusqu’à `$39E3` /
`$39D4` inclus, soit 1 564 / 1 579 octets libres sous `$4000` (65C02 /
6502). Les deux builds et gardes passent. Neuf injections exécutent le
vrai C sur une image jetable, en répertoire, avant CREATE, pendant la
copie et pendant la dernière vérification, avec nettoyage refusé aussi.
Elles contrôlent le nombre de CREATE, la fermeture source unique et les
octets source/existants/précédemment vérifiés conservés ; un nettoyage
refusé garde exactement les octets du fichier en cours. Les 11 tests
PASCAL et 15 tests des gardes passent.

CPM, erreurs source malgré un compte complet (11 octobre 2026) : les
lectures normalisées propres à l’extracteur contrôlent ferror() avant
d’accepter les secteurs du répertoire ou des données. Une lecture
signalée en erreur arrête le parcours ou la copie, y compris pendant
la vérification du dernier fichier. Seule la sortie exclusivement créée
pour le fichier en cours est nettoyée ; les sorties déjà vérifiées restent
conservées. Le lecteur partagé imageio et CPMW restent inchangés. Aucun
tampon ni accès AUX ajouté, résident inchangé. CPM mesure 8 190 / 8 159
octets, BSS jusqu’à `$3F53` / `$3F35` inclus, soit 172 / 202 octets libres
sous `$4000` (65C02 / 6502). Les deux builds et gardes passent. Dix-neuf
injections exécutent le vrai C sur une image jetable : validation du
répertoire, lecture initiale, mesure avant CREATE, copie et dernière
vérification, avec nettoyage refusé aussi. Elles contrôlent les CREATE,
la fermeture source unique et les octets source/existants/précédemment
vérifiés conservés ; un nettoyage refusé conserve exactement la sortie
en cours et signale l’échec. Les 14 tests CPM et 15 tests des gardes
passent. Ces contrôles ne garantissent pas l’atomicité d’une écriture
physique en cas de coupure.

CPM, annulation pendant les fermetures de sortie (11 octobre 2026) :
ESC est contrôlé après la fermeture de l’écriture et après celle de la
relecture. Une annulation empêche désormais de commencer la vérification
ou de compter le fichier en cours comme extrait. Seule sa sortie créée
exclusivement est nettoyée ; les fichiers précédemment vérifiés restent
conservés. Source et AUX ne sont pas écrits, aucun tampon ajouté,
résident inchangé. CPM mesure 8 208 / 8 181 octets, BSS jusqu’à `$3F65` /
`$3F4B` inclus, soit 154 / 180 octets libres sous `$4000` (65C02 / 6502).
Les deux builds et gardes passent. Huit cas exécutent le vrai C sur une
image jetable : ESC à chacune des deux fermetures, sur le premier et le
dernier fichier, avec nettoyage réussi ou refusé. Ils contrôlent les
octets source/existants/précédemment vérifiés, le nombre de CREATE,
la fermeture source unique et l’absence de relecture après une annulation
à la fermeture d’écriture. Le nettoyage refusé conserve exactement la
sortie et signale son échec. Les 15 tests CPM et 15 tests des gardes passent.
Cette correction ne garantit pas l’atomicité des écritures physiques.

PASCAL, annulation pendant les fermetures de sortie (11 octobre 2026) :
ESC est contrôlé après la fermeture d’écriture et après celle de la
relecture. L’annulation empêche désormais de lancer la vérification ou
de compter le fichier en cours comme extrait. Seule sa sortie créée
exclusivement est nettoyée ; les fichiers précédemment vérifiés restent
conservés. Source et AUX ne sont pas écrits, aucun tampon ajouté,
résident inchangé. PASCAL mesure 7 137 / 7 125 octets, BSS jusqu’à `$39F5` /
`$39EA` inclus, soit 1 546 / 1 557 octets libres sous `$4000` (65C02 / 6502).
Les deux builds et gardes passent. Huit cas exécutent le vrai C sur une
image jetable : ESC à chacune des deux fermetures, sur le premier et le
dernier fichier, avec nettoyage réussi ou refusé. Ils contrôlent les
octets source/existants/précédemment vérifiés, les CREATE, la fermeture
source unique et l’absence de relecture après une annulation pendant la
fermeture d’écriture. Un nettoyage refusé conserve exactement la sortie
en cours et signale l’échec. Les 12 tests PASCAL et 15 tests des gardes
passent. Cette correction ne garantit pas l’atomicité des écritures
physiques en cas de coupure.

UNSQ, annulation pendant la fermeture de vérification (11 octobre 2026) :
la relecture contrôle ESC après sa fermeture, avant de valider longueur
et somme. L’annulation ne peut plus compter le fichier courant comme
extrait ni démarrer le suivant. Seule sa sortie créée exclusivement est
nettoyée ; les sorties précédemment vérifiées restent conservées.
Source et AUX ne sont pas écrits, aucun tampon ajouté, résident inchangé.
UNSQ mesure 6 910 / 6 986 octets, BSS jusqu’à `$3E29` / `$3E76` inclus,
soit 470 / 393 octets libres sous `$4000` (65C02 / 6502). Les deux builds
et gardes passent. Quatre cas exécutent le vrai C sur des archives ACU
jetables de trois fichiers : annulation à la fermeture de la vérification
du deuxième fichier, vide ou de 1 536 octets, avec nettoyage réussi ou
refusé. Ils contrôlent les octets source/existants/précédemment vérifiés,
la fermeture unique de la vérification, l’absence de CREATE du troisième
fichier et le retrait du deuxième. Un nettoyage refusé conserve exactement
ses octets et signale l’échec. Les 17 tests UNSQ et 15 tests des gardes
passent. Cette correction ne garantit pas l’atomicité des écritures
physiques en cas de coupure.

SMALLDOS, extraction Wilderness (11 octobre 2026) : nouvel overlay autonome
en lecture seule, menu Disks, pour les images brutes 35 pistes `.DSK/.DO`
en ordre DOS ou `.PO` en ordre ProDOS. Le catalogue entier (20 entrées de
32 octets) est lu et validé avant CREATE ; la longueur réelle de l’image
est mesurée sans utiliser la taille du panneau. Le secteur DOS est `15-s` ;
les pistes sont normales pour la démo ou `34-t` pour le jeu. Les sorties
conservent tous les octets des secteurs alloués : ni EOF exact ni adresse
de chargement binaire ne sont connus. Types A/B : `$FC/$0801`, `$06/$0000`.
Chaque sortie est créée exclusivement, écrite, fermée, puis comparée
secteur par secteur avec la source relue, EOF et erreurs de flux compris.
ESC est contrôlé dans les parcours et après les fermetures. Le nettoyage
vise uniquement la sortie courante ; un refus est annoncé et les sorties
précédemment vérifiées sont conservées. Aucun accès AUX ni écriture source.

SMALLDOS mesure 4 406 / 4 448 octets, BSS jusqu’à `$30F4` / `$311F` inclus,
soit 3 851 / 3 808 octets libres sous `$4000` (65C02 / 6502). Le catalogue
occupant 640 octets et le tampon de comparaison 256 octets vivent en MAIN.
L’ajout du nom de menu et le raccourcissement de son message de dossier
absent augmentent MENU d’un octet : 3 784 / 3 835, réserves 56 / 5 octets.
Réserves résident inchangées : MAIN 2 / 389, LC 13 / 11, LOWRAM 87 / 112,
écart pile 19 / 595. Aucune limite de disposition n’a été relâchée.

Les 12 tests SMALLDOS exécutent le vrai C sur des images jetables : les
deux sens de pistes et ordres de secteurs, les 20 entrées, collisions,
catalogues malformés, tailles invalides, lectures courtes ou signalées en
erreur malgré un compte complet, recherches, écritures, ouvertures,
fermetures, annulations et nettoyage refusé. Les octets source/existants
et conservés sont comparés intégralement. Les images locales SIERRA (20
fichiers) et WILDERNESS_DEMO (10) sont copiées en fixtures, relues en ordre
DOS et converties en ordre ProDOS ; JOURNEY sans catalogue est refusé.
Ces fixtures réelles sont facultatives hors du poste, les fixtures
synthétiques restent autonomes. Les tests UI (1), inventaire historique
(4), distribution (7), éditions (4) et gardes (15) passent aussi.

Les deux builds et images XL passent ; SMALLDOS.PLG extrait des deux XL
est identique au binaire compilé. La fabrication 800K reste impossible
dans l’état du dépôt : 1 634 blocs nécessaires sans SMALLDOS, 1 644 avec,
pour 1 600 disponibles. Aucune suppression d’outil ou modification du
format 800K n’a été faite pour contourner cette limite. La source n’est
pas modifiée et une coupure peut laisser une sortie ProDOS incomplète :
aucune atomicité d’écriture physique n’est promise.

800K, sélection pratique (11 octobre 2026) : la liste explicite de
`config/800k.mk` conserve les 24 overlays natifs et 70 overlays de service,
dont SMALLDOS, la gestion des fichiers, les outils disque/récupération,
les archives, les lecteurs BASIC/assembleur et les lecteurs courants.
Les helpers DOSIMAGE/DOSPUT, MOVECOPY, MCSIMPORT/MCSPLAY et IDREAD/IDFORMATS/
IDV1 sont conservés avec leurs commandes. BASIC.SYSTEM, INTBASIC.SYSTEM,
PPT3.BIN, VISICALC.BIN, FANTA.SYSTEM et TAKE1.SYSTEM restent présents.
Les 34 outils plus spécialisés restent disponibles dans les deux XL,
dont l’inventaire complet de 128 overlays a été contrôlé après génération.

La nouvelle image 800K utilise 1 322 blocs sur 1 600 et conserve 278 blocs
libres (139 KiB), contre 1 644 blocs nécessaires avec tous les overlays.
`check_800k.py` vérifie après fabrication la géométrie, l’inventaire exact,
les helpers et les octets des exécutables/overlays par rapport au build.
Il exige au moins 160 blocs libres (80 KiB), sans changer la capacité du
volume. Aucune modification native ni relaxation des limites mémoire.
Les réserves MAIN/LC/LOWRAM/pile et MENU restent celles du build SMALLDOS.

Les cinq tests 800K passent : politique de sélection et dépendances,
noms inconnus/doublons, image générée, quatre helpers/overlays manquants
et octets SMALLDOS altérés. Les corruptions portent uniquement sur des
copies jetables ; les octets de l’image source et des fixtures sont
contrôlés inchangés après refus. Distribution (7), éditions (4), anciens
inventaires (4) et gardes mémoire (15) passent aussi, soit 35 tests.
`make disk` termine pour les éditions 6502, 65C02 et Mini ; les deux
dispositions natives restent valides. La sélection 800K corrige le
dépassement documenté ci-dessus sans retirer d’outil des XL.

800K, carte d’allocation incohérente (11 octobre 2026) : l’audit comparait
les fichiers au build et comptait l’espace libre sans vérifier les blocs
réellement utilisés. Un bloc occupé marqué libre passait ces contrôles,
alors qu’une écriture ultérieure pourrait écraser le programme. L’audit
exécute désormais le vérificateur ProDOS en lecture seule avant de suivre
les répertoires ou de valider l’inventaire et l’espace disponible. Tout
parcours incomplet ou toute incohérence refuse l’image ; aucune réparation
automatique ni écriture n’est effectuée par le contrôle. Les dépendances
Make incluent les lecteurs/vérificateurs employés par cet audit.

Quatre régressions modifient uniquement des copies jetables du bitmap :
bloc d’amorce, bloc de répertoire, bloc d’index et bloc de données d’un
overlay marqués libres. Les octets du fichier sont toujours identiques,
mais les quatre images sont désormais refusées. Les fixtures et l’image
source restent inchangées après contrôle. Les six tests 800K, 65 tests du
vérificateur ProDOS et 15 tests de disposition passent, soit 86 tests.
`make disk` et les dispositions 6502/65C02 passent. L’image saine conserve
94 overlays et 278 blocs libres (139 KiB). Aucun code natif, accès AUX ou
budget mémoire modifié ; aucune atomicité d’écriture physique ajoutée.

800K, métadonnées de chargement (11 octobre 2026) : des octets identiques
au build ne suffisaient pas à garantir qu’un programme était chargeable.
L’audit acceptait un SYS d’un autre type, un helper d’adresse auxiliaire
incorrecte ou un fichier privé de lecture. Il contrôle désormais pour
chaque fichier requis le stockage standard, l’accès en lecture, le type
SYS/BIN/TXT attendu et l’auxiliaire déclaré par le staging : `$1B00` pour
les overlays, `$0800` pour PPT3.BIN, zéro pour les autres fichiers requis.
Les protections contre l’écriture restent acceptées. Le contrôle lit
uniquement l’image et les fichiers du build ; aucune réparation ou
modification de l’image par l’audit, aucun accès AUX, aucun code natif changé.

Vingt et une injections sur des copies jetables couvrent type, auxiliaire
et accès en lecture du lanceur, de BASIC.SYSTEM, de SMALLDOS.PLG, de
PPT3.BIN, de VISICALC.BIN, de FANTA.SYSTEM et de l’aide. Elles sont toutes
refusées après correction ; les octets de l’image source et des fixtures
restent inchangés. Un cas positif conserve une protection en écriture
sur SMALLDOS.PLG et reste accepté sans modification. Les huit tests 800K,
sept tests distribution et quinze tests des gardes passent, soit 30 tests.
`make disk` passe et la validation 6502/65C02 reste valide, avec les mêmes
réserves mémoire. L’image saine conserve 94 overlays et 139 KiB libres.
Ce contrôle de fabrication n’ajoute pas d’atomicité aux écritures physiques.

SMALLDOS : erreurs de création (11 octobre 2026). Seule la collision de
nom ProDOS `$47` est désormais ignorée ; une erreur d’E/S, un disque plein
ou un accès refusé arrête l’extraction et signale l’échec. La destination
refusée n’est ni ouverte ni supprimée. Les sorties déjà fermées et vérifiées
restent intactes, comme l’image source et les fichiers préexistants.
Aucune écriture brute ou AUX : seuls les nouveaux fichiers ProDOS réservés
par CREATE sont écrits. Les essais utilisent uniquement des images jetables.

Neuf cas de régression exécutent le vrai C avec CREATE refusé au premier,
deuxième ou dernier fichier pour les erreurs `$27`, `$48` et `$4E` ; ils
échouaient tous avant correction. Les 13 tests SMALLDOS contrôlent les
octets conservés, les collisions et la fermeture de la source. Les 15 tests
des gardes de disposition et les builds complets 65C02/6502 passent.
SMALLDOS mesure 4 421 / 4 463 octets, BSS jusqu’à `$3103` / `$312E` inclus,
soit 3 836 / 3 793 octets libres sous `$4000`. Les réserves résidentes et
MENU restent inchangées ; aucun plafond n’est relevé. L’arrêt sur CREATE
ne fournit pas d’atomicité face à une coupure pendant une écriture physique.

PASCAL et CP/M : erreurs de création (11 octobre 2026). Les extracteurs
ignoraient toutes les erreurs de CREATE comme un nom déjà pris. Seul `$47`
est désormais une collision ; `$27` (E/S), `$48` (disque plein), `$4E`
(accès refusé) et les autres erreurs arrêtent l’extraction avec un bilan
d’échec. Le chemin refusé n’est ni ouvert ni supprimé. Les seules écritures
concernent les nouvelles sorties ProDOS créées exclusivement ; les images
sources sont en lecture seule, sans écriture brute ni allocation AUX/RAM.

Les dix-huit cas de régression, au premier, deuxième et dernier fichier,
échouaient avant correction. Ils exécutent le vrai C et contrôlent tous
les octets des sorties vérifiées et du fichier préexistant, l’arrêt des
CREATE suivants et la fermeture unique de la source. Les 12 tests Pascal,
15 CP/M, 13 SMALLDOS (harness partagé) et 15 gardes de disposition passent.
Les builds complets 65C02/6502 et leurs contrôles de disposition passent.

| Surcouche | Fichier 65C02 / 6502 | BSS fin incluse 65C02 / 6502 | Libre sous `$4000` |
| --- | ---: | ---: | ---: |
| CP/M | 8 234 / 8 207 | `$3F7F` / `$3F65` | 128 / 154 |
| PASCAL | 7 163 / 7 151 | `$3A0F` / `$3A04` | 1 520 / 1 531 |

Les réserves résidentes et MENU restent inchangées ; aucun plafond n’est
relevé. Les fixtures sont jetables. Ces contrôles ne rendent pas une
écriture physique atomique en cas de coupure.

PASCAL et CP/M : chemins de sortie trop longs (11 octobre 2026). Un
échec de construction du chemin était compté comme une collision de nom,
puis l’extraction continuait avec un bilan de réussite. Il arrête désormais
l’opération avec un bilan d’échec, avant CREATE pour ce fichier. Les seules
écritures restent celles des nouvelles sorties ProDOS réservées exclusivement ;
les sources, les fichiers préexistants et AUX/RAM restent intacts.

Sept cas exécutent le vrai C dans des arborescences jetables dont chaque
composant respecte la limite ProDOS : cinq refus reproduisaient le défaut,
deux cas positifs acceptent un chemin final de 63 caractères. Le refus après
une première sortie Pascal vérifiée conserve tous ses octets ; aucun CREATE
suivant n’est tenté. Les tests comparent tous les fichiers, le compteur de
CREATE et la fermeture unique de la source. Les 13 tests Pascal, 16 CP/M,
13 SMALLDOS (harness partagé) et 15 gardes passent, ainsi que les builds
complets et contrôles de disposition 65C02/6502.

| Surcouche | Fichier 65C02 / 6502 | BSS fin incluse 65C02 / 6502 | Libre sous `$4000` |
| --- | ---: | ---: | ---: |
| CP/M | 8 238 / 8 212 | `$3F83` / `$3F6A` | 124 / 149 |
| PASCAL | 7 167 / 7 156 | `$3A13` / `$3A09` | 1 516 / 1 526 |

Les réserves résidentes et MENU restent inchangées ; aucun plafond n’est
relevé. La correction n’apporte pas d’atomicité en cas de coupure pendant
une écriture physique.

PASCAL et CP/M : Échap pendant la fermeture finale (11 octobre 2026).
Les extracteurs ne vérifiaient plus le clavier après la fermeture de
l’image source et pouvaient annoncer une réussite malgré une annulation.
Une dernière vérification signale désormais l’arrêt. Les sorties déjà
fermées et vérifiées restent conservées ; aucune suppression supplémentaire
n’est ajoutée. Les seules écritures restent celles des nouvelles sorties
ProDOS créées exclusivement, sans écriture de l’image source ou d’AUX/RAM.

Huit cas exécutent le vrai C sur des images jetables : annulation pendant
la fermeture finale, avec ou sans erreur de fermeture, sur quatre sorties
et sur un volume Pascal vide ou une entrée CP/M sans enregistrements.
Quatre cas échouaient avant correction. Tous contrôlent les octets des
sorties et du fichier préexistant, le compteur de CREATE et une fermeture
unique de la source. Les 14 tests Pascal, 17 CP/M, 13 SMALLDOS (harness
partagé), 15 gardes de disposition et les builds complets 65C02/6502 passent.

| Surcouche | Fichier 65C02 / 6502 | BSS fin incluse 65C02 / 6502 | Libre sous `$4000` |
| --- | ---: | ---: | ---: |
| CP/M | 8 249 / 8 223 | `$3F8E` / `$3F75` | 113 / 138 |
| PASCAL | 7 178 / 7 167 | `$3A1E` / `$3A14` | 1 505 / 1 515 |

Les contrôles de disposition natifs passent sans changement des réserves
résidentes ou MENU ni relèvement des plafonds. La correction ne garantit
pas d’atomicité face à une coupure pendant une écriture physique.

PASCAL/PASCALW : volume plus petit que son catalogue (11 octobre 2026).
Le lecteur partagé acceptait un volume vide déclarant 1 à 5 blocs, alors
que les deux blocs de démarrage et les quatre de catalogue exigent au
moins six blocs. Dans PASCALW, `vblocks - tail` sous-débordait et autorisait
des écritures à partir du bloc 6, hors du volume déclaré mais dans le
conteneur. Le contrôle partagé refuse désormais ces métadonnées avant
toute création de sortie ou écriture du conteneur. L’oracle Python impose
la même borne minimale.

PASCAL ne peut écrire que ses nouvelles sorties ProDOS créées exclusivement.
PASCALW peut écrire les blocs de données et de catalogue de l’image ciblée,
jamais ses sources ProDOS. Aucun accès AUX/RAM n’est ajouté. Les fixtures
sont jetables ; les tests comparent tous les octets du conteneur et des
sources après refus, ainsi que le compteur d’écritures.

Dix cas reproduisaient le défaut (1 à 5 blocs, dans les deux sens). Les
tests couvrent aussi zéro bloc, six blocs sans place pour une sortie, et
sept blocs avec un fichier tenant exactement dans l’unique bloc de données.
Ce dernier conserve tous les octets au-delà du volume déclaré. Les 15 tests
PASCAL, 17 PASCALW (dont les contrôles de capacité natifs), 13 SMALLDOS
(harness partagé), 15 gardes de disposition et l’autotest de l’oracle passent.
Les builds complets 65C02/6502 et leurs contrôles de disposition passent.

| Surcouche | Fichier 65C02 / 6502 | BSS fin incluse 65C02 / 6502 | Libre sous `$4000` |
| --- | ---: | ---: | ---: |
| PASCAL | 7 184 / 7 173 | `$3A24` / `$3A1A` | 1 499 / 1 509 |
| PASCALW | 7 242 / 7 248 | `$3AB7` / `$3ABE` | 1 352 / 1 345 |

Les réserves résidentes et MENU sont inchangées ; aucun plafond n’est
relevé. Le refus avant écriture ne rend pas atomiques les écritures d’un
volume valide face à une coupure physique.

PASCALW : contrôler la source avant publication (11 octobre 2026). Une
lecture au compte complet mais portant une erreur, un échec de fermeture,
Échap pendant cette fermeture ou une taille de panneau sous-estimée
pouvaient laisser publier une copie incomplète dans le catalogue Pascal.
Chaque lecture vérifie désormais `ferror`, puis une sonde d’EOF propre
confirme la longueur réelle. La fermeture doit réussir et une dernière
vérification d’Échap précède le commit du catalogue.

PASCALW écrit les blocs de données libres en fin de volume, puis les blocs
du catalogue de l’image confirmée. Les sources ProDOS sont en lecture
seule ; aucun accès AUX/RAM. En cas de refus avant commit, les données
déjà écrites dans la fin libre peuvent rester physiquement présentes, mais
aucune nouvelle entrée ne les référence. Le catalogue et les fichiers
préexistants restent identiques. Une source n’est fermée qu’une fois.

Sept cas exécutent le vrai C sur une image jetable : lectures complètes
avec erreur au premier/deuxième bloc, erreur lors de la sonde EOF, échec
de fermeture, annulation pendant la fermeture et tailles périmées inférieure
ou supérieure à la taille réelle. Six reproduisaient le défaut ; le cas de
taille surestimée vérifie aussi le refus déjà présent. Ils contrôlent les
octets du catalogue, du fichier Pascal préexistant et de toutes les sources,
l’absence d’entrée publiée et la fermeture unique. Les 18 tests PASCALW,
15 PASCAL et 15 gardes de disposition passent, ainsi que les builds complets
et contrôles de disposition 65C02/6502.

PASCALW mesure 7 359 / 7 364 octets, BSS jusqu’à `$3B2C` / `$3B32` inclus,
soit 1 235 / 1 229 octets libres sous `$4000`. Les réserves résidentes et
MENU sont inchangées ; aucun plafond n’est relevé. Le commit du catalogue
reste une écriture physique sans garantie d’atomicité face à une coupure.

PASCALW : erreurs au compte complet dans l’image (11 octobre 2026).
Le lecteur/écrivain de blocs pouvait rendre succès sur un compte complet
portant une erreur de flux, puis effacer cette erreur au bloc suivant.
Un contrôle local à PASCALW vérifie désormais `ferror` après chaque bloc,
y compris pendant la restauration du catalogue. L’en-tête 2MG, lu hors
de ce chemin, est aussi contrôlé avant toute écriture. Les autres overlays
et le lecteur partagé `imageio.h` restent inchangés.

L’opération peut écrire les blocs libres de données et le catalogue de
l’image confirmée ; les sources ProDOS restent en lecture seule, sans
accès AUX/RAM. Après un échec de publication, la restauration tente de
remettre les octets sauvegardés. Si elle ne peut pas être vérifiée, le
message demande de contrôler le volume au lieu de le déclarer intact.
Les écritures physiques et leur restauration ne sont pas atomiques face
à une coupure ; des données non référencées peuvent rester en fin libre.

Dix-huit cas sur images jetables exécutent le vrai C : validation initiale
et après confirmation, vérification des données, sauvegarde du catalogue,
publication, erreurs persistantes pendant restauration, en-tête 2MG et
les deux moitiés d’un bloc DOS. Quinze cas et l’en-tête 2MG ont été observés
en échec avant leurs corrections. Le mock reproduit aussi `clearerr` entre
blocs. Les tests comparent les octets du catalogue et du fichier Pascal
préexistant, toutes les sources et l’absence de publication ; les refus
avant écriture conservent l’intégralité du conteneur.

Les 20 tests PASCALW, 15 PASCAL et 15 gardes de disposition passent, ainsi
que les builds complets et contrôles natifs 65C02/6502. PASCALW mesure
7 431 / 7 438 octets, BSS jusqu’à `$3B74` / `$3B7C` inclus, soit 1 163 /
1 155 octets libres sous `$4000`. Les réserves résidentes et MENU restent
inchangées ; aucun plafond n’est relevé.

PASCALW : distinguer un nom pris d’un catalogue illisible (11 octobre 2026).
La recherche de noms retournait « présent » lorsqu’une entrée ne pouvait
pas être lue ; l’import comptait alors une collision et poursuivait avec un
bilan de réussite. Elle distingue maintenant nom libre, nom présent et
erreur. Cette dernière arrête l’import avec un message de lecture du
catalogue, avant l’ouverture de la source et toute écriture de ce fichier.

L’opération peut écrire les blocs libres et le catalogue de l’image ciblée,
mais la recherche corrigée n’écrit rien. Les sources ProDOS restent en
lecture seule et aucun accès AUX/RAM n’est ajouté. Huit cas exécutent le
vrai C sur des images jetables : lecture courte ou compte complet signalé
en erreur, premier nom recherché et chacune des deux parties de l’entrée
19 qui traverse une limite de bloc. Tous échouaient avant correction.
Une seconde source vérifie que l’import ne continue pas après le refus.
Les tests contrôlent zéro écriture, zéro fermeture de source (aucune n’est
ouverte), tous les octets du conteneur et de toutes les sources. Les vraies
collisions restent ignorées et sont couvertes par les tests existants.

Les 21 tests PASCALW, 15 PASCAL et 15 gardes de disposition passent, ainsi
que les builds complets et contrôles natifs 65C02/6502. PASCALW mesure
7 485 / 7 491 octets, BSS jusqu’à `$3BAA` / `$3BB1` inclus, soit 1 109 /
1 102 octets libres sous `$4000`. Les réserves résidentes et MENU restent
inchangées ; aucun plafond n’est relevé. Les écritures physiques d’un
import valide ne deviennent pas atomiques face à une coupure.

PASCALW : contrôler la fermeture finale de l’image (11 octobre 2026).
La fermeture de l’image ignorait son résultat et l’annulation pendant
cette fermeture. Après un import publié, le bilan pouvait donc rester une
réussite malgré un échec de CLOSE. La fermeture est désormais contrôlée,
effectuée une seule fois, puis le pointeur est invalidé. Son échec demande
de contrôler le volume, y compris après un refus antérieur de lecture.
Une annulation après un import terminé est signalée en conservant les
fichiers publiés. Un diagnostic antérieur n’est pas masqué par Échap.

Les écritures restent celles des blocs libres et du catalogue de l’image
confirmée ; cette correction n’ajoute aucune écriture ni restauration
après publication. Les sources ProDOS et AUX/RAM sont inchangés. Un échec
de CLOSE n’autorise pas à effacer un fichier publié et ne prouve pas que
toutes les écritures ont atteint le support physique.

Huit cas exécutent le vrai C sur une image jetable : échec de fermeture,
annulation ou les deux, avec et sans source ; échec de fermeture après une
erreur de lecture de source ou de recherche dans le catalogue. Tous
échouaient avant correction. Les tests contrôlent les octets des anciens
et nouveaux fichiers publiés, toutes les sources, une fermeture unique
de l’image et des sources ouvertes. Sans publication, le conteneur entier
est comparé lorsque rien n’a été écrit.

Les 22 tests PASCALW, 15 PASCAL et 15 gardes de disposition passent, ainsi
que les builds complets et contrôles natifs 65C02/6502. PASCALW mesure
7 578 / 7 585 octets, BSS jusqu’à `$3C08` / `$3C10` inclus, soit 1 015 /
1 007 octets libres sous `$4000`. Les réserves résidentes et MENU restent
inchangées ; aucun plafond n’est relevé. Ces contrôles ne garantissent pas
l’atomicité des écritures physiques face à une coupure.

PASCALW/CPMW : ne pas importer après un parcours incomplet du dossier
source (11 octobre 2026). Les deux imports ignoraient le statut de
`dir_close` : une lecture interrompue ressemblait à la fin normale du
dossier, et un échec de fermeture après sélection d’une entrée autorisait
quand même son import. Ils contrôlent désormais le statut renvoyé par le
résident avant d’interpréter EOF ou d’ouvrir la source sélectionnée. Le
message signale que le panneau opposé ne peut pas être lu.

L’API figée déclare `dir_close` en `void`, mais le résident renvoie bien
`dir_error` ; la lecture du résultat reprend la convention déjà employée
par FIND, sans changer l’ABI. Un test sim65 compile l’appel des overlays
avec chaque compilateur 65C02/6502 et vérifie les statuts 0, 1 et `$27`.

Douze cas exécutent le vrai C des imports sur des images jetables : erreur
de lecture ou de fermeture au premier passage, après un fichier importé
et au parcours final. Tous échouaient avant correction. Les tests comparent
chaque fichier du volume avec ses octets attendus, toutes les sources et
l’arrêt des passages suivants. Avant le premier import, tout le conteneur
reste identique. Les fichiers déjà publiés ne sont pas effacés ; les seules
écritures restent les blocs libres et le catalogue de l’image confirmée.
Aucune écriture de source ProDOS ni aucun accès AUX/RAM n’est ajouté.

Les 24 tests PASCALW, 13 CPMW et 15 gardes de disposition passent, ainsi
que les builds complets et contrôles natifs 65C02/6502.

| Surcouche | Fichier 65C02 / 6502 | BSS fin incluse 65C02 / 6502 | Libre sous `$4000` |
| --- | ---: | ---: | ---: |
| PASCALW | 7 593 / 7 600 | `$3C17` / `$3C1F` | 1 000 / 992 |
| CPMW | 7 295 / 7 257 | `$3AC6` / `$3AA1` | 1 337 / 1 374 |

Les réserves résidentes et MENU restent inchangées ; aucun plafond n’est
relevé. L’arrêt sur une erreur de parcours ne rend pas atomiques les
écritures physiques déjà effectuées face à une coupure.

CPMW : contrôler la source avant publication (11 octobre 2026). L’import
CP/M pouvait publier un fichier malgré une lecture au compte complet
portant une erreur, un échec de fermeture, Échap pendant cette fermeture
ou une taille de panneau sous-estimée. Les lectures vérifient désormais
`ferror`, une sonde d’EOF propre confirme la longueur réelle, puis la
fermeture et l’annulation sont contrôlées avant l’écriture de l’entrée.

CPMW peut écrire les blocs libres de données et le catalogue de l’image
confirmée. Les sources ProDOS sont en lecture seule et AUX/RAM reste
inchangé. Avant publication, un refus laisse les octets déjà écrits dans
les blocs libres non référencés ; le catalogue et les fichiers préexistants
restent intacts. La source est fermée une seule fois.

Sept cas exécutent le vrai C sur une image jetable : erreur au compte
complet du premier/quatrième secteur, erreur de sonde EOF, échec de
fermeture, annulation à la fermeture et tailles périmées inférieure ou
supérieure à la taille réelle. Six reproduisaient le défaut ; la taille
surestimée contrôle le refus déjà présent. Les tests comparent l’intégralité
du catalogue, tous les fichiers préexistants et toutes les sources, et
vérifient l’absence de publication et la fermeture unique. Une erreur
au premier secteur conserve aussi le conteneur entier sans écriture.

Les 14 tests CPMW, 17 CP/M et 15 gardes de disposition passent, ainsi que
les builds complets et contrôles natifs 65C02/6502. CPMW mesure 7 439 /
7 400 octets, BSS jusqu’à `$3B56` / `$3B30` inclus, soit 1 193 / 1 231
octets libres sous `$4000`. Les réserves résidentes et MENU restent
inchangées ; aucun plafond n’est relevé. La publication reste une écriture
physique sans garantie d’atomicité face à une coupure.

CPMW : distinguer une collision d’une recherche illisible (11 octobre 2026).
Le parcours des noms renvoyait « présent » sur une erreur de lecture ou de
positionnement. Le fichier était compté comme ignoré, puis l’import pouvait
continuer et annoncer une réussite. La recherche distingue désormais nom
libre, nom présent et erreur ; cette dernière arrête l’import avec un
diagnostic du catalogue CP/M, avant toute ouverture de la source concernée.

L’opération peut écrire les blocs libres et le catalogue de l’image
confirmée, mais la recherche n’écrit rien. Les sources ProDOS restent en
lecture seule et aucun accès AUX/RAM n’est ajouté. Seize cas exécutent le
vrai C sur une image jetable : lecture courte ou échec de seek dans chacun
des huit secteurs du catalogue, après les validations initiale et après
confirmation. Tous échouaient avant correction. Une seconde source vérifie
que le refus n’est pas suivi d’un nouvel import. Chaque cas contrôle zéro
écriture, l’arrêt au premier passage, aucune source ouverte et tous les
octets du conteneur et des sources. Les vraies collisions restent couvertes
par les tests existants et conservent leurs octets.

Les 15 tests CPMW, 17 CP/M et 15 gardes de disposition passent, ainsi que
les builds complets et contrôles natifs 65C02/6502. CPMW mesure 7 491 /
7 451 octets, BSS jusqu’à `$3B8A` / `$3B63` inclus, soit 1 141 / 1 180
octets libres sous `$4000`. Les réserves résidentes et MENU restent
inchangées ; aucun plafond n’est relevé. Le refus avant écriture ne rend
pas atomiques les écritures physiques d’un import valide face à une coupure.

CPMW : contrôler la fermeture finale de l’image (11 octobre 2026).
L’import ignorait le résultat de CLOSE et Échap pendant cette fermeture,
ce qui pouvait laisser un bilan de réussite après un échec. La fermeture
est désormais contrôlée et effectuée une fois, puis le pointeur est
invalidé. Un échec demande de contrôler le volume, même après un refus de
lecture de source ou du catalogue. Une annulation après un parcours terminé
est signalée ; les diagnostics antérieurs ne sont pas masqués par Échap.

Les écritures restent les blocs libres et le catalogue de l’image
confirmée. Cette correction n’ajoute ni écriture ni suppression après
publication : les fichiers déjà publiés restent récupérables. Les sources
ProDOS restent en lecture seule, sans accès AUX/RAM. Un CLOSE en échec ne
prouve pas que les écritures ont toutes atteint le support physique.

Huit cas exécutent le vrai C sur une image jetable : échec de fermeture,
annulation ou les deux avec/sans source, puis échec de fermeture après une
erreur de source ou de recherche de nom. Tous échouaient avant correction.
Les tests contrôlent les octets de chaque fichier ancien et nouveau publié,
toutes les sources et la fermeture unique de chaque flux ouvert. Les cas
sans écriture comparent aussi le conteneur entier.

Les 16 tests CPMW, 17 CP/M et 15 gardes de disposition passent, ainsi que
les builds complets et contrôles natifs 65C02/6502. CPMW mesure 7 584 /
7 545 octets, BSS jusqu’à `$3BE8` / `$3BC2` inclus, soit 1 047 / 1 085
octets libres sous `$4000`. Les réserves résidentes et MENU restent
inchangées ; aucun plafond n’est relevé. Ces contrôles ne rendent pas
atomiques les écritures physiques face à une coupure.

CPMW : restaurer le bloc partagé après une écriture en échec (11 octobre
2026). Une écriture partielle ou corrompue du catalogue pouvait endommager
une entrée existante, tandis que le message affirmait le volume intact.
Chaque modification de secteur sauvegarde désormais les 512 octets du
bloc ProDOS partagé avant écriture. Un échec d’écriture ou de vérification
restaure ce bloc entier et relit les 512 octets. Si cette restauration
échoue ou ne peut être vérifiée, le diagnostic demande de contrôler le
volume, pour les données comme pour le catalogue.

Les écritures possibles restent dans les blocs libres et le catalogue de
l’image confirmée, avec une restauration du même bloc en cas d’échec.
La sauvegarde de 512 octets est en BSS MAIN, jamais AUX/RAM. Les sources
ProDOS restent en lecture seule. Restaurer uniquement l’entrée ou le
secteur concerné ne protégerait pas les autres entrées et le secteur voisin.
Cette sauvegarde en mémoire ne protège pas d’une coupure pendant l’écriture
physique ou la restauration ; les commentaires précédents promettant une
préservation sur coupure ont été corrigés.

Vingt-deux cas exécutent le vrai C sur des images jetables : 15 erreurs
d’écriture nulle, partielle ou corrompue aux quatre secteurs de données et
au catalogue, quatre restaurations en échec ou illisibles, puis trois
publications corrompues en 2MG/DOS (chaque moitié du bloc DOS). Douze cas
avaient échoué avant correction. Les tests capturent les octets physiques
du bloc avant l’écriture fautive, comparent les 512 octets restaurés,
l’intégralité du catalogue, tous les fichiers préexistants et toutes les
sources. Une restauration non vérifiable ne déclare jamais le volume intact.

Les 19 tests CPMW, 17 CP/M et 15 gardes de disposition passent, ainsi que
les builds complets et contrôles natifs 65C02/6502. CPMW mesure 7 787 /
7 752 octets, BSS jusqu’à `$3EB4` / `$3E92` inclus, soit 331 / 365 octets
libres sous `$4000`. Les réserves résidentes et MENU restent inchangées ;
aucun plafond n’est relevé.

CPMW : erreurs au compte complet dans l’image (11 octobre 2026).
Les blocs lus ou écrits au compte complet étaient acceptés malgré une
erreur du flux, puis le bloc suivant effaçait l’indicateur. Un contrôle
local à CPMW vérifie désormais chaque résultat avant cet effacement, y
compris pendant la restauration. Une erreur d’E/S est aussi mémorisée :
la sélection de l’ordre des secteurs s’arrête au lieu d’essayer le candidat
suivant après une lecture invalide. L’en-tête 2MG, lu hors du chemin de
blocs, est vérifié avant toute écriture. `imageio.h` et les autres overlays
restent inchangés.

Les écritures possibles restent les blocs libres et le catalogue de
l’image confirmée, plus la restauration du même bloc après échec. Les
sources ProDOS sont en lecture seule, sans accès AUX/RAM. Une restauration
en erreur ne permet plus de déclarer le volume intact. La sauvegarde MAIN
ne rend pas atomiques les écritures physiques face à une coupure.

Quarante-cinq cas exécutent le vrai C sur des images jetables : 35 lectures
de validation, recherche, sauvegarde et vérification ; cinq écritures ;
deux erreurs persistantes pendant restauration ; l’en-tête 2MG et chaque
moitié d’un bloc DOS. Les 42 premiers cas échouaient avant correction.
Le mock reproduit `clearerr` entre blocs. Tous les cas comparent les octets
du catalogue, des fichiers préexistants et de toutes les sources, et
l’absence de publication. Les refus avant écriture conservent le conteneur
entier ; une restauration non vérifiable demande de contrôler le volume.

Les 21 tests CPMW, 17 CP/M et 15 gardes de disposition passent, ainsi que
les builds complets et contrôles natifs 65C02/6502. CPMW mesure 7 886 /
7 853 octets, BSS jusqu’à `$3F18` / `$3EF8` inclus, soit 231 / 263 octets
libres sous `$4000`. Les réserves résidentes et MENU restent inchangées ;
aucun plafond n’est relevé.

PASCALW : reconnaître l’image sous une autre casse (11 octobre 2026).

La comparaison sensible à la casse entre le chemin source et le chemin de
l’image pouvait manquer leur identité, alors que ProDOS ignore la casse.
L’image était alors traitée comme un fichier à importer et sa taille faisait
échouer l’opération avec « No room after the last file. », interrompant les
autres imports. Une comparaison ASCII locale ignore maintenant la casse et
compte l’image comme ignorée. Les écritures restent dans l’image confirmée,
sans modification des sources ni utilisation de la mémoire auxiliaire.

Quatre cas exécutent le vrai C avec des chemins de dossier entièrement ou
partiellement en majuscules : image seule inchangée, puis image avec un
fichier distinct dont l’import doit aboutir. Les fichiers existants, les
octets importés et la source sont contrôlés. Ces quatre cas échouaient avant
la correction. Les 26 tests PASCALW, 15 tests Pascal et 15 gardes de
disposition passent ; les deux builds et leurs contrôles mémoire passent.
PASCALW mesure 7 674 / 7 667 octets (65C02 / 6502), avec fin de BSS à
`$3C6A / $3C64`, soit 917 / 923 octets libres dans la fenêtre. Le résident
reste inchangé. Les distributions sont reconstruites et le contrôle 800K
est exécuté. Ce correctif ne change pas les limites des écritures physiques
interrompues et ne prétend pas les rendre atomiques.

PASCALW / CPMW : fermeture du dossier de l’image (11 octobre 2026).

La recherche de la taille de l’image dans `imageio.h` retenait l’entrée
trouvée sans vérifier l’erreur renvoyée à la fermeture du dossier. Les
imports Pascal et CP/M pouvaient donc ouvrir puis modifier l’image après
une erreur de lecture ou de fermeture de ces métadonnées. Ils activent
désormais `IMAGEIO_CHECK_CLOSE` : une erreur invalide la taille trouvée et
arrête l’import avant l’ouverture de l’image. Le retour réel du résident
est récupéré à travers l’API historique typée `void`, comme pour les
énumérations source. Les autres overlays gardent leur code inchangé.

Douze cas du vrai C injectent deux statuts d’erreur sur les conteneurs PO,
2MG et DSK des deux imports. Ils échouaient tous avant la correction :
l’import effectuait des écritures malgré l’erreur. Ils contrôlent maintenant
l’absence d’ouverture et d’écriture de l’image, le conteneur complet
inchangé et les octets des sources. Le cast du retour est aussi exécuté
sous sim65 avec les deux compilateurs et les valeurs 0, 1 et `$27`.
Les écritures possibles restent dans l’image confirmée ; les sources sont
en lecture seule et aucune mémoire auxiliaire n’est utilisée. Le correctif
n’apporte aucune atomicité aux écritures physiques interrompues.

Les 27 tests PASCALW, 22 CPMW, 15 Pascal, 17 CP/M et 15 gardes de disposition
passent, ainsi que les deux builds et contrôles de mémoire. PASCALW mesure
7 680 / 7 675 octets (65C02 / 6502), BSS jusqu’à `$3C70 / $3C6C` inclus,
soit 911 / 915 octets libres. CPMW mesure 7 892 / 7 861 octets, BSS jusqu’à
`$3F1E / $3F00`, soit 225 / 255 octets libres. Le résident et les plafonds
restent inchangés. Les distributions sont reconstruites et les huit tests
800K sont exécutés sur des images jetables.

PASCALW / CPMW : droits ProDOS de l’image (11 octobre 2026).

Les deux imports ouvraient l’image en mise à jour sans vérifier son bit
ProDOS d’écriture. ProDOS autorise cette ouverture puis refuse WRITE :
le fichier restait protégé, mais l’import commençait inutilement et
annonçait un échec d’écriture, voire de restauration pour CP/M, au lieu
d’identifier la protection. `IMAGEIO_CHECK_ACCESS` fait retenir les droits
de l’entrée fraîchement relue pour la taille, sans se fier au panneau.
L’image protégée est ouverte en lecture seule et l’import affiche
« The image is read-only. » avant lecture des sources ou écriture. Le
contrôle de fermeture du dossier reste obligatoire ; le verrou du
conteneur 2MG et le repli après échec d’ouverture sont conservés.

Trente cas du vrai C couvrent cinq droits sans bit d’écriture, les formats
PO/2MG/DSK et les deux imports. Le mock reproduit le refus WRITE de ProDOS
et compte séparément les ouvertures en mise à jour. Les essais avant
correction montrent les tentatives d’écriture et les diagnostics erronés.
Après correction, les conteneurs complets et les sources restent inchangés,
sans tentative d’ouverture en mise à jour ni d’écriture. Six cas vérifient
que le droit d’écriture suffit sans le droit de destruction, avec un
panneau périmé indiquant l’inverse : les nouveaux octets et tous les fichiers
préexistants sont vérifiés. Les seuls fichiers susceptibles d’être écrits
restent les images confirmées ; aucun accès AUX/RAM n’est ajouté. Ce refus
précoce ne rend pas les écritures physiques atomiques face à une coupure.

Les 29 tests PASCALW, 24 CPMW, 15 Pascal, 17 CP/M et 15 gardes de disposition
passent avec les builds et contrôles natifs des deux architectures.
PASCALW mesure 7 713 / 7 707 octets (65C02 / 6502), BSS jusqu’à
`$3C91 / $3C8C` inclus, soit 878 / 883 octets libres. CPMW mesure
7 925 / 7 893 octets, BSS jusqu’à `$3F3F / $3F20`, soit 192 / 223 octets
libres. Le résident et les autres overlays conservent leur code. Les
distributions sont reconstruites et les huit tests 800K passent.

CP/M : arrêter la sélection des secteurs après une erreur d’E/S
(11 octobre 2026).

Le lecteur CP/M traitait un échec de lecture de bloc comme un catalogue
incompatible avec l’ordre de secteurs essayé. Il continuait avec le
candidat suivant : une lecture courte ou une recherche échouée pouvait
être suivie d’une extraction complète, malgré l’erreur initiale. Le wrapper
de lecture mémorise désormais l’échec dans l’indicateur `bad` existant et
la recherche s’arrête immédiatement, avant tout CREATE. Un catalogue
lisible mais incompatible permet toujours d’essayer l’ordre suivant.

Six cas du vrai C injectent une lecture courte, un compte complet avec
erreur du flux ou une recherche échouée, sur chacun des deux premiers
blocs de validation d’une image à secteurs déjà réordonnés. Ils échouaient
tous avant correction : quatre créaient les fichiers après l’erreur,
les deux autres tentaient encore une lecture sous un autre ordre. Les
tests contrôlent maintenant le nombre exact de lectures et de recherches,
zéro CREATE, une seule fermeture et les octets de l’image et du fichier
préexistant dans la destination. Les extractions normales restent vérifiées
pour les deux ordres. L’image est en lecture seule, seuls les fichiers
exclusivement créés dans le dossier opposé peuvent être écrits lors d’une
extraction validée. Aucun accès AUX/RAM n’est ajouté.

Les 18 tests CP/M, 24 CPMW et 15 gardes de disposition passent avec les
builds et contrôles natifs 65C02/6502. CP/M mesure 8 264 / 8 235 octets,
BSS jusqu’à `$3F9D / $3F81` inclus, soit 98 / 126 octets libres sous
`$4000`. L’indicateur réutilisé n’ajoute pas de BSS. Le résident et les
plafonds restent inchangés ; les distributions sont reconstruites et les
huit tests 800K passent.

Pascal / CP/M : métadonnées de l’image avant extraction (11 octobre 2026).

Les extracteurs utilisaient la variante générale de `size_of`, qui retenait
la taille trouvée sans vérifier le statut de fermeture du dossier contenant
l’image. Une erreur de lecture ou de fermeture des métadonnées pouvait
donc être suivie de créations et d’une extraction déclarée réussie. Ils
activent maintenant `IMAGEIO_CHECK_CLOSE`, étendu à cette variante : le
statut réel du résident est récupéré à travers l’API historique typée
`void`, et une erreur refuse l’ouverture de l’image avant tout CREATE.
Les autres consommateurs de la variante générale gardent leur code.

Six cas du vrai C injectent deux statuts d’erreur, pour Pascal et chacun
des deux ordres CP/M. Tous échouaient avant correction avec quatre CREATE.
Ils vérifient désormais zéro CREATE, zéro ouverture de l’image refermée,
la conservation du conteneur entier et les octets d’un fichier préexistant
dans la destination. Les tests CP/M comptent aussi zéro lecture de l’image.
Le cast du retour reste contrôlé sous sim65 pour les deux architectures
par la suite PASCALW. Les images sont uniquement lues ; lors d’une
extraction autorisée, seuls les fichiers exclusivement créés dans le dossier
opposé sont écrits et nettoyés. Aucun accès AUX/RAM n’est ajouté.

Les 16 tests Pascal, 19 CP/M, 29 PASCALW, 24 CPMW et 15 gardes de disposition
passent, ainsi que les deux builds et contrôles natifs. Pascal mesure
7 183 / 7 174 octets (65C02 / 6502), BSS jusqu’à `$3A23 / $3A1B` inclus,
soit 1 500 / 1 508 octets libres. CP/M mesure 8 263 / 8 236 octets,
BSS jusqu’à `$3F9C / $3F82`, soit 99 / 125 octets libres. Le résident,
les importeurs et les plafonds restent inchangés. Les distributions sont
reconstruites et les huit tests 800K passent.

CP/M : attributs distincts entre les extents (11 octobre 2026).

La mesure du fichier et la recherche de ses extents comparaient les onze
octets bruts du nom, alors que leur bit 7 porte des attributs. Deux extents
du même fichier avec un attribut différent étaient donc séparés : la
première partie était extraite comme un fichier complet, et la suivante
pouvait être ignorée comme un nom déjà pris. Le fichier extrait était
tronqué sans diagnostic d’échec. Une comparaison locale masque maintenant
le bit 7 pour les deux recherches ; le contrôle du numéro utilisateur et
les caractères du nom restent distinctifs.

Douze cas du vrai C changent un seul attribut (lecture seule, système ou
archive) dans le premier ou le second extent d’un fichier de plus de
16 KiB, pour chacun des deux ordres de secteurs. Tous échouaient avant la
correction. Ils comparent l’ensemble des fichiers extraits, octet par octet,
avec l’oracle qui regroupe déjà les noms sans les bits d’attributs ; ils
contrôlent aussi les quatre créations, l’absence de faux doublon et les
octets du fichier préexistant dans la destination. L’image entière reste
inchangée. Les tests existants continuent de vérifier les noms distincts,
les erreurs d’E/S et la suppression des seuls fichiers créés par l’opération.
Seuls ces nouveaux fichiers ProDOS sont écrits ; aucun accès AUX/RAM
n’est ajouté.

Les 20 tests CP/M, 24 CPMW et 15 gardes de disposition passent avec les
builds et contrôles natifs 65C02/6502. CP/M mesure 8 327 / 8 282 octets,
BSS jusqu’à `$3FDD / $3FB1` inclus, soit 34 / 78 octets libres sous
`$4000`. Le résident et les plafonds restent inchangés. Les distributions
sont reconstruites et les huit tests 800K passent.

BLKVIEW : erreurs de flux au compte complet (11 octobre 2026).

Les lectures normalisées du visualiseur acceptaient un compte complet
malgré une erreur du flux source. Une recherche pouvait annoncer un
résultat et une extraction copier les blocs puis annoncer un succès.
Un wrapper local vérifie désormais `ferror` avant d’utiliser un bloc de
l’image, dans l’affichage, la recherche et l’extraction. Les périphériques
n’ont pas de `FILE` : leur statut MLI suffit et aucun `ferror(NULL)` n’est
appelé. L’image et le périphérique restent en lecture seule ; seuls les
blocs précédemment validés peuvent être conservés dans la sortie créée
exclusivement. L’erreur est signalée comme extraction incomplète. Aucun
accès AUX/RAM n’est ajouté.

Pour tenir sous l’API fixe, BLKVIEW utilise désormais `IMAGEIO_ONE` pour
son unique source, image ou périphérique : la recherche de taille réutilise
son chemin au lieu de conserver les deux copies de la variante générale.
Les gardes de disposition restent actives. Dix-huit cas du vrai C injectent
une erreur avec compte complet dans les trois premiers appels de lecture,
pour PO, DSK et 2MG, en recherche et en extraction. Tous échouaient avant
correction. Ils vérifient l’arrêt et les octets exacts du préfixe conservé,
sans copier le bloc en erreur, ainsi que le conteneur entier inchangé.
Trois cas supplémentaires ouvrent réellement les images par `image_open`
et contrôlent des secteurs distincts en ordre normalisé ; deux cas lisent
un périphérique sans flux fichier, avec succès ou erreur MLI.

Les 17 tests BLKVIEW, 33 BLKEDIT et 15 gardes de disposition passent avec
les builds et contrôles natifs 65C02/6502. BLKVIEW mesure 8 698 / 8 746
octets, BSS jusqu’à `$3E0D / $3E3E` inclus, soit 400 / 351 octets libres
avant l’API fixe à `$3F9E`. Le résident, BLKEDIT et les plafonds restent
inchangés. Les distributions sont reconstruites et les huit tests 800K
passent sur des images jetables.

BLKEDIT : compte complet et erreurs de flux (11 octobre 2026).

L’éditeur pouvait accepter une lecture ou une écriture d’image au compte
complet malgré une erreur du flux, ensuite effacée au bloc suivant par
`clearerr`. Le bloc pouvait être déclaré écrit et vérifié, même si son
identité, l’écriture ou la relecture n’avaient pas été validées. Un wrapper
local contrôle maintenant chaque transfert avant cet effacement. Les
périphériques continuent d’utiliser le statut MLI sans `FILE`. L’en-tête
2MG, lu hors des blocs, est contrôlé avant la première lecture normalisée.
Une autre erreur était ignorée après écriture du bloc d’identité : l’échec
de son renouvellement est maintenant signalé, sans effacer le statut dirty.

Vingt et un cas du vrai C injectent des erreurs au compte complet dans
l’en-tête, l’identité, le bloc édité, le contrôle avant écriture, l’écriture
et la relecture, pour PO, DSK et 2MG. Seize annonçaient un succès avant
correction ; les cinq autres contrôlent les refus déjà obtenus lorsqu’une
première moitié DSK bloquait la seconde. Quatre cas supplémentaires
reproduisent l’erreur ignorée pendant le renouvellement de l’identité.
Les tests comparent le conteneur entier, vérifient zéro écriture avant une
lecture validée et, après une écriture non entièrement validée, le maintien
de l’avertissement de perte de l’édition au départ. Le mock reproduit
`clearerr` entre blocs et le refus d’un flux en erreur par cc65.

La seule écriture possible reste le bloc explicitement confirmé par ERASE,
dans l’image ou le périphérique sélectionné. L’édition et la relecture
utilisent MAIN ; aucun accès AUX/RAM n’est ajouté. Une erreur après
écriture ne restaure pas automatiquement l’ancien bloc : les écritures
brutes demeurent destructrices et ne sont pas atomiques face à une coupure.

Les 35 tests BLKEDIT, 17 BLKVIEW et 15 gardes de disposition passent avec
les builds et contrôles natifs 65C02/6502. BLKEDIT mesure 8 402 / 8 363
octets, BSS jusqu’à `$3EC3 / $3E9D` inclus, soit 218 / 256 octets libres
avant l’API fixe à `$3F9E`. Le résident et les plafonds restent inchangés.
Les distributions sont reconstruites et les huit tests 800K passent.

BLKEDIT / IMGPUT : fermeture du dossier contenant l’image
(11 octobre 2026).

Ces deux chemins d’écriture retenaient encore la taille de l’image après
une erreur de lecture ou de fermeture du dossier qui la contient. Le
contrôle existant `IMAGEIO_CHECK_CLOSE` est désormais activé : une erreur
invalide les métadonnées avant l’ouverture du fichier image. BLKEDIT refuse
de commencer l’édition et IMGPUT refuse avant sa demande de confirmation.
Les autres chemins et les gardes du catalogue ProDOS restent inchangés.

Douze cas du vrai C injectent les statuts 1 et `$1B` à la fermeture du
dossier, pour PO, DSK et 2MG dans les deux overlays. Tous modifiaient
l’image avant correction. Ils vérifient maintenant le conteneur complet
inchangé et zéro écriture ; BLKEDIT vérifie aussi zéro lecture d’image et
aucun avertissement de perte d’édition, IMGPUT l’absence de confirmation
et les octets de la source conservés. Les images d’essai sont jetables.

BLKEDIT ne peut écrire que le bloc choisi après ERASE ; IMGPUT peut écrire
les blocs libres, les index, la bitmap et le catalogue de l’image confirmée.
Ce refus arrive avant ces écritures. Les sources restent en lecture seule,
sans accès AUX/RAM. Il ne change pas les limites des écritures physiques
interrompues ni leur absence d’atomicité.

Les 36 tests BLKEDIT, 59 IMGPUT, 17 BLKVIEW et 15 gardes de disposition
passent avec les builds et contrôles natifs 65C02/6502. BLKEDIT mesure
8 401 / 8 364 octets, BSS jusqu’à `$3EC2 / $3E9E` inclus, soit 219 / 255
octets libres avant l’API fixe à `$3F9E`. IMGPUT mesure 8 059 / 8 027
octets, BSS jusqu’à `$3FFD / $3FDE`, soit 2 / 33 octets libres sous `$4000`.
Le résident et les plafonds restent inchangés ; aucun garde n’est désactivé.
Les distributions sont reconstruites et les huit tests 800K passent.

IMGPUT : erreurs au compte complet dans l’image (11 octobre 2026).

Une lecture ou une écriture d’image au compte complet pouvait porter une
erreur du flux sans être refusée. Le bloc suivant effaçait cette erreur
avec `clearerr`, et IMGPUT pouvait annoncer « Copied into the image ».
`IMAGEIO_CHECK_STREAM` vérifie désormais chaque transfert avant le suivant,
y compris chaque moitié DSK, ainsi que l’en-tête 2MG avant la première
lecture normalisée. Cette option ne change aucun autre overlay.

Pour financer les contrôles, l’entrée ProDOS de 39 octets est construite
dans `idx` après écriture et attribution de l’index sapling : à cet instant
son contenu mémoire n’est plus nécessaire. Le nom reste dans le snapshot
résident de l’entrée sélectionnée pendant les recherches ; l’entrée est
copiée dans `dirb` avant que la vérification réutilise `idx`. Les contrôles
de disposition restent actifs et le résident n’est pas modifié.

La régression injecte une erreur avec compte complet à chacun des 117
points de lecture/écriture d’une copie normale, pour PO, DSK et 2MG, avec
deux fichiers préexistants. Sans le contrôle, les 117 cas annoncent une
copie réussie ; avec lui, aucun ne l’annonce. Chaque cas compare les
entrées et les octets des deux anciens fichiers, ainsi que la source
ProDOS entière. Les tests existants vérifient aussi l’allocation, les
index, les collisions, les catalogues malformés et les erreurs partielles.
Le mock reproduit l’effacement de l’erreur entre blocs. Les seules
écritures restent les blocs libres, l’index, la bitmap et le catalogue de
l’image confirmée, sans accès AUX/RAM. Une erreur tardive peut laisser des
blocs attribués ou une entrée déjà publiée : le diagnostic demande de
contrôler l’image. Le correctif ne rend pas ces écritures atomiques.

Les 60 tests IMGPUT, 36 BLKEDIT et 15 gardes de disposition passent avec
les builds et contrôles natifs 65C02/6502. IMGPUT mesure 8 094 / 8 066
octets, BSS jusqu’à `$3FF9 / $3FDE` inclus, soit 6 / 33 octets libres
sous `$4000`. Les plafonds restent inchangés ; les distributions sont
reconstruites et les huit tests 800K passent sur des images jetables.

IMGPUT : fermeture finale de l’image (11 octobre 2026).

Le résultat était affiché avant la fermeture de l’image, dont le statut
était ignoré. Une erreur de fermeture pouvait donc laisser « Copied into
the image » comme résultat. IMGPUT ferme désormais l’image avant de publier
le résultat et remplace celui-ci par « Close failed. » si la fermeture
échoue. La fermeture est unique ; `image_open` réinitialise le pointeur au
prochain appel. Le résident et la mémoire auxiliaire ne sont pas modifiés.

La régression exécute le vrai C sur neuf cas PO/DSK/2MG : copie complète,
confirmation refusée et erreur de fermeture de la source avant écriture.
Les neuf cas échouaient avant correction. Chaque cas compare la source
entière et les entrées et données de deux fichiers préexistants. Après une
copie complète, le fichier importé reste présent avec ses octets exacts ;
dans les deux refus, l’image entière reste identique. Une fermeture en
erreur rend la persistance incertaine : ce diagnostic ne garantit ni
restauration de l’image ni atomicité des écritures physiques.

Les 61 tests IMGPUT et 15 gardes de disposition passent. Les builds et
contrôles natifs 65C02/6502 passent avec IMGPUT à 8 096 / 8 067 octets,
BSS jusqu’à `$3FFB / $3FDF` inclus : 4 / 32 octets libres sous `$4000`,
sans modification des plafonds. Les distributions sont reconstruites et
les huit tests 800K passent sur des images jetables.

BLKEDIT : permissions fraîches de l’image (11 octobre 2026).

BLKEDIT utilisait le bit d’écriture du snapshot du panneau après ouverture
de l’image. Une image verrouillée depuis la lecture du panneau était donc
ouverte pour mise à jour et atteignait ERASE puis une tentative d’écriture ;
ProDOS peut accepter OPEN et ne refuser que WRITE. Inversement, une image
déverrouillée restait refusée. L’éditeur active `IMAGEIO_CHECK_ACCESS`, et
la forme générale de `size_of` relève maintenant les permissions fraîches
dans le même catalogue que la taille. L’image protégée s’ouvre avec `rb`,
et le contrôle périmé du panneau est supprimé. Une erreur de fermeture du
catalogue invalide toujours ces métadonnées. Les autres overlays conservent
leurs branches conditionnelles ; les protections du conteneur 2MG restent
prises en compte après celles du fichier.

Le vrai C reproduisait 18 échecs sur PO/DSK/2MG : cinq valeurs d’accès sans
écriture face à un panneau autorisant l’écriture, puis une image autorisée
face à un panneau verrouillé. Les régressions comparent l’image entière,
le nombre d’écritures, le mode d’ouverture et la présence du prompt ERASE.
Les images protégées restent identiques, sans WRITE ni prompt ERASE ; les
images déverrouillées ne changent que l’octet confirmé du bloc édité. Le
mock de fermeture du premier harness renvoie aussi explicitement le statut
réel attendu par le résident, au lieu d’appeler une fonction void par un
type retournant un octet.

Les 37 tests BLKEDIT, 29 PASCALW, 24 CPMW, 61 IMGPUT et 15 gardes de
disposition passent. Les builds et contrôles natifs 65C02/6502 passent :
BLKEDIT mesure 8 407 / 8 367 octets, BSS jusqu’à `$3EC8 / $3EA1` inclus,
soit 213 / 252 octets libres avant l’API fixe à `$3F9E`. Les seules
écritures restent celles du bloc confirmé, sans accès AUX/RAM ; elles ne
deviennent pas atomiques. Les plafonds sont inchangés. Les distributions
sont reconstruites et les huit tests 800K passent sur des images jetables.

BLKVIEW : fermeture du catalogue de l’image (11 octobre 2026).

Le lecteur relevait la taille de l’image dans son catalogue, mais ignorait
le statut de fermeture de ce catalogue. Une erreur de parcours ou de
fermeture pouvait donc laisser des métadonnées incertaines autoriser
l’ouverture puis l’extraction. BLKVIEW active maintenant
`IMAGEIO_CHECK_CLOSE` : ces erreurs invalident la taille avant l’ouverture
du flux et avant toute demande ou création de fichier de destination.
Le diagnostic reste « Invalid or unreadable image. ».

Un nouveau harness exécute `plugin_entry`, la navigation et l’extraction
du vrai C. Les 12 cas d’erreur combinent PO/DSK/2MG, les statuts 1 et 27,
et une destination absente ou déjà présente. Tous poursuivaient jusqu’à
une tentative de CREATE avant correction ; désormais aucun n’ouvre
l’image, ne la lit, ne pose la question d’extraction ni ne tente CREATE.
Chaque cas compare l’image entière et les fichiers préexistants ; aucune
destination absente n’est créée. Trois témoins sans erreur vérifient aussi
les 512 octets extraits en ordre normalisé. Le mock du harness d’ouverture
renvoie désormais explicitement zéro pour une fermeture réussie, comme
le résident derrière le type void figé de l’API.

Les 19 tests BLKVIEW et 15 gardes de disposition passent, ainsi que les
builds et contrôles natifs 65C02/6502. BLKVIEW mesure 8 707 / 8 757 octets,
BSS jusqu’à `$3E16 / $3E49` inclus, soit 391 / 340 octets libres avant
l’API fixe à `$3F9E`. Le résident et les plafonds ne changent pas. Les
seules écritures possibles restent celles d’une destination créée
exclusivement par l’extraction ; aucune écriture de l’image source ou
d’AUX/RAM n’est introduite. Les distributions sont reconstruites et les
huit tests 800K passent sur des images jetables. Une extraction interrompue
peut toujours conserver son fichier partiel ; ce contrôle ne rend pas
les écritures physiques atomiques.

BLKVIEW : fermeture finale de la source (11 octobre 2026).

La sortie du lecteur utilisait `source_close`, qui ignorait le statut
de fermeture du flux de l’image. Une erreur restait donc silencieuse après
consultation ou extraction. BLKVIEW ferme désormais ce flux une seule fois,
contrôle le statut et publie « BLKVIEW: source close failed. » en cas
d’erreur. Les fichiers déjà extraits sont conservés ; aucune restauration
ni suppression n’est ajoutée. Le pointeur est remis à zéro, et une session
sur périphérique, sans FILE, ne tente aucune fermeture.

Le harness de `plugin_entry` injecte l’erreur finale dans neuf cas
PO/DSK/2MG, après consultation seule, extraction ou collision de nom.
Tous avaient un diagnostic vide avant correction. Chaque cas compare
l’image entière, un fichier témoin et, selon le cas, la destination
préexistante ou les 512 octets extraits. Une destination absente reste
absente après simple consultation. Le compteur vérifie une fermeture
unique. Un témoin supplémentaire parcourt le vrai chemin périphérique
avec deux READ_BLOCK MLI, sans ouvrir ni fermer de flux de fichier.

Les 21 tests BLKVIEW et 15 gardes de disposition passent, ainsi que les
builds et contrôles natifs 65C02/6502. BLKVIEW mesure 8 720 / 8 769 octets,
BSS jusqu’à `$3E23 / $3E55` inclus : 378 / 328 octets libres avant l’API
fixe à `$3F9E`. Le résident et les plafonds restent inchangés. Les seules
écritures demeurent celles de la destination exclusivement créée pour
l’extraction, sans modification de la source ou d’AUX/RAM. Le diagnostic
ne promet aucune atomicité des écritures physiques. Les distributions
sont reconstruites et les huit tests 800K passent sur des images jetables.

IMGPUT : protection du fichier contenant l’image (11 octobre 2026).

IMGPUT contrôlait les protections du volume contenu, de son répertoire
destination et du conteneur 2MG, mais pas celles du fichier image lui-même.
ProDOS peut accepter OPEN pour mise à jour sur un fichier verrouillé et
ne refuser que WRITE. L’importeur active désormais `IMAGEIO_REQUIRE_WRITE`
dans la recherche de taille : un bit d’écriture absent invalide l’ouverture
avant le flux, la confirmation et toute écriture. Le diagnostic est
« Cannot open the image. ». L’option exige à la compilation la forme
`IMAGEIO_ONE` d’un écrivain. La recherche s’arrête à l’entrée trouvée,
même si ses permissions interdisent l’écriture ; une erreur de fermeture
du catalogue continue d’invalider le résultat.

Les 15 cas d’erreur combinent PO/DSK/2MG avec cinq valeurs d’accès sans
écriture. Avant correction, les copies atteignaient les écritures ; après,
aucune image n’est ouverte, aucune confirmation n’est demandée, et l’image
entière et la source restent identiques. Trois témoins autorisés extraient
les octets importés avec l’oracle ProDOS et comparent aussi les entrées et
les données de deux fichiers préexistants.

Pour conserver les gardes mémoire, `image_open` n’initialise plus le numéro
de périphérique quand `IMAGEIO_NODEVICE` exclut tous ses usages. Le type
de l’image est affecté après reconnaissance de l’extension, avant toute
lecture, au lieu d’être initialisé deux fois. La recherche de catalogue
utilise un break après correspondance plutôt qu’un test du drapeau à
chaque itération. IMGPUT stocke la longueur du nom dans l’octet `src.unit`
ainsi inutilisé et préservé par l’ouverture file-only ; son BSS perd un
octet sans modifier les buffers ni leur durée de vie. Aucun changement
du résident, des plafonds ou d’AUX/RAM n’est introduit.

Les 62 tests IMGPUT, 29 PASCALW, 24 CPMW, 21 BLKVIEW, 37 BLKEDIT,
16 PASCAL, 20 CPM et 15 gardes de disposition passent avec les builds
et contrôles natifs 65C02/6502. IMGPUT mesure 8 101 / 8 073 octets,
BSS jusqu’à `$3FFF / $3FE4` inclus : **0 / 27 octets libres** sous
`$4000`. L’overlay 65C02 remplit exactement son espace ; tout ajout devra
libérer de la place et repasser les contrôles. Les écritures restent celles
des blocs libres, de l’index, de la bitmap et du catalogue de l’image
confirmée, sans garantie d’atomicité physique. Les distributions sont
reconstruites et les huit tests 800K passent sur des images jetables.

SCIIBIN : annulation pendant la fermeture de vérification (11 octobre 2026).

`read_back` contrôlait ESC avant les lectures et après la dernière mise à
jour de progression, puis fermait le flux sans recontrôler l’annulation.
ESC arrivé pendant cette fermeture pouvait donc laisser un diagnostic de
décodage réussi. La fonction contrôle désormais `stop()` après une
fermeture réussie avant de valider le résultat. Une fermeture en erreur
reste un échec ; aucun second CLOSE n’est ajouté. Le nettoyage existant
reste limité au fichier créé exclusivement par cette opération.

La régression exécute le vrai C avec trois tailles, dont un décodage sur
plusieurs segments, et trois variantes : ESC seul à la fermeture finale,
ESC avec suppression refusée, ESC avec fermeture en erreur. Six des neuf
cas annonçaient une réussite avant correction ; les trois autres étaient
déjà refusés grâce au statut de fermeture. Les neuf cas vérifient une
fermeture unique au bout de tous les octets, la tentative de nettoyage de
la seule sortie créée, les sources complètes et un fichier préexistant.
Quand la suppression échoue, la sortie entière reste présente avec ses
octets exacts et le diagnostic de nettoyage en erreur.

Les 11 tests SCIIBIN, dont le calcul CRC sous sim65 pour les deux
architectures, et les 15 gardes de disposition passent. Les builds et
contrôles natifs 65C02/6502 passent avec SCIIBIN à 6 532 / 6 552 octets,
BSS jusqu’à `$3FD6 / $3FEB` inclus : 41 / 20 octets libres sous `$4000`.
Le résident et les plafonds ne changent pas. Aucune écriture des sources,
des destinations préexistantes ou d’AUX/RAM n’est ajoutée. Le correctif
ne rend pas les écritures physiques atomiques. Les distributions sont
reconstruites et les huit tests 800K passent sur des images jetables.

UNSQ : erreurs de création distinctes des doublons (11 octobre 2026).

`one` traitait toute erreur de CREATE comme un nom déjà pris, incrémentait
le compteur de fichiers ignorés et poursuivait l’archive. Un disque plein,
un accès refusé ou une erreur d’E/S pouvait donc laisser « name taken »
et autoriser d’autres créations après une erreur. Le code distingue
désormais le seul doublon `$47` : les autres statuts arrêtent l’extraction
avant toute ouverture ou suppression de la destination en erreur. `bad=2`
identifie ce refus pour publier « create failed, stopped. » ; il ne
diagnostique pas une archive endommagée. Les fichiers déjà vérifiés restent
présents. Les règles de filtrage des noms non représentables et des types
non pris en charge ne changent pas.

Les 12 injections exécutent le vrai C sur un SQueezed autonome et une
archive ACU, au premier fichier ou après un fichier déjà vérifié. Elles
couvrent les statuts `$27/$48/$4E` et une destination créée entre-temps
avant un retour CREATE en erreur. Avant correction, ces cas étaient ignorés
et l’archive pouvait continuer ; après, le compteur d’appels CREATE
s’arrête exactement au refus. Les sources entières, le fichier témoin,
la première sortie vérifiée et les octets de la destination apparue sont
comparés ; aucune suppression n’est tentée et aucun fichier suivant
n’est créé. Un témoin de vraies collisions vérifie que l’extraction
continue pour l’entrée libre et préserve tous les anciens fichiers.

Les 19 tests UNSQ et 15 gardes de disposition passent, ainsi que les
builds et contrôles natifs 65C02/6502. UNSQ mesure 6 983 / 7 060 octets,
BSS jusqu’à `$3E72 / $3EC0` inclus, soit 397 / 319 octets libres sous
`$4000`. Aucun buffer, résident, plafond ou accès AUX/RAM n’est ajouté.
Les seules écritures restent celles des fichiers créés exclusivement
par l’extraction ; un CREATE en erreur ne donne aucun droit de nettoyage
sur sa cible. Le correctif ne garantit pas l’atomicité des écritures
physiques. Les distributions sont reconstruites et les huit tests 800K
passent sur des images jetables.

UNSQ : annulation pendant la fermeture finale de l’archive (11 octobre 2026).

La fermeture finale du flux source était contrôlée pour les erreurs d’E/S,
mais pas pour ESC arrivé pendant cet appel. Une extraction complète ou une
archive vide pouvait donc garder un résultat de réussite malgré une
annulation. UNSQ appelle maintenant `stop()` après cette fermeture et
invalide le résultat complet. Le diagnostic d’archive endommagée sans
sortie exclut explicitement une annulation : une archive vide interrompue
reste « stopped ». Une erreur d’E/S garde son diagnostic prioritaire.
Les fichiers déjà vérifiés restent conservés, sans nouvelle suppression,
seconde fermeture ou écriture de la source et d’AUX/RAM.

Les dix injections exécutent le vrai C : SQueezed autonome, ACU avec deux
sorties dont une vide, ACU vide, nom déjà pris et type `$0F` ignoré, chacun
avec ESC seul ou ESC et fermeture en erreur. Les cinq cas avec ESC seul
annonçaient encore une réussite avant correction ; les autres étaient
déjà refusés grâce au statut d’E/S. Les régressions comparent les octets
de l’archive source, des fichiers déjà extraits et des destinations
préexistantes, vérifient une fermeture source unique et l’absence de
toute tentative de suppression.

Les 20 tests UNSQ et 15 gardes de disposition passent avec les builds et
contrôles natifs 65C02/6502. UNSQ mesure 6 997 / 7 076 octets, BSS jusqu’à
`$3E80 / $3ED0` inclus, soit 383 / 303 octets libres sous `$4000`. Le
résident, les buffers et les plafonds restent inchangés. Les écritures
physiques des sorties ne deviennent pas atomiques. Les distributions
sont reconstruites et les huit tests 800K passent sur des images jetables.

SCIIBIN : liste de parties incertaine (11 octobre 2026).

`list_parts` gardait le fichier sélectionné comme première partie même
quand l’ouverture du catalogue échouait, quand sa lecture s’interrompait
ou quand sa fermeture signalait une erreur. Elle ignorait également
l’absence de l’entrée sélectionnée dans le catalogue frais. Le décodage
pouvait donc commencer et créer une sortie avec une liste incertaine.
La fonction retourne désormais un statut : ouverture réussie, entrée
sélectionnée retrouvée et fermeture sans erreur de lecture ni de CLOSE.
Le statut renvoyé par le résident est lu à travers le type void figé de
l’API. La fermeture reste unique et obligatoire après une ouverture,
même quand l’entrée sélectionnée n’a pas été rencontrée. Un refus publie
« Directory unreadable. » avant toute ouverture de source ou création.

Les 14 injections exécutent le vrai C sur un décodage en une partie et
un décodage en plusieurs parties : ouverture refusée, lecture interrompue
avant ou après l’entrée sélectionnée ou après la partie suivante, deux
statuts de fermeture et sélection absente du catalogue. Les 14 cas
créaient une sortie avant correction ; aucun ne commence maintenant
le décodage. Les sources et fichiers préexistants sont comparés en entier,
aucune création ou suppression n’a lieu, et les compteurs vérifient zéro
ou une fermeture de catalogue selon que l’ouverture a échoué ou réussi.

Pour conserver les plafonds, la table d’alphabet passe de 256 à 128 octets,
avec un effacement utilisant `sizeof table`. Toutes ses lectures et
écritures indexent `line`, dont `next_line` supprime systématiquement le
bit 7 avant stockage. La table CRC à 256 entrées reste entière. Quatre
témoins décodent trois segments avec l’alphabet normal ou DEL à l’index
127, avec ou sans bit haut sur tous les caractères et fins de ligne.
Les octets décodés sont comparés au payload entier ; l’oracle Python ne
sert pas pour les fins de ligne à bit haut, qu’il coupe avant normalisation.

Les 13 tests SCIIBIN, les 29 PASCALW comprenant le contrôle du statut de
fermeture via l’API sous sim65 pour les deux processeurs, et les 15 gardes
de disposition passent. Les builds et contrôles natifs 65C02/6502 passent :
SCIIBIN mesure 6 583 / 6 601 octets, BSS jusqu’à `$3F89 / $3F9C` inclus,
soit 118 / 99 octets libres sous `$4000`. Le résident et les plafonds ne
changent pas ; aucun accès AUX/RAM n’est ajouté. Les seules écritures et
nettoyages possibles restent ceux de la sortie exclusivement créée par
le décodage, sans garantie d’atomicité physique. Les distributions sont
reconstruites et les huit tests 800K passent sur des images jetables.

IMGCONV : annulation après la dernière lecture de vérification (11 octobre 2026).

La vérification contrôlait ESC avant chaque bloc, mais pas après la sonde
EOF et les fermetures finales des deux flux. ESC pendant ces étapes
pouvait donc laisser installer la conversion à la place de l’ancienne
destination. `verify_output` contrôle maintenant le clavier après les
deux fermetures, acquitte ESC et invalide le résultat avant tout renommage.
Le chemin d’échec existant nettoie uniquement le temporaire créé par
l’opération ; la source et l’ancienne destination restent intactes. Une
erreur de nettoyage conserve le temporaire vérifié et son diagnostic.

Les 30 injections exécutent le vrai C sur PO vers 2MG, PO vers DSK,
DSK vers PO, 2MG vers PO, PO vers DiskCopy et DiskCopy vers PO. Elles
couvrent ESC à la fermeture de chaque flux de vérification, à la sonde
EOF de la destination, ESC avec nettoyage refusé et ESC avec fermeture
en erreur. Avec le contrôle final retiré d’une copie temporaire du C,
24 cas installent la conversion malgré ESC ; les six erreurs de fermeture
étaient déjà refusées. Avec le contrôle, les 30 cas ferment les quatre
flux ouverts, ne font aucun renommage, ne créent aucune sauvegarde et
préservent la source et l’ancienne destination octet pour octet. Les
temporaires retenus sont comparés entièrement à une conversion indépendante,
y compris les en-têtes et sommes DiskCopy. Les secteurs des fixtures
diffèrent pour rendre une mauvaise permutation visible.

Pour financer le contrôle sous les plafonds, l’index de comparaison de
demi-bloc passe à un octet, parcouru par un do/while jusqu’à son retour
à zéro : les 256 octets, dont l’index 255, sont toujours contrôlés. Deux
régressions injectent une corruption dans le dernier octet de chaque
demi-bloc de la lecture de vérification et vérifient le refus d’installation.
Le compteur perd aussi un octet de BSS, sans réduire le tampon de 256
octets ni la quantité de données vérifiée. Aucun accès AUX/RAM n’est ajouté.

Les 25 tests IMGCONV et 15 gardes de disposition passent avec les builds
et contrôles natifs 65C02/6502. IMGCONV mesure 8 798 / 8 964 octets,
BSS jusqu’à `$3F46 / $3FED` inclus, soit 185 / 18 octets libres sous
`$4000`. Le résident et les plafonds restent inchangés. Les distributions
sont reconstruites et les huit tests 800K passent sur des images jetables.
La protection de l’original pendant cette annulation ne rend pas les
écritures physiques ou les renommages ProDOS atomiques lors d’une coupure.

## MKIMAGE : annulation après la dernière fermeture (11 octobre 2026)

Une annulation arrivée à la lecture de l’EOF de vérification ou pendant
la fermeture finale pouvait être ignorée et l’image annoncée comme créée.
MKIMAGE contrôle désormais ESC après cette fermeture, avant de décider
du succès. Seule l’image réservée par création exclusive est supprimée ;
si sa suppression échoue, elle reste en place avec le diagnostic de
nettoyage. Les écritures concernent ce fichier et les tampons MAIN,
sans accès AUX ni modification de `/RAM`.

Le vrai point d’entrée C est testé avec 16 scénarios : PO et 2MG, 140K
et 800K, annulation à l’EOF, à la fermeture, fermeture en erreur ou
nettoyage en erreur. Douze annonçaient une création avant la correction.
Les fichiers retenus après un échec de nettoyage sont comparés entièrement
au résultat normal et une nouvelle tentative doit préserver leurs octets.
Chaque scénario contrôle aussi une collision avec un fichier préexistant.

Les six tests MKIMAGE, les 64 tests des overlays partagés et les 15 gardes
de disposition passent. Builds et contrôles natifs 65C02/6502 valides :
MKIMAGE mesure 4 684 / 4 784 octets, BSS jusqu’à `$3076 / $30DB`
inclus, soit 3 977 / 3 876 octets libres sous `$4000`. Le résident et
les plafonds restent inchangés. Distributions reconstruites et huit tests
800K validés sur les images de distribution. Ce contrôle ne garantit pas
le nettoyage du fichier lors d’une coupure pendant une écriture physique.

## TXTCONV : annulation avant le remplacement (11 octobre 2026)

ESC reçu pendant la lecture finale de vérification ou l’une des deux
fermetures pouvait laisser renommer l’original puis annoncer le succès.
Le contrôle clavier est désormais partagé entre la boucle de conversion
et la sortie après les deux fermetures, avant toute installation. Une
annulation nettoie uniquement le fichier créé exclusivement par cette
opération. Source, ancienne destination et sauvegardes préexistantes
restent intactes ; les tampons utilisés sont en MAIN, sans accès AUX/RAM.

Le vrai point d’entrée C couvre 45 scénarios : conversion sur place,
remplacement dans l’autre panneau ou nouvelle destination, textes de
0, 256 et 800 octets, ESC au contrôle d’EOF, à la fermeture source ou
destination, avec erreur de fermeture ou de nettoyage. Avant correction,
36 scénarios remplaçaient l’original ou annonçaient un succès. Après
correction, les quatre flux sont fermés et aucun renommage ne commence.
Les octets des deux originaux et d’un fichier tiers sont contrôlés ; les
résultats conservés après un nettoyage en erreur sont comparés entièrement
à la conversion attendue puis protégés lors d’une nouvelle tentative.

Les 26 tests TXTCONV et 15 gardes de disposition passent. Builds et
contrôles natifs 65C02/6502 valides : TXTCONV mesure 6 105 / 6 143
octets, BSS jusqu’à `$352A / $3551` inclus, soit 2 773 / 2 734 octets
libres sous `$4000`. Le résident et les plafonds restent inchangés.
Distributions reconstruites et huit tests 800K validés. Les renommages
et écritures ProDOS restent non atomiques en cas de coupure physique.

## RESCUE : taille refusée si le catalogue est en erreur (11 octobre 2026)

La recherche de taille courante trouvait l’entrée sélectionnée mais ignorait
le statut renvoyé par la fermeture du catalogue. Une erreur de lecture
différée ou de fermeture pouvait donc valider cette taille et déclencher
la création du journal et de la récupération. RESCUE lit désormais ce
statut via le retour octet du résident, malgré la déclaration void de
l’API figée, et refuse avant toute création ou confirmation en cas d’erreur.
La source reste en lecture seule ; seuls les fichiers exclusivement créés
de récupération et de journal sont normalement écrits, avec des tampons
MAIN. Aucun accès AUX/RAM n’est ajouté.

Le vrai point d’entrée C couvre 36 scénarios de catalogue : ouverture
impossible, erreur de lecture, entrée absente, fermetures en erreur `$27`
ou `$01`, et erreur différée malgré une entrée renvoyée. Sources de
0, 100 et 1 600 octets, avec ou sans anciens fichiers de récupération.
Avant correction, 18 scénarios continuaient au-delà de la recherche.
Après correction, aucun flux fichier n’est ouvert, aucun CREATE ni aucune
confirmation n’est appelé ; le catalogue ouvert est fermé exactement une
fois. Tous les fichiers préexistants sont comparés octet pour octet.

Les 11 tests RESCUE, 29 tests PASCALW (dont le retour natif de l’API figée
sur les deux processeurs) et 15 gardes de disposition passent. Builds et
contrôles natifs 65C02/6502 valides : RESCUE mesure 6 853 / 6 925 octets,
BSS jusqu’à `$379B / $37E4` inclus, soit 2 148 / 2 075 octets libres
sous `$4000`. Le résident et les plafonds restent inchangés. Distributions
reconstruites et huit tests 800K validés. La récupération reste une copie
au mieux avec journal des manques, sans garantie d’atomicité physique.

## RESCUE : annulation pendant la clôture et statut du journal (11 octobre 2026)

ESC reçu pendant la dernière lecture, la fermeture de la sortie ou de la
source, ou l’écriture/fermeture du journal pouvait être ignoré et annoncer
une récupération complète. RESCUE contrôle désormais ESC après la fermeture
source, avant la ligne COMPLETE, puis après la clôture de cette ligne.
En cas d’annulation tardive, les octets récupérés restent en place et une
ligne INCOMPLETE termine le journal. Si cette ligne ne peut pas être ajoutée,
l’interface annonce explicitement « log update failed » : une ancienne
ligne COMPLETE peut alors rester la dernière sur disque. Le code ne promet
pas une correction du journal qu’une erreur d’I/O empêche d’écrire.

Le vrai point d’entrée C couvre 75 scénarios de fin de récupération :
sources fichiers de 0, 1, 512 et 1 600 octets et volumes jetables de
3, 7 et 280 blocs ; ESC à l’EOF, à la fermeture source/sortie, pendant
l’écriture COMPLETE ou à sa fermeture, avec erreurs de flux/fermeture
combinées. Le journal INCOMPLETE est aussi soumis à un échec d’ouverture,
une erreur après écriture complète ou un échec de fermeture. Avant les
contrôles, 29 scénarios annonçaient le succès malgré ESC ; les 21 cas de
journal non fiable ne signalaient pas l’échec de sa mise à jour.
Les tests contrôlent intégralement les octets de la récupération, de la
source, d’un fichier tiers et d’une récupération antérieure, ainsi que la
fermeture de chaque flux ouvert. Aucun fichier récupéré n’est supprimé.
Les écritures concernent uniquement les fichiers de sortie/journal créés
exclusivement par cette opération et les tampons MAIN, sans accès AUX/RAM.

Les 12 tests RESCUE et 15 gardes de disposition passent. Builds et contrôles
natifs 65C02/6502 valides : RESCUE mesure 6 940 / 7 012 octets, BSS
jusqu’à `$37F2 / $383B` inclus, soit 2 061 / 1 988 octets libres sous
`$4000`. Le résident et les plafonds restent inchangés. Distributions
reconstruites et huit tests 800K validés. Une coupure pendant l’écriture
physique peut toujours interrompre le fichier ou le journal.

## VOLINFO : entrée de catalogue refusée sur erreur du flux (11 octobre 2026)

La recherche de l’entrée sélectionnée vérifiait la fermeture mais pas
ferror après les lectures. Une lecture de 512 octets signalée en erreur
pouvait donc fournir une entrée utilisée pour la liste des blocs et un
rapport annoncé comme enregistré. Une fermeture en erreur marquait bien
le rapport partiel mais retournait encore l’entrée trouvée, dont l’en-tête
FILE pouvait être écrit. La recherche vérifie désormais l’indicateur de
flux avant fermeture et ne retourne aucune entrée après une erreur.
Le résumé d’audit déjà écrit reste disponible dans le rapport partiel,
sans liste issue de cette entrée ni marqueur END REPORT.

Le vrai export C couvre 15 scénarios de catalogue : entrée en positions
1, 6 et 12, erreur après lecture complète, lecture courte, zéro octet
en erreur, fermeture en erreur ou ouverture impossible. Six cas utilisaient
encore l’entrée avant correction, dont trois annonçaient un rapport sauvé.
Les mêmes 15 scénarios avec un rapport préexistant vérifient son identité
octet pour octet, sans ouverture tronquante ni lecture du catalogue.
Trois contrôles sains conservent la liste complète et END REPORT. Les
catalogues sources et un fichier tiers sont comparés intégralement.
Seul le rapport créé exclusivement est écrit, ainsi que les tampons MAIN ;
aucune écriture de volume source ni aucun accès AUX/RAM n’est ajouté.

Les neuf tests d’export, 30 tests d’audit VOLINFO et 15 gardes de disposition
passent. Builds et contrôles natifs 65C02/6502 valides : VOLINFO mesure
7 807 / 7 762 octets, BSS jusqu’à `$3F2F / $3F03` inclus, soit 110 / 154
octets libres avant sa table d’API fixe à `$3F9E`. Le résident et les
plafonds restent inchangés. Distributions reconstruites et huit tests 800K
validés. Un rapport partiel est conservé ; une coupure physique pendant
l’écriture peut toujours interrompre ou altérer ce fichier de sortie.

## DOSIMAGE : annulation aux fermetures des deux phases (11 octobre 2026)

ESC reçu pendant une fermeture après vérification de la copie préparatoire,
ou pendant la fermeture de l’original après son contrôle CRC final, pouvait
être ignoré et laisser commencer les renommages. DOSIMAGE contrôle désormais
ESC après les deux fermetures de préparation et après la fermeture du
contrôle final. La copie préparatoire appartient encore à cette phase :
elle est nettoyée, ou retenue si sa suppression échoue. La copie contenant
déjà le fichier importé est conservée à l’annulation de l’installation,
avec le diagnostic A2FC.DOS retained. Aucun renommage ne commence.

Le vrai C de DOSIMAGE et DOSPUT est testé avec 28 scénarios : DSK, DO,
2MG et 2MG avec commentaire, annulation pendant la fermeture source ou
temporaire de préparation, ou celle de l’original avant installation,
avec échecs combinés de fermeture ou de nettoyage. Un wrapper de test
inclut le C livré sans le modifier et expose uniquement son indicateur
d’annulation aux mocks de fermeture. Avant correction, 20 scénarios
commençaient encore les renommages. Après correction, original, source
importée et fichier tiers restent identiques octet pour octet ; aucune
sauvegarde n’est créée. Les copies retenues sont comparées entièrement à
l’image originale ou au résultat sain de l’import, y compris le conteneur
et son commentaire, puis protégées lors d’une nouvelle tentative.

Les 18 tests DOSIMAGE, 15 tests du moteur DOSWRITE et 15 gardes de
disposition passent, avec CRC sous sim65 sur les deux processeurs.
Builds et contrôles natifs 65C02/6502 valides : DOSIMAGE mesure
7 357 / 7 491 octets, BSS jusqu’à `$3A51 / $3AD8` inclus, soit
1 454 / 1 319 octets libres sous `$4000`. Le résident et les plafonds
restent inchangés. Distributions reconstruites et huit tests 800K validés.
Les écritures concernent la copie réservée exclusivement et les tampons
MAIN ; aucune écriture AUX/RAM n’est ajoutée. Les renommages ProDOS
restent non atomiques lors d’une coupure physique.

## MOVECOPY : préserver le type et l’adresse auxiliaire de la source (11 octobre 2026)

MOVE entre volumes relisait les métadonnées de la source avant copie et
avant suppression, mais ne vérifiait que le stockage et la protection.
La destination étant créée avec le type/aux du panneau, un panneau périmé
ou une modification de ces attributs pendant la copie pouvait laisser
supprimer une source dont les métadonnées n’étaient pas préservées. La
vérification complète des octets ne suffit pas à conserver, par exemple,
le type BIN et son adresse de chargement.

Le contrôle partagé compare désormais aussi type et aux avec l’entrée du
panneau. Une incohérence initiale refuse avant CREATE ; une incohérence
après copie et relecture conserve les deux fichiers sans effacer la copie
vérifiée. Seule la destination créée exclusivement est écrite ; la source
ne peut être supprimée qu’après toutes les vérifications. Les tampons
restent en MAIN, sans accès AUX/RAM ni écriture brute supplémentaire.

Le vrai C de MOVE/MOVECOPY couvre 24 régressions : type périmé, aux périmé
(les deux octets ou chaque octet isolément), type ou aux changé après
vérification, avec fichiers de 0, 1, 512 et 1 600 octets. Avant correction,
tous supprimaient la source. Après correction, les octets de la source et
d’un fichier tiers restent intacts ; aucune création n’a lieu au refus
initial et la copie vérifiée reste intégrale au refus final. Six contrôles
sains vérifient les arguments CREATE pour BIN `$06/$2000` et GS/OS
`$B3/$FFFF`, ainsi que les octets déplacés et la suppression autorisée.

Les 66 tests MOVE et 15 gardes de disposition passent. Builds et contrôles
natifs 65C02/6502 valides : MOVECOPY mesure 3 055 / 3 042 octets, BSS
jusqu’à `$29D9 / $29CD` inclus, soit 5 670 / 5 682 octets libres sous
`$4000`. Le résident et les plafonds restent inchangés. Distributions
reconstruites et huit tests 800K validés. Cette revalidation n’assure pas
une atomicité de la copie/suppression ni une protection contre une coupure
pendant les écritures physiques ProDOS.

## DISKCMP : refuser les tailles et en-têtes lus en erreur (11 octobre 2026)

DISKCMP utilisait imageio sans ses contrôles de fermeture du catalogue et
d’erreur du flux à la lecture de l’en-tête 2MG. Une taille trouvée malgré
une erreur du catalogue pouvait donc servir à annoncer des images
identiques. Un en-tête renvoyé intégralement avec ferror pouvait être
accepté et suivi de lectures du contenu sur ce flux déjà en erreur.
DISKCMP active désormais IMAGEIO_CHECK_CLOSE et IMAGEIO_CHECK_STREAM.
L’ouverture échoue avant d’utiliser ces métadonnées douteuses, et chaque
image déjà ouverte est fermée. La comparaison reste entièrement en
lecture seule ; seules ses structures et ses tampons MAIN sont modifiés,
sans écriture d’image, de volume ou de mémoire AUX/RAM.

Le vrai point d’entrée C couvre 30 scénarios de catalogue sur PO, DO et
2MG : erreur de fermeture `$27` ou `$01`, erreur différée malgré une
entrée renvoyée, ouverture impossible ou erreur de parcours, chaque fois
sur la source puis la destination. Avant correction, les 18 scénarios
avec entrée trouvée concluaient « Identical ». Deux régressions ajoutent
une erreur après lecture complète de l’en-tête 2MG sur chaque côté :
avant correction, le mock interrompait une lecture ultérieure du flux
déjà en erreur. Après correction, aucun bloc de contenu n’est lu après
ces refus ; le nombre exact d’ouvertures, fermetures de catalogue et
lectures d’en-tête est contrôlé. Les octets des deux images et d’un
fichier tiers restent identiques. Les contrôles sains et les tests de
comparaison physique, de disquettes échangées et de conteneurs avec
commentaires continuent de passer.

Les 16 tests DISKCMP, 29 tests PASCALW (dont le retour natif octet de
l’API void figée sur les deux processeurs) et 15 gardes de disposition
passent. Builds et contrôles natifs 65C02/6502 valides : DISKCMP mesure
7 666 / 7 640 octets, BSS jusqu’à `$3F83 / $3F6A` inclus, soit 124 / 149
octets libres sous `$4000`. Le résident et les plafonds restent inchangés.
Distributions reconstruites et huit tests 800K validés.

## CPM : conserver les fichiers de zéro octet à l’extraction (11 octobre 2026)

Une entrée CP/M valide sans enregistrement ni bloc de données était
ignorée après sa mesure, et comptée « skipped (name taken) » même lorsque
son nom était libre. L’extraction omettait donc ce fichier. La branche
de saut est supprimée : one() réserve son nom par CREATE exclusif,
ferme le flux d’écriture, rouvre le résultat vide et contrôle l’EOF,
ferror, les fermetures et ESC comme pour un fichier non vide. L’échec
de mesure est toujours contrôlé avant one() et ne devient pas un fichier
vide valide. Seuls les outputs créés par cette extraction et les tampons
MAIN sont écrits ; image source et mémoire AUX/RAM restent inchangées.

Le vrai C est testé avec une entrée zéro-record suivie d’un fichier normal,
ainsi que 44 scénarios sur les deux ordres de secteurs : extraction saine,
collision, CREATE refusé/I/O/disque plein/protection, erreur de fermeture,
erreur d’EOF de vérification, annulation aux fermetures et échec de
nettoyage. Les collisions conservent les octets préexistants ; les erreurs
de CREATE ne donnent aucun droit de nettoyage. Les résultats vides retenus
après échec de nettoyage sont vérifiés puis protégés lors d’une nouvelle
tentative, qui extrait seulement le fichier suivant. L’image source et
un fichier tiers sont contrôlés intégralement. Les tests d’annulation à
la fermeture finale de l’image vérifient désormais la conservation du
fichier vide déjà créé et vérifié, au lieu de son omission.

Les 21 tests CP/M et 15 gardes de disposition passent. Builds et contrôles
natifs 65C02/6502 valides : CPM mesure 8 284 / 8 243 octets, BSS jusqu’à
`$3FB2 / $3F8A` inclus, soit 77 / 117 octets libres sous `$4000`.
La suppression du saut réduit le code sans réduire les contrôles
d’I/O ni augmenter les tampons. Le résident et les plafonds restent
inchangés. Distributions reconstruites et huit tests 800K validés. Une
coupure physique pendant CREATE ou une fermeture reste susceptible de
laisser un résultat incomplet ; aucune atomicité ProDOS n’est promise.

## CP/M : refuser les extents ambigus avant CREATE

Deux entrées du même utilisateur et du même nom pouvaient revendiquer le même
numéro d'extent, avec des blocs distincts : `measure` les marquait toutes comme
traitées, puis `extent_at` ne lisait que la première. La vérification relisait
le même choix et pouvait annoncer un fichier complet en omettant l'autre entrée.
`measure` réutilise désormais le bitmap MAIN de détection du skew pour refuser
les doublons et les numéros hors des 64 entrées possibles, avant toute création.
Les attributs du nom restent exclus de l'identité. Image source, fichiers
préexistants et mémoire AUX ne sont pas écrits ; seuls les nouveaux fichiers
exclusivement créés par l'extraction normale peuvent être écrits ou nettoyés.

L'extracteur utilise `IMAGEIO_NODEVICE` : il ouvre uniquement des fichiers images,
et n'embarque plus la branche inutilisée de lecture d'un périphérique brut.
Les overlays CP/M mesurent 8024/7967 octets (65C02/6502), BSS jusqu'à
`$3EA8`/`$3E70`, soit 343/399 octets libres avant `$4000`.
Les contrôles mémoire restent actifs.

Régression : huit cas de doublons échouaient avant correction. Le vrai C passe
désormais 23 tests CP/M, dont 48 nouveaux scénarios : doublons avec/sans collision,
attributs, entrée déplacée jusqu'au dernier slot, numéros 64/256/8191 et extents
valides désordonnés. Les tests comparent les octets de l'image, des fichiers
préexistants et des extractions valides, et exigent zéro CREATE pour les catalogues
ambigus. Les deux builds, leurs contrôles de disposition et les 15 tests des
gardes mémoire passent. Les distributions sont reconstruites et leurs huit tests
800K passent. Ces contrôles ne promettent pas d'atomicité lors d'une coupure
pendant une écriture physique ProDOS.

## CP/M : respecter les compteurs de records et les blocs requis

L'extraction ignorait RC dans les extents précédant le dernier et sautait les
allocations nulles. Avec une allocation manquante dans le préfixe requis et un
bloc supplémentaire plus loin, elle pouvait produire et vérifier des octets
décalés ; avec un extent précédent partiel, elle pouvait copier des octets que
son catalogue ne déclarait pas. `measure` vérifie désormais, avant CREATE, la
présence de chaque bloc couvrant RC et l'égalité entre la somme des RC et la
longueur calculée. Avec les identités uniques déjà contrôlées, cette égalité
impose une suite complète d'extents antérieurs à 128 records.

Seuls les buffers MAIN et les marqueurs de catalogue sont modifiés par ces
contrôles. Image source, fichiers préexistants et AUX restent intacts ; la
création exclusive et le nettoyage des seuls nouveaux fichiers restent ceux
de l'extracteur. Les blocs réservés au-delà du préfixe requis, les fichiers
vides et l'extent terminal vide restent acceptés.

Seize scénarios reproduisaient l'absence de refus avant correction. Les 25 tests
du vrai C passent, avec 40 nouveaux scénarios : 20 catalogues incohérents dans
les deux skews, avec/sans collision, et 20 extractions valides aux limites des
blocs et des extents. Chaque cas compare les octets conservés ou extraits.
Les deux builds et leurs contrôles de disposition passent, ainsi que les
15 tests des gardes mémoire. CP/M : 8168/8165 octets (65C02/6502), BSS jusqu'à
`$3F3B`/`$3F39`, 196/198 octets libres avant `$4000` sans désactiver de garde.
Les distributions sont reconstruites et les huit tests 800K passent. Une
coupure pendant l'écriture physique ProDOS reste hors de toute garantie
d'atomicité.

## UNWRAP : refuser deux descriptions de la data fork AppleSingle

Le parseur AppleSingle remplaçait silencieusement `off` et `len` lorsqu'une
seconde entrée d'identifiant 1 apparaissait. L'extraction puis sa vérification
ne portaient que sur cette dernière entrée, sans signaler l'autre description
des données. Il refuse désormais le doublon avec le bit de présence déjà
conservé dans `typed`, même pour une data fork vide ou après des métadonnées
ProDOS. La référence Python refuse le même cas.

Le refus précède CREATE : seuls les buffers et l'état du parseur en MAIN
changent ; source, destinations préexistantes et AUX restent intacts.
Le chemin normal conserve la création exclusive et le nettoyage des seuls
nouveaux fichiers. Aucun buffer ni bit de présence supplémentaire n'est ajouté.

Les 48 nouveaux scénarios de doublons échouaient avant correction. Les 20
tests du vrai C passent, incluant ces 48 cas (versions 1/2, données vides,
identiques ou différentes, métadonnées intercalées, collisions) et 18 cas
valides vérifiant les octets et les types avec des métadonnées désordonnées.
Les auto-tests de la référence, les deux builds, leurs contrôles de disposition
et les 15 tests des gardes mémoire passent. UNWRAP mesure 7189/7193 octets
(65C02/6502), BSS jusqu'à `$3CF7`/`$3CFC`, soit 776/771 octets libres avant
`$4000`. Les distributions sont reconstruites et les huit tests 800K passent.
La correction ne fournit pas d'atomicité lors d'une coupure pendant une
écriture physique ProDOS.

## UNSQ : ne pas transformer un nom/path invalide en collision

`one` comptait un nom vide après normalisation ou un chemin refusé par `join`
comme un fichier existant, puis continuait l'archive. Une entrée inexploitable
pouvait donc disparaître derrière une réussite et le compteur « name taken ».
Le refus arrête désormais l'extraction avant CREATE avec « name/path invalid,
stopped », sans incrémenter les collisions. Les vrais noms pris restent des
skips ; les enregistrements répertoire/type `$0F` conservent leur traitement.

Le contrôle touche uniquement l'état MAIN. Il n'a encore créé aucun fichier
pour cette entrée et ne tente aucun nettoyage ; les extractions précédentes,
destinations préexistantes, source et AUX sont conservées. Le chemin valide
garde sa création exclusive et ses contrôles d'écriture/fermeture/relecture.

Les 22 tests du vrai C passent, avec 30 nouveaux scénarios : noms ACU vides,
sans lettre ou terminant par un séparateur, stockés/squeezés, avant/après une
extraction valide ; chemins résultants de 63/64/65 caractères pour QQ et ACU,
avec/sans collision préexistante. Les tests comparent les octets conservés et
extraits, les appels CREATE et l'absence de suppression. Le seuil existant
de `join` reste inchangé : la longueur résultante doit être inférieure à 64.
Les deux builds, leurs contrôles de disposition et les 15 tests des gardes
mémoire passent. UNSQ mesure 7037/7117 octets (65C02/6502), BSS jusqu'à
`$3EA8`/`$3EF9`, soit 343/262 octets libres avant `$4000`.
Les distributions sont reconstruites et les huit tests 800K passent.
Une coupure pendant l'écriture physique ProDOS reste hors de toute garantie
d'atomicité.

## BinSCII : vérifier type et auxiliaire de chaque fragment

Après le premier chunk, SCIIBIN vérifiait le nom et la longueur totale, mais
ignorait son type ProDOS et son auxiliaire. Deux fragments portant le même nom
et la même longueur, avec des CRC valides mais des métadonnées incompatibles,
pouvaient être assemblés et annoncés comme un fichier décodé. Chaque chunk
suivant doit désormais répéter le type et l'auxiliaire du premier ; le refus
précède l'ajout de ses données. La référence Python applique la même règle.

L'opération écrit uniquement son nouveau fichier ProDOS créé exclusivement et
l'état MAIN. Elle ne modifie ni les parties sources, ni les destinations
préexistantes, ni AUX. Sur erreur, seul son fichier est nettoyé ; si la suppression
échoue, le préfixe déjà écrit est conservé et le diagnostic de nettoyage reste
visible. Aucun buffer supplémentaire n'est introduit.

Les 48 nouveaux scénarios négatifs échouaient avant correction. Les 15 tests
du vrai C passent, incluant ces 48 cas (type, auxiliaire bas/haut, type répertoire,
chunks dans un seul fichier ou plusieurs, tailles 1/49/12288 du dernier chunk,
nettoyage réussi/refusé) et 18 cas valides BIN/PSYS/PS16. Les octets sources,
préexistants et conservés sont comparés ; un nettoyage refusé garde exactement
le premier chunk de 12288 octets. Les auto-tests de référence, CRC sous sim65,
deux builds, contrôles de disposition et 15 tests des gardes mémoire passent.
SCIIBIN : 6610/6628 octets (65C02/6502), BSS jusqu'à `$3FA4`/`$3FB7`, soit
91/72 octets libres avant `$4000`, sans désactiver de garde. Les distributions
sont reconstruites et leurs huit tests 800K passent. La correction ne fournit
pas d'atomicité lors d'une coupure pendant l'écriture physique ProDOS.

## DISASM : annulation pendant la dernière écriture ou fermeture d'export

`export_text` renvoyait une réussite après l'écriture du marqueur END sans
relire ESC ; `export` publiait ensuite sa réussite après fermeture sans ce
contrôle. Une annulation reçue pendant l'un de ces appels était ignorée.
Le décodeur teste désormais ESC avant/après END, puis après fermeture avant
de choisir le message. Une erreur de fermeture sans annulation continue de
signaler un export incomplet ; une annulation signale le fichier conservé.

Seul le TXT créé exclusivement et l'état MAIN sont écrits. Aucun fichier
préexistant ni source, aucun volume brut ni AUX ne sont modifiés ; l'export
est conservé comme pour les autres interruptions. END peut déjà figurer dans
les octets conservés si ESC arrive pendant son écriture ou la fermeture :
le résultat d'interface reste alors annulé.

Les 24 scénarios d'annulation tardive échouent avec le code antérieur dans
une copie temporaire de contrôle. Les 17 tests du vrai C passent, dont 48
nouveaux scénarios : dernière écriture, fermeture normale/en erreur/annulée,
annulation avec erreur de fermeture et collision de nom, sur deux CPU et
tailles 0/1/57/200. Le vrai `export` est exécuté ; les octets conservés sont
comparés à l'export normal, avec contrôle de la source et d'un fichier témoin.
Les deux builds, contrôles de disposition et les 15 tests des gardes mémoire
passent. DISASM : 8089/8079 octets (65C02/6502), BSS jusqu'à `$3D21`/`$3D18`,
734/743 octets libres avant `$4000`. Les distributions sont reconstruites et
leurs huit tests 800K passent. Une coupure pendant l'écriture physique ProDOS
reste hors de toute garantie d'atomicité.

## DISASM : EOF réel avant de terminer un export

L'export utilisait la taille du panneau et écrivait END dès que ce nombre
d'octets avait été désassemblé. Une source agrandie depuis la lecture du
panneau, y compris une taille affichée à zéro, pouvait donc produire un export
de préfixe annoncé complet. Après ses lignes, `export_text` recherche désormais
la taille attendue dans la source et exige une lecture d'un octet donnant zéro
sans erreur de flux. Toute donnée supplémentaire ou erreur de recherche/lecture
refuse END et la réussite. ESC est contrôlé avant et après cette sonde.

Seul le nouveau TXT créé exclusivement et l'état MAIN sont écrits ; source,
destinations préexistantes et AUX restent intacts. Le texte partiel est conservé
et l'interface signale l'export incomplet. La taille du panneau ne fait donc
plus office de preuve de fin de fichier ; la navigation garde son fonctionnement.

Cinquante-six cas de régression échouaient avant correction. Les 20 tests du
vrai C passent avec 72 nouveaux scénarios : tailles périmées 0/1/57/200,
source prolongée de 1/16 octets, export depuis zéro ou la taille attendue,
erreurs et ESC pendant la sonde finale, puis appel du vrai `export` avec/sans
collision. Ils contrôlent les octets de la source, du fichier témoin, de l'ancien
export et du préfixe conservé, ainsi que l'absence de END en cas d'échec.
Les deux builds, contrôles de disposition et 15 tests des gardes mémoire
passent. DISASM : 8251/8235 octets (65C02/6502), BSS jusqu'à `$3DC3`/`$3DB4`,
572/587 octets libres avant `$4000`. Les distributions sont reconstruites et
leurs huit tests 800K passent. Ce contrôle ne garantit pas l'atomicité d'une
écriture physique ProDOS ni l'absence de modification externe après la sonde.

## UNWRAP : position réelle des données après un en-tête secondaire MacBinary

Le parseur MacBinary supposait que les données commençaient à l'octet 128.
Un en-tête secondaire déclaré à `+$78` doit pourtant être sauté, arrondi à
128 octets ([notes CiderPress II](https://ciderpress2.com/formatdoc/MacBinary-notes.html)).
Avec un CRC d'en-tête valide, UNWRAP extrayait ainsi des octets de cet en-tête
et les vérifiait à la même mauvaise position. Il calcule désormais le début
réel en arithmétique 32 bits avant arrondi, puis contrôle ce début et la longueur
par soustraction dans la taille réellement lue. La référence Python et ses
fixtures prennent aussi en compte l'en-tête secondaire ; la fixture III porte
sa signature `mBIN` et son numéro `$82`.

Le parseur écrit uniquement son état MAIN et refuse les limites invalides avant
CREATE. Source, destinations préexistantes et AUX restent intacts. Une extraction
valide garde sa création exclusive, ses contrôles de fermeture et la comparaison
des octets ; seul son nouveau fichier peut être nettoyé sur erreur.

Soixante-quatre cas échouaient avant correction. Les 23 tests du vrai C passent,
dont 78 nouveaux scénarios sur les versions II/III : en-têtes de 1/127/128/129/
65535 octets, données vides/courtes/700 octets, troncature de l'en-tête, de son
alignement ou des données, avec/sans collision. Les octets extraits, les anciens
fichiers et la source sont comparés. Trente scénarios supplémentaires exécutent
les fonctions de parsing/CRC réelles compilées pour 6502 et 65C02 sous sim65,
notamment `65535 + 127`, qui doit être élargi avant addition.
Les auto-tests de référence, deux builds, contrôles de disposition et 15 tests
des gardes mémoire passent. UNWRAP : 7294/7293 octets (65C02/6502), BSS jusqu'à
`$3D60` sur les deux, 671 octets libres avant `$4000`. Les distributions sont
reconstruites et leurs huit tests 800K passent. La correction ne fournit pas
d'atomicité lors d'une coupure pendant l'écriture physique ProDOS.

## UNWRAP : contrôler aussi les bornes des ressources MacBinary

Le parseur validait la data fork mais ne contrôlait pas la présence des ressources
annoncées. Une archive amputée de cette partie, ou déclarant une longueur de
ressources `$FFFFFF`/`$FFFFFFFF`, pouvait être extraite et annoncée comme valide
avec « Resource fork left out ». Il exige désormais, lorsque des ressources sont
déclarées, que leur début aligné et leur longueur tiennent dans la taille réellement
lue. Les calculs soustraient les bornes déjà vérifiées avant de comparer : une
longueur 32 bits hostile ne peut pas contourner le contrôle par débordement.
Le bourrage final des ressources n'est pas exigé. La référence Python suit le
même contrôle.

Le refus intervient dans le parseur avant CREATE ; seuls l'état et les buffers
MAIN changent. Source, fichiers préexistants et AUX restent intacts. Le chemin
valide écrit exclusivement son nouveau fichier et garde ses contrôles de
fermeture/relecture et de nettoyage des seuls fichiers créés par cette opération.

Les 108 cas négatifs échouaient avant correction. Les 26 tests du vrai C passent,
avec 168 nouveaux scénarios hôtes (108 refus, 60 extractions valides) : versions
I/II/III, data fork de 0/1/127/128/129/513 octets, ressources tronquées, collisions,
longueurs extrêmes, ressources non bourrées et en-tête secondaire présent/absent.
Les fichiers sources et préexistants ainsi que les données extraites sont comparés.
Cinquante scénarios supplémentaires exécutent les fonctions réelles du parseur
et du CRC sous sim65 sur les deux CPU ; le contrôle natif couvre désormais 80 cas.
Les auto-tests de référence, deux builds, contrôles de disposition et 15 tests des
gardes mémoire passent. UNWRAP : 7560/7561 octets (65C02/6502), BSS jusqu'à
`$3E6F`/`$3E71`, 400/398 octets libres avant `$4000`. Les distributions sont
reconstruites et leurs huit tests 800K passent. Une coupure pendant l'écriture
physique ProDOS reste hors de toute garantie d'atomicité.

## UNWRAP : refuser les métadonnées ProDOS AppleSingle dupliquées

Une seconde entrée ID 11 remplaçait silencieusement le type et le type
auxiliaire de la première, y compris un type répertoire qui aurait dû
empêcher l'extraction. Le parseur refuse désormais ce doublon avant CREATE,
même si la première entrée est vide ou trop courte. Un bit du statut garde
la présence de l'entrée à travers la lecture des métadonnées ID 7 ; les
entrées uniques ID 7/11 et Finder restent compatibles. Le changement écrit
uniquement l'état du parseur en MAIN : source en lecture, aucune écriture
AUX ou disque avant validation, destinations préexistantes conservées.

`tools/test_unwrap.py` exécute le vrai C sur fichiers temporaires jetables :
72 scénarios de doublon (versions 1/2, type/aux divergents ou identiques,
entrée vide/courte, type répertoire, Finder/ID 7 intercalé, collision) et
18 cas valides avec ID 7, ID 11 et Finder. Les 72 premiers échouaient avant
correction ; les 28 tests passent après correction. Source, destinations
préexistantes, octets extraits et métadonnées sont contrôlés. L'oracle
Python refuse les mêmes doublons.

Builds et gardes mémoire inchangés validés sur les deux architectures :
UNWRAP **7608/7614 octets** (65C02/6502), fin de BSS **$3E9F/$3EA6**,
soit **352/345 octets** disponibles sous $4000. Les 15 tests de garde de
disposition passent. Les distributions sont reconstruites et contrôlées
par les 8 tests du disque 800K. Cette validation n'ajoute aucune garantie
d'atomicité en cas de coupure pendant une écriture physique.

## UNWRAP : ne pas ignorer une entrée ProDOS AppleSingle incomplète

Une entrée ID 11 de moins de huit octets était ignorée comme si elle
n'existait pas. L'extraction pouvait alors annoncer un succès avec le type
Finder, ou le type par défaut, malgré des métadonnées ProDOS illisibles.
Le parseur et l'oracle Python refusent désormais cette entrée avant CREATE.
La correction n'écrit que l'état MAIN ; source en lecture, aucune écriture
AUX, destinations existantes conservées. Les métadonnées complètes et leur
priorité sur Finder restent acceptées.

Les 96 scénarios de refus échouaient avant correction : versions 1/2,
longueurs 0 à 7, data fork vide/1/513 octets, avec ou sans collision.
Les 18 scénarios valides vérifient les entrées de 8/9/32 octets, le type
$06, l'auxiliaire $2000 et tous les octets extraits. Le vrai C est exécuté
sur des fichiers temporaires jetables ; source et fichiers préexistants
sont comparés. Les 30 tests UNWRAP, l'auto-test de référence et les 15 tests
des gardes mémoire passent.

Les deux builds et contrôles de disposition passent sans relâcher les
limites : UNWRAP **7638/7644 octets** (65C02/6502), BSS jusqu'à
**$3EBD/$3EC4**, **322/315 octets** libres sous $4000. Distributions
reconstruites, contrôlées par les 8 tests du disque 800K. Les contrôles
n'ajoutent aucune atomicité lors d'une coupure pendant l'écriture physique.

## UNWRAP : ne pas masquer les ressources AppleSingle par un doublon

Une seconde entrée ID 2 remplaçait la longueur des ressources de la
première. Si elle était vide, l'extraction de la data fork annonçait un
succès sans « Resource fork left out », malgré les ressources omises.
Les descriptions de ressources dupliquées sont désormais refusées avant
CREATE, même vides ou identiques. Le bit de présence est conservé lors de
la lecture des métadonnées ProDOS ID 7/11 ; l'oracle Python suit ce refus.
La correction écrit uniquement l'état MAIN, source en lecture, aucune
écriture AUX, destinations préexistantes conservées.

Les 72 scénarios négatifs échouaient avant correction : versions 1/2,
paires de ressources vides/non vides/identiques/différentes, ID 7/11
intercalés, avec ou sans collision. Les 18 cas valides vérifient l'ordre
des métadonnées, les ressources vides ou de 1/513 octets, le message
d'omission, les métadonnées et tous les octets extraits. Le vrai C tourne
sur fichiers temporaires jetables ; sources et destinations préexistantes
sont comparées. Les 32 tests UNWRAP, l'auto-test de référence et les
15 tests des gardes de disposition passent.

Les deux builds et contrôles mémoire passent sans changer les limites :
UNWRAP **7654/7671 octets** (65C02/6502), BSS jusqu'à **$3ECD/$3EDF**,
**306/288 octets** libres sous $4000. Distributions reconstruites et
contrôlées par les 8 tests du disque 800K. Aucune garantie d'atomicité
n'est ajoutée pour une coupure pendant l'écriture physique ProDOS.

## UNWRAP : refuser plusieurs noms AppleSingle

Une seconde entrée ID 3 remplaçait silencieusement le nom de destination
issu de la première, ou le vidait pour revenir au nom de l'archive.
Le parseur refuse désormais plusieurs entrées de nom avant CREATE, même
vides ou identiques. Le bit de présence est conservé à travers les
métadonnées ProDOS ID 7/11 ; l'oracle Python applique le même refus.
Seul l'état MAIN est modifié, source en lecture, aucune écriture AUX et
aucune création ou suppression lors du refus.

Les 72 scénarios négatifs échouaient avant correction : versions 1/2,
noms distincts/inversés/identiques/vides, métadonnées ID 7/11 intercalées,
avec ou sans collisions sur les noms possibles. Les 18 cas valides
vérifient un nom unique, sa normalisation et le repli sur le nom de
l'archive si cette unique entrée est vide. Le vrai C est exécuté sur des
fichiers temporaires jetables ; source, destinations préexistantes et
octets extraits sont comparés, ainsi que type/aux et avertissement de
ressources omises. Les 34 tests UNWRAP, l'auto-test de référence et les
15 tests des gardes de disposition passent.

Les deux builds et contrôles mémoire passent sans changement des limites :
UNWRAP **7673/7693 octets** (65C02/6502), BSS jusqu'à **$3EE0/$3EF5**,
**287/266 octets** libres sous $4000. Distributions reconstruites et
contrôlées par les 8 tests du disque 800K. Les contrôles ne garantissent
pas l'atomicité lors d'une coupure pendant l'écriture physique ProDOS.

## UNWRAP : refuser le type Finder incomplet ou dupliqué

Plusieurs entrées ID 9 pouvaient remplacer silencieusement le type Finder
utilisé pour l'extraction ; une entrée de moins de huit octets était
ignorée malgré son type/créateur incomplet. Le parseur refuse ces entrées
avant CREATE, y compris lorsqu'une entrée ProDOS prend priorité. Le bit
de présence survit aux métadonnées ID 7/11 ; l'oracle Python applique les
mêmes contrôles. Seul l'état MAIN change : source en lecture, aucune
écriture AUX, aucune création ou suppression lors du refus.

Les 136 scénarios négatifs échouaient avant correction : 72 doublons
(versions 1/2, types divergents/identiques, type répertoire, entrées
vides/courtes, métadonnées intercalées, collisions), et 64 entrées uniques
de 0 à 7 octets avec/sans ProDOS et collision. Les 24 cas valides vérifient
TEXT, un type/aux 'pdos', un type Mac sans correspondance, les ordres
Finder/ProDOS et leur priorité. Le vrai C tourne sur fichiers temporaires
jetables ; sources, destinations existantes, octets extraits et type/aux
sont comparés. Les 37 tests UNWRAP, l'auto-test de référence et les
15 tests des gardes de disposition passent.

Les deux builds et contrôles mémoire passent sans changer les limites :
UNWRAP **7751/7776 octets** (65C02/6502), BSS jusqu'à **$3F2E/$3F48**,
**209/183 octets** libres sous $4000. Distributions reconstruites et
contrôlées par les 8 tests du disque 800K. Aucune atomicité supplémentaire
n'est garantie en cas de coupure pendant l'écriture physique ProDOS.

## UNWRAP : vérifier les anciennes métadonnées ProDOS AppleSingle v1

L'entrée ID 7 d'un AppleSingle v1 de système d'origine ProDOS pouvait
être ignorée si elle était trop courte, ou être remplacée par une seconde
entrée, donnant un succès avec un type/aux de remplacement. Elle doit
désormais contenir les seize octets lus et être unique avant CREATE.
Le bit de présence survit à l'entrée ID 11. La référence Python suit ces
contrôles. Seuls les buffers et l'état MAIN changent ; source en lecture,
aucune écriture AUX, aucune destination créée ou supprimée lors du refus.

Les 68 scénarios négatifs échouaient avant correction : 36 doublons
(type/aux divergents ou identiques, type répertoire, entrée vide/courte,
Finder/ID 11 intercalé et collision) et 32 entrées uniques de 0 à 15 octets
avec/sans collision. Les 60 cas valides vérifient les entrées complètes,
leurs positions, la data fork vide ou non vide et les systèmes/versions
où ID 7 n'est pas une métadonnée ProDOS : ces derniers continuent à ignorer
les entrées étrangères courtes ou répétées. Le vrai C est exécuté sur
fichiers temporaires jetables ; source, destinations existantes, type/aux
et octets extraits sont comparés. Les 40 tests UNWRAP, l'auto-test de
référence et les 15 tests des gardes de disposition passent.

Les deux builds et contrôles mémoire passent sans modifier les limites :
UNWRAP **7762/7787 octets** (65C02/6502), BSS jusqu'à **$3F39/$3F53**,
**198/172 octets** libres sous $4000. Distributions reconstruites et
contrôlées par les 8 tests du disque 800K. Les contrôles n'offrent aucune
atomicité supplémentaire lors d'une coupure pendant l'écriture ProDOS.

## UNWRAP : refuser l'identifiant d'entrée AppleSingle zéro

Le parseur ignorait un descripteur ID 0 comme une extension inconnue et
pouvait annoncer une extraction valide. La spécification Apple interdit
explicitement cet identifiant (chapitre 2, Entry descriptors, page 6 de la
[note AppleSingle/AppleDouble](https://nulib.com/library/AppleSingle_AppleDouble.pdf)).
Il est désormais refusé avant CREATE, même pour une entrée vide. Les
identifiants non nuls inconnus restent opaques. Seul l'état MAIN change :
source en lecture, aucune écriture AUX, aucune destination créée ou
supprimée lors du refus. L'oracle Python applique le même contrôle.

Les 36 scénarios négatifs échouaient avant correction : versions 1/2,
entrée vide/1/513 octets, trois positions dans la table, avec/sans collision.
Les 80 cas valides vérifient dix identifiants opaques, y compris les bornes
$7FFFFFFF/$80000000/$FFFFFFFF, des entrées vides ou non vides et leurs
positions. Le vrai C est exécuté sur fichiers temporaires jetables ; les
sources, destinations préexistantes, métadonnées et octets extraits sont
comparés. Les 42 tests UNWRAP, l'auto-test de référence et les 15 tests des
gardes de disposition passent.

Les deux builds et contrôles mémoire passent sans changer les limites :
UNWRAP **7803/7828 octets** (65C02/6502), BSS jusqu'à **$3F62/$3F7C**,
**157/131 octets** libres sous $4000. Distributions reconstruites et
contrôlées par les 8 tests du disque 800K. Aucune atomicité supplémentaire
n'est garantie lors d'une coupure pendant l'écriture physique ProDOS.

## UNWRAP : annuler la lecture du catalogue avant CREATE

Un ESC arrivé pendant la lecture de l'en-tête ou du catalogue pouvait
laisser le parseur poursuivre tous les descripteurs, puis créer un fichier
avant que la copie constate l'annulation. Le nettoyage devenait nécessaire
alors qu'aucune extraction n'avait été demandée après ESC ; s'il échouait,
un fichier vide restait. `grab()` vérifie désormais l'annulation avant la
lecture suivante, et l'entrée du plugin la vérifie après le parseur, avant
la création. Le message devient « Stopped: nothing extracted. ». Seul le
flux source en lecture est fermé ; aucun fichier créé/supprimé, aucune
écriture AUX, seuls l'état et les buffers MAIN changent.

Les 82 scénarios ciblés échouaient avant correction. Le vrai C exécute
78 annulations à l'en-tête, au premier/dernier descripteur, aux métadonnées
ou avec une lecture courte : AppleSingle v1/v2, MacBinary I/II/III, forks
vides/1/513 octets et collisions. Quatre catalogues de 1000/65535 entrées
vérifient qu'ESC au premier descripteur ne lit aucun descripteur suivant.
Le banc compte tous les appels CREATE, même refusés : aucun lors de ces
annulations. Les sources et destinations préexistantes sont comparées sur
fichiers temporaires jetables. Les 44 tests UNWRAP et les 15 tests des
gardes de disposition passent.

Les deux builds et contrôles mémoire passent sans relâcher les limites :
UNWRAP **7854/7880 octets** (65C02/6502), BSS jusqu'à **$3F95/$3FB0**,
**106/79 octets** libres sous $4000. Distributions reconstruites et
contrôlées par les 8 tests du disque 800K. Une coupure pendant une écriture
physique ProDOS reste hors de toute garantie d'atomicité.

## SCIIBIN : refus avant CREATE sur lecture douteuse ou ESC (11 octobre 2026)

Un en-tête BinSCII complet pouvait être extrait d'un tampon obtenu par une
lecture ayant signalé une erreur ; ESC durant cette lecture pouvait aussi
rester sans effet jusqu'à la première écriture des données. Dans les deux
cas, CREATE intervenait avant le refus et le nettoyage. SCIIBIN contrôle
désormais l'annulation et l'état du flux après la validation de l'en-tête,
avant toute création ou ajout de données d'un morceau.

La source reste ouverte en lecture seule. Seule la destination réservée par
création exclusive peut être écrite et nettoyée ; aucun fichier préexistant,
volume brut ou banque auxiliaire n'est modifié. Les échecs de lecture tardifs,
de fermeture et de vérification restent couverts par les contrôles existants.
Cette correction ne rend pas les écritures ProDOS atomiques en cas de coupure.

Le vrai point d'entrée C est exécuté sur des fichiers jetables : 12 nouveaux
scénarios croisent erreur de lecture à compte complet ou ESC, trois tailles
et présence ou absence d'une collision. Tous échouaient avant la correction.
Ils contrôlent zéro appel CREATE et REMOVE, les octets des sources et les
fichiers déjà présents. Les 16 tests SCIIBIN et les 15 tests des gardes de
disposition passent, ainsi que les builds et contrôles mémoire des deux
architectures. SCIIBIN mesure 6659/6677 octets (65C02/6502), avec BSS finissant
à `$3FD5`/`$3FE8`, soit 42/23 octets libres avant `$4000`. Aucun contrôle de
disposition n'a été désactivé.

## UNSQ : ESC avant la création d'un membre (11 octobre 2026)

UNSQ contrôlait l'annulation pendant la mesure initiale, la décompression
et la vérification, mais pas entre la lecture d'un en-tête et CREATE. ESC
pendant la relecture d'un en-tête `.QQ`/ACU ou une recherche entre deux
membres pouvait donc créer un fichier, ensuite supprimé, ou compter une
collision comme un fichier ignoré. Le contrôle au début de `one()` refuse
désormais ces opérations avant CREATE, même pour un membre vide.

La source est ouverte en lecture seule ; seule une sortie effectivement
réservée par création exclusive peut être écrite et nettoyée. L'annulation
ne touche aucun fichier préexistant ni membre précédemment vérifié. Aucun
volume brut ou mémoire auxiliaire n'est écrit. Les contrôles d'erreurs de
lecture, d'écriture, de fermeture et de nettoyage restent en place ; aucune
atomicité physique en cas de coupure n'est promise.

Le vrai point d'entrée C est testé sur des fichiers jetables : 24 nouveaux
scénarios croisent deux formats, trois tailles (dont zéro), deux moments
d'annulation et une collision éventuelle ; quatre autres annulent entre
deux membres ACU, stockés ou comprimés. Tous les 28 scénarios échouaient
avant la correction. Les tests vérifient le nombre d'appels CREATE, aucune
suppression, une fermeture de la source et les octets conservés, y compris
le premier membre déjà extrait. Les 24 tests UNSQ et les 15 tests des gardes
passent. Builds et contrôles de disposition valides sur les deux processeurs,
sans désactivation des limites : UNSQ 7047/7127 octets (65C02/6502), BSS fin
`$3EB2`/`$3F03`, réserves 333/252 octets avant `$4000`.

## PASCAL : revalider les entrées relues avant CREATE (11 octobre 2026)

Le catalogue était validé par `read_dir()`, puis chaque entrée relue pour
l'extraction sans revalider ses champs. Une relecture différente pouvait
donner une taille de dernier bloc supérieure au tampon de 512 octets,
conduire à une écriture lisant au-delà de ce tampon, ou extraire des blocs
du catalogue ou d'un fichier précédent. Les champs de l'entrée effectivement
utilisée sont désormais contrôlés avant CREATE : longueur du nom, début,
fin et taille du dernier bloc. La fin de l'entrée précédente est conservée,
y compris pour un fichier ignoré à cause d'une collision, afin de refuser
les chevauchements apparus lors de la relecture.

L'image source reste ouverte en lecture seule. Seuls les fichiers réservés
par création exclusive peuvent être écrits et nettoyés ; les originaux,
collisions et fichiers précédemment vérifiés sont conservés. Aucun volume
brut ni mémoire auxiliaire n'est écrit. Ces contrôles ne fournissent pas une
photographie atomique d'une image modifiée simultanément, ni une atomicité
physique des écritures ProDOS en cas de coupure.

Le vrai C reçoit des octets modifiés uniquement lors de la relecture d'une
entrée, après validation du catalogue, sur une image jetable dont les octets
restent inchangés. Les 58 scénarios couvrent noms de taille zéro ou 16,
dernier bloc de taille zéro, 513 ou 1024, bornes inversées ou hors volume,
chevauchements, premier ou deuxième fichier, et collisions sur le fichier
courant ou précédent. Sans le nouveau contrôle, 43 assertions échouent ;
les autres vérifient les refus déjà assurés. Avec la correction, les 17 tests
PASCAL et 15 tests des gardes passent, ainsi que les builds et contrôles
mémoire 65C02/6502. PASCAL mesure 7286/7278 octets, BSS fin `$3A8C`/`$3A85`,
soit 1395/1402 octets libres avant `$4000`. Les contrôles de disposition
restent activés ; les distributions sont reconstruites et contrôlées.

## CPM : allocations relues après validation du skew (11 octobre 2026)

La détection du skew valide les entrées, mais des secteurs de catalogue sont
relus pendant le calcul de taille et la copie. Une allocation différente
pouvait pointer vers un bloc du catalogue : ses octets étaient copiés et
vérifiés comme données du fichier. Un trou dans les allocations relues
pouvait aussi être remplacé par un bloc déclaré plus loin. Le calcul de
taille refuse maintenant les allocations nécessaires hors de `[2,128[` et
un RC supérieur à 128, avant d'indexer les seize allocations de l'entrée.
La copie recontrôle les blocs effectivement utilisés, avant toute écriture,
même lorsque leur secteur de catalogue a changé depuis le calcul de taille.

L'image reste ouverte en lecture seule ; seules les sorties réservées par
création exclusive sont écrites et nettoyées. Les collisions, les originaux
et les fichiers déjà vérifiés restent conservés. Aucun volume brut ou banque
auxiliaire n'est écrit. Ces bornes ne fournissent pas une photographie
atomique d'une image modifiée simultanément, ni une atomicité physique des
écritures ProDOS en cas de coupure.

Le vrai C est exécuté sur des fichiers jetables avec 32 scénarios : deux
skews, mutations après validation ou après mesure, allocations zéro (avec
un bloc disponible après le trou), 1, 128 et 255, RC 129 et 255, collisions
avant CREATE. Les mutations sont injectées dans la réponse de lecture ;
l'image conserve ses octets. Sans les nouveaux contrôles, 24 assertions
échouent ; les huit autres contrôlent des refus déjà assurés. Tous passent
après correction, avec zéro écriture de données pour le fichier refusé,
aucun CREATE avant un refus de mesure, nettoyage du seul fichier réservé
pour les refus de copie, conservation des octets existants et fermeture de
la source. Les 26 tests CPM, 15 tests des gardes et huit tests 800K passent.
Builds et limites mémoire validés sur 65C02/6502, sans désactiver de garde :
CPM 8241/8247 octets, BSS fin `$3F84`/`$3F8B`, réserves 123/116 octets avant
`$4000`. Distributions reconstruites et contrôlées.

## DOS 3.3 : ESC après la lecture précédant l'écriture brute (11 octobre 2026)

La routine partagée `write_sector()` contrôlait ESC avant la protection et
la lecture du bloc de 512 octets contenant le secteur DOS à modifier. Une
annulation arrivée durant cette lecture pouvait encore laisser passer une
écriture, notamment le basculement du catalogue de DOSREPL vers le nouveau
fichier. Le contrôle est désormais répété immédiatement avant `writeblk()`,
après préparation du bloc dans MAIN. DOSWRITE, DOSREPL et DOS33W bénéficient
du même contrôle. La branche image n'est pas modifiée.

Les seules écritures possibles concernent le disque DOS précisément ciblé
et confirmé par l'interface : bitmap, données, listes et catalogue selon
l'opération. La source ProDOS reste en lecture seule. Le secteur voisin
reste conservé par le read-modify-write existant ; aucune mémoire auxiliaire
n'est utilisée. L'annulation ne restaure pas les réservations déjà écrites
et ne peut interrompre sans risque une écriture physique déjà commencée.
Aucune atomicité en cas de coupure n'est promise.

Le vrai point d'entrée DOSREPL C est exécuté sur des disquettes jetables.
82 nouveaux scénarios croisent TXT/BIN/BAS, sources de 0/1/513 octets,
chaque lecture précédant une écriture jusqu'au basculement du catalogue,
ESC seul ou accompagné d'une erreur de lecture. Avant correction, les 41
cas ESC seul échouent, dont ceux qui remplacent encore les octets de l'ancien
fichier malgré l'annulation ; les erreurs MLI étaient déjà refusées. Tous
passent après correction. Les tests contrôlent les octets de l'ancien
fichier et du voisin, la source inchangée et l'absence d'écriture après le
point annulé. Pour la première écriture, toute l'image doit rester identique.

11 tests DOSREPL, 15 DOSWRITE, 17 DOS33W, 15 tests des gardes et huit tests
800K passent. Builds et dispositions mémoire validés sur 65C02/6502, avec
gardes actives. DOSREPL mesure 7526/7624 octets, BSS fin `$3F86`/`$3FE9`, soit
121/22 octets libres avant `$4000`. DOSWRITE conserve 457/373 octets et DOS33W
2786/2725 octets. Distributions reconstruites et contrôlées.

## DISKCMP : pas de verdict complet après ESC tardif (11 octobre 2026)

DISKCMP contrôlait ESC au début de chaque groupe de blocs, mais pas après
la dernière lecture, les sondes EOF ou la fermeture des images. Une
annulation à ces endroits pouvait donc laisser affiché `Identical` ou le
nombre définitif de blocs différents. Un contrôle précède maintenant le
verdict, et un autre le refuse après fermeture des deux sources. Les
erreurs de fermeture restent prioritaires et signalent une comparaison
incomplète, même accompagnées d'ESC.

L'opération reste strictement en lecture seule : seules les sources et les
tampons MAIN sont lus ou mis à jour ; aucun fichier, volume ou banque AUX
n'est écrit. Les deux images sont fermées, y compris après annulation. La
comparaison ne fournit pas une photographie atomique de sources modifiées
simultanément.

Le vrai point d'entrée C est testé sur des images et volumes jetables.
48 nouveaux scénarios couvrent PO/DO/2MG, volumes sur deux lecteurs, données
identiques ou différentes, ESC sur la dernière lecture de chaque source,
chaque sonde EOF et chaque fermeture, avec ou sans erreur de fermeture.
Avant correction, 36 cas laissaient un verdict complet ; les 12 autres
vérifient les erreurs de fermeture déjà traitées. Tous passent après
correction, avec contrôle des octets inchangés et fermeture des deux images.
Les 17 tests DISKCMP, 15 tests des gardes et huit tests 800K passent.
Builds et limites mémoire validés sur les deux processeurs, gardes actives :
DISKCMP 7686/7661 octets (65C02/6502), BSS fin `$3F97`/`$3F7F`, réserves
104/128 octets avant `$4000`. Distributions reconstruites et contrôlées.

## RESCUE : taille finale du fichier avant COMPLETE (11 octobre 2026)

La sonde EOF à la taille annoncée détectait une source agrandie, mais pas
une source raccourcie pendant la confirmation : un SEEK au-delà d'EOF peut
réussir, et les lectures manquantes sont volontairement remplacées par des
zéros lors d'une récupération. RESCUE pouvait donc journaliser COMPLETE à
l'ancienne taille. Après fermeture de la source, sa taille est désormais
relue dans le catalogue et comparée au nombre d'octets récupérés avant
COMPLETE. Une taille différente, introuvable, une erreur de lecture ou de
fermeture du catalogue, ou ESC pendant ce contrôle conduit à INCOMPLETE.
La branche récupération de volume brut n'est pas modifiée.

Seuls les fichiers de récupération et leur journal, réservés par création
exclusive, sont écrits. La source reste en lecture seule ; aucune banque
auxiliaire ni volume brut n'est écrit. Les octets déjà récupérés, les
fichiers préexistants et le journal sont conservés sur refus. Ce contrôle
de longueur ne détecte pas une modification de contenu à taille identique
et n'offre pas une photographie atomique de la source ni une atomicité
physique des écritures ProDOS en cas de coupure.

Le vrai point d'entrée C est testé sur des fichiers jetables avec 23
nouveaux scénarios : quatre tailles dont zéro, réduction du fichier pendant
la confirmation (pour les tailles non nulles), erreur de recherche ou de
fermeture du catalogue final, ouverture impossible, nom absent et ESC à la
fermeture du catalogue. Les 15 premiers scénarios reproduisaient le faux
COMPLETE avant correction ; les autres couvrent les limites ajoutées.
Les tests contrôlent les octets récupérés (y compris les zéros attendus),
ceux des fichiers préexistants et de la source, l'absence de COMPLETE, le
dernier enregistrement INCOMPLETE et zéro flux laissé ouvert.
Les 13 tests RESCUE, 15 tests des gardes et huit tests 800K passent.
Builds et dispositions valides, sans désactiver de garde : RESCUE 7014/7086
octets (65C02/6502), BSS fin `$383C`/`$3885`, réserves 1987/1914 octets avant
`$4000`. Distributions reconstruites et contrôlées.

## PASCALW : borne d'allocation relue après validation (11 octobre 2026)

`read_dir()` valide toutes les entrées puis `find_tail()` relit la dernière
pour choisir le premier bloc de l'import. Cette seconde lecture ne devait
pas changer sa borne : un dernier bloc plus petit pouvait envoyer les
écritures sur le démarrage, le catalogue ou les données d'un fichier déjà
présent. Le dernier bloc de l'entrée validée, que `read_dir()` laisse dans
`ent`, est désormais conservé et comparé à la relecture. Toute différence
refuse avant une écriture, y compris après la confirmation de l'utilisateur.

Seule l'image confirmée peut recevoir des écritures de données puis de
catalogue, avec les contrôles et restaurations existants. Les sources
ProDOS restent ouvertes en lecture seule et aucune mémoire auxiliaire ou
volume brut n'est écrit. Ce contrôle ne fournit pas une photographie
atomique d'une image modifiée simultanément ; les écritures physiques et
restaurations ProDOS ne sont pas atomiques en cas de coupure.

Le vrai C est exécuté sur des images jetables PO, DO et 2MG. 48 scénarios
font varier la borne uniquement dans la réponse de relecture, après la
validation qui suit la confirmation : huit bornes différentes et deux
tailles de source. Avant correction, 42 cas écrivaient malgré la différence ;
les six bornes hors volume étaient déjà refusées. Tous sont désormais
refusés sans écriture, avec image et sources intégralement inchangées.
Six contrôles avec borne identique importent correctement et vérifient les
octets de l'ancien et du nouveau fichier. Les 30 tests PASCALW, 15 tests des
gardes et huit tests 800K passent. Builds et dispositions valides, gardes
actives : PASCALW 7742/7737 octets (65C02/6502), BSS fin `$3CB0`/`$3CAC`,
réserves 847/851 octets avant `$4000`. Distributions reconstruites et contrôlées.

## CPMW : entrée libre jusqu'à la publication (11 octobre 2026)

CPMW choisissait une entrée libre avant les écritures de données, puis la
relisait avant publication sans contrôler qu'elle était encore libre. Un
fichier apparu entre-temps pouvait perdre son entrée. La relecture vérifie
désormais le marqueur libre `$E5`, et le contrôle est répété dans les octets
du bloc partagé relu par `cpm_write()` avant de remplacer le secteur. ESC
est contrôlé après la relecture d'entrée et après la lecture du bloc partagé,
avant toute écriture physique. Une annulation ou une entrée occupée à ces
points ne déclenche pas de restauration d'un bloc qui n'a pas été écrit.

Seule l'image confirmée peut recevoir les données encore non référencées
et l'entrée publiée. Les sources ProDOS restent en lecture seule ; aucune
mémoire auxiliaire ni volume brut n'est écrit. Un refus laisse les blocs de
données non référencés et préserve le catalogue, le fichier arrivé et les
fichiers existants. Le secteur voisin reste protégé par les contrôles et
restaurations du bloc complet. Un changement entre la dernière lecture et
l'écriture reste possible ; ni les écritures physiques ni leur restauration
ne sont atomiques en cas de coupure.

Le vrai point d'entrée C est testé sur des images jetables PO, DSK et 2MG.
30 scénarios croisent deux tailles de source et une arrivée d'entrée vide
dans les utilisateurs 0 ou 15, ESC lors des deux lectures précédant la
publication, ou une réponse de dernière lecture indiquant un emplacement
occupé. Les 18 scénarios initiaux reproduisaient l'écrasement/publication
avant correction ; six scénarios supplémentaires reproduisaient encore
l'écriture après ESC pendant le read-modify-write. Les six derniers couvrent
la vérification dans le bloc réellement lu pour cette écriture.
Tous passent, avec catalogue complet conservé (hormis l'arrivée injectée),
octets des fichiers existants et des sources inchangés, entrée arrivée
conservée, aucun nouveau fichier publié et aucune écriture de catalogue.
Les 25 tests CPMW, 15 tests des gardes et huit tests 800K passent. Builds et
dispositions valides, gardes actives : CPMW 8036/8009 octets (65C02/6502), BSS
fin `$3FAE`/`$3F94`, réserves 81/107 octets avant `$4000`. Distributions
reconstruites et contrôlées.

## PASCALW : ESC pendant la lecture du catalogue (11 octobre 2026)

Le dernier contrôle d'annulation de `one()` précédait `commit()`. Un ESC
arrivé pendant une lecture de bloc dans `patch()` laissait donc écrire
l'entrée et relever le compteur de fichiers. Le contrôle suit maintenant
chaque lecture, avant toute modification du bloc et avant son écriture.
Cela couvre l'entrée à cheval sur deux blocs et la publication du compteur
séparée de l'entrée. La restauration après une écriture défectueuse reste
obligatoire même après ESC. L'interface signale l'annulation.

Seule l'image confirmée est écrite : les données déjà copiées et d'éventuels
fragments d'entrée restent hors du catalogue actif. Les fichiers sources
sont uniquement lus ; aucune mémoire auxiliaire n'est utilisée. Cette
correction ne fournit pas d'atomicité en cas de coupure pendant une écriture
physique.

Le vrai C est exercé sur des images jetables PO, DOS et 2MG, avec 1, 18 et
19 fichiers existants, deux tailles de source et une annulation à chaque
lecture physique précédant une écriture du catalogue : 40 scénarios. Ils
contrôlent le nombre exact d'écritures, tous les octets des anciens fichiers,
le catalogue actif inchangé et les sources inchangées. Les 31 tests PASCALW,
15 tests des gardes et 8 tests des distributions passent. Les deux builds
et leurs gardes restent actifs : PASCALW 7766/7762 octets (65C02/6502), BSS
fin `$3CC8`/`$3CC5`, marges de 823/826 octets avant `$4000`. Les distributions
sont reconstruites et contrôlées.

## PASCALW : compteur frais avant publication (11 octobre 2026)

Après la copie et la fermeture de la source, `commit()` utilisait encore
le compteur validé avant la copie. Une entrée ajoutée entre-temps pouvait
être écrasée à l'index `count+1`, puis le compteur réécrit avec la valeur
périmée. Le bloc du compteur est maintenant relu et comparé avant la
première écriture d'une entrée séparée ou à cheval sur deux blocs ;
`patch()` compare aussi le compteur dans le bloc effectivement publié.
Toute différence ou erreur de lecture refuse la publication. Le compteur
est comparé sur ses deux octets.

L'opération écrit uniquement l'image confirmée ; sources en lecture seule,
aucun accès à la mémoire auxiliaire. Les blocs de données déjà copiés restent
hors du catalogue actif. Cette vérification détecte un compteur modifié aux
lectures contrôlées : elle n'est pas un verrou contre un autre écrivain
concurrent et ne garantit pas l'atomicité d'une écriture physique interrompue.

Le vrai code C est testé sur des images jetables PO, DOS et 2MG, avec 0, 1,
18 ou 19 entrées existantes et deux tailles de source. Une écriture externe
à la fermeture de la source ajoute réellement ARRIVED dans la place prévue
pour l'import : 24 scénarios vérifient son entrée et son contenu, l'ensemble
du catalogue, les octets des anciens fichiers et les sources. Les 64
scénarios de lectures courtes ou signalant une erreur refusent toute écriture
de catalogue. Les tests d'ESC ont été adaptés à la lecture supplémentaire :
56 scénarios vérifient chaque lecture précédant une écriture du catalogue.
Les 33 tests PASCALW, 15 gardes et 8 contrôles de distribution passent.
Les deux builds gardent leurs contrôles actifs : PASCALW 7863/7864 octets
(65C02/6502), BSS fin `$3D29`/`$3D2B`, marges de 726/724 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## CPMW : voisins frais dans le secteur publié (11 octobre 2026)

`entry_at()` chargeait le secteur du catalogue dans `dsec`, puis
`cpm_write()` relisait le bloc partagé avant l'écriture. Le contrôle du
slot empêchait d'écraser une entrée devenue occupée, mais la copie des
256 octets de `dsec` effaçait une modification d'une autre entrée survenue
entre ces deux lectures. Le vrai C reproduisait cette perte dans 84 cas.

Lors de la publication, `cpm_write()` vérifie toujours que son slot est
libre, reconstruit `dsec` depuis le secteur fraîchement lu et y place
uniquement `newent`. Le reste du secteur et la moitié voisine du bloc
physique sont préservés. La sauvegarde de restauration contient elle aussi
ces octets frais. Les écritures concernent uniquement l'image confirmée,
avec sources en lecture seule et aucun accès AUX. Cela ne fournit pas de
verrou contre un écrivain concurrent ni d'atomicité sur coupure physique.

Les 252 scénarios de régression exécutent le C sur des images jetables :
deux ordres CP/M, trois conteneurs PO/DOS/2MG, deux tailles de source,
sept slots voisins et trois résultats de publication (réussite, écriture
partielle, corruption suivie de restauration). Une modification externe
réelle intervient avant la dernière lecture du bloc. Les contrôles portent
sur les entrées modifiées, le catalogue entier, les octets des anciens
fichiers, le nouvel import ou son absence après restauration et les sources.
Les 26 tests CPMW, 15 gardes et 8 contrôles de distribution passent. Les deux
builds gardent leurs contrôles actifs : CPMW 8090/8059 octets (65C02/6502),
BSS fin `$3FE4`/`$3FC6`, marges de 27/57 octets avant `$4000`. Les distributions
sont reconstruites et contrôlées.

## PASCAL : annulation avant CREATE (11 octobre 2026)

`one()` relisait l'entrée du catalogue, puis créait sa sortie sans vérifier
ESC avant CREATE. Une annulation pendant cette relecture entraînait donc
une création suivie de nettoyage, ou une tentative CREATE sur un nom déjà
pris. Les 88 scénarios d'annulation seule reproduisaient cette écriture
inutile. Le contrôle suit maintenant `entry_at()`, avant le traitement des
métadonnées et avant toute création. Les sorties déjà vérifiées restent
conservées ; l'image est uniquement lue et aucune mémoire AUX n'est touchée.

Le vrai C est testé sur des images jetables PO, DOS et 2MG de 19 fichiers,
avec deux tailles de contenu et ESC à chaque lecture physique de la
première, deuxième et dix-neuvième entrée (cette dernière est à cheval sur
deux blocs). Les collisions sur la cible ou sur une sortie précédente
sont incluses. Les 176 scénarios couvrent l'annulation seule et accompagnée
d'une erreur de lecture : nombre de CREATE strictement limité aux entrées
antérieures, tous les octets des sorties conservées et de l'image contrôlés,
source fermée une fois. Le banc choisit désormais le format d'image depuis
son nom pour exécuter réellement les trois lecteurs.

Les 18 tests PASCAL, 15 gardes et 8 contrôles de distribution passent.
Les builds restent soumis aux gardes : PASCAL 7295/7286 octets (65C02/6502),
BSS fin `$3A95`/`$3A8D`, marges de 1386/1394 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## CPM : annulation des scans avant CREATE (11 octobre 2026)

Les lectures de catalogue effectuées avant `one()` pouvaient recevoir ESC,
mais cette fonction créait sa sortie sans consulter l'annulation. Le
premier contrôle arrivait pendant la copie, après CREATE et éventuellement
une écriture ; un nom déjà pris était aussi sondé par CREATE malgré ESC.
Les 192 cas d'annulation seule reproduisaient une tentative CREATE en trop.
Le contrôle ouvre maintenant `one()` : aucune création pour le fichier
courant, même vide ou déjà présent. Les sorties antérieures vérifiées sont
conservées. L'image source est uniquement lue et la mémoire AUX est intacte.

Les 384 scénarios exécutent le vrai C sur des images jetables : deux ordres
CP/M, trois conteneurs PO/DOS/2MG, fichier cible vide, d'un octet ou de
17000 octets (plusieurs extents), trois positions dans l'extraction,
collisions sur la cible ou un fichier antérieur, annulation seule ou avec
erreur de lecture et les deux lectures physiques DOS. Ils vérifient le
nombre exact de CREATE, tous les octets des sorties conservées et de
l'image source, ainsi que la fermeture unique de la source. Le banc choisit
le lecteur depuis le nom du conteneur et compte les sorties vérifiées ou
ignorées pour injecter ESC avant le bon fichier.

Les 27 tests CPM, 15 gardes et 8 contrôles de distribution passent. Les deux
builds gardent leurs contrôles actifs : CPM 8258/8264 octets (65C02/6502),
BSS fin `$3F95`/`$3F9C`, marges de 106/99 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## RESCUE : ESC avant création du journal ou d'une partie (11 octobre 2026)

RESCUE consultait ESC après la création d'une partie. Une annulation reçue
pendant la fermeture du journal initial pouvait donc créer une sortie vide
ou tenter CREATE sur un fichier déjà présent. De même, un ESC arrivé avant
la création du journal, ou à la fermeture d'une partie brute de 8192000
octets, ne bloquait pas la création suivante. Le contrôle précède désormais
le premier CREATE et chaque ouverture de partie ; le contrôle après
l'ouverture est aussi conservé pour les annulations pendant CREATE/OPEN.

Les seules écritures autorisées concernent les sorties exclusivement
créées et le journal possédé par RESCUE. L'annulation avant le premier CREATE
ne crée rien ; ensuite le journal reçoit INCOMPLETE et les parties déjà
écrites sont conservées. Sources et fichiers préexistants restent intacts,
aucun accès AUX n'est introduit.

Le vrai C est exercé dans 34 nouveaux scénarios sur données jetables :
fichiers de 0, 1 et 1600 octets, volumes bruts de 3 et 280 blocs, ESC avant
le journal ou à sa fermeture (avec ou sans erreur), collisions sur la sortie,
puis quatre annulations à la fermeture de la première partie de 8192000
octets (avec ou sans erreur et collision sur P02). Les contrôles vérifient
le nombre exact de CREATE, tous les octets des sources et sorties conservées,
l'absence de nouvelle sortie, INCOMPLETE dans le journal et les fermetures
sans fuite. Les 20 cas d'annulation initiale sans erreur reproduisaient le
CREATE supplémentaire avant correction.

Les 15 tests RESCUE, 15 gardes et 8 contrôles de distribution passent. Les
deux builds gardent leurs contrôles actifs : RESCUE 7074/7146 octets
(65C02/6502), BSS fin `$3878`/`$38C1`, marges de 1927/1854 octets avant
`$4000`. Les distributions sont reconstruites et contrôlées.

## PASCALW : géométrie fraîche avant publication (11 octobre 2026)

La publication vérifiait le compteur frais mais conservait la taille de
volume validée avant la copie. Un en-tête modifié sans changer ce compteur
pouvait donc recevoir une nouvelle entrée dont les blocs dépassaient la
nouvelle limite, ou une entrée dans un catalogue devenu malformé.
`same_volume()` vérifie désormais les mots de début, fin et type de
l'entrée de volume, ainsi que sa taille et son compteur. Cette vérification
utilise les mêmes lectures déjà effectuées avant les écritures : avant une
entrée séparée ou partagée entre deux blocs, et dans le bloc portant le
compteur au moment de publier. Toute différence refuse la publication.

Seule l'image confirmée peut être écrite ; les blocs de données antérieurs
restent non référencés après refus. Sources en lecture seule, aucun accès
AUX. Il ne s'agit pas d'un verrou contre les modifications concurrentes,
et aucune atomicité sur coupure physique n'est promise.

Le vrai C reproduisait les 144 scénarios de refus avant correction. Les
images jetables PO, DOS et 2MG contiennent 0, 1, 18 ou 19 fichiers, les
sources ont 1 ou 1500 octets. Une écriture externe réelle à la fermeture de
la source réduit la limite à la fin du dernier fichier, dépasse la taille
du conteneur ou modifie les mots de structure de l'en-tête. Les tests
contrôlent le catalogue entier préservé après cette mutation, les octets
des anciens fichiers et des sources et l'absence d'écriture de publication.
Les 24 témoins dont l'en-tête reste identique vérifient aussi les octets de
l'import réussi. Les 34 tests PASCALW, 15 gardes et 8 contrôles de distribution
passent. Les builds gardent leurs contrôles actifs : PASCALW 7921/7922 octets
(65C02/6502), BSS fin `$3D63`/`$3D65`, marges de 668/666 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## CPM : une entrée disparue n'est pas un fichier vide (11 octobre 2026)

`measure()` validait la somme des records contre l'extent terminal, mais
une identité sans aucune entrée correspondante donnait aussi zéro des
deux côtés. Si une relecture du catalogue perdait l'entrée sauvegardée
par l'appelant, l'extraction pouvait donc créer et vérifier une sortie vide,
ou compter une collision, malgré l'absence de fichier mesurable. Le bitmap
des extents doit maintenant contenir le bit zéro avant d'autoriser CREATE,
même pour un fichier vide. Aucune mémoire supplémentaire n'est nécessaire.
Seules les sorties exclusivement créées peuvent être écrites ; images et
fichiers préexistants restent intacts et aucun accès AUX n'est introduit.

Les 96 cas de refus reproduisaient le CREATE supplémentaire dans le vrai C.
Le banc utilise neuf fichiers pour obliger `measure()` à relire le secteur
de l'entrée cible après avoir sauvegardé son identité. Il simule alors une
entrée supprimée, renommée, passée à un autre utilisateur ou effacée. Deux
tailles (0 et 1500 octets), deux ordres CP/M, trois conteneurs PO/DOS/2MG et
les collisions sur la sortie sont couverts. Les octets de toutes les huit
sorties antérieures, des fichiers préexistants et de l'image sont contrôlés,
avec aucun CREATE pour la cible et une fermeture unique de la source.
Les 24 témoins sans mutation vérifient aussi l'extraction correcte du fichier
vide ou non vide, ou la préservation du nom déjà pris.

Les 28 tests CPM, 15 gardes et 8 contrôles de distribution passent. Les deux
builds gardent leurs contrôles actifs : CPM 8284/8274 octets (65C02/6502),
BSS fin `$3FAF`/`$3FA6`, marges de 80/89 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## CPM : records relus cohérents avec la taille mesurée (11 octobre 2026)

`copy_file()` relisait les extents, mais utilisait exclusivement `fsize`
pour déterminer le nombre d'octets à copier. Un compteur de records modifié
après `measure()` était ignoré : la copie pouvait lire au-delà du nouvel
EOF ou accepter un préfixe comme complet. Le compteur frais de chaque
extent doit maintenant correspondre au reste mesuré : 128 records pour
un extent complet, puis le nombre exact de records du dernier extent.
Le reste est un multiple de 128 ; la conversion en entier 16 bits intervient
uniquement lorsqu'il ne dépasse pas 16384, et le compteur attendu tient
sur un octet. Seule la sortie possédée est nettoyée en cas d'échec ; l'image,
les fichiers préexistants et AUX restent intacts.

Le vrai C reproduisait les 132 cas incohérents avant correction. Les données
jetables de 1, 1536 ou 17000 octets couvrent deux ordres CP/M et trois
conteneurs PO/DOS/2MG. Les compteurs 0, 1, 127, 128, 129 et 255 sont fournis
uniquement lors de la relecture après CREATE, dans le premier ou dernier
extent. Les tests vérifient l'absence de sortie acceptée, les octets du
fichier préexistant et de l'image, la fermeture unique, et l'arrêt avant
les écritures de l'extent incohérent (64 écritures antérieures uniquement
pour le second extent). Les 24 témoins aux compteurs inchangés vérifient
les octets complets du fichier extrait.

Les 29 tests CPM, 15 gardes et 8 contrôles de distribution passent. Les deux
builds gardent leurs contrôles actifs : CPM 8364/8358 octets (65C02/6502),
BSS fin `$3FFF`/`$3FFA`, marges de 0/5 octets avant `$4000`. La fenêtre
65C02 est entièrement occupée : toute extension devra libérer de la place
sans désactiver les gardes. Les distributions sont reconstruites et contrôlées.

## SMALLDOS : ESC pendant une lecture de secteur (11 octobre 2026)

`pass()` vérifiait ESC après l'écriture et avant la lecture suivante, mais
un ESC reçu pendant `sector()` laissait encore écrire les 256 octets lus.
Le contrôle suit maintenant chaque lecture, avant WRITE ou la lecture de
vérification. Seule la sortie exclusivement créée peut être nettoyée ; si
son nettoyage échoue, le message conserve cette information et les octets
partiels restent récupérables. L'image source, les fichiers préexistants
et AUX ne sont jamais modifiés.

Le banc SMALLDOS héritait du lecteur de test Pascal ; ses nouveaux hooks
spécifiques au catalogue rendaient ce banc incompatible. Son lecteur est
maintenant remplacé explicitement par les hooks SMALLDOS, et le nom court
fourni au programme est conservé pour choisir le bon ordre de secteurs.
Les hooks de corruption, annulation de lecture et erreurs complètes sont
actifs de nouveau. Les anciens remplacements de corps devenus inopérants
ont été retirés.

Les 168 cas d'annulation sans erreur de lecture reproduisaient l'écriture
supplémentaire avant correction. Les 252 scénarios passent : deux directions
de pistes, ordres DOS/ProDOS, fichiers de 1, 513 ou 4097 octets, annulation
pendant chacune de leurs lectures de secteur, seule ou avec erreur de
lecture ou échec de suppression de la sortie possédée. Ils vérifient le
nombre exact d'écritures, tous les octets du préfixe conservé en cas de
nettoyage impossible, les fichiers préexistants, l'image inchangée et sa
fermeture unique.

Les 14 tests SMALLDOS, 18 tests Pascal, 15 gardes et 8 contrôles de
distribution passent. Les deux builds gardent leurs contrôles actifs :
SMALLDOS 4430/4473 octets (65C02/6502), BSS fin `$310C`/`$3138`, marges de
3827/3783 octets avant `$4000`. Les distributions sont reconstruites et
contrôlées.

## UNSQ : vérification octet par octet après une seconde décompression (11 octobre 2026)

La relecture de sortie comparait seulement sa longueur et sa somme 16 bits.
Une permutation de deux octets conservait ces deux valeurs et était annoncée
comme vérifiée, même après une véritable écriture corrompue. Les 18 nouveaux
cas de permutation à l'écriture (avec nettoyage réussi ou impossible)
reproduisaient cette acceptation avant correction.

`read_back()` revient maintenant au début du flux du fichier courant et
le décode une seconde fois. `putb()` compare alors chaque octet attendu avec
la sortie relue par blocs de 512 octets dans le tampon `obuf` existant.
Les octets restant dans ce tampon et la sonde EOF détectent une sortie
plus longue ; les lectures courtes, erreurs, annulations et fermetures
empêchent la validation. Les records ACU suivants sont repris à leur
position normale. La seconde décompression ajoute du calcul mais les
lectures ProDOS restent groupées, sans appel de lecture par octet.

La sortie est exclusivement créée et seule cette sortie peut être nettoyée.
Une suppression impossible laisse les octets corrompus récupérables et le
message de nettoyage prime. Les archives, les destinations préexistantes
et AUX ne sont pas modifiés. Aucun tampon de données supplémentaire n'est
alloué : après le repositionnement, la variable du décalage sert au nombre
d'octets pour la barre de vérification. Les deux builds passent les gardes
sans les désactiver ; une première version dépassait d'un octet en 6502
et a été corrigée par cette réutilisation, pas par un relâchement de limite.

Les 36 nouveaux scénarios couvrent QQ, ACU stocké et ACU comprimé, avec
2, 513 ou 2000 octets, permutation à l'écriture, permutation dans la réponse
de relecture, permutation avec nettoyage impossible et témoins sains.
Ils contrôlent les octets des archives et destinations préexistantes,
l'absence de sortie acceptée, les octets exacts conservés après nettoyage
impossible et la fermeture unique de la source. Les anciens tests de
progression, EOF, fermeture et annulation passent également ; l'injection
entre deux records ACU distingue désormais le repositionnement de
vérification du repositionnement vers le record suivant.

Les 25 tests UNSQ, 15 gardes et 8 contrôles de distribution passent.
UNSQ mesure 7300/7380 octets (65C02/6502), BSS fin `$3FAB`/`$3FFC`, marges de
84/3 octets avant `$4000`. Les distributions sont reconstruites et contrôlées.

## SCIIBIN : fichiers ordinaires dans chaque morceau (11 octobre 2026)

Le contrôle des métadonnées refusait les fichiers étendus (stockage 5)
et les répertoires (stockage `$0D`) uniquement dans le premier morceau.
Un morceau suivant de même nom, type, auxiliaire et longueur pouvait
ainsi être ajouté et annoncé comme décodé malgré ces métadonnées non prises
en charge. Le contrôle est maintenant effectué pour chaque en-tête avant
CREATE ou ajout de données. Les types de stockage ordinaires 1, 2 et 3
restent acceptés ; aucun besoin de mémoire auxiliaire n'est introduit.

Les 24 nouveaux cas négatifs échouaient avant correction. Ils couvrent
deux stockages interdits, trois longueurs de dernier morceau, une archive
unique ou deux fichiers et un nettoyage réussi ou impossible. Dans ce
dernier cas, le vrai code C conserve exactement le premier morceau de
12288 octets, sans ajouter les données incompatibles. Les sources et le
fichier préexistant KEEP sont comparés octet par octet. Les 18 témoins
avec stockage ordinaire contrôlent la sortie complète. La référence Python
applique également la restriction à chaque morceau.

Les 18 tests SCIIBIN, 15 tests de gardes et 8 contrôles de distribution
passent. Les builds 65C02/6502 et les contrôles de disposition passent :
SCIIBIN reste à 6659/6677 octets, BSS fin `$3FD5`/`$3FE8`, marges de
42/23 octets avant `$4000`. Les distributions sont reconstruites.

## UNWRAP : lecture validée avant écriture d'un bloc (11 octobre 2026)

La copie de la fourche de données écrivait chaque bloc dès que fread
renvoyait le compte demandé. Une erreur signalée avec ce compte, ou ESC
pendant la lecture, n'était contrôlée qu'après l'écriture. L'opération
échouait finalement, mais si le nettoyage était impossible, la sortie
conservait aussi ce bloc douteux ou interrompu.

`pass()` contrôle maintenant l'indicateur d'erreur et l'annulation juste
après la lecture source, avant toute écriture de ce bloc. Seule la sortie
exclusivement créée peut être écrite ou nettoyée. Les sources, les fichiers
préexistants et AUX restent intacts ; les tampons restent dans MAIN.
Une suppression impossible conserve uniquement le préfixe précédemment
copié et donne toujours le message de nettoyage impossible.

Les 120 nouveaux scénarios échouaient avant correction. Le vrai code C
est exécuté pour AppleSingle 1/2 et MacBinary 1/2/3, avec des fourches de
1, 513 ou 1536 octets. Les fautes couvrent une erreur à compte complet ou
ESC sur le premier ou dernier bloc, avec nettoyage réussi ou impossible.
Les tests contrôlent le nombre d'octets transmis à fwrite, le préfixe exact
conservé, les octets de la source et du fichier préexistant KEEP, ainsi que
le nettoyage limité à DOC. Les anciens contrôles d'extraction passent.

Les 45 tests UNWRAP, 15 tests de gardes et 8 contrôles de distribution
passent. Les builds et dispositions 65C02/6502 sont validés sans relâcher
les limites : UNWRAP mesure 7875/7905 octets, BSS fin `$3FAA`/`$3FC9`,
marges de 85/54 octets avant `$4000`. Les distributions sont reconstruites.

## PASCAL : ESC après lecture, avant écriture du bloc (11 octobre 2026)

L'extracteur contrôlait ESC après l'écriture de chaque bloc. Une annulation
reçue pendant la lecture de l'image pouvait donc encore écrire ce bloc
dans la sortie exclusivement créée. L'opération échouait ensuite, mais
un nettoyage impossible laissait aussi ces octets interrompus.

`copy_file()` contrôle maintenant ESC immédiatement après `source_read()`,
avant l'écriture ou la relecture de la sortie. Le contrôle existant des
erreurs de lecture à compte complet reste actif. Seules les sorties
exclusivement créées sont écrites ou nettoyées ; l'image, les destinations
préexistantes et AUX restent intacts. Aucune allocation supplémentaire.

Les 120 nouveaux scénarios exécutent le vrai C sur des images PO, DOS et
2MG contenant un fichier de 1, 513 ou 1536 octets. Chaque lecture physique
de données est interrompue : pour DOS, chaque demi-bloc est couvert.
Les modes comprennent ESC, ESC avec nettoyage impossible, ESC avec erreur
de lecture et erreurs sans ESC avec ou sans nettoyage possible. Avant
correction, les 48 cas d'ESC sans erreur écrivaient un bloc supplémentaire ;
les 72 témoins d'erreur étaient déjà refusés. Tous passent maintenant avec
contrôle du nombre d'écritures, du préfixe exact conservé, de KEEP, des
octets de l'image et de sa fermeture unique.

Les 19 tests PASCAL, 14 tests SMALLDOS utilisant le même harnais, 15 gardes
et 8 contrôles de distribution passent. Builds et dispositions 65C02/6502
validés : PASCAL mesure 7306/7296 octets, BSS fin `$3AA0`/`$3A97`, marges
de 1375/1384 octets avant `$4000`. Les distributions sont reconstruites.

## MKIMAGE : annulation avant CREATE et première écriture (11 octobre 2026)

Une annulation reçue à la fin du prompt de nom n'était contrôlée qu'à la
première barre de progression : CREATE et OPEN avaient déjà eu lieu.
Pour 2MG, l'en-tête de 64 octets était même écrit avant ce contrôle, y
compris après ESC pendant CREATE ou OPEN. Un nettoyage impossible laissait
alors cet en-tête malgré l'annulation avant toute écriture souhaitée.

MKIMAGE contrôle maintenant ESC avant CREATE, puis après OPEN et avant
l'en-tête 2MG ou le premier bloc. Avant CREATE, aucune destination n'est
possédée ni nettoyée. Après une création exclusive, seule cette sortie
est fermée et nettoyée ; un nettoyage impossible conserve un fichier vide
avec le message correspondant. Les destinations préexistantes et AUX
restent intacts, sans nouveau tampon.

Les 120 scénarios supplémentaires exécutent le vrai C pour PO et 2MG,
les six tailles proposées, ESC au prompt, à CREATE ou à OPEN, nettoyage
réussi ou impossible et collision avec des octets préexistants. Les 48
cas fautifs échouaient avant correction ; les 72 autres étaient déjà
refusés sans écriture. Les tests contrôlent CREATE, OPEN, WRITE et CLOSE,
les octets préexistants et le fichier vide retenu après nettoyage impossible.

Les 7 tests MKIMAGE, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : MKIMAGE mesure 4734/4834 octets,
BSS fin `$30A8`/`$310D`, marges de 3927/3826 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## MOVE : ESC pendant les métadonnées avant CREATE ou suppression (11 octobre 2026)

Le déplacement entre volumes contrôlait ESC avant le dernier appel de
GET_FILE_INFO, puis supprimait immédiatement la source si ses métadonnées
étaient valides. ESC reçu pendant cet appel n'était donc pas pris en compte :
la source était supprimée malgré l'annulation. Le premier contrôle des
métadonnées pouvait également autoriser CREATE après réception d'ESC.

`copy_across()` contrôle maintenant ESC après chaque `standard_source()` :
avant CREATE au début et avant REMOVE après vérification. Dans le second
cas, la source et la copie fermée, vérifiée octet par octet, sont toutes
deux conservées. Au début, aucune destination n'est créée ou nettoyée.
L'opération écrit uniquement sa destination exclusive, supprime la source
uniquement après les contrôles complets et n'utilise pas AUX.

Les 24 nouveaux scénarios exécutent le vrai C avec des fichiers de 0, 1,
513 ou 1536 octets, ESC pendant le premier ou le dernier GET_FILE_INFO,
réponse correcte ou erreur, et collision initiale. Avant correction,
les 8 cas du premier contrôle réussi tentaient CREATE ; les 4 du dernier
contrôle réussi supprimaient la source. Les 12 témoins d'erreur étaient
déjà refusés. Tous passent avec contrôle des octets de la source, de la
copie vérifiée ou de la destination préexistante, et absence de CREATE
après l'annulation initiale.

Les 67 tests MOVE, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : MOVECOPY mesure 3067/3054 octets,
BSS fin `$29E5`/`$29D9`, marges de 5658/5670 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## MOVE : taille source relue après fermeture de la vérification (11 octobre 2026)

GET_FILE_INFO ne fournit pas l'EOF du fichier. Le dernier contrôle du
déplacement vérifiait type, auxiliaire, stockage et protection, mais une
source qui grandissait après fermeture des deux flux de vérification
était encore supprimée. La destination conservait uniquement l'ancien
contenu : les octets ajoutés étaient perdus. Une source raccourcie passait
également ce dernier contrôle.

`same_source_size()` relit maintenant l'entrée dans le catalogue source
avant REMOVE et exige la taille exacte vérifiée. Une entrée absente, une
ouverture ou fermeture de catalogue en erreur et ESC interdisent la
suppression. Source et copie vérifiée restent présentes. Le tampon scratch
de relecture, devenu libre après fermeture des flux, contient le chemin
parent ; le catalogue utilise le tampon résident buf. Aucun nouveau tampon
ni accès AUX, aucune écriture source avant sa suppression autorisée.

Les 27 nouveaux scénarios exécutent le vrai C avec 0, 1, 513 ou 1536
octets : ajout réel de TAIL ou raccourcissement réel après vérification,
entrée absente, erreur d'ouverture, erreur de fermeture après entrée trouvée,
ESC pendant la lecture et témoin normal. Les sept mutations réelles de
taille supprimaient la source avant correction. Les tests vérifient les
octets exacts de la source modifiée et de la copie originale, le refus de
suppression, le bon chemin parent et les ouvertures/fermetures du catalogue.
Les anciens tests de métadonnées, protections et annulation restent valides.

Les 68 tests MOVE, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : MOVECOPY mesure 3397/3390 octets,
BSS fin `$2B31`/`$2B2B`, marges de 5326/5332 octets avant `$4000`.
Les distributions sont reconstruites. Ce contrôle n'est pas un verrou :
une modification concurrente après la dernière lecture, ou à taille égale,
n'est pas exclue ; ProDOS ne fournit pas de suppression conditionnelle
atomique ni de garantie contre une coupure pendant une écriture physique.

## SCIIBIN : ESC pendant le texte avant ajout des octets (11 octobre 2026)

Le décodeur contrôlait ESC après l'ajout de chaque ligne de données.
Une annulation reçue pendant un remplissage du tampon texte de 512 octets
laissait donc encore ajouter la ligne décodée de 48 octets avant l'échec.
Si le nettoyage était impossible, le fichier retenu comprenait ces octets
ajoutés après l'annulation.

`chunk()` contrôle maintenant ESC avant fwrite, tout en conservant le
contrôle après l'écriture et la barre de progression. Seule la sortie
exclusivement créée peut être écrite ou nettoyée. Les sources, le fichier
préexistant KEEP et AUX restent intacts ; aucun nouveau tampon.

Les 24 nouveaux scénarios exécutent le vrai C pour des fichiers de 768,
1536 ou 12336 octets, aux trois premiers remplissages de données possibles.
Ils couvrent ESC seul, ESC avec nettoyage impossible et ESC avec lecture
à compte complet signalée en erreur. Tous échouaient avant correction
avec exactement 48 octets supplémentaires transmis à fwrite. Les tests
comparent le nombre d'octets écrits, le préfixe exact conservé lorsque
le nettoyage échoue et les octets des sources et destinations préexistantes.

Les 19 tests SCIIBIN, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés sans désactiver les limites :
SCIIBIN mesure 6679/6697 octets, BSS fin `$3FE9`/`$3FFC`, marges de
22/3 octets avant `$4000`. Les distributions sont reconstruites et contrôlées.

## SCIIBIN : refus immédiat d'un tampon texte en erreur (11 octobre 2026)

Le lecteur de lignes utilisait les octets d'un remplissage en erreur
tant que fread renvoyait un compte non nul. Le contrôle après l'en-tête
protégeait CREATE, et celui avant fermeture refusait finalement le fichier,
mais entre ces deux contrôles le décodeur pouvait écrire des données
douteuses. Un nettoyage impossible conservait ces octets supplémentaires.

`next_line()` refuse maintenant chaque remplissage dès que ferror est
signalé, à compte complet comme à compte court, avant d'utiliser ses octets.
Le contrôle ancien après l'en-tête est devenu redondant et supprimé ; le
contrôle final conserve le diagnostic Read. L'indicateur EOF, seulement
écrit et jamais lu, est également supprimé. Sources, destinations
préexistantes et AUX restent intacts ; seule la sortie exclusive peut
être écrite ou nettoyée, sans nouveau tampon.

Les 24 nouveaux scénarios exécutent le vrai C sur des fichiers de 768,
1536 et 12336 octets, aux trois premiers remplissages de données possibles.
Ils couvrent erreur à compte complet, erreur avec nettoyage impossible et
lecture courte signalée en erreur. Tous écrivaient trop d'octets avant
correction. Les tests vérifient le nombre d'octets transmis à fwrite, le
préfixe exact conservé après échec de nettoyage et les octets de la source
et de KEEP. Les anciens contrôles d'ESC, en-tête et CRC passent également.

Les 20 tests SCIIBIN, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : SCIIBIN mesure 6658/6676 octets,
BSS fin `$3FD3`/`$3FE6`, marges de 44/25 octets avant `$4000`.
La première version dépassait la limite 6502 de six octets ; le déplacement
du contrôle et la suppression de l'état inutilisé ont résolu ce dépassement,
sans désactiver aucune garde. Les distributions sont reconstruites et contrôlées.

## SCIIBIN : morceau borné par la longueur totale (11 octobre 2026)

Le décodeur validait la longueur de chaque morceau, mais pas sa place
dans la longueur totale annoncée. Un premier morceau trop long pouvait
créer et remplir un fichier avant refus final ; un dernier morceau pouvait
ajouter tous ses octets au-delà de cette limite. En cas de nettoyage
impossible, ces octets superflus restaient dans la sortie incomplète.

`chunk()` exige maintenant `written + seglen <= le24(attrs)` avant CREATE
ou ajout. La somme est élargie à 32 bits et le nombre maximal de morceaux
borne les octets accumulés à 3 Mio, sans risque de débordement. Un premier
morceau incohérent ne possède aucune sortie ; un morceau ultérieur refusé
ne permet de nettoyer que le fichier exclusivement créé par l'opération.
Sources, destinations préexistantes et AUX restent intacts.

Les 24 nouveaux scénarios échouaient avant correction : premiers morceaux
de 2, 48 ou 513 octets, total zéro ou inférieur d'un octet, avec ou sans
collision ; derniers morceaux de 2, 49 ou 12288 octets dépassant le total
d'un octet, en fichier unique ou deux parties, avec nettoyage réussi ou
impossible. Le vrai C est exécuté et les octets écrits, ceux des sources,
KEEP et les destinations préexistantes sont contrôlés. Un nettoyage
impossible conserve exactement le premier morceau de 12288 octets.
La référence Python applique également la borne avant ajout.

Le contrôle dépassait initialement la fenêtre native de 12/31 octets.
SCIIBIN utilise maintenant les relais `service_stubs.h` déjà employés par
les autres overlays : les appels à la même table de services coûtent moins
de code, sans nouveau tampon ni modification du protocole. Les gardes
restent actives. Les 21 tests SCIIBIN (CRC sous sim65 sur les deux CPU),
15 gardes et 8 contrôles de distribution passent. Builds et dispositions
65C02/6502 validés : SCIIBIN mesure 6087/6098 octets, BSS fin `$3D98`/`$3DA4`,
marges de 615/603 octets avant `$4000`. Les distributions sont reconstruites.

## UNSQ : longueur ACU contrôlée avant création et pendant le décodage (11 octobre 2026)

Les entrées ACU stockées étaient créées et entièrement écrites avant de
comparer leur taille à la longueur déclarée. Les entrées compressées
pouvaient également dépasser cette longueur avant refus et nettoyage.
De plus, une longueur ACU `$FFFFFFFF` devenait la sentinelle « longueur
inconnue » réservée aux fichiers .QQ : le contrôle final était contourné.

`acu()` refuse désormais une longueur supérieure à l'EOF ProDOS de
24 bits avant CREATE, même avec une collision. `one()` refuse une entrée
stockée dont la taille du fork diffère de la longueur annoncée avant
CREATE. Pour une entrée compressée, `putb()` refuse le premier octet
au-delà de la longueur déclarée, y compris au milieu d'une répétition
RLE et lors de la seconde décompression de vérification. Le tampon final
ne contient donc que des octets compris dans cette limite. Le contrôle
final de longueur reste nécessaire pour une sortie trop courte.

Seules les sorties exclusivement créées peuvent être écrites ou nettoyées.
Les sources, les noms préexistants, les extractions antérieures vérifiées
et AUX restent intacts. Un échec de nettoyage conserve la sortie partielle
et son diagnostic ; aucune atomicité en cas de coupure n'est ajoutée.

Les 92 nouveaux scénarios exécutent le vrai C : 72 refus avant création
sur des fichiers de 1, 513 et 1536 octets, avec tailles contradictoires,
tailles `$1000000`/`$FFFFFFFF`, collisions et extraction antérieure ;
20 dépassements compressés par RLE, avec longueur zéro ou inférieure
d'un octet, extraction antérieure et nettoyage réussi ou impossible.
82 scénarios échouaient avant correction ; les dix nettoyages réussis
contrôlaient déjà la suppression. Les octets des sources, de KEEP, des
noms pris et des sorties antérieures sont vérifiés. En cas de nettoyage
impossible, le fichier conservé contient exactement le préfixe annoncé.

UNSQ utilise les relais `service_stubs.h` existants pour conserver de la
marge native, sans nouveau tampon ni changement de table de services.
Les 27 tests UNSQ, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : UNSQ mesure 6819/6900 octets,
BSS fin `$3DCE`/`$3E20`, marges de 561/479 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## UNSQ : lecture interrompue sans octet fictif (11 octobre 2026)

La copie des entrées ACU stockées appelait `putb(getb())` avant de tester
l'état de lecture. Si le remplissage du tampon échouait, `getb()` renvoyait
zéro et positionnait EOF, mais cet octet fictif était ajouté à la sortie,
puis écrit par le flush final. En cas de nettoyage impossible, le fichier
partiel contenait un octet qui ne provenait pas de la source. Une annulation
pendant fread n'était pas contrôlée avant de consommer le nouveau tampon ;
le bloc reçu pouvait donc être écrit avant la détection d'ESC.

`getb()` contrôle maintenant les erreurs et ESC immédiatement après fread,
même avec un compte d'octets complet. `copy()` contrôle EOF et l'état
d'erreur avant `putb()`, puis contrôle aussi l'échec d'écriture. L'annulation
d'un en-tête passe par la fermeture et le diagnostic communs, afin de
conserver le message « stopped » au lieu de déclarer le format inconnu.
Seuls les fichiers exclusivement créés restent susceptibles d'être écrits
ou nettoyés ; sources, noms préexistants, sorties vérifiées et AUX ne sont
pas écrits. Les octets déjà décodés correctement restent dans le préfixe
partiel si son nettoyage échoue ; aucune atomicité physique n'est promise.

Les 48 nouveaux scénarios échouaient avant correction : sorties de 1,
513 et 1536 octets, chaque lecture de données, ESC seul, erreur avec
compte complet, ESC et erreur, lecture courte en erreur, chacun avec
nettoyage réussi ou impossible. Le vrai C est exécuté : le nombre d'octets
transmis à fwrite doit être exactement celui du préfixe lu avant le bloc
refusé. Le fichier conservé doit contenir ce même préfixe, sans octet zéro
ajouté. Les octets de la source et de KEEP ainsi que la fermeture unique
de la source sont également vérifiés. Les anciens tests de collision,
annulation d'en-tête, décompression et vérification passent.

Les 28 tests UNSQ, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : UNSQ mesure 6847/6928 octets,
BSS fin `$3DEB`/`$3E3D`, marges de 532/450 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## TXTCONV : refuser le bloc interrompu et arrêter les écritures en échec (11 octobre 2026)

La conversion traitait le tampon reçu avant de consulter ferror ou une
annulation arrivée pendant fread. Même une lecture signalée en erreur
avec un compte complet était convertie et écrite avant le refus final.
Après une erreur d'écriture, la boucle convertissait également le reste
du tampon : avec 256 tabulations, une première écriture refusée pouvait
être suivie de sept écritures supplémentaires. Le flush final pouvait
encore écrire des octets en attente ou un '?' synthétisé pour un UTF-8
interrompu. Ces sorties n'étaient pas installées, mais restaient sur disque
en cas de nettoyage impossible.

La passe contrôle désormais ESC et ferror immédiatement après fread,
avant consommation du tampon. La boucle de conversion s'arrête dès que
fail est positionné. La fin de séquence UTF-8 et le flush final ne sont
exécutés que pour une passe sans erreur. Les contrôles de fermeture,
vérification, protections, installation avec sauvegarde et nettoyage
restent en place. Seule la sortie exclusivement créée est écrite ou
supprimée ; les deux originaux, les fichiers préexistants et AUX restent
intacts. Le temporaire conservé après échec de nettoyage ne contient que
les blocs de sortie écrits avant le bloc refusé. Aucune atomicité en cas
de coupure physique n'est promise.

Les 434 nouveaux scénarios échouaient avant correction : 432 lectures
interrompues avec sources de 1, 257 et 768 octets, chaque bloc d'entrée,
modes H, T et A, conversion en place, remplacement confirmé ou nouvelle
destination, ESC, erreur avec compte complet, ESC avec erreur et lecture
courte en erreur, chacun avec nettoyage réussi ou impossible. Le mode A
coupe une séquence UTF-8 à la frontière de 256 octets. Deux autres cas
refusent la première écriture d'une conversion de 256 tabulations, avec
ou sans échec de nettoyage : aucun second fwrite n'est autorisé.
Le vrai C est exécuté ; les compteurs d'écriture et de fermeture, l'absence
de renommage, les octets des originaux, de KEEP et du temporaire conservé
sont vérifiés.

Les 28 tests TXTCONV, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : TXTCONV mesure 6164/6202 octets,
BSS fin `$3565`/`$358C`, marges de 2714/2675 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## IMGCONV : refuser une lecture interrompue avant l'écriture du bloc (11 octobre 2026)

Les lecteurs de blocs et de secteurs contrôlaient le compte de fread,
mais pas une erreur signalée avec un compte complet ni ESC arrivé
pendant cette lecture. Le bloc reçu pouvait être écrit, et la conversion
continuait jusqu'au contrôle périodique d'ESC ou à la fermeture finale.
La sortie n'était pas installée, mais un nettoyage impossible conservait
ces blocs supplémentaires. Pour une sortie DSK, le défaut concernait
chaque secteur de 256 octets ; pour une source DSK, chaque moitié lue
devait être validée avant de publier son bloc de 512 octets.

`read_source()` partage maintenant les lectures exactes des en-têtes,
blocs et secteurs : compte attendu, absence de ferror et absence d'ESC
avant retour réussi. Un ESC sans erreur de lecture est acquitté avant
refus. Les deux moitiés DSK sont contrôlées séparément. Les anciens
contrôles de fermeture, checksum DiskCopy, comparaison de tous les octets,
EOF, protections et installation avec sauvegarde restent actifs. Seule
la sortie exclusivement créée peut être écrite ou nettoyée ; sources,
destinations préexistantes, KEEP et AUX restent intacts. Le préfixe conservé
après échec de nettoyage ne contient aucun octet du bloc refusé ; aucune
atomicité en cas de coupure physique n'est promise.

Les 192 nouveaux scénarios exécutent le vrai C sur PO vers 2MG, PO vers
DSK, DSK vers PO, 2MG vers PO, PO vers DiskCopy et DiskCopy vers PO.
Les lectures ciblées sont la première, la deuxième, la troisième et la
dernière, avec ESC, erreur à compte complet, ESC avec erreur et lecture
courte en erreur, chaque fois avec nettoyage réussi ou impossible.
144 scénarios échouaient avant correction ; les 48 lectures courtes
étaient déjà refusées. Les tests vérifient le nombre d'octets transmis
à fwrite, le préfixe exact du temporaire conservé, les octets de la source,
de l'ancienne destination et de KEEP, les fermetures et l'absence de
renommage. Le checksum de l'en-tête DiskCopy partiel reste zéro, car la
conversion interrompue ne doit pas exécuter sa mise à jour finale.

Les 26 tests IMGCONV de préservation, 6 tests du lecteur, 15 gardes et
8 contrôles de distribution passent. Builds et dispositions 65C02/6502
validés : IMGCONV mesure 8764/8930 octets, BSS fin `$3F24`/`$3FCB`,
marges de 219/52 octets avant `$4000`. La mise en commun des lectures
réduit le code de 34 octets sur chaque architecture ; aucune garde n'est
désactivée. Les distributions sont reconstruites et contrôlées.

## MKIMAGE : ESC reçu pendant une écriture arrête avant le bloc suivant (11 octobre 2026)

La création ne contrôlait ESC que tous les 32 blocs, à l'affichage de
progression. Si fwrite livrait une annulation entre deux de ces contrôles,
jusqu'à 31 blocs supplémentaires étaient écrits avant arrêt. Une annulation
pendant le dernier bloc lançait également la passe de vérification avant
refus. L'image n'était pas annoncée complète, mais ces octets supplémentaires
restaient en cas de nettoyage impossible.

L'écriture de l'en-tête 2MG et celle de chaque bloc contrôlent maintenant
stop immédiatement après le compte et ferror. L'opération ferme alors
la sortie et ne peut nettoyer que l'image exclusivement créée. Les noms
préexistants et AUX restent intacts. Une annulation reçue par fwrite peut
survenir après l'écriture physique de ce bloc : il est conservé dans le
préfixe partiel si le nettoyage échoue, mais aucun bloc suivant n'est
écrit. Il ne s'agit pas d'une garantie d'atomicité en cas de coupure.

Les 240 nouveaux scénarios exécutent le vrai C : six tailles de 280 à
32767 blocs, PO et 2MG, écritures ciblées 1, 2, 32, 33 et dernière,
ESC seul ou avec erreur d'écriture, chacun avec nettoyage réussi ou
impossible. 84 scénarios échouaient avant correction ; 156 contrôlaient
des erreurs déjà refusées ou une annulation à la frontière de progression.
Les compteurs exigent une seule ouverture/fermeture, exactement le nombre
d'écritures atteint avant annulation et aucune ouverture de vérification.
Le préfixe conservé est comparé octet par octet à l'image créée normalement,
avec l'en-tête et les bitmaps. Chaque préfixe conservé est ensuite soumis
à une reprise : CREATE refuse la collision sans ouverture ni écriture,
et tous les octets restent identiques.

Les 8 tests MKIMAGE, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : MKIMAGE mesure 4749/4847 octets,
BSS fin `$30B7`/`$311A`, marges de 3912/3813 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## RESCUE : annulation du journal ZERO avant écriture du bloc manquant (11 octobre 2026)

Après trente échecs de lecture, RESCUE remplit le tampon de zéros et
journalise le bloc manquant. `logline()` ferme éventuellement la source,
puis ouvre, écrit et ferme le journal. Si l'une de ces étapes livrait ESC
sans erreur d'E/S, son retour restait réussi et le bloc rempli de zéros
était encore écrit avant l'arrêt à l'itération suivante. Le fichier partiel
contenait donc un bloc supplémentaire après annulation et offset avançait.

La boucle contrôle maintenant stop après les lectures et l'éventuelle
ligne ZERO, immédiatement avant fwrite. Les annulations pendant la
fermeture de source ou l'écriture/fermeture du journal refusent ce bloc.
Les fichiers de récupération déjà créés sont conservés avec leur préfixe
antérieur ; le journal peut contenir ZERO puis se termine par INCOMPLETE.
Seuls les fichiers de récupération et le journal exclusivement créés sont
écrits. La source, les noms préexistants et AUX restent intacts. L'opération
de secours n'offre pas d'atomicité en cas de coupure physique.

Les 80 nouveaux scénarios exécutent le vrai C sur des fichiers de 1, 513
et 1536 octets et des volumes bruts jetables de 3 et 8 blocs, chaque bloc
étant rendu illisible pendant les trente tentatives. Ils injectent ESC
pendant l'écriture ou la fermeture du journal ZERO, seuls ou accompagnés
d'une erreur, et pour les fichiers pendant la fermeture de source avec
ou sans erreur. 40 scénarios échouaient avant correction ; les 40 autres
contrôlaient des erreurs de journal ou fermeture déjà refusées. Les tests
exigent exactement trente tentatives, aucun octet de récupération écrit
après le préfixe antérieur, les octets exacts de la source, de KEEP et du
fichier partiel, le diagnostic INCOMPLETE à l'ancien offset et la fermeture
de tous les flux. Les tests de secours normal et de zéro-fill volontaire
sans annulation passent également.

Les 16 tests RESCUE, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : RESCUE mesure 7085/7157 octets,
BSS fin `$3883`/`$38CC`, marges de 1916/1843 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## TXTCONV : erreur à compte complet ou ESC dans l'E/S de sortie (12 octobre 2026)

`flush()` refusait un compte court ou une différence lors de la
vérification, mais ne contrôlait ni ferror ni ESC immédiatement après
l'E/S de sortie. Une écriture renvoyant tous les octets avec erreur
pouvait donc être suivie d'autres écritures avant le contrôle final.
Une annulation pendant la conversion d'un tampon expansif, notamment
des tabulations, pouvait également laisser passer plusieurs blocs.
La vérification avait le même défaut d'arrêt sur une lecture identique
signalée en erreur ou annulée. Le refus final protégeait les originaux,
mais les écritures supplémentaires restaient si le nettoyage échouait.

La fonction contrôle maintenant ferror(out) et ESC après chaque E/S
effective. La boucle de conversion et le flush final respectent déjà
fail : aucun bloc suivant ni lecture de vérification supplémentaire
n'est donc engagé après le premier échec. Les originaux, les sauvegardes
préexistantes et AUX ne sont pas écrits ; seule la sortie exclusivement
créée reste nettoyable. Un bloc peut avoir été écrit physiquement avant
qu'ESC ou l'erreur ne soit signalé : il reste dans la sortie conservée
si le nettoyage échoue. Aucune atomicité physique n'est promise.

Les 240 nouveaux scénarios exécutent le vrai C. Les 216 cas d'écriture
couvrent H sur 256/513 octets, T sur 256 tabulations, D sur 256 CR,
les blocs 1, 2 et dernier lorsque distincts, conversion en place,
remplacement confirmé et nouvelle destination. ESC, erreur à compte
complet, ESC avec erreur et écriture courte en erreur sont combinés
avec nettoyage réussi ou impossible. Les compteurs interdisent toute
écriture après le bloc ciblé, et la sortie conservée est comparée
octet par octet, y compris le dernier bloc court. Les 24 cas de
vérification ciblent H et T, y compris la dernière lecture d'un octet,
avec les mêmes quatre événements et un compteur de lectures. Tous
exigent des fermetures équilibrées, aucun renommage et la préservation
des octets de la source, de l'ancienne destination et de KEEP selon le
cas. 74 scénarios échouaient avant correction ; les 166 autres sont
des contrôles d'arrêts déjà détectés aux limites de tampon ou en cas
de compte court.

Les 30 tests TXTCONV, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : TXTCONV mesure 6133/6225 octets,
BSS fin `$3546`/`$35A3`, marges de 2745/2652 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## IMGCONV : erreur à compte complet ou ESC après chaque écriture (12 octobre 2026)

Les écritures de blocs, secteurs et en-têtes ne contrôlaient que le
compte de fwrite. Une erreur signalée avec un compte complet pouvait
laisser la conversion écrire le reste de l'image avant son contrôle
final. Une annulation pendant le dernier bloc DiskCopy pouvait encore
déclencher l'écriture du checksum ; une annulation lors de la dernière
écriture lançait la vérification avant refus. Les originaux restaient
protégés, mais le temporaire conservé après nettoyage impossible pouvait
contenir des octets écrits après l'événement d'arrêt.

`write_output()` regroupe maintenant toutes les écritures exactes : blocs
de 512 octets, moitiés DSK de 256 octets, en-têtes 2MG/DiskCopy et mise
à jour de quatre octets du checksum. Il contrôle compte, ferror et ESC
avant retour réussi. Une écriture refusée ferme les deux flux et empêche
toute écriture ou vérification suivante. Seule la sortie exclusivement
créée est écrite ou nettoyée ; les sources, destinations préexistantes,
sauvegardes préexistantes et AUX restent intacts. Le bloc ciblé peut
avoir été écrit avant le signal d'erreur ou d'annulation : il est conservé
si le nettoyage échoue. Aucune atomicité physique n'est promise.

Les 200 nouveaux scénarios exécutent le vrai C sur PO vers 2MG, PO vers
DSK, DSK vers PO, 2MG vers PO, PO vers DiskCopy et DiskCopy vers PO.
Ils ciblent les écritures 1, 2, 3 et dernière, plus le dernier bloc avant
le checksum DiskCopy, avec ESC, erreur à compte complet, ESC avec erreur
et écriture courte en erreur, chacun avec nettoyage réussi ou impossible.
54 scénarios échouaient avant correction ; les 146 autres contrôlaient
des arrêts déjà détectés par la lecture suivante, un compte court ou
les contrôles de fermeture. Les compteurs exigent exactement le nombre
d'écritures atteint, deux ouvertures et fermetures et aucun renommage.
Les octets de la source, de l'ancienne destination et de KEEP restent
identiques. Le temporaire conservé est reconstruit et comparé octet par
octet, y compris les écritures courtes et la mise à jour partielle du
checksum à l'intérieur d'une image déjà écrite.

Les 27 tests IMGCONV de préservation, 6 tests du lecteur, 15 gardes et
8 contrôles de distribution passent. Builds et dispositions 65C02/6502
validés : IMGCONV mesure 8747/8915 octets, BSS fin `$3F13`/`$3FBC`,
marges de 236/67 octets avant `$4000`. La mise en commun réduit le code
de 17/15 octets, sans nouveau tampon ni désactivation des gardes.
Les distributions sont reconstruites et contrôlées.

## UNSQ : arrêter la production RLE dès le premier échec d'écriture (12 octobre 2026)

Une écriture courte positionnait bad dans `flush()`, mais la boucle d'une
répétition RLE pouvait encore appeler `putb()` jusqu'à la fin de la
répétition. Ces octets remplissaient à nouveau le tampon et le flush final
les écrivait malgré l'échec précédent. Les écritures renvoyant un compte
complet avec ferror, et ESC pendant fwrite, étaient également détectées
trop tard. Les sorties n'étaient pas validées, mais un nettoyage impossible
conservait des octets écrits après le premier événement d'arrêt.

`flush()` contrôle maintenant compte, ferror et ESC après fwrite.
`putb()` refuse tout nouvel octet dès que bad est positionné, avant le
compteur, le checksum et le tampon. Même une répétition en cours ne peut
donc remplir à nouveau le tampon ni provoquer une écriture finale
supplémentaire. La limite de longueur ACU, la comparaison octet par octet,
les fermetures et le nettoyage exclusif restent actifs. Seule la sortie
créée par l'opération est écrite ou nettoyée ; l'archive, les fichiers
préexistants et AUX restent intacts. Le bloc signalé en erreur ou annulé
peut déjà être écrit physiquement et reste dans le fichier conservé si
son nettoyage échoue. Aucune atomicité physique n'est promise.

Les 200 nouveaux scénarios exécutent le vrai C : QQ répétitif et littéral,
ACU stocké, ACU compressé répétitif et littéral, sorties de 513/2000 octets,
écritures 1, 2 et dernière lorsque distinctes, ESC, erreur à compte complet,
ESC avec erreur et écriture courte en erreur, chacun avec nettoyage réussi
ou impossible. 82 scénarios échouaient avant correction ; les 118 autres
contrôlaient des arrêts déjà reconnus aux limites du tampon ou à la fin
du fichier. Les tests exigent exactement le nombre d'écritures atteint,
aucune vérification de sortie en échec, la fermeture unique de la source
et le nettoyage de DOC uniquement. Ils comparent les octets de l'archive,
de KEEP et du préfixe conservé, y compris l'octet absent d'une écriture
courte et le dernier tampon d'un octet.

Les 29 tests UNSQ, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : UNSQ mesure 6876/6957 octets,
BSS fin `$3E08`/`$3E5A`, marges de 503/421 octets avant `$4000`.
Les distributions sont reconstruites et contrôlées.

## UNSQ : dernier composant complet du nom QQ, sans troncature à 64 octets (12 octobre 2026)

Le nom zéro-terminé d'un fichier QQ était lu entièrement, mais seuls ses
64 premiers octets étaient conservés avant normalisation. Si le dernier
composant se trouvait plus loin, l'extraction utilisait le nom tronqué
d'un répertoire, ou le nom du wrapper alors qu'un vrai nom était présent.
Une collision sur ce mauvais nom pouvait ignorer le fichier, même lorsque
sa destination correcte était libre. Un long préfixe de caractères non
autorisés en tête du composant pouvait également masquer sa partie valide.

La normalisation traite maintenant chaque caractère à la lecture, avec
un compteur borné à 15 caractères et le tampon name existant. Chaque
séparateur `/` ou `:` remet le composant à zéro, même après une longue
portion ignorée. Le traitement commun garde la même normalisation ACU,
et un dernier composant sans nom conserve le repli sur le wrapper QQ.
Le tampon raw[64] de standalone est supprimé. Seules les sorties créées
exclusivement peuvent être écrites ou nettoyées ; une collision correcte
reste ignorée sans remplacement. Archives, fichiers préexistants et AUX
restent intacts ; aucune garantie d'atomicité physique n'est ajoutée.

Les 60 nouveaux scénarios exécutent le vrai C et le comparent à la
référence : premier composant de 64, 65, 511, 512 ou 1024 octets,
séparateurs Unix ou Mac, dernier composant DOC, 80 chiffres puis DOC,
ou composant vide. Le nom tronqué du répertoire existe systématiquement ;
la destination correcte est alternativement libre ou déjà prise.
30 scénarios échouaient avant correction ; 30 contrôlent des collisions
où aucun fichier ne doit être créé. Les tests vérifient nom, compteurs,
absence de nettoyage et octets exacts de l'archive, de KEEP, du nom de
répertoire préexistant, de la destination préexistante et de l'extraction.

Les 30 tests UNSQ, 15 gardes et 8 contrôles de distribution passent.
Builds et dispositions 65C02/6502 validés : UNSQ mesure 6821/6897 octets,
BSS fin `$3D8F`/`$3DDC`, marges de 624/547 octets avant `$4000`.
La correction réduit le code de 55/60 octets et la BSS de 66 octets sur
chaque architecture. Les distributions sont reconstruites et contrôlées.

## SCIIBIN : arrêt immédiat sur erreur d'écriture (12 octobre 2026)

Une écriture de données pouvait rendre le compte demandé avec `ferror`
actif. Le contrôle effectué à la fermeture refusait bien le résultat,
mais les lignes suivantes étaient encore écrites. Chaque appel à `fwrite`
contrôle désormais aussi l'erreur du flux avant de poursuivre. Seule la
destination créée exclusivement est écrite ou nettoyée ; les sources,
les fichiers préexistants et la mémoire auxiliaire ne sont pas modifiés.

Le harnais exécute le vrai code C dans 40 nouveaux scénarios : fichiers
de 49, 2560 et 12289 octets, erreur sur la première, deuxième, médiane ou
dernière écriture, compte complet ou court, avec ou sans échec du nettoyage.
Avant correction, 14 scénarios échouaient et 26 servaient de contrôles.
Les tests comptent les écritures, refusent toute vérification après l'erreur
et comparent les octets effectivement conservés, y compris le préfixe
incomplet lorsque la suppression échoue. Les sources et KEEP restent intacts.

Les 22 tests SCIIBIN, dont les CRC sous sim65 sur les deux CPU, passent.
Les 15 tests de gardes, les dispositions natives 65C02/6502 et les 8
contrôles de distribution 800K après reconstruction sont validés.
SCIIBIN mesure 6102/6113 octets, avec BSS fin `$3DA7`/`$3DB3`, soit
600/588 octets disponibles avant `$4000`. Les contrôles de disposition
restent actifs. Cette correction ne garantit pas l'atomicité d'une écriture
physique interrompue par une coupure.

## UNWRAP : arrêt sur la première écriture en erreur (12 octobre 2026)

La copie du fork de données contrôlait le compte rendu par `fwrite`, mais
attendait la fermeture pour contrôler `ferror`. Une écriture renvoyant le
compte complet avec une erreur active laissait donc écrire les blocs
suivants. Chaque écriture contrôle maintenant les deux résultats avant de
poursuivre. Les seuls fichiers écrits ou supprimés sont les destinations
créées exclusivement ; aucune source, aucun fichier préexistant et aucune
banque auxiliaire ne sont modifiés.

Le vrai code C est exécuté dans 140 nouveaux scénarios : AppleSingle 1/2,
MacBinary I/II/III, forks de 1, 513 ou 2560 octets, première, deuxième,
médiane ou dernière écriture, compte complet avec erreur ou écriture courte,
avec ou sans échec de suppression. Avant correction, 40 scénarios échouaient
et 100 servaient de contrôles. Les tests comptent les écritures, vérifient
l'absence de réouverture pour validation après l'erreur et comparent les
octets du préfixe conservé si le nettoyage échoue. La source et KEEP sont
comparés également.

Les 46 tests UNWRAP passent, y compris les contrôles natifs MacBinary sur
les deux processeurs. Builds et dispositions 65C02/6502 validés, avec
UNWRAP à 7890/7923 octets, BSS fin `$3FB9`/`$3FDB`, soit 70/36 octets
disponibles avant `$4000`. Les 15 tests de gardes et les 8 contrôles de
distribution 800K après reconstruction passent. Les contrôles de
disposition restent actifs.
Cette correction ne garantit pas l'atomicité en cas de coupure physique.

## SYNC : annulation avant remplacement après fermeture (12 octobre 2026)

Une annulation reçue pendant la fermeture des flux de copie ou de
vérification, ou pendant le dernier GET_FILE_INFO de la destination, pouvait
être ignorée. SYNC installait alors la copie et supprimait la sauvegarde
malgré ESC. Le contrôle d'annulation intervient maintenant après les deux
paires de fermetures et après le contrôle courant de la destination, avant
le premier renommage de remplacement.

Avant cette phase, seule la copie temporaire créée exclusivement peut être
écrite ou supprimée. L'original, les sources, une sauvegarde préexistante et
la mémoire auxiliaire restent intacts. Si le nettoyage échoue, la copie
temporaire est conservée et le message de récupération arrête la suite de
l'arborescence. Les étapes de restauration d'un remplacement déjà commencé
ne sont pas interrompues par ce nouveau contrôle.

Le vrai code C est exécuté dans 30 nouveaux scénarios, tous en échec avant
correction : fichiers vides, de 1 et de 1600 octets ; ESC pendant chacune
des quatre fermetures ou pendant le contrôle final de destination ; avec
ou sans échec du nettoyage. Les tests contrôlent les octets de la source,
de l'original, de KEEP et du temporaire éventuellement conservé. Ils
vérifient aussi qu'aucun renommage ni SET_FILE_INFO n'a lieu et que les
annulations après la copie empêchent l'ouverture des flux de vérification.

Les 65 tests des six overlays passent. Builds et dispositions natives
65C02/6502 validés : SYNC mesure 7436/7464 octets, BSS fin `$3EDF`/`$3EFC`,
soit 288/259 octets disponibles avant `$4000`. Les 15 tests de gardes et
les 8 contrôles de distribution 800K après reconstruction passent. Les
contrôles de disposition restent actifs. Cette correction ne garantit pas l'atomicité d'une coupure
pendant les écritures physiques ou les renommages ProDOS.

## SYNC : refus du bloc dès une erreur de flux ou ESC (12 octobre 2026)

La boucle de copie vérifiait les comptes rendus par `fread` et `fwrite`,
mais attendait la fermeture pour vérifier `ferror`. Un bloc source rendu
avec le compte complet et une erreur active pouvait donc être écrit dans
le temporaire. De même, ESC reçu pendant cette lecture n'empêchait pas
l'écriture du bloc. Les lectures de vérification et les écritures pouvaient
également laisser continuer les opérations avant le refus final.

Chaque lecture est maintenant suivie du contrôle d'erreur et d'annulation
avant toute écriture ou lecture suivante. Chaque écriture contrôle aussi
immédiatement ces états. Seul le temporaire créé exclusivement peut être
écrit ou nettoyé ; sources, original, sauvegardes préexistantes et mémoire
auxiliaire ne sont pas modifiés. Un nettoyage impossible conserve le
temporaire et son message de récupération.

Le vrai code C est exécuté dans 168 nouveaux scénarios : fichiers de 1,
257 et 1600 octets ; première, deuxième, médiane ou dernière opération ;
lecture source de copie, écriture temporaire, lecture source de vérification
ou lecture temporaire de vérification ; ESC, erreur avec compte complet
ou compte court avec erreur ; nettoyage réussi ou impossible. Avant la
correction, 84 scénarios échouaient et 84 servaient de contrôles. Les tests
comptent les opérations pour imposer l'arrêt immédiat, refusent tout
renommage ou changement de métadonnées, et comparent les octets de l'original,
de la source, de KEEP et du préfixe temporaire éventuellement conservé.

Les 66 tests des six overlays passent. Builds et dispositions 65C02/6502
validés : SYNC mesure 7521/7546 octets, BSS fin `$3F34`/`$3F4E`, soit
203/177 octets disponibles avant `$4000`. Les 15 tests de gardes et les 8
contrôles de distribution 800K après reconstruction passent. Les contrôles
de disposition restent actifs. Cette correction ne garantit pas l'atomicité d'une écriture
physique interrompue par une coupure.

## SYNC : annulation avant toute création (12 octobre 2026)

Une annulation déjà reçue avant la copie, ou reçue pendant GET_FILE_INFO
du nom de sauvegarde, la lecture du catalogue, la recherche de destination
ou l'affichage du chemin source, pouvait laisser créer le temporaire. Une
entrée de dossier pouvait même créer un dossier de destination après ESC,
sans être couverte par les contrôles de la copie de fichiers.

SYNC contrôle maintenant ESC à l'entrée de la copie et après la recherche
du nom de sauvegarde, ainsi qu'après dir_next et GET_FILE_INFO de la
destination dans la boucle d'arborescence. Ces contrôles précèdent CREATE
de fichier ou de dossier. Aucune cible n'est créée ni nettoyée après ces
annulations ; sources, fichiers préexistants, noms réservés et mémoire
auxiliaire restent intacts.

Les 63 nouveaux scénarios exécutent le vrai code C : fichiers de 0, 1
et 1600 octets ; sept points d'annulation couvrant copie et dossier ; nom
réservé absent, A2FC.SYNC présent ou A2FC.BAK présent. Avant correction,
48 scénarios échouaient et 15 servaient de contrôles. Les tests imposent
zéro CREATE et zéro suppression, renommage ou changement de métadonnées,
et comparent les octets de toutes les sources et destinations préexistantes.
Les anciennes attentes du cas déjà annulé sont mises à jour : aucune
création implique qu'aucun nettoyage n'est nécessaire, même lorsque ce
nettoyage aurait échoué.

Les 68 tests des six overlays passent, ainsi que les 15 tests de gardes et
les 8 contrôles de distribution 800K après reconstruction. Builds et
dispositions natives 65C02/6502 validés : SYNC mesure 7558/7581 octets,
BSS fin `$3F59`/`$3F71`, soit 166/142 octets disponibles avant `$4000`.
Les contrôles de disposition restent actifs. Ces contrôles ne garantissent
pas l'atomicité d'une écriture physique interrompue par une coupure.

## SYNC : date courante avant remplacement (12 octobre 2026)

La comparaison source plus récente que destination avait lieu avant la
copie. Le contrôle final de la destination vérifiait protection, stockage
et validité de la date, mais ne refaisait pas la comparaison. Une destination
devenue aussi récente ou plus récente pendant la copie pouvait donc être
remplacée, puis sa sauvegarde supprimée. SYNC refait maintenant la
comparaison avec les métadonnées courantes avant le premier renommage.
En cas de refus, la destination et la copie vérifiée A2FC.SYNC sont
conservées, et le message de récupération arrête l'arborescence.

Seul le temporaire créé exclusivement a été écrit jusque-là ; aucune
source, sauvegarde préexistante ni banque auxiliaire n'est modifiée.
Le harnais met réellement à jour les octets de destination après la
fermeture de vérification, puis fournit sa nouvelle date à GET_FILE_INFO.
Les 48 nouveaux scénarios couvrent les fichiers de 0, 1 et 1600 octets,
la copie directe et la boucle d'arborescence, les dates égales, la minute,
le jour ou l'année suivante, et les bornes de la convention 1940–2039.
Avant correction, 36 scénarios échouaient et 12 contrôlaient que les
destinations plus anciennes restent remplaçables. Les tests comparent
sources, destinations, KEEP et copie conservée, imposent zéro renommage
ou écriture de métadonnées au refus, et vérifient que le fichier suivant
n'est pas traité dans l'arborescence.

Les 69 tests des six overlays, les 15 tests de gardes et les 8 contrôles
de distribution 800K après reconstruction passent. Builds et dispositions
65C02/6502 validés : SYNC mesure 7597/7620 octets, BSS fin `$3F80`/`$3F98`,
soit 127/103 octets disponibles avant `$4000`. Les gardes restent actives.
Les dates ProDOS ne détectent pas une modification qui conserve la même
date, et une modification après le dernier contrôle reste possible :
ProDOS ne fournit pas de remplacement conditionnel atomique. Aucune
atomicité physique en cas de coupure n'est promise.

## UNDELETE : ESC pendant la lecture des données (12 octobre 2026)

Le contrôle d'annulation précédait la lecture brute d'un bloc de données.
ESC reçu pendant cette lecture pouvait donc laisser écrire ce bloc dans
la récupération avant l'arrêt. UNDELETE contrôle maintenant l'annulation
dans la même condition que l'erreur de lecture, avant l'écriture. Seul le
fichier récupéré créé exclusivement peut être écrit ou nettoyé ; la source
ProDOS, sa bitmap, son catalogue, les fichiers préexistants de destination
et la mémoire auxiliaire ne sont pas modifiés.

Les 36 nouveaux scénarios exécutent le vrai code C : fichiers de 1, 513
et 4097 octets, seedling ou sapling, première, médiane ou dernière lecture,
ESC seul, erreur de lecture ou les deux, nettoyage réussi ou impossible.
Avant correction, les 12 scénarios d'ESC seul échouaient ; les 24 scénarios
avec erreur de lecture servaient de contrôles. Les tests comptent les
lectures et écritures, imposent l'absence d'écriture du bloc annulé,
comparent le préfixe conservé lorsque la suppression échoue, ainsi que KEEP,
les octets de l'image source et du catalogue lus par ProDOS.

Les 70 tests des six overlays, les 15 tests de gardes et les 8 contrôles
de distribution 800K après reconstruction passent. Builds et dispositions
65C02/6502 validés : UNDELETE mesure 6933/6948 octets, BSS fin `$3FEB`/`$3FFB`,
soit 20/4 octets disponibles avant `$4000`. La version avec un contrôle
séparé dépassait de 4 octets sur 6502 ; intégrer le contrôle dans la
condition de lecture a conservé tous les contrôles et respecte la limite.
La marge 6502 reste très réduite. Aucun garde n'a été désactivé et aucune
atomicité physique en cas de coupure n'est promise.

## UNDELETE : annulation de validation avant CREATE (12 octobre 2026)

La seconde validation de récupération pouvait réussir malgré ESC reçu
pendant sa dernière lecture de bitmap ou d'index. Le code appelait alors
CREATE, y compris pour un fichier vide. Le contrôle d'annulation intervient
maintenant à la sortie de cette validation, avant toute création.
Aucun fichier n'est donc créé ou nettoyé dans ce cas ; sources, catalogue,
bitmap, fichiers préexistants de destination et mémoire auxiliaire restent
intacts. Ce contrôle ne modifie aucune étape de restauration ou suppression
d'un fichier dont la récupération aurait déjà commencé.

Les 24 nouveaux scénarios exécutent le vrai code C avec fichiers de 0,
1, 513 et 4097 octets, ESC sur la dernière lecture de validation de bitmap
ou d'index, nom libre ou déjà présent, et nettoyage disponible ou impossible.
Tous échouaient avant correction. Les tests imposent zéro CREATE, zéro
lecture de données de récupération et zéro écriture, et comparent les
octets de KEEP, de DATA préexistant, de l'image source et du catalogue.

Pour conserver la limite native, la table API copiée s'arrête désormais
après selected (`UTIL_API_END cfg_path`) : UNDELETE ne lit ni cfg_path,
ni les services de configuration, média ou mémoire auxiliaire qui suivent.
Cette réduction économise 10 octets de BSS sans modifier les offsets des
champs utilisés. Les 71 tests des six overlays, les 15 tests de gardes et
les 8 contrôles de distribution 800K après reconstruction passent.
Builds et dispositions 65C02/6502 validés : UNDELETE mesure 6939/6954 octets,
BSS fin `$3FE7`/`$3FF7`, soit 24/8 octets disponibles avant `$4000`.
La marge 6502 reste réduite ; tous les contrôles de disposition restent
actifs. Aucune atomicité physique en cas de coupure n'est promise.

## UNDELETE : vérification intégrale après fermeture (12 octobre 2026)

La récupération annonçait son succès après les comptes d'écriture et la
fermeture, sans relire la destination. Une écriture renvoyant un compte
correct mais contenant un octet corrompu, ou une fermeture laissant un
octet supplémentaire, pouvait donc être annoncée comme récupération
réussie. Le fichier créé exclusivement est maintenant fermé, rouvert en
lecture et comparé octet par octet avec un nouveau parcours des blocs
source. Le contrôle exige aussi une fin de fichier propre et une fermeture
réussie. Toute erreur ou annulation refuse le succès et ne nettoie que la
destination effectivement créée ; si le nettoyage échoue, ses octets
restent accessibles avec le message de récupération approprié.

La vérification réutilise `bits[512]`, dont le contenu bitmap n'est plus
nécessaire après validation. `writing == 2` distingue cette comparaison
de l'écriture ; les index et le master gardent leurs buffers séparés. Les
trous sont comparés avec des zéros comme pendant la récupération, et les
index inversés par DESTROY suivent la même normalisation. Aucun nouveau
buffer, aucune écriture source, aucun écrasement de fichier préexistant et
aucun accès à la mémoire auxiliaire ne sont introduits.

Les 80 premiers scénarios du vrai code C échouaient tous avant correction :
fichiers de 0, 1, 513 et 4097 octets, corruption d'une écriture, octet final
en trop, erreurs ou comptes courts en lecture de vérification, erreur à la
sonde EOF, échec de fermeture et annulation, avec ou sans échec de nettoyage.
32 scénarios supplémentaires contrôlent l'échec de réouverture, les erreurs
brutes source et ESC pendant cette nouvelle lecture source. Les octets de
la destination éventuellement conservée sont comparés, même corrompus,
ainsi que KEEP, l'image source et le catalogue. Six contrôles positifs
vérifient les fichiers vides, seedling, sapling et tree creux, dont les
index inversés : tous les octets et la sonde EOF sont contrôlés.

UNDELETE utilise les relais existants `service_stubs.h` pour les appels
de services, en conservant leurs offsets et le préfixe API déjà borné.
Les 73 tests des six overlays, les 15 tests de gardes et les 8 contrôles
de distribution 800K après reconstruction passent. Builds et dispositions
65C02/6502 validés : UNDELETE mesure 6476/6465 octets, BSS fin `$3E18`/`$3E0E`,
soit 487/497 octets disponibles avant `$4000`, sans désactiver de garde.
La comparaison établit les octets lus pendant ces passes, pas l'historique
des blocs libres ; elle ne fournit pas d'atomicité face à une modification
concurrente après le contrôle ou à une coupure pendant l'écriture physique.

## CPM : annulation au niveau du secteur (12 octobre 2026)

La copie CP/M contrôlait ESC après un groupe de quatre secteurs, sans
contrôle après la lecture source. Une annulation reçue pendant cette
lecture pouvait laisser écrire le secteur et les suivants ; une annulation
pendant une écriture pouvait aussi laisser continuer les écritures du
kilooctet. La copie contrôle maintenant ESC après la lecture source,
avant toute écriture ou lecture de vérification, et après chaque secteur
traité avant la lecture suivante. Le même contrôle couvre la vérification.

Seules les destinations créées exclusivement peuvent être écrites ou
nettoyées. Image source, fichiers préexistants et mémoire auxiliaire
restent intacts. Si la suppression échoue, le préfixe exact écrit jusqu'à
l'annulation est conservé avec le message de récupération approprié.

Les 260 nouveaux scénarios exécutent le vrai code C avec fichiers de
128, 1536 et 17000 octets (plusieurs extents), deux skews, images PO/DSK/2MG,
annulation sur la première, médiane ou dernière lecture ou écriture,
erreur source combinée et nettoyage réussi ou impossible. Avant correction,
136 scénarios échouaient et 124 servaient de contrôles. Les tests comptent
les écritures, comparent les octets du préfixe éventuellement conservé,
KEEP et l'image source, et contrôlent CREATE et la fermeture source.

Le préfixe API copié s'arrête après selected (`UTIL_API_END cfg_path`),
aucun champ de configuration, média ou AUX suivant n'étant utilisé.
Les 30 tests CPM, les 15 tests de gardes et les 8 contrôles de distribution
800K après reconstruction passent. Builds et dispositions 65C02/6502
validés : CPM mesure 8373/8368 octets, BSS fin `$3FFE`/`$3FFA`, soit
1/5 octets disponibles avant `$4000`. La marge reste extrêmement réduite ;
aucun contrôle de disposition n'a été désactivé. Cette correction ne
garantit pas l'atomicité d'une écriture physique interrompue par une coupure.

## PASCAL : arrêt immédiat sur lecture de vérification douteuse (12 octobre 2026)

La vérification comparait les octets après une lecture dont le compte
correspondait, mais contrôlait `ferror` seulement à la fin du fichier et
ESC à la fin du bloc source. Elle pouvait donc poursuivre les lectures
de destination ou de source après une lecture de vérification en erreur
ou annulée. Le résultat était finalement refusé ; il faut néanmoins
s'arrêter dès cette lecture. Chaque lecture de vérification contrôle
maintenant compte, erreur du flux et annulation avant de comparer ou de
poursuivre. Aucune écriture source, fichier préexistant ou mémoire auxiliaire
n'est concerné ; seul le fichier créé exclusivement peut être nettoyé.

Les 168 nouveaux scénarios exécutent le vrai code C : fichiers de 1, 513
et 1536 octets, images PO/DSK/2MG, première, médiane ou dernière lecture,
erreur avec compte complet, ESC, erreur et ESC combinés ou compte court
avec erreur, nettoyage réussi ou impossible. Avant correction, 78
scénarios échouaient et 90 servaient de contrôles. Les tests comptent les
lectures de vérification et les lectures source pour imposer l'arrêt,
comparent tous les octets du fichier conservé si la suppression échoue,
KEEP et l'image source, et contrôlent CREATE et la fermeture source.

Les 20 tests PASCAL et les 14 tests SMALLDOS, dont le harnais partage les
services de simulation, passent. Les 15 tests de gardes et les 8 contrôles
de distribution 800K après reconstruction passent également. Builds et
dispositions 65C02/6502 validés : PASCAL mesure 7326/7316 octets, BSS fin
`$3AB4`/`$3AAB`, soit 1355/1364 octets disponibles avant `$4000`.
Tous les contrôles de disposition restent actifs. Cette correction ne
garantit pas l'atomicité d'une écriture physique interrompue par une coupure.

## MKIMAGE : annulation immédiate pendant la vérification (12 octobre 2026)

La relecture de l'image contrôlait ESC tous les 32 blocs, puis à la
fermeture. ESC reçu pendant une lecture pouvait donc laisser relire jusqu'à
31 blocs supplémentaires. ESC reçu pendant le dernier bloc pouvait aussi
laisser effectuer la sonde EOF avant le refus final. Le contrôle intervient
maintenant dans matches, immédiatement après chaque lecture de l'en-tête
ou d'un bloc et avant toute comparaison ou lecture suivante.

Seule l'image créée exclusivement est écrite puis relue ou nettoyée ; aucun
fichier préexistant ni aucune mémoire auxiliaire n'est modifié. L'image
complète est conservée avec le message de nettoyage impossible lorsque
sa suppression échoue ; cette conservation ne vaut pas validation.

Les 192 nouveaux scénarios exécutent le vrai code C : images PO/2MG de
280, 1600 ou 32767 blocs, première, deuxième, médiane ou dernière lecture,
ESC, erreur avec compte complet, les deux ou compte court avec erreur,
nettoyage réussi ou impossible. Avant correction, 36 scénarios échouaient
et 156 servaient de contrôles. Les tests comptent les lectures pour imposer
l'arrêt au point injecté, vérifient les ouvertures, écritures et fermetures,
refusent toute annonce de succès, et comparent tous les octets de l'image
éventuellement conservée.

Les 9 tests MKIMAGE, les 15 tests de gardes et les 8 contrôles de distribution
800K après reconstruction passent. Builds et dispositions 65C02/6502 validés :
MKIMAGE mesure 4755/4853 octets, BSS fin `$30BD`/`$3120`, soit
3906/3807 octets disponibles avant `$4000`. Tous les contrôles de disposition
restent actifs. Aucune atomicité physique en cas de coupure n'est promise.

## DISASM : annulation avant la création de l'export (12 octobre 2026)

L'export ne contrôlait pas ESC après la saisie du nom, avant CREATE.
Il réinitialisait aussi l'état d'annulation après l'ouverture de la sortie.
La remise à zéro intervient maintenant au début de chaque nouvelle tentative,
puis ESC est contrôlé avant la création exclusive. Une annulation reçue
pendant CREATE ou l'ouverture reste mémorisée jusqu'au contrôle initial
d'export_text : aucun enregistrement n'est écrit.

Seul le nouveau TXT est créé et ouvert en écriture ; la source, les autres
fichiers et la mémoire auxiliaire restent intacts. Une annulation avant CREATE
annonce qu'aucun fichier n'a été créé. Après CREATE, le fichier vide ou partiel
appartenant à l'opération est conservé comme auparavant. Les collisions ne
permettent jamais l'ouverture tronquante d'un fichier préexistant.

Les 48 nouveaux scénarios exécutent le vrai code C avec injection de l'état
ESC à la fin de la saisie, de CREATE ou de l'ouverture, ainsi qu'un état
annulé hérité d'une tentative précédente. Ils couvrent les deux modes CPU,
les sources de 0, 1 et 200 octets, avec ou sans collision. Avant correction,
24 échouaient et 24 servaient de contrôles. Les tests contrôlent les créations,
ouvertures et écritures, tous les octets de la source et des fichiers conservés,
l'absence de sortie avant CREATE et la réussite d'une nouvelle tentative.

Les 21 tests DISASM, les 15 tests de gardes et les 8 contrôles de distribution
800K après reconstruction passent. Builds et dispositions 65C02/6502 validés :
DISASM mesure 8305/8289 octets, BSS fin `$3DF9`/`$3DEA`, soit
518/533 octets disponibles avant `$4000`. Tous les contrôles de disposition
restent actifs. Aucune atomicité physique en cas de coupure n'est promise.

## UNWRAP : refus immédiat des lectures de vérification douteuses (12 octobre 2026)

La relecture de la sortie comparait les octets après un compte complet sans
contrôler immédiatement l'erreur du flux. Une erreur persistante ne provoquait
le refus qu'après les blocs suivants et la sonde EOF. ESC était contrôlé après
la comparaison et la progression. Le contrôle de ferror et d'ESC intervient
maintenant dès la lecture, avant comparaison, progression ou lecture suivante.
Le refus final existait déjà : la correction évite de poursuivre les lectures
ou d'afficher une progression après une lecture douteuse.

Seul le fichier créé exclusivement par l'extraction est écrit, relu et,
en cas d'échec, nettoyé. La source, les fichiers préexistants et la mémoire
auxiliaire restent intacts. Si le nettoyage échoue, la sortie entière est
conservée et signalée comme telle, sans être annoncée comme validée.

Les 360 nouveaux scénarios exécutent le vrai code C : AppleSingle 1/2,
MacBinary I/II/III, fourches de 1, 513, 1536 et 4097 octets, première,
médiane ou dernière lecture, compte complet avec erreur, ESC, les deux ou
compte court avec erreur, nettoyage réussi ou impossible. Avant correction,
270 échouaient et 90 servaient de contrôles. Les tests comptent les lectures
et sondes EOF, exigent l'arrêt de la progression au bloc concerné et comparent
tous les octets de la source, des fichiers préexistants et de la sortie
éventuellement conservée.

Les 47 tests UNWRAP, les 15 tests de gardes et les 8 contrôles de distribution
800K après reconstruction passent. Builds et dispositions 65C02/6502 validés :
UNWRAP mesure 7911/7948 octets, BSS fin `$3FCE`/`$3FF4`, soit
49/11 octets disponibles avant `$4000`. Tous les contrôles de disposition
restent actifs. La marge 6502 reste serrée ; aucune atomicité physique en cas
de coupure n'est promise.

## SCIIBIN : arrêt avant le CRC sur une relecture douteuse (12 octobre 2026)

La vérification de la sortie contrôlait le compte lu et ESC avant fread,
mais pas l'erreur du flux ni ESC immédiatement après. Un compte complet
avec erreur pouvait donc alimenter le CRC et laisser relire les blocs suivants
avant le refus final ; ESC reçu pendant fread alimentait encore le CRC.
Les deux contrôles interviennent maintenant avant le remplissage du dernier
bloc, le CRC, la progression et toute lecture suivante.

Seule la sortie créée exclusivement est écrite, relue et nettoyée en cas
d'échec. Les sources BinSCII, les fichiers préexistants et la mémoire
auxiliaire restent intacts. Lorsque le nettoyage échoue, tous les octets
de la sortie complète sont conservés avec le message d'échec ; aucune
réussite du décodage n'est annoncée.

Les 240 nouveaux scénarios exécutent le vrai code C : sorties de 1, 49, 513,
2560 et 12289 octets, fichier unique ou parties séparées, première, deuxième,
médiane ou dernière lecture, erreur avec compte complet, ESC, les deux ou
compte court avec erreur, nettoyage réussi ou impossible. Avant correction,
180 échouaient et 60 servaient de contrôles. Les tests comptent les lectures,
sondes EOF et fermetures, contrôlent la position finale et le CRC exact des
seuls blocs précédant le défaut, et comparent tous les octets des sources,
fichiers préexistants et sorties éventuellement conservées.

Les 23 tests SCIIBIN, les 15 tests de gardes et les 8 contrôles de distribution
800K après reconstruction passent. Builds et dispositions 65C02/6502 validés :
SCIIBIN mesure 6129/6140 octets, BSS fin `$3DC2`/`$3DCE`, soit
573/561 octets disponibles avant `$4000`. Tous les contrôles de disposition
restent actifs. La vérification existante repose sur les CRC BinSCII ; cette
correction n'en renforce pas la résistance aux collisions. Aucune atomicité
physique en cas de coupure n'est promise.

## IMGCONV : contrôle immédiat des relectures de sortie (12 octobre 2026)

La vérification des en-têtes et demi-blocs comparait les comptes et octets
sans contrôler immédiatement l'erreur du flux ni ESC reçu pendant fread.
Une erreur avec compte complet pouvait laisser poursuivre la relecture
jusqu'au contrôle final. ESC pendant le premier demi-bloc pouvait laisser
lire le second ; ESC pendant le dernier pouvait laisser effectuer les
sondes EOF. Le helper read_output vérifie maintenant ces états avant toute
comparaison ou lecture suivante, pour les en-têtes 2MG/DiskCopy et les
blocs PO/DSK/2MG/DiskCopy.

Seul le nouveau fichier créé exclusivement est écrit, relu et nettoyé.
L'ancienne destination reste à son nom jusqu'à la validation ; aucune
source, sauvegarde préexistante ou mémoire auxiliaire n'est modifiée.
Lorsque le nettoyage échoue, tous les octets de IMGCONV.TMP sont conservés,
l'ancienne destination reste intacte et aucun succès n'est annoncé.

Les 192 nouveaux scénarios exécutent le vrai code C sur six conversions :
PO vers 2MG, DSK ou DiskCopy ; DSK, 2MG ou DiskCopy vers PO. Ils couvrent
la première, deuxième, médiane et dernière lecture de sortie, ESC,
erreur avec compte complet, les deux ou compte court avec erreur,
nettoyage réussi ou impossible. Avant correction, 96 échouaient et 96
servaient de contrôles. Les tests comptent les lectures et imposent
l'absence de toute lecture après le défaut, contrôlent ouvertures,
fermetures, confirmations et absence de renommage, et comparent tous les
octets des sources, anciennes destinations et temporaires conservés.

Les 28 tests de sécurité IMGCONV, les 6 tests de formats, les 15 tests de
gardes et les 8 contrôles de distribution 800K après reconstruction passent.
Builds et dispositions 65C02/6502 validés : IMGCONV mesure 8782/8950 octets,
BSS fin `$3F36`/`$3FDF`, soit 201/32 octets disponibles avant `$4000`.
Tous les contrôles de disposition restent actifs. La marge 6502 reste
serrée ; aucune atomicité physique en cas de coupure n'est promise.

## IMGCONV : ESC avant création et première écriture (12 octobre 2026)

Un ESC reçu pendant les métadonnées ou la confirmation du remplacement
laissait encore CREATE ouvrir une sortie. Un ESC pendant CREATE ou fopen
pouvait aussi laisser écrire l'en-tête 2MG ou DiskCopy avant son refus.
Le contrôle intervient maintenant avant CREATE, puis après l'ouverture
et avant la première écriture. Le helper stopped partage la lecture et
l'acquittement du clavier entre ces contrôles et les contrôles d'I/O existants.

Avant CREATE, seule la source en lecture est fermée, sans tentative de
nettoyage. Après CREATE, seul le nouveau fichier appartenant à l'opération
est fermé et nettoyé. Si sa suppression échoue, le fichier vide est conservé
avec le message de nettoyage impossible. L'ancienne destination, les fichiers
préexistants, la source et la mémoire auxiliaire restent intacts.

Les 84 nouveaux scénarios exécutent le vrai code C sur six conversions
PO/DSK/2MG/DiskCopy, nouvelle destination ou remplacement, ESC pendant les
métadonnées, la confirmation (remplacement seulement), CREATE ou l'ouverture,
nettoyage réussi ou impossible. Ils contrôlent les créations, suppressions,
ouvertures, fermetures, confirmations, absence de renommage et zéro octet
écrit, puis comparent toutes les données conservées. Avant correction,
52 nouveaux scénarios échouaient et 32 servaient de contrôles. Deux assertions
antérieures ont été adaptées : ESC initial ne crée plus de sortie et ne
nécessite donc plus de nettoyage ; l'échec de nettoyage après ESC pendant
CREATE conserve maintenant une sortie vide au lieu d'un en-tête écrit.
Ces deux comportements échouaient aussi avant correction.

Le premier build 6502 dépassait la fenêtre de 11 octets. La copie de l'API
native s'arrête maintenant avant cfg_path : IMGCONV n'utilise aucun service
de configuration, média ou AUX de cette fin de structure. Les offsets des
champs utilisés restent identiques pour les trampolines. La sortie avant
CREATE réutilise aussi la fermeture existante de la source. Ces adaptations
ne retirent aucun contrôle de disposition.

Les 29 tests de sécurité IMGCONV, les 6 tests de formats, les 15 tests de
gardes et les 8 contrôles de distribution 800K après reconstruction passent.
Builds et dispositions 65C02/6502 validés : IMGCONV mesure 8815/8984 octets,
BSS fin `$3F4B`/`$3FF5`, soit 180/10 octets disponibles avant `$4000`.
La marge 6502 reste serrée ; aucune atomicité physique en cas de coupure
n'est promise.

## UNSQ : aucune vidange partielle après ESC pendant une lecture (12 octobre 2026)

Le lecteur refusait correctement un refill de source annulé, mais one
appelait encore flush avant de fermer la sortie. Si des octets décodés
attendaient dans obuf, cette dernière vidange les écrivait avant de contrôler
ESC. flush contrôle maintenant l'annulation avant fwrite, en conservant
le contrôle après écriture pour ESC reçu pendant fwrite.

Seul le fichier créé exclusivement est écrit ou nettoyé ; l'archive, les
fichiers préexistants et la mémoire auxiliaire restent intacts. Après ESC,
aucun octet encore en mémoire n'est écrit. Si le nettoyage échoue, seuls
les octets déjà écrits avant la lecture annulée sont conservés avec le
message de nettoyage impossible, sans annonce de réussite.

Les 210 nouveaux scénarios exécutent le vrai code C : QQ et ACU comprimés,
avec données variées ou longues répétitions RLE, ainsi qu'ACU stocké,
sorties de 513, 1536 ou 4097 octets, annulation aux refills 1, 2, 3, 4, 5,
8 ou 16, nettoyage réussi ou impossible. Les points non atteints servent
de contrôles de réussite. Avant correction, 28 scénarios échouaient et
182 servaient de contrôles. Les tests enregistrent les octets écrits avant
ESC, imposent zéro appel d'écriture après ESC, vérifient la fermeture de
la source et comparent tous les octets de l'archive, des fichiers existants
et du préfixe éventuellement conservé.

Les 31 tests UNSQ, les 15 tests de gardes et les 8 contrôles de distribution
800K après reconstruction passent. Builds et dispositions 65C02/6502 validés :
UNSQ mesure 6827/6903 octets, BSS fin `$3D95`/`$3DE2`, soit
618/541 octets disponibles avant `$4000`. Tous les contrôles de disposition
restent actifs. Aucune atomicité physique en cas de coupure n'est promise.

## SMALLDOS : ESC avant comparaison et progression de vérification (12 octobre 2026)

ESC reçu pendant la relecture d'un secteur de sortie était contrôlé après
memcmp et la progression. Le contrôle intervient maintenant immédiatement
après fread et ferror, avant comparaison et affichage. Le refus final
existait déjà : cette correction évite de traiter un secteur dont la
relecture vient d'être annulée.

Seul le fichier créé exclusivement est écrit, relu et nettoyé en cas
d'échec. L'image source, les fichiers préexistants et la mémoire auxiliaire
restent intacts. Si le nettoyage échoue, tous les octets de la sortie
complète sont conservés avec le message de nettoyage impossible ; aucune
réussite n'est annoncée pour ce fichier.

Les 224 nouveaux scénarios exécutent le vrai code C : sources de 1, 513
ou 4097 octets avec leur remplissage de secteur, deux sens de pistes,
ordres DOS/ProDOS, première, médiane ou dernière lecture de vérification,
ESC, erreur avec compte complet, les deux ou compte court avec erreur,
nettoyage réussi ou impossible. Avant correction, 56 échouaient et 168
servaient de contrôles. Les tests comptent les relectures, comparaisons
et progressions après le défaut, vérifient créations, écritures et fermeture
de la source, et comparent tous les octets de l'image, des fichiers
préexistants et de la sortie éventuellement conservée.

Les 15 tests SMALLDOS, les 15 tests de gardes et les 8 contrôles de distribution
800K après reconstruction passent. Builds et dispositions 65C02/6502 validés :
SMALLDOS mesure 4436/4479 octets, BSS fin `$3112`/`$313E`, soit
3821/3777 octets disponibles avant `$4000`. Tous les contrôles de disposition
restent actifs. Aucune atomicité physique en cas de coupure n'est promise.

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

## Menu complet des lecteurs (2026-10-12)

La liste passe de 88 entrées de 64 octets à 128 entrées de 40 octets :
12 octets pour le nom complet, 28 pour la description terminée (27 visibles).
Elle occupe exactement MAIN `$2C00–$3FFF`, soit 5 120 octets, sans AUX ni
écriture sur volume. Le plafond de MENU dans `tools/check_layout.py` suit
la nouvelle frontière `$2C00` ; tous les contrôles restent actifs.

MENURO finit à `$2A08` (65C02) / `$2A31` (6502), laissant **503/462 octets**
avant la table. Les 115 commandes visibles XL sont accessibles, y compris
les lecteurs d'images et de films auparavant perdus en fin de liste.
Les enregistrements du catalogue restent à 78 octets sur disque et sont
compactés lors de la lecture ; les doublons et relais internes sont exclus.

Le vrai C passe 9 tests avec cc65 2.19 et HEAD, hôte ASan/UBSan et les deux
CPU sim65 : gardes avant/après la table, saturation, description longue,
catalogue, doublons et choix d'une commande tardive. Les builds et quatre
images distribuées sont validés. `bench/menu.py` passe **60/60 contrôles par
CPU**, avec AUX, volume entier et garde de pile conservés.
Le banc complet `bench/retrotext.py` passe **16/16 par CPU**, dont FONTRIX
depuis le menu et le lecteur SCASM auparavant masqué.

## Navigation Movie Maker (2026-10-12)

MVMOVIE réutilise son décodeur de commandes pour revenir à une image ou
redémarrer : seules des positions et un numéro d'image sont ajoutés.
Le flux d'animation est relu jusqu'à l'image demandée ; recherches et lectures
restent contrôlées. Aucun historique proportionnel au film, aucune écriture
AUX ou volume. La page lores reste dans MAIN `$0400–$07FF` et les pixels dans
la BSS du lecteur. Validation et fermeture complètes avant le premier affichage.

Fichiers MVMOVIE : **5031/5096 octets**, BSS **2633 octets** (65C02/6502).
Fin BSS `$38EF/$3930`, marges **1808/1743 octets** avant `$4000`.
Les deux builds et les quatre images passent avec les gardes actives.
Les 11 tests du vrai C passent avec cc65 2.19 et HEAD, dont les deux CPU sim65,
pixels après retour/redémarrage, limite de première image et erreurs de
recherche/lecture au retour. POM2 : **15/15 contrôles par CPU**, pages lores
comparées, AUX, volume source complet et garde de pile conservés.
L'aperçu conserve ses limites : rectangles opaques 40×48, cadence originale
et masque transparent non reproduits. Le retour peut relire beaucoup de
commandes pour une image tardive ; aucune durée constante n'est promise.

## Imports MacPaint (2026-10-12)

IDV1 reconnaît les imports MacBinary PNTG ProDOS BIN/typeless sur un
échantillon MAIN d'au moins 128 octets, avec octet initial nul, type PNTG
aux offsets 65–68 et EOF réel d'au moins 2080 octets (640 d'en-têtes,
720 lignes compressées à deux octets minimum). IDFORMATS et OPEN ajoutent
le suffixe `.PNTG`. Aucun décodeur ni accès AUX n'est ajouté au détecteur ;
MACPAINT conserve sa validation, son défilement et le consentement AUX.

Le type est lu une fois dans `extra_v1`. Les longueurs des suffixes IDV1
tiennent dans un octet (noms de panneau bornés à 17) ; le test EOF >=256
de Magic Window DOS était déjà impliqué par n>=256 et `id_restore`.
Ces économies conservent les plafonds existants, sans retirer de garde.
IDV1 mesure **9156/9277 octets**, BSS 121, finit à `$3F3C/$3FB5`,
marges **195/74 octets**. IDFORMATS mesure **9143/9391**, BSS 68,
finit à `$3EFA/$3FF2`, marges **261/13 octets** (65C02/6502).
La réserve IDFORMATS 6502 reste très faible.

Les deux builds et quatre images passent. Détecteur (15), routage C/OPEN
assembleur (35), décodeur MacPaint (5) et DOS (12) passent avec cc65 2.19
et HEAD sur les deux CPU. Handoff (4), inventaire (7), signedness (zéro site)
et contrôles de disposition passent. Les tests couvrent les collisions
8K/16K, les noms trompeurs, les en-têtes courts et les tailles périmées.
Les fichiers sources sont comparés octet par octet.
OPEN finit exactement à `$1FFF` sur les deux CPU après l'ajout de `.PNTG`
à la table des suffixes : **aucun octet libre avant `$2000`**. Le contrôle
reste actif et refusera toute croissance qui empiète sur la page graphique.
POM2 imports : **36/36 par CPU**, Entrée/I, pixels après défilement,
avertissement/refus avant AUX, reconstruction de RAM vide, entrée malformée,
garde de pile et volume source entier inchangé.
POM2 sur le build final, navigation entre deux `.PNTG` via OPEN : **8/8
par CPU**, pixels après Droite/Gauche, refus AUX, RAM vide reconstruite,
garde de pile et volume entier conservés.

## Pixmaps DGR complets (2026-10-12)

DGRVIEW réutilise son tracé masqué pour 80×48 pixels, soit 3840 octets.
Un octet de dépassement détecte les sources trop grandes : staging MAIN
`$3000–$3F00` inclus, sans allocation AUX. Le plafond code/BSS reste
`$3000` ; les pages sauvegardées restent bornées à 2048 octets. Les écritures
de rendu restent sur les pages texte/lores MAIN et AUX `$0400–$07FF`, trous
d'écran exclus. Aucun accès au contenu du disque RAM AUX `$0800–$BFFF`,
aucune reconstruction de `/RAM` ni écriture source.

Une erreur de lecture (même avec des octets retournés) ou de fermeture
refuse l'affichage avant toute écriture de page. Les tests comparent les
deux banques préremplies et les octets source pour ouverture impossible,
lecture partielle/en erreur, fermeture en erreur et page trop grande.
L'adaptateur sim65 utilise des pointeurs de banque explicites : le ternaire
de tableaux du banc hôte était mal compilé par HEAD ; le code matériel
conserve ses commutations explicites.

Fichiers DGRVIEW **3894/3987 octets**, BSS **69**, fin `$2A7A/$2AD7`,
marges **1413/1320 octets** avant `$3000` (65C02/6502). Tous les contrôles
de disposition restent actifs, les deux builds et quatre images passent.
Les **30 tests** exécutent le vrai C sur l'hôte et les deux CPU sim65,
avec cc65 2.19 et HEAD. POM2 sur volumes jetables : **11/11 par CPU**,
pixels et masques 80×48, quatre bords, garde `$3F01–$3FFF`, annulation de
largeur, source trop grande, page sauvegardée trop grande, RAM occupé,
garde de pile et volume entier conservés. Les deux variantes du banc
figurent dans le runner de qualification.

## Zoom des pixmaps DGR (2026-10-12)

Z réutilise le rendu DGRVIEW pour agrandir les pixmaps ×2/×4, en revenant
à ×1 dès que le niveau suivant dépasse 80×48. Le rendu initial reste ×1 ;
dimensions source, centrage et masque sont conservés. Le staging MAIN
`$3000–$3F00` n'est ni relu ni modifié. Seuls les pixels visibles MAIN/AUX
`$0400–$07FF` sont écrits ; trous d'écran et AUX `/RAM` restent intacts.
Les pages sauvegardées et les images à en-tête DGR ne sont pas zoomées.

Fichiers DGRVIEW **4162/4250 octets**, BSS **76**, fin `$2B8D/$2BE5`,
marges **1138/1050 octets** avant `$3000` (65C02/6502). Les deux builds,
quatre images et contrôles de disposition passent sans retirer de garde.
Les **31 tests** passent avec cc65 2.19 et HEAD : vrai C hôte et deux CPU
sim65, comparaison de chaque pixel, masques, centrage, limites des niveaux,
retour à ×1, trous d'écran et absence de zoom sur les autres formats.
POM2 sur volumes jetables : **19/19 par CPU**, dont le cycle ×1/×2/×4/×1
et la conservation du contenu RAM à chaque niveau, garde de pile et volume
source entier inchangé.

## Dernière image Movie Maker (2026-10-12)

L utilise le compteur 16 bits obtenu pendant la validation initiale
complète du film. Le saut reconstruit l'image cible par les recherches et
lectures contrôlées existantes, sans afficher les images intermédiaires ni
conserver une table d'images. B et R restent disponibles après le saut.
Sur les films longs, la relecture depuis le début peut prendre du temps.

Écritures : buffers MAIN de l'overlay et pixels visibles de la page lores
MAIN `$0400–$07FF`, trous exclus. Aucun accès AUX, reconstruction RAM,
écriture sur volume ou modification du fichier source.
Fichiers MVMOVIE **5106/5172 octets**, BSS **2635**, fin `$393C/$397E`,
marges **1731/1665 octets** avant `$4000` (65C02/6502). Les contrôles
de disposition restent actifs ; les deux builds et quatre images passent.
Les 12 tests médias passent avec cc65 2.19 et HEAD, vrai C hôte et deux
CPU sim65 : L/l, film à une image, compteur au-delà de 255, B/R après L,
erreurs de recherche/lecture et octets source conservés. POM2 passe
19/19 contrôles par CPU sur volumes jetables : pixels suivant/précédent,
redémarrage/dernière image, AUX, garde de pile et volume entier inchangés.

## Damier DGRVIEW (2026-10-12)

C affiche un damier gris/blanc derrière les pixmaps a2dgrx, à ×1/×2/×4,
puis rétablit le fond noir. Le masque existant conserve le damier pour les
pixels transparents ; un pixel noir opaque reste noir. Les cases de 4×4
utilisent les couleurs 5/15 : les deux gris lores 5/10 peuvent se confondre
en composite. L'entrée du lecteur initialise toujours le fond noir.

Le fichier et son staging MAIN ne sont pas modifiés. Le rendu écrit
uniquement les pixels visibles MAIN/AUX `$0400–$07FF`, sans toucher aux
trous d'écran, à AUX `/RAM` ni aux volumes. C ne change pas les pages
sauvegardées ou les images DGR à en-tête.
Fichiers DGRVIEW **4278/4371 octets**, BSS **77**, fin `$2C02/$2C5F`,
marges **1021/928 octets** avant `$3000` (65C02/6502). Les deux builds,
quatre images et contrôles de disposition passent avec toutes les gardes.
Les **32 tests** passent avec cc65 2.19 et HEAD : vrai C hôte et deux CPU
sim65, chaque pixel du damier et du sprite, noir opaque, masques, zoom,
activation/désactivation, autres formats inchangés et trous conservés.
POM2 final gris/blanc : **27/27 contrôles par CPU** sur volumes jetables,
pixels/masques à ×1/×2/×4, restauration du fond noir à ×4, contenu RAM
occupé inchangé à chaque rendu, garde de pile et volume source conservés.

## Extrémités MacPaint (2026-10-12)

T/B (majuscules ou minuscules) choisissent directement les vues indexées
0 et 11, lignes 0–191 et 528–719. Les flèches conservent leurs pas de
96 lignes, y compris après un saut. Le lecteur réutilise les checkpoints
48 lignes et le décodeur PackBits existants, sans nouvelle allocation.

Écritures : buffers et code auto-modifié MAIN sous `$2000`, pages DHGR
MAIN/AUX `$2000–$3FFF`, cellule d'activité MAIN `$06F7` et reconstruction
du disque RAM par le service existant au retour. Le consentement avant
réutilisation de la mémoire AUX reste obligatoire si RAM n'est pas vide
avec certitude : tous ses fichiers seraient perdus. Aucune écriture source
ni sur les volumes d'entrée ; essais sur HD jetables seulement.

Fichiers MACPAINT **1129/1132 octets**, BSS **123**, fin `$1FE3/$1FE6`,
marges **28/25 octets** avant `$2000` (65C02/6502). Cette réserve reste
faible ; aucune garde n'est retirée. Les deux builds et quatre images
passent. Les 5 tests du décodeur assembleur passent avec cc65 2.19 et HEAD
sur les deux CPU sim65 ; aucun changement du décodage des pixels.
POM2 : **15/15 contrôles par CPU**, vrai point d'entrée et overlay livré,
deux plans graphiques comparés à chaque saut T/B, répétitions, minuscules,
butées et flèches après saut. Avertissement avant AUX, refus conservant
RAM, reconstruction de RAM vide, garde de pile et volume source entier
inchangé. Les deux variantes figurent dans `bench/all.py` ; inventaire 7/7.

## Sauts de dix images Movie Maker (2026-10-12)

+/− réutilisent la relecture MVMOVIE pour atteindre dix images plus loin
ou plus tôt, bornées au nombre validé d'images et à la première. Les
recherches/lectures restent contrôlées et les images intermédiaires ne sont
pas rendues. B, R et L restent disponibles après un saut ; la relecture
depuis le début peut prendre du temps sur un film long.

Écritures inchangées : buffers MAIN de l'overlay et pixels visibles de
la page lores MAIN `$0400–$07FF`, trous exclus. Aucun nouveau buffer,
accès AUX, reconstruction RAM ou écriture source/volume.
Fichiers MVMOVIE **5243/5314 octets**, BSS **2635**, fin `$39C5/$3A0C`,
marges **1594/1523 octets** avant `$4000` (65C02/6502). Les deux builds,
quatre images et contrôles de disposition passent avec toutes les gardes.
Les **13 tests médias** passent avec cc65 2.19 et HEAD, vrai C hôte et
deux CPU sim65 : films de 1/9/10/11/12/300 images, bornes des sauts,
combinaisons avec L/B/R et erreurs de recherche/lecture, sources conservées.
POM2 : **29/29 contrôles par CPU** sur HD jetables, pixels exacts après
les sauts et aux extrémités, retour/redémarrage, AUX et garde de pile
intacts, volume source entier inchangé. Les deux variantes sont inscrites
dans `bench/all.py` ; inventaire 7/7, signedness zéro site.

## Aperçu du masque DGRVIEW (2026-10-12)

M affiche l'opacité des pixmaps en blanc sur noir, en réutilisant le tracé
existant : tout nibble de masque non nul est opaque, y compris quand la
couleur source est noire. Le zoom reste actif ; le damier est masqué pendant
cet aperçu, puis couleurs et fond choisi sont restaurés avec M. C peut
changer le fond à restaurer. Chaque entrée initialise le mode couleurs.

Écritures limitées aux pixels visibles MAIN/AUX `$0400–$07FF`, trous
exclus. Le staging MAIN, les fichiers et AUX `/RAM` restent intacts ;
aucune relecture, reconstruction RAM ou écriture volume. Les pages
sauvegardées et les images DGR à en-tête ignorent cette commande.
Fichiers DGRVIEW **4335/4426 octets**, BSS **78**, fin `$2C3C/$2C97`,
marges **963/872 octets** avant `$3000` (65C02/6502). Les deux builds,
quatre images et contrôles de disposition passent avec toutes les gardes.
Les **33 tests** passent avec cc65 2.19 et HEAD : vrai C hôte et deux
CPU sim65, tous les nibbles de masque, noir opaque, combinaisons M/C/Z,
restauration des couleurs et du fond, autres formats et trous conservés.
POM2 : **37/37 contrôles par CPU** sur HD jetables, pixels exacts du masque
à ×1/×2/×4 et retour au damier en couleurs, contenu RAM occupé inchangé
à chaque rendu, garde de pile et volume source entier conservés.

## Décor et acteurs Movie Maker (2026-10-12)

O/o réutilise `mv_scene` pour redessiner la même image avec le décor seul
ou avec les acteurs de l'aperçu. Les sprites du frame courant restent
disponibles pendant la bascule. Le choix suit les déplacements B/R/L/+/-
et est remis au mode acteurs à l'entrée. Chaque redessin contrôle les
lectures/recherches de bitmaps et ne publie l'image qu'après succès.

Écritures : buffers MAIN de l'overlay et pixels visibles de la page lores
MAIN `$0400–$07FF`, trous exclus. Aucun accès AUX, reconstruction RAM ou
écriture source/volume. Le rendu reste un aperçu opaque 40×48, sans
reproduction du masque transparent ni de la cadence originale du film.
Fichiers MVMOVIE **5286/5359 octets**, BSS **2636**, fin `$39F1/$3A3A`,
marges **1550/1477 octets** avant `$4000` (65C02/6502). Les deux builds,
quatre images et contrôles de disposition passent avec toutes les gardes.
Les **15 tests médias** passent avec cc65 2.19 et HEAD, vrai C hôte et
deux CPU sim65 : décors colorés, O/o sur la même image, navigation avec et
sans acteurs, restauration et erreurs de recherche/lecture, sources intactes.
POM2 : **42/42 contrôles par CPU** sur HD jetables, pixels exacts après
les bascules et déplacements, acteurs restaurés à la réouverture, AUX et
garde de pile intacts, volume source entier inchangé.

## Fond et objets PCS (2026-10-12)

PCSVW conserve le bitmap original dans AUX `$6000–$7FFF` avant de tracer
les polygones dans AUX `$4000–$5FFF`. Ces deux plans appartenaient déjà à
la zone initialisée du lecteur. O/o engage alternativement une vue dans
MAIN `$2000–$3FFF`, par la routine ROM existante, sans lecture de fichier
ni modification des vues AUX. Aucun code de jeu n'est exécuté.

Le passage complet de validation et la fermeture précèdent le consentement
et la première écriture AUX. Réutiliser AUX détruit tous les fichiers de
RAM ; l'avertissement/refus restent obligatoires si elle n'est pas vide
avec certitude. La reconstruction RAM au retour reste dans la queue
protégée. Aucune écriture sur les sources ; les HD d'essai sont jetables.

La queue partagée avec DGMAGI a besoin de 30 octets de code et d'un octet
d'état supplémentaires. `sdk/v1gfx.cfg` réserve désormais `$1B00–$1CFF`
à la queue et `$1D00–$3FFF` à la phase C, toujours détruite seulement après
son retour. Les limites restent imposées par le linker, sans désactivation.
VGTAIL finit à `$1CAD`, VGDATA à `$1CB1`, soit **78 octets libres**.
PCSVW mesure **5327/5367 octets**, BSS **826**, fin `$3308/$3330`,
marges **3319/3279 octets** avant `$4000` (65C02/6502).
DGMAGI mesure **6745/6822**, BSS **332**, fin `$36A4/$36F1`,
marges **2395/2318** ; il conserve son comportement à une seule vue.
Les deux builds et quatre images passent avec toutes les gardes actives.
Les **14 tests médias** passent avec cc65 2.19 et HEAD, vrai C hôte et deux
CPU sim65 : bitmap original conservé, aperçu comparé octet par octet,
corpus PCS/DPC, erreurs d'E/S et validation avant consentement.
POM2 PCS : **28/28 contrôles par CPU**, Entrée/I, fond et aperçu exacts,
O/o répétés, deux vues AUX intactes, avertissement/refus RAM, reconstruction,
garde de pile et volume entier inchangé. Les deux variantes sont inscrites
dans `bench/all.py` ; inventaire 7/7.
POM2 DGMAGI avec la nouvelle queue : **10/10 par CPU**, mêmes pixels
DHGR, sortie par O, consentement/refus, RAM vide reconstruite, garde de
pile et volume entier inchangé.

## Miroirs des sprites DGRVIEW (2026-10-12)

H/V inversent les coordonnées horizontales/verticales du sprite dans son
rectangle centré, sans modifier le staging MAIN. Chaque touche restaure
son orientation lorsqu'elle est pressée à nouveau. Zoom, damier et masque
restent combinables ; le fond du damier reste fixé à l'écran. Les pages
sauvegardées et les images DGR à en-tête ignorent H/V.

Écritures inchangées : pixels visibles MAIN/AUX `$0400–$07FF`, trous
exclus. Aucun accès au contenu AUX `/RAM`, reconstruction RAM, écriture
source/volume ou nouvelle lecture. L'orientation est réinitialisée à l'entrée.
Fichiers DGRVIEW **4485/4580 octets**, BSS **79**, fin `$2CD3/$2D32`,
marges **812/717 octets** avant `$3000` (65C02/6502). Les deux builds,
quatre images et contrôles de disposition passent avec toutes les gardes.
Les **34 tests** passent avec cc65 2.19 et HEAD : vrai C hôte et deux
CPU sim65, chaque pixel après H/V et les combinaisons avec Z/C/M, dimensions
impaires, limites 80×48, couleurs/masques, restauration, trous et sources
conservés ; la note reste sous 80 caractères.
POM2 : **49/49 contrôles par CPU** sur HD jetables, pixels exacts après
H/V puis M et restauration des orientations, contenu RAM occupé inchangé
à chaque rendu, garde de pile et volume source entier conservés.

## Défilement fin MacPaint (2026-10-12)

+/− déplacent la vue d'un checkpoint de 48 lignes, entre les positions
0 et 11. Les flèches gardent leurs pas de 96 lignes et T/B leurs sauts
aux extrémités. Le décodeur et l'index existants sont réutilisés sans
nouvelle allocation ni modification des données de l'image.

Écritures inchangées : buffers et code auto-modifié MAIN sous `$2000`,
pages DHGR MAIN/AUX `$2000–$3FFF`, cellule d'activité MAIN `$06F7` et
reconstruction RAM au retour. Le consentement précède toute réutilisation
AUX si RAM n'est pas vide avec certitude ; tous ses fichiers seraient
perdus. Les sources et volumes d'entrée ne sont pas écrits.

Huit octets de padding inutilisé de l'en-tête et un message d'erreur
raccourci permettent de garder toutes les gardes mémoire actives.
Fichiers MACPAINT **1142/1145 octets**, BSS **123**, fin `$1FF0/$1FF3`,
marges **15/12 octets** avant `$2000` (65C02/6502). La réserve reste faible.
Les deux builds et quatre images passent. Les **5 tests** du décodeur
assembleur passent avec cc65 2.19 et HEAD sur les deux CPU sim65.
POM2 : **23/23 contrôles par CPU** sur HD jetables, deux plans comparés
à chaque déplacement fin, saut T/B et déplacement grossier, butées,
avertissement/refus avant AUX, reconstruction de RAM vide, garde de pile
et volume source entier conservés. Les deux variantes restent inscrites
dans `bench/all.py`.

## Réinitialisation des sprites DGRVIEW (2026-10-12)

R/r restaure la vue ×1, les orientations d'origine, les couleurs et le
fond noir après combinaison de Z/C/M/H/V. Le lecteur redessine le staging
existant sans lecture supplémentaire ; les pages sauvegardées, textes et
images DGR à en-tête ignorent cette commande.

Écritures : état et pixels visibles MAIN/AUX `$0400–$07FF`, trous exclus.
Le staging MAIN `$3000–$3F00` reste inchangé après chaque réinitialisation.
Aucun accès au contenu AUX `/RAM`, reconstruction RAM ou écriture source
et volume. Les essais natifs utilisent des HD jetables.
Fichiers DGRVIEW **4519/4616 octets**, BSS **79**, fin `$2CF5/$2D56`,
marges **778/681 octets** avant `$3000` (65C02/6502). Les deux builds et
quatre images passent avec toutes les gardes de disposition actives.
Les **35 tests** passent avec cc65 2.19 et HEAD : vrai C hôte et deux CPU
sim65, comparaison de tous les pixels, masques et trous après R/r répétés,
dimensions 1×1, impaires et 80×48, options réactivées après réinitialisation,
formats inchangés, sources conservées et note sous 80 caractères.
POM2 : **74/74 contrôles par CPU**, pixels et RAM occupé après chaque
option, réinitialisation de toutes les options, staging inchangé après
R/r, garde de pile et volume source entier préservés. Les deux variantes
restent inscrites dans `bench/all.py`.

## Miroirs Movie Maker (2026-10-12)

H/V inversent horizontalement/verticalement la scène réduite 40×48,
après composition et découpage des acteurs. Chaque touche restaure son
orientation au second appui. Les miroirs s'appliquent au décor seul O,
restent actifs pendant B/R/L/+/− et sont réinitialisés à l'ouverture.

Le tampon MAIN existant de 1920 pixels est inversé en place, sans tableau
d'historique ni nouveau tampon d'image. Toute nouvelle vue reconstruit
ce tampon par les lectures contrôlées existantes avant de l'inverser.
La recherche de retour au flux doit réussir avant la transformation et
l'affichage. Écritures : état et tampon MAIN de l'overlay, pixels visibles
MAIN `$0400–$07FF`, trous exclus. Aucun accès au contenu AUX `/RAM`,
reconstruction RAM, écriture source ou volume ; essais sur HD jetables.

Fichiers MVMOVIE **5686/5777 octets**, BSS **2637**, fin `$3B82/$3BDD`,
marges **1149/1058 octets** avant `$4000` (65C02/6502). Les deux builds
et quatre images passent avec toutes les gardes de disposition actives.
Les **16 tests médias** passent avec cc65 2.19 et HEAD, vrai C hôte et
deux CPU sim65 : miroirs répétés, décor coloré, acteurs coupés aux bords,
navigation et erreurs de lecture/recherche sans nouvelle image affichée.
POM2 : **60/60 contrôles par CPU**, tous les pixels comparés à un oracle
indépendant après H/V, O, avance/retour/redémarrage/fin et sauts de dix,
réouverture sans miroir, trous d'écran, AUX, garde de pile et volume source
entier conservés. Les deux variantes restent inscrites dans `bench/all.py`.
L'aperçu conserve ses limites : acteurs opaques, résolution réduite et
navigation manuelle, sans reproduction de la cadence d'animation originale.

## Zoom ajusté DGRVIEW (2026-10-12)

F/f choisit directement le plus grand facteur ×1/×2/×4 qui tient dans
80×48, en conservant damier, masque et miroirs. Z garde son cycle existant ;
après F, Z revient à ×1. R conserve sa réinitialisation complète.
Les pages sauvegardées, textes et images DGR à en-tête ignorent F.

Le rendu utilise le staging MAIN existant sans lecture supplémentaire.
Écritures : état et pixels visibles MAIN/AUX `$0400–$07FF`, trous exclus.
Aucun accès au contenu AUX `/RAM`, reconstruction RAM, écriture source
ou volume. Les essais natifs utilisent des HD jetables.
Fichiers DGRVIEW **4549/4649 octets**, BSS **79**, fin `$2D13/$2D77`,
marges **748/648 octets** avant `$3000` (65C02/6502). Les deux builds et
quatre images passent avec toutes les gardes de disposition actives.
Les **36 tests** passent avec cc65 2.19 et HEAD : vrai C hôte et deux CPU
sim65, limites exactes 20×12/40×24, dépassement par un pixel horizontal ou
vertical, facteur ×1/×2/×4, F/f répétés, options conservées, Z/R après F,
pixels et trous conservés, autres formats inchangés et note sous 80 caractères.
POM2 : **95/95 contrôles par CPU**, image 80×48 à ×1 et petit sprite à
×4, masque/damier/miroirs avant et après F, Z puis F et réinitialisation,
RAM occupé, staging, garde de pile et volume source entier conservés.
Les deux variantes restent inscrites dans `bench/all.py`.

## Avance automatique Movie Maker (2026-10-12)

S/s active l'avance automatique et l'arrête sur l'image courante sans
redessin ni saut. Une autre touche arrête l'automatisme puis effectue sa
commande habituelle. L'expiration de l'attente réutilise la progression
normale du décodeur ; la fin du film revient aux panneaux. Une ouverture
réinitialise le mode manuel, le décor et les orientations.

La routine clavier du diaporama est partagée dans `src/key_wait.inc`,
avec les mêmes instructions pour le résident. MVMOVIE utilise quatre
périodes, environ **2,88 secondes à 1 MHz**, plus le rendu. L'attente lit
seulement `$C000` et laisse la touche en place pour le service clavier.
Pas de nouvelle banque ni tampon d'image : état et rendu MAIN existants,
pixels visibles MAIN `$0400–$07FF`, trous exclus. Aucun accès au contenu
AUX `/RAM`, reconstruction RAM, écriture source ou volume.

Fichiers MVMOVIE **5758/5853 octets**, BSS **2638**, fin `$3BCB/$3C2A`,
marges **1076/981 octets** avant `$4000` (65C02/6502). Les deux builds
et quatre images passent avec toutes les gardes de disposition actives.
L'aide respecte la limite de 79 caractères, vérifiée par les tests.
Les **17 tests médias** passent avec cc65 2.19 et HEAD, vrai C hôte et
deux CPU sim65 : expiration, pause, interruption, annulation, film à une
image, fin, erreurs de recherche/lecture/fermeture et sources conservées.
Les tests de présentation exécutent le vrai assembleur : diaporama
inchangé, délai Movie Maker mesuré en cycles et interruption immédiate
sans consommer la touche, sur les deux processeurs.
Les **4 tests de présentation** passent avec cc65 2.19. Avec HEAD, les
tests du délai et du rendu C passent, mais le test d'interface assembleur
dépasse le délai sur les deux CPU, même avec 120 secondes : cette suite
n'est pas entièrement qualifiée avec HEAD. Le délai partagé produit les
mêmes octets que la routine précédente sur les deux processeurs ; la
limite du banc reste à 60 secondes et aucune garde mémoire n'est retirée.
POM2 : **67/67 contrôles par CPU** sur HD jetables, pause stable, reprise,
commande B et Échap interrompant l'attente, réouverture manuelle, pixels
des images suivantes et retour à la fin, AUX, garde de pile et volume
source entier conservés. Les deux variantes restent dans `bench/all.py`.
L'aperçu conserve ses acteurs opaques et sa résolution 40×48 ; sa vitesse
dépend du processeur et ne reproduit pas la cadence d'animation originale.

## Vitesses Movie Maker (2026-10-12)

1/2/3 choisissent les délais rapide/normal/lent, sans redessiner ni
avancer l'image. L'automatisme reste actif pendant le réglage et reprend
une attente complète à la nouvelle vitesse. À l'arrêt, seul le réglage
change. B/R/L/+/− conservent la vitesse ; une ouverture rétablit normale.

La routine interruptible existante reçoit 1/4/8 périodes, soit environ
**0,72/2,88/5,77 secondes à 1 MHz**, plus le rendu, plus court sur machine
accélérée. Aucun nouveau tampon ni écriture source/volume : état et rendu
MAIN existants, pixels visibles MAIN `$0400–$07FF`, trous exclus. Aucun
accès au contenu AUX `/RAM` ni reconstruction RAM ; essais sur HD jetables.

Fichiers MVMOVIE **5799/5897 octets**, BSS **2639**, fin `$3BF5/$3C57`,
marges **1034/936 octets** avant `$4000` (65C02/6502). Les deux builds
et quatre images passent avec toutes les gardes de disposition actives.
La note reste sous 80 caractères. Les **18 tests médias** passent avec
cc65 2.19 et HEAD, vrai C hôte et deux CPU sim65 : délais transmis,
changement pendant l'automatisme, sélection manuelle, pause/reprise,
navigation conservant la vitesse, erreurs de recherche/lecture et sources
conservées. Le test ciblé de temporisation passe avec les deux compilateurs
et CPU : cycles pour 1/4/8 périodes, interruption immédiate et touche non
consommée. Le code du délai et du résident reste inchangé dans cette étape ;
la limite HEAD du banc d'interface décrite précédemment reste applicable.
POM2 ciblé : **22/22 contrôles par CPU**, imports, sélection à l'arrêt, trois vitesses,
pauses stables, réglage pendant l'avance, redémarrage puis reprise, sortie,
pixels, AUX, garde de pile et volume source entier conservés. Les deux
variantes restent inscrites dans `bench/all.py`.

Les 72 premiers contrôles du parcours complet ont réussi sur les deux CPU,
avant le refus HTTP lors de la restauration d'une vitesse hors plage.
Après correction par le preset officiel `max`, les contrôles ciblés
incluent les vérifications finales de conservation. Le parcours complet
de 75 contrôles n'a pas été intégralement relancé après cette correction
du banc ; le code du lecteur n'a pas changé pendant ce diagnostic.

Le banc temporisé utilise le preset émulateur 1×, et observe chaque pause
pendant sept secondes. `--speed 4000000` désigne des cycles par image vidéo,
pas 4 MHz : le turbo pouvait avancer avant que la commande du banc arrive.
Le contrôle garde ses comparaisons exactes, puis rétablit le turbo pour les
vérifications finales. `--auto-only` permet 22 contrôles ciblés par CPU.


### Rotations des pixmaps DGRVIEW — 2026-10-12

O tourne l'affichage courant de 90° dans le sens horaire. Le rendu existant
compose une transposition et les miroirs sans modifier les pixels chargés ;
les dimensions affichées suivent la transformation. Le zoom diminue pour
tenir dans 80×48, F/Z utilisent ces dimensions, R restaure aussi la rotation.
Si la nouvelle hauteur dépasserait 48 à ×1, la commande est ignorée avant
toute modification de l'état ou du rendu. La note tient dans 80 octets.

Écritures : état MAIN de l'overlay, staging MAIN `$3000–$3F00` au chargement
seulement, pixels visibles MAIN/AUX `$0400–$07FF` au rendu, trous exclus.
Aucun tampon supplémentaire, aucune écriture source/volume, aucun accès AUX
`$0800–$BFFF` de `/RAM`, aucune reconstruction RAM ni nouvelle confirmation.
Les commandes utilisent les pixels déjà chargés, après lecture et fermeture
contrôlées. Les pages sauvegardées et DGR à en-tête ignorent O.

Fichiers **4685/4773 octets**, BSS **82**, fin `$2D9F/$2DF7`, marges
**609/521 octets** avant `$3000` (65C02/6502). Builds des deux architectures
et quatre images validés avec les gardes de disposition actives.
Les **38 tests** passent avec cc65 2.19 et HEAD : vrai C hôte et sim65 des
deux CPU, comparaison indépendante de chaque pixel après rotation, miroirs,
zoom, fit, masque et damier, limites 48/49/80, quatre tours et reset, erreurs
d'ouverture/lecture/fermeture refusées avant écriture, sources et trous
d'écran conservés.

POM2 : **137/137 contrôles par CPU**, sur volumes jetables : pixels des deux
banques, rotations combinées avec miroirs et masque, zoom réduit puis fit,
refus du plein écran trop haut, staging inchangé après O/R, AUX occupée,
garde de pile et volume source entier conservés. Les deux parcours restent
inscrits dans `bench/all.py`.

### Fantavision image par image et boucle Movie Maker — 2026-10-12

Fantavision : pendant la pause, Droite/Entrée appelle une fois `fv_next`,
affiche la page qu'il vient de construire et reste dans l'attente clavier.
La fin d'un film compté ou d'une image unique conserve la dernière vue.
Space/Échap, Tab, chiffres et S restent disponibles. Aucun décodage parallèle,
aucun tampon ajouté : moteur, transitions et backdrops existants réutilisés.
Les helpers getkey/pause/unit sont déplacés dans FCOLD, toujours présent en
LOW après le chargement, afin de conserver les deux fenêtres de liaison.

Écritures du moteur : variables MAIN/ZP existantes, extents MAIN
`$0800–$0BFF`, pages MAIN `$2000–$5FFF` et copie de décor MAIN `$6000–$7FFF`
(selon les objets Background). Commandes source MAIN `$8000–$A3FF` conservées,
aucune écriture fichier/disque ni accès AUX `/RAM`. Le lecteur autonome
sauvegarde/restaure toujours le bitmap ProDOS et le chemin de retour.
FANTA.SYSTEM **10605 octets**, identique dans les deux éditions 6502 et
65C02 : BSS **2994**, ZP **122**, TABLES `$17B2–$1D78`, FCOLD
`$1D79–$1FED` (629 octets), **18 octets libres avant `$2000`** ;
CODE/RODATA jusqu'à `$BEF6`, **9 octets libres avant `$BF00`**.
Aucune fenêtre ou garde de disposition agrandie/désactivée. Les quatre
images ont été contrôlées après compilation des deux architectures.

Les **16 tests Fantavision** passent (moteur, chargement, retour Échap et
Reset, deux CPU). Les deux tests de temporisation passent sur les deux CPU.
Le nouveau test de touches exécute les vraies routines pause/key avec moteur
instrumenté, cinq séquences sur chaque CPU, avec cc65 2.19 et HEAD.
POM2 : **37/37 contrôles par CPU**, référence indépendante des deux pages
et de la page sélectionnée, Right/Return en vitesse accélérée/originale,
pause après chaque pas, reprise, backdrops, retour/reset, diaporama,
source et AUX `$0800–$BFFF` et volume entier conservés. Le banc capture
ensemble pages et décor pour éviter qu'une lecture séparée du décor tombe
pendant le rechargement automatique en turbo ; comparaison exacte maintenue.

Movie Maker : Q/q active/désactive la boucle sans avancer ni arrêter auto.
Au dernier timeout automatique, le parcours vérifié relit le début de
l'animation. Vitesse, décor et miroirs persistent ; S pause/reprend, sortie
manuelle et Échap restent normales, ouverture avec boucle désactivée.
Écritures limitées à l'état/tampon MAIN et pixels visibles MAIN
`$0400–$07FF`, trous exclus. Aucun accès AUX, aucune écriture source/disque.
Fichiers MVMOVIE **5852/5951 octets**, BSS **2640**, fin `$3C2C/$3C8F`,
marges **980/881 octets** avant `$4000` (65C02/6502).
Les **19 tests médias** passent avec cc65 2.19 et HEAD, vrai C hôte et deux
CPU sim65 : boucles à une/plusieurs images, activation/désactivation en
lecture, pause/reprise, fin manuelle, décor/miroirs, erreurs de recherche,
lecture et fermeture pendant la boucle, sources conservées. POM2 complet :
**83/83 contrôles par CPU**, AUX, garde de pile et volume entier préservés.
Ce parcours complet valide aussi la restauration du preset turbo corrigée
précédemment. `--auto-only` regroupe désormais 30 contrôles du même parcours.


### Newsroom noir/blanc inversé — 2026-10-12

I/i réutilise la page HGR chargée : XOR $7F sur 40 octets visibles de
chacune des 192 lignes, décor autour de l'image compris. Bit de palette et
512 octets de trous conservés ; deux appuis restaurent les 8192 octets
exactement. La boucle reprend cgetc/media_key, comme l'attente média
existante, avec navigation/diaporama et retour Échap conservés. Chaque
ouverture reprend les couleurs originales. Les lecteurs DOS restent distincts.

Écritures supplémentaires : uniquement pixels visibles MAIN `$2000–$3FFF`
et compteurs/pointeurs MAIN existants. Chargement et activité MAIN `$06F7`
existants conservés, fermeture contrôlée avant affichage/commandes. Aucun
accès AUX `/RAM`, aucune reconstruction RAM, aucun nouveau tampon ni
réouverture/écriture source ou volume. Le menu indique I: inverse.

Fichiers **1010/1016 octets**, BSS **82/83**, fin `$1F44/$1F4B`, marges
**188/181 octets** avant `$2000` (65C02/6502). Les deux architectures et
quatre images passent avec les gardes de disposition actives.
Les **7 tests** passent avec cc65 2.19 et HEAD, overlay assembleur réel
sous sim65 des deux CPU : pixels inversés par référence indépendante,
restauration, lettres minuscules, navigation, octets hors page, données
malformées, tailles périmées, erreurs de lecture/fermeture et source intacte.
Le banc requiert la relocalisation effective de la région MAIN à `$8000` :
l'expression de taille du cfg HEAD avait changé et l'ancien remplacement
silencieux laissait le banc dans la zone d'activité du lecteur. Cette garde
refuse désormais une configuration inconnue au lieu de lancer ce placement.
POM2 : **24/24 contrôles par CPU**, quatre photos/bannières, dimensions
maximales 37×192, page entière et trous, navigation, refus, AUX occupée
`$0800–$BFFF`, garde de pile et volume source entier conservés ; disques jetables.


### AppleWorks dernière fiche et Epistole dernière page visitée — 2026-10-12

AWDATA : L/l choisit `nrecs-1` uniquement dans une base de données après
le parcours existant, jamais dans un tableur ou une base sans fiche lisible.
Le décompte parcouru et les repères de 64 fiches sont réutilisés ; les
catégories supplémentaires et B/R restent disponibles. La barre R/L Ends
tient dans ses 36 colonnes : un premier essai avec une sixième touche
faisait revenir le texte sur la première ligne, détecté et corrigé par les
comparaisons natives. L'en-tête de description passe de 52 à 28 caractères
pour garder la fenêtre mémoire, sans nouveau tampon ni changement ABI.

Écritures : état et tampon de lecture MAIN existants, texte conio
MAIN/AUX `$0400–$07FF`, sauvegarde/restauration de la ZP pour le FOUT ROM
existant. Aucun accès AUX `/RAM` à partir de `$0800`, aucune reconstruction,
aucune écriture source/volume. Fichiers **8000/8179 octets**, BSS **1282**,
fin `$3F42/$3FF5`, marges **190/11 octets** avant `$4000` (65C02/6502).
Les contrôles de disposition restent actifs ; marge 6502 très serrée.
Les **9 tests AWDATA** passent avec cc65 2.19 et HEAD, C hôte réel et
conversion assembleur sur les deux CPU : dernier élément, repères
63/64/65/130, catégories conservées, base vide, compte d'en-tête périmé,
erreurs de lecture et sources inchangées ; tableurs également couverts.
POM2 complet : **62/62 contrôles par CPU**, tous les champs et décompte
d'une base de 130 fiches, bases/tableurs réels, aide sans débordement,
AUX occupée, pile et volume source entier conservés, images jetables.

DOCVIEW : L/l choisit la page la plus avancée déjà visitée, dans les
16 positions d'historique existantes, avec wrap conservé. Aucun balayage
des pages inconnues ; layout/accents et calculs reprennent les procédures
de relecture vérifiées. R remet la destination à la première page.
Écritures MAIN : état, scratch `$3D60–$3FFF`, tampon copy_buf et ZP ROM
existants ; conio MAIN/AUX `$0400–$07FF` pour les pages et leur barre.
Aucun accès AUX `/RAM` `$0800–$BFFF`, aucune écriture source/volume.
Fichiers **8417/8418 octets**, BSS **354**, fin `$3D43/$3D44`, marges
**29/28 octets** avant le scratch `$3D60`. La barre reste sous 80
caractères, même avec numéro maximal et erreur de lecture.
Les **13 tests de rendu hôte** et **15 tests C/ROM sim65** passent, ces
derniers avec cc65 2.19 et HEAD sur les deux CPU : calculs, erreurs, limites
d'écran et pile, dernière page après retours, wrap sur 20 pages et R.
POM2 : **31/31 contrôles par CPU**, accents/layout, totaux calculés,
historique complet, AUX occupée, pile et volume source entier conservés.
Les deux architectures et quatre images disque sont contrôlées.

Les bancs ROM sim65 requièrent un remplacement exact de la région MAIN,
dont l'expression de taille a changé dans HEAD. Ils chargent les vrais
octets ROM `$D000–$FFBF` : l'aperture périphérique sim65 à `$FFC0` et
au-delà reste intacte. Écrire ces adresses avec les octets ROM activait
la trace du simulateur et polluait les sorties de tests. Calculs et FOUT
utilisent la ROM réelle sous cette limite ; les vecteurs Reset ne font
pas partie de ces bancs. POM2 qualifie le lecteur avec sa ROM complète.

## 12 octobre 2026 — Take 1 : avance pendant la pause

Droite/Entrée dans `pause` pose un octet `step` en HIBSS. Le prochain
`t1_show` reste dans `pause` ; Espace remet l'octet à zéro, Tab conserve la
pause et Échap reprend le retour existant. Le moteur, ses décors, sa scène
et ses attentes sont réutilisés. Les fondus se déroulent entièrement et
les attentes interactives restent à acquitter ; l'arrêt se fait au prochain
basculement de page, pas à chaque étape d'un fondu.

Écritures : octet HIBSS et état MAIN/ZP existant ; le moteur continue ses
écritures MAIN aux mêmes emplacements (variables, pages HGR $2000–$7FFF,
chargements vérifiés $8000–$AFFF et buffers dans la page cachée). Aucun
accès AUX n'est ajouté ; $0800–$BFFF AUX et /RAM restent intacts. Aucun
appel disque dans les nouvelles commandes. Le lecteur conserve ses appels
MLI de lecture uniquement. Le lancement RUN existant sauvegarde A2FILE.CFG
avant transfert ; cette sauvegarde explique pourquoi tout le volume n'est
pas identique après plusieurs lancements. Le banc contrôle séparément tout
le volume pendant l'exécution de TAKE1, puis les octets et entrées de tous
les autres fichiers après retour.

Budget identique pour les deux éditions : SYS **11593 octets**, CODE finit
à **$1FFE** (1 octet libre avant $2000), TIMED **118 octets** à $0800–$0875,
HIBSS **111 octets** à $0600–$066E (9 libres), TXC6/TXC7 **119 octets chacun**
(1 libre par fenêtre). `unit` passe en TXC7, l'aide froide `incw` en TXC6,
et la décision à l'affichage utilise les octets restants de TXC6. Ces
routines sont copiées avant lecture du film ; `getkey`, utilisé aussi lors
d'un refus avant copie et après effacement du texte, reste dans CODE.
Les boucles de délai déplacées restent dans une page ; les contrôles de
placement, les fenêtres et le code de retour sont conservés. La marge de
CODE reste extrêmement serrée ; ne pas agrandir cette zone.

Validation : quatre tests de commandes réelles sur les deux CPU, cc65 2.19
et HEAD ; 14 tests existants du moteur/chargeur/interpréteur et chronométrie,
y compris erreurs de lecture, formats malformés, retours Échap/reset et
comparaison des octets des images à la référence. Banc POM2 : **33/33 contrôles par CPU** sur des HD
jetables pour les deux architectures, avec AUX occupé et conservation des
fichiers. Les quatre images de distribution sont contrôlées.

## 12 octobre 2026 — Newsroom : miroirs H/V

H/h retourne les 280 pixels de chaque ligne ; V/v échange les lignes
visibles 0/191 à 95/96. Les transformations portent sur la page chargée,
y compris son fond, se composent avec I/i et s'annulent par un second appui.
Aucun second lecteur ni tampon de page : H réutilise les 64 octets `buf`
après fermeture réussie du fichier, V échange les octets avec X. Les 512
trous HGR restent intacts. La nouvelle image est chargée dans son orientation
et ses couleurs d'origine par la navigation média existante.

Écritures ajoutées : pixels MAIN $2000–$3FFF, `buf` et `row` dans la BSS
existante, ZP `ptr1`, `ptr2` et `tmp1`. Les fichiers et volumes ne sont pas
écrits, et aucun appel de lecture, recherche ou fermeture n'est ajouté
aux commandes. Pas d'accès AUX ni de reconstruction /RAM. Les commandes
n'existent qu'après validation et fermeture réussie ; une erreur d'ouverture
ou de fermeture ne montre pas la page et ne consomme pas les touches.
Le calcul de ligne réutilise `_hv_row` : son résultat A/X complet est stocké
pour les deux lignes, y compris les tiers de 40/80 octets.

Fichiers **1151/1157 octets** (enhanced/6502), BSS **82/83 octets** inchangée,
fin code+données+BSS **$1FD1/$1FD8**, donc **47/40 octets libres** avant $2000.
La fenêtre $1B00–$1FFF et les contrôles du lieur restent inchangés ; aucun
agrandissement sur la page HGR. La pile réutilise le seul octet de touche
sauvé, retiré avant chaque transformation.

Validation : **8 tests** du vrai assembleur sous sim65, deux CPU avec cc65
2.19 et HEAD, oracle indépendant en matrice 280×192, formes 1×1, 37×192,
8×43, 37×1 et 1×192, doubles retournements et H/V/I combinés, navigation,
refus de données malformées/tailles périmées et erreurs d'E/S. POM2 passe
**56/56 contrôles par CPU**, compare les pages complètes, préserve le volume jetable, AUX occupé $0800–$BFFF et
la garde de pile sur les deux architectures. Les quatre images de
publication respectent les contrôles de disposition.

## 12 octobre 2026 — Fantavision : prochaine pose enregistrée

N/n dans la pause appelle le moteur `fv_next` jusqu'au prochain `fv_vkey`,
puis sélectionne `fv_shown` et reste en pause. Droite/Entrée conserve son
avance d'une seule image, y compris intermédiaire. La fin comptée ou un
film à une seule image garde la vue courante. Le moteur continue de dessiner
les images intermédiaires et leurs objets de décor ; aucune accélération
par décodage parallèle ni saut dans les données. Tab, délai, diaporama,
Espace et Échap conservent leur état et leur comportement existants.

Écritures : les mêmes pages MAIN $2000–$7FFF (affichage et décor), variables
MAIN/ZP et compteurs du moteur. Pas de nouveau tampon, allocation, état BSS,
accès AUX ou appel disque dans N/n. Le film chargé en $8000–$A3FF reste
identique, /RAM n'est ni touché ni reconstruit. La pile ne s'accumule pas :
chaque appel de `fv_next` revient avant l'itération suivante, puis la routine
saute vers la pause/affichage existant. Les transferts des fichiers et la
restauration du bitmap restent ceux du lecteur en lecture seule.

Les deux éditions ont les mêmes **10630 octets**. BSS **2994**, ZP **122**
inchangés. FCOLD $1D79–$1FFD : **645 octets**, **2 libres** avant $2000.
CODE/RODATA $A455–$BEFF : **0 libre** avant ProDOS $BF00. La décision N/n
consomme les 9 derniers octets hauts ; les 16 octets du helper vont dans
FCOLD déjà copié au démarrage. Les fenêtres et assertions de placement
restent inchangées. Ces zones sont désormais pleines ou presque : toute
extension doit dégager de la place, sans élargir la fenêtre dans ProDOS.

Validation : dix scénarios exécutant les vraies commandes et le helper,
sous sim65 sur les deux processeurs, cc65 2.19 et HEAD ; **16 tests** du
moteur/chargement/retour, dont formats malformés, erreurs de lecture,
décors, tous modes, temporisation, Échap et reset. POM2 : **43/43 contrôles
par CPU**, film à huit étapes par transition, oracle indépendant de chaque
image et des deux pages, trois avances N/n à la prochaine pose, pauses
stables et reprise. Le banc couvre toutes les phases d'interpolation pour
la détection initiale (80 images de référence, plutôt que les six premières).
Film, AUX $0800–$BFFF et volume jetable conservés octet par octet. Les quatre
images disque passent les contrôles de construction et de disposition.

## 12 octobre 2026 — DOCVIEW : début de l'historique

H/h pose `page` à zéro dans l'historique existant. Après 20 pages visitées,
les 16 positions gardées couvrent les pages 5–20 : H va à 5, L revient à 20.
Contrairement au redémarrage R, H ne modifie ni `known`, ni `head`, ni `first`.
L'affichage reprend les mêmes offsets, états de mise en page et replay
vérifié des calculs ; le mode accents reste conservé. Aucune exploration
supplémentaire des pages non visitées et aucun nouveau tableau.

Écritures : état/scratch MAIN existant, tampons existants, variables de
calcul et ZP ROM, texte MAIN/AUX $0400–$07FF via conio. Aucun accès AUX
$0800 ou au-delà, aucune reconstruction /RAM ni écriture sur les sources
ou volumes. Les seuls accès fichiers restent la relecture contrôlée des
pages existantes ; les erreurs de lecture ne deviennent pas des EOF.

DOCVIEW **8429/8432 octets**, BSS **354 octets** inchangée. Fin BSS exclusive
**$3D4F/$3D52**, donc **17/14 octets libres** avant le scratch $3D60.
Les fenêtres, buffers, limites et assertions restent inchangés. L'aide
H/L réunit les deux extrémités de l'historique ; son maximum avec une page
65535 et « (read error) » est **79 caractères**, sans débordement de ligne.

Validation : **16 tests** du vrai C et de la ROM de calcul sur les deux CPU,
cc65 2.19 et HEAD, plus les **13 tests** de rendu hôte. Nouveau scénario
H/h/L/R sur calculs cumulatifs et document de 420 lignes, historique cyclique,
marges, retour aux mêmes lignes, avance normale et remise à zéro. Banc POM2 :
**35/35 contrôles par CPU**, conservation du volume jetable, AUX occupé
et garde de pile. Les quatre images de distribution restent valides.

## 12 octobre 2026 — AppleWorks : page indexée des tableurs

L/l utilise désormais `last - 1` : le nombre de fiches vérifié pour une
base, le nombre de pages indexées pour une feuille. Le point de départ
le plus avancé peut être celui de la page suivante, préparé par le rendu
précédent. Aucun parcours complet de la feuille n'est ajouté. La colonne
courante reste en place, B revient d'une page, R reprend en haut à gauche,
et F réinitialise les repères de la nouvelle vue grille/cellules.

Écritures : index `k` existant, état/tampons MAIN, ZP de calcul et écran
texte MAIN/AUX $0400–$07FF via les services existants. Aucun nouveau buffer,
état BSS ou appel fichier dans la commande. La relecture de la page reste
contrôlée ; les erreurs ne sont pas des fins normales. Pas d'accès AUX
$0800–$BFFF, de reconstruction /RAM ni d'écriture des sources ou volumes.
`known` reste au moins 1, plafonné à 42 ; `marks` dispose des 43 entrées
existantes pour la page courante et son successeur. Le dernier indice est
donc borné avant son accès, même au plafond et après changement de vue.

AWDATA **7993/8172 octets**, BSS **1282 octets** inchangée ; fin exclusive
**$3F3B/$3FEE**, donc **197/18 libres** avant $4000. La condition spécifique
aux bases disparaît, et l'aide des feuilles regroupe SPC/B pour garder cinq
commandes dans les 36 colonnes de la barre. Fenêtre, pile, buffers et
contrôles de placement inchangés ; sept octets gagnés dans chaque édition.

Validation : **10 tests** avec cc65 2.19 et HEAD, vrai C hôte et conversion
numérique réelle sur les deux CPU. Oracle indépendant des grilles et
formules pour feuilles vides, courtes ou longues, L/l après B/R, maintien
de la colonne, changement F et erreurs de lecture. Les bases continuent
de passer les tests de comptage, repères de 64 fiches, catégories, tailles
périmées et erreurs d'E/S. Banc POM2 : **66/66 contrôles par CPU** sur HD
jetables, avec conservation des nombres ROM, volume, AUX occupé et garde de pile.
Les quatre images disque passent leurs contrôles de disposition.

## 13 octobre 2026 — Koala et qualification de la pile

IDENT accepte les images HGR Koala sauvegardées en BIN $4000 de
8 184 à 8 191 octets, comme celles à $2000. Les descriptions des pages
HGR/DHGR perdent une virgule pour conserver la limite native inchangée.
IDENT : **9 160/9 352 octets**, BSS **120**, fin exclusive
**$3F40/$4000** en 65C02/6502, soit **192/0 octets libres**. Aucune
réserve supplémentaire n'est disponible dans la version 6502.

Les essais du vrai C refusent les erreurs de lecture, recherche et fermeture,
ainsi que les tailles et adresses hors des cas prévus, et contrôlent les
octets des sources. Le banc Koala passe **11/11 contrôles par CPU** et les
relais natifs **4 tests**, avec les gardes de disposition actives.

Le banc `memory:stack` utilise une installation complète sur deux volumes
jetables, affiche une image DHGR compressée et copie les 135 fichiers de
l'arborescence des outils. Ses **4/4 contrôles** passent : **145 octets
utilisés sur 192**, soit **47 octets de marge**.

Le repli vers OPEN lorsque IDENT est absent convertit la commande O/I en
argument booléen attendu par l'ancien lecteur. Le nom constant `OPEN` est
placé en LC pour conserver les limites existantes. Les tests exécutent le
dispatch assembleur sur les deux CPU. Après reconstruction, les marges
65C02/6502 restent **1/388 octets en MAIN**, **8/6 en LC**, **87/112 en
LOWRAM** et **18/594 pour la garde de pile**, sans désactiver de contrôle.

La détection VisiCalc normalise aussi le bit haut des caractères de colonne
et de ligne, y compris les colonnes à deux lettres (BJ, BK). Les
**11 tests du vrai C** et **16 tests des vrais relais**
passent, avec simulations 6502/65C02, sources inchangées et refus des erreurs
d'E/S ou contextes invalides. La description de son en-tête interne utilise
16 octets, comme les surcouches ordinaires, pour conserver les gardes.
IDFORMATS mesure **9 148/9 394 octets** en
65C02/6502 ; les deux constructions et les quatre images passent leurs
gardes, avec **256/10 octets libres** après la BSS. La comparaison des
262 binaires confirme que seuls les deux
IDFORMATS.PLG changent, sans modification du résident ni de l'ABI.

VOLNAME conserve ses messages dans la note MAIN du résident avant son
retour, pour survivre au rafraîchissement des panneaux. Les confirmations
et écritures de renommage restent les mêmes ; aucune écriture AUX n'est
ajoutée. **19 scénarios par CPU** exécutent le vrai C et l'assembleur,
avec contrôle des octets du volume et du préfixe lors des erreurs MLI,
annulations et refus d'une image. Aucun scénario ne relit les panneaux
pendant l'exécution : leurs tables à $2000 peuvent écraser les DATA/BSS
d'une grande surcouche. Le résident assure cette relecture après le retour.
VOLNAME mesure **1 259/1 244 octets** en
65C02/6502. Après ces deux corrections, **258 des 262 binaires sont
identiques** : seuls IDFORMATS et VOLNAME changent sur chaque architecture.
