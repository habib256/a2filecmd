# A2 File Cmd — feuille de route

[0.9.3](https://github.com/habib256/a2filecmd/releases/tag/v0.9.3)
([CHANGELOG](CHANGELOG.md)), publiée le 22 septembre 2026. Mini et
ProDOS, même numéro ; `make mini` ne partage pas `src/a2fc.c`.
Ce qui est fait vit dans le CHANGELOG et les rapports
[0.9.1](docs/QUALIFICATION-0.9.1.md), [0.9.2](docs/QUALIFICATION-0.9.2.md),
[0.9.3](docs/QUALIFICATION-0.9.3.md) ; ce fichier ne garde que la suite.

Préserver les données prime ([AGENTS.md](AGENTS.md)). Ne pas relever
les plafonds ([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)). Une étape
se ferme avec un oracle hôte et un banc POM2.

## Deux trains

- **1.0** : la 0.9.3 durcie. Aucune fonctionnalité nouvelle, aucun
  overlay plein retouché sauf pour corriger un défaut.
- **1.1** : les formats et le reste, une fois la 1.0 publiée.

## 0.9.4 — prochaine publication

Ce qui est prêt depuis la 0.9.3, publié avant la 1.0 pour être essayé sur
machine réelle. Même règle : pas de fonctionnalité nouvelle hors affichage.

- [x] Mini : la case d'activité tourne pendant le FORMAT RWTS et pendant
  les tentatives sur une disquette jamais formatée.
- [x] Noms d'images `A2FILECMD-PRODOS-*` et `A2FILECMD-DOS3.3` ; « enhanced
  ou non » dans le README, le manuel et les notes de release.
- [x] DEMO du XL rangé par sorte de fichier (`tools/stage_demo.py`).
- [x] README révisé et capture 80 colonnes au bon ratio
  (`bench/capture_panels.py`), aussi en couverture du manuel.
- [x] ABI des overlays et `A2FILE.CFG` gelés (`tools/test_abi_freeze.py`).
- [ ] Mini : hexadécimal lisible, 8 octets par ligne espacés avec leurs
  caractères, en deux moitiés (Gauche/Droite).
- [x] Manuel : Dazzle Draw (BIN `$2000`, 16 Ko, AUX d'abord) cité parmi
  les images DHGR déjà lues.
- [ ] Une vraie image Dazzle Draw dans un banc (oracle : `DD.PICLOADER`
  sous POM2) : le manuel l'affirme d'après le code, pas encore d'après
  l'écran.
- [ ] Publier : version dans le Makefile, CHANGELOG, `make test`,
  `make qualify`, `tools/check_images.py`, liens du README et du manuel
  vers les nouveaux noms, capture reprise.

## 1.0 — chemin critique

Chaque étape suppose la précédente fermée. Un défaut trouvé aux étapes
4 ou 5 renvoie à l'étape 2, puis à une nouvelle RC.

1. **Gel des fonctionnalités.**
   - [x] Geler les formats : `A2FILE.CFG` et l'ABI des overlays (API v5,
     structures, constantes), [sdk](sdk/README.md) ;
     `tools/test_abi_freeze.py` dans `make test`.
2. **Solder la dette (1.0-rc1).**
   - [ ] Indexer les grands catalogues sans état périmé après changement
     de disque ; le parcours relit encore les blocs précédents
     ([mesures](docs/PERFORMANCE-0.9.2.md)).
   - [ ] Trancher : cache des informations de volume. Prototype écarté
     pour préserver les marges mémoire ; le fermer ou le reporter en 1.1.
   - [ ] Trancher : MAIN 65C02 à 82 octets, objectif 256. Bloquant 1.0,
     ou condition d'entrée d'un format 1.1.
   - [ ] VDrive sonde `$C2` puis `$C1` (`src/vsdrive.s`) : sur un IIe dont
     la seule SSC est en slot 1, reliée à une imprimante, il la
     reprogrammerait à 115 200 bauds et y enverrait ses enveloppes (vu par
     POM2 sur le port imprimante du //c en 0.6.6). Reproduire sous POM2,
     puis ne jamais prendre une carte réglée en mode imprimante.
3. **Retour visuel.**
   - [ ] Vérifier que la progression 0.9.3 couvre les pauses à 1 MHz
     (catalogue, copie, vérification, chargement), puis fermer cette ligne.
4. **Qualification (1.0-rc).**
   - [ ] `make test`, `make qualify`, `tools/check_images.py` sur les
     cinq images, les deux CPU.
5. **Recette matérielle (1.0-rc2 si besoin).**
   - [ ] [HARDWARE-CHECKLIST.md](docs/HARDWARE-CHECKLIST.md) sur machine
     réelle : IIe enhanced, //c, 6502.
6. **Manuel.**
   - [ ] Limites restantes écrites ; aucune atomicité promise que ProDOS
     ne fournit pas.
7. **Tag 1.0.**
   - [ ] Aucun défaut connu qui puisse perdre des données.
   - [ ] README et manuel : passer les liens de téléchargement aux
     nouveaux noms d'images, reprendre `bench/capture_panels.py`.

Rappels de release : `/RAM` se confirme **avant** d'y toucher ; images
jetables pour les essais destructifs ; deux CPU.

## 1.1 — formats

Seulement s'il reste des octets. OPEN a 28 octets en 6502 (43 en
65C02), UNSHRINK ~900, SHAPES est plein. Une petite surcouche (DELETE,
COPY, IMGFS, ATTR, OPEN) ne bouge que si on doit la modifier.

Méthode, avant d'ajouter des formats un par un :
- [ ] **Recensement** (`tools/corpus_survey.py`) : parcourir Asimov et les
  collections archive.org, passer chaque fichier dans une copie Python des
  règles d'identification d'A2FC, publier le taux de couverture et la
  liste des fichiers non reconnus classés par fréquence. Ce classement
  valide ou corrige l'ordre ci-dessous.
- [ ] **Signatures en fichier** lues par IDENT (type, aux, octets à une
  position → format et outil) : reconnaître un format sans octet de code,
  nommer ceux qu'on ne lit pas encore, noter les inconnus pour les
  rapports de bug.
- [ ] **API v6, briques partagées** : lecteur de bits, RLE/PackBytes,
  copie hi-res, texte à bit haut, pour qu'un lecteur tienne en quelques
  centaines d'octets.
- [ ] **Outillage de rétro-ingénierie** : traceur POM2 générique (secteurs
  lus, routine de tracé), comparaison d'écran automatique avec le
  programme d'origine, modèle de `docs/<FORMAT>-FORMAT.md`.
- Convertir plutôt qu'afficher quand l'affichage coûte trop (Super Hi-Res,
  polices GS, films) ; publier les spécifications (CiderPress II,
  Justsolve) ; lancer un appel à disques d'utilisateurs.

Ordre retenu après la recherche du 25 septembre 2026 (File Type Notes,
CiderPress II, rétro-ingénieries publiques ; échantillons vérifiés sur des
images publiques). Aucun de ces formats n'a de spécification officielle.

0. [ ] **The Newsroom** (Springboard) : photos `PH.*` et bannières
   `BN.*` des disques d'utilisateurs, vrais fichiers DOS 3.3 de type B
   (chargés en `$4000`). Format décodé : longueur L, cadre y1 y2 x1 x2,
   historique des clips jusqu'au premier `$FF`, puis bitmap de
   (x2 − x1) div 7 + 1 octets × (y2 − y1 + 1) lignes, 7 pixels par
   octet, bit 0 à gauche, 1 = blanc. Contrôles : L = largeur × hauteur =
   taille − (position du `$FF` + 1) ; 125 fichiers réels décodés sans
   écart (bulletins de chorale, de paroisse, de lycée). Sources :
   routines NRTOGP/NRTONR de Ferg Brand (1986),
   [newswire](https://github.com/classilla/newswire) (format C64).
   Échantillons : archive.org `703_Newsroom_Page`, `103_…` à `106_…`,
   `105_The_Newsroom_Photo_Data_Disk`, `169_Page_Data_Disk_The_Newsroom`,
   `a2_Newsroom_Banner_Datadisk_198x_`, `009_`/`010_Clipart_*_For_NewsRoom`.
   À faire : visualiseur hi-res en lecture seule (refus si un contrôle
   échoue, Gauche/Droite entre photos), oracle Python et tests sur les
   vrais fichiers, spécification `docs/NEWSROOM-FORMAT.md`. Ensuite : le
   texte des panneaux `PN.*` et pages `PG.*` (compris en partie), puis le
   clip art commercial (index piste 34 « SSI CLIP » lu, compression non
   décodée).
1. [ ] **Print Shop GS, clip art** (`$F8`/`$C323` couleur, `$C313` mono,
   88 × 52) : trois plans jaune, magenta, cyan, 8 couleurs fixes, décodés
   par CiderPress II (`PrintShopClip.cs`, Apache-2.0) ; 707 clips sur les
   disques Asimov `images/gs/graphics/Print_Shop.zip`. Mono dans
   PRINTSHOP (~100 octets, ~280 libres), aiguillage résident ~20-30 octets
   **avant** la sonde Arlequin (`$F8` aussi) sur auxtype et taille exacts ;
   la couleur en DHGR ensuite (nouvel overlay, consentement /RAM, ~1 Ko).
2. [ ] **Movie Maker** (Interactive Picture Systems, Reston 1984 / EA
   1985, DOS 3.3) : décors `.BKG` (B, 8 192 octets à `$4000`, page HGR
   brute) et planches `.SHP` (B, 8 720 octets à `$1DF0` : en-tête de
   528 octets puis page HGR), vérifiés sur disques. Coût quasi nul :
   reconnaissance, et sauter l'en-tête de `.SHP`.
3. [ ] **Epistole** (Version Soft, France). Documents ProDOS `$04`, ASCII
   7 bits, CR ; commandes en ligne `_MG10`, `_CE`, `_JD`…, variables
   `#NOM]`, calculs `#:PR=…]` ; accents ISO 646-FR (`{`=é, `}`=è, `@`=à).
   Dans TEXT, détecté par le contenu : pas d'entrée dans la table de
   suffixes d'OPEN. Échantillons et oracle : collection Antoine Vignau
   ([Spring 2023](https://archive.org/details/Antoine_Applesauce_5.25_Vignau_Spring_2023),
   v5.06 : EXEMPLE.LETTRE, DOCUM.DEMO, DEMO.FACTURE ;
   [autres versions](https://archive.org/details/Antoine_Applesauce_Vignau)).
4. [ ] **Papyrus traitement de texte** (Ediciel) et **HomeWord** (Sierra),
   dont Papyrus est l'adaptation. Fichiers T DOS 3.3 : bit haut, CR,
   ISO 646-FR, quelques codes (`$19` = ê). Même lecteur que 3 ; codes de
   contrôle à confirmer avec l'oracle. Ne pas confondre avec *Papyrus, le
   cours de dactylographie* (adaptation de MasterType).
5. [ ] **Graphics Magician** (Penguin Software). Commandes de tracé HGR de
   1 à 3 octets, documentées par la rétro-ingénierie de
   [McFadden (2025)](https://6502disassembly.com/a2-graphics-magician/).
   Effort moyen : lignes, remplissage, 108 motifs, pinceaux, police.
   Trancher la licence avant de reprendre motifs et police de PICDRAWH.
6. [ ] **Bordures Print Shop / Print Shop Companion** (BIN, 144 ou
   148 octets, 12 × 12). Disposition des octets à établir avec Print Shop
   sous POM2, puis spécification publiée dans `docs/`. Se greffe sur
   PRINTSHOP. Échantillons : 77 bordures du disque « Gordon's Print Shop
   Borders » (Asimov `productivity/graphics/printshop/`). Avec les
   bordures **Print Shop GS** (`$C312` mono 130 octets, `$C322` couleur
   382 octets) : en-tête de 4 octets, une tuile de coin et une de côté de
   24 × 21 ; l'assemblage autour de la page reste à établir (oracle IIgs).
7. [ ] **Music Construction Set** : le morceau compilé `.OBJ` sur
   Mockingboard, flux déduit du source officiel du lecteur (`MUSIC
   SOURCE`, et [mcs-player](https://github.com/cybernesto/mcs-player),
   MIT) ; en-tête à confirmer. Réutilise l'infrastructure de DUET.
8. [ ] **LZC 12 bits dans UNSHRINK** (NuFX 4, et 5 si l'en-tête dit
   ≤ 12 bits). `tools/lzc_ref.py` est dans `make test`. Le cœur actuel
   tient en `$1B00–$1F59` ; PREFIX commence à `$2000`. Le décodeur LZC
   est un second cœur, recopié en AUX `$1B00`.
9. [ ] Merlin (sources à bit haut, colonnes étiquette / opcode /
   opérande / commentaire) et AppleWriter.
10. [ ] Dazzle Draw, sections `.SEC` (`$06`/`$F200`, 11 522 octets :
   largeur, hauteur, lignes en flux de 7 bits), déduites de deux fichiers.
   Rares ; les images plein écran sont déjà lues.

Limites connues : CPMW un extent (16 Ko) et volume vide refusé ; CPM
`CPAM40B.dsk` / `CPM.DSK` refusés ; PASCALW sans Krunch ; IMGPUT sans
tree (> 128 Ko) ni extension de répertoire.

## 1.2 — impression

Étude du 25 septembre 2026. PRINT.PLG, grand overlay lancé par `!` : coût
résident nul, services de l'API v5 suffisants, rien d'écrit sur disque
(sauf un éventuel `PRINT.CFG` selon les règles des services fichiers).
Pas d'impression dans le Mini (19 octets libres ; `PR#1` depuis BASIC).

- [ ] **Version minimale** (~1 à 1,5 semaine) : catalogue ou dossier,
  texte (dont l'export de DISASM), vidage hexadécimal. Grappler+ et SSC /
  ports //c en accès direct au matériel, attente bornée, Échap, barre de
  progression, message « imprimante pas prête » ; autres cartes Pascal 1.1
  par leur firmware, avec avertissement. Refuser le slot de VDrive.
- [ ] Bancs : `--printer grappler|parallel|ssc1` et `--spool` dans
  `pom2_playtest` (POM2 émule déjà Grappler, SSC imprimante, ImageWriter,
  Epson) ; tests sim65 avec un pilote bouchon ; section imprimante dans
  HARDWARE-CHECKLIST.
- [ ] Ensuite (~1 semaine) : images HGR / DHGR / Print Shop en ImageWriter
  (`ESC G`) et Epson (`ESC K`), lues dans le fichier par bandes, sans
  écran ni AUX ; AppleWorks WP ; `PRINT.CFG`.
- Plus tard : Ctrl-P résident, AWDATA, Newsroom, LaserWriter. La copie
  d'écran du firmware Grappler est écartée (lit la page 2 du résident,
  ni annulation ni progression, AUX en DHGR).
- À trancher : matériel de recette ; réglages mémorisés ou détectés ;
  images en 1.2 ou après ; repli firmware au risque d'un blocage ;
  `setOnline` dans POM2 pour tester l'imprimante hors ligne.

## Plus tard

Favoris de programmes ; PT3 sous pression, ANIMATE ; Fantavision 8 bits
(films `M.*` BIN `$8400`, format non documenté, moteur d'interpolation
coûteux ; échantillons nombreux) ; Beagle « Double Scrunch » (routine de
469 octets, mais aucune image compressée trouvée) ; lecteur de films
Movie Maker `.MVM` (lecteur d'origine MMA.OBJ ~4 Ko à désassembler,
oracle AUTOPLAY sous POM2, ~13 films d'éditeur, aucun d'utilisateur) ;
Print Shop GS polices (`$C316`), motifs et pixels ;
DIRSORT, BACKUP, SHRINK ; NIBCOPY reprise de piste **ou** `.NIB` (pas
les deux, pas de 3½) ; XMODEM, ADTPro blocs, TFTP ; PASSWORD ;
`GISTDATA.hdv` ; CPMW à plusieurs extents si la fenêtre se libère.

## Écarté

- Hors de portée : NuFX 5 en 16 bits, Squeeze NuFX, Teach, a2dgrx.
- Sans documents ni spécification trouvés : Bank Street Writer, Fontrix
  GRAFFILE, The New Print Shop (`$F5`).
