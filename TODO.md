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
1. [ ] **Epistole** (Version Soft, France). Documents ProDOS `$04`, ASCII
   7 bits, CR ; commandes en ligne `_MG10`, `_CE`, `_JD`…, variables
   `#NOM]`, calculs `#:PR=…]` ; accents ISO 646-FR (`{`=é, `}`=è, `@`=à).
   Dans TEXT, détecté par le contenu : pas d'entrée dans la table de
   suffixes d'OPEN. Échantillons et oracle : collection Antoine Vignau
   ([Spring 2023](https://archive.org/details/Antoine_Applesauce_5.25_Vignau_Spring_2023),
   v5.06 : EXEMPLE.LETTRE, DOCUM.DEMO, DEMO.FACTURE ;
   [autres versions](https://archive.org/details/Antoine_Applesauce_Vignau)).
2. [ ] **Papyrus traitement de texte** (Ediciel) et **HomeWord** (Sierra),
   dont Papyrus est l'adaptation. Fichiers T DOS 3.3 : bit haut, CR,
   ISO 646-FR, quelques codes (`$19` = ê). Même lecteur que 1 ; codes de
   contrôle à confirmer avec l'oracle. Ne pas confondre avec *Papyrus, le
   cours de dactylographie* (adaptation de MasterType).
3. [ ] **Graphics Magician** (Penguin Software). Commandes de tracé HGR de
   1 à 3 octets, documentées par la rétro-ingénierie de
   [McFadden (2025)](https://6502disassembly.com/a2-graphics-magician/).
   Effort moyen : lignes, remplissage, 108 motifs, pinceaux, police.
   Trancher la licence avant de reprendre motifs et police de PICDRAWH.
4. [ ] **Bordures Print Shop / Print Shop Companion** (BIN, 144 ou
   148 octets, 12 × 12). Disposition des octets à établir avec Print Shop
   sous POM2, puis spécification publiée dans `docs/`. Se greffe sur
   PRINTSHOP. Échantillons : 77 bordures du disque « Gordon's Print Shop
   Borders » (Asimov `productivity/graphics/printshop/`).
5. [ ] **Music Construction Set** : le morceau compilé `.OBJ` sur
   Mockingboard, flux déduit du source officiel du lecteur (`MUSIC
   SOURCE`, et [mcs-player](https://github.com/cybernesto/mcs-player),
   MIT) ; en-tête à confirmer. Réutilise l'infrastructure de DUET.
6. [ ] **LZC 12 bits dans UNSHRINK** (NuFX 4, et 5 si l'en-tête dit
   ≤ 12 bits). `tools/lzc_ref.py` est dans `make test`. Le cœur actuel
   tient en `$1B00–$1F59` ; PREFIX commence à `$2000`. Le décodeur LZC
   est un second cœur, recopié en AUX `$1B00`.
7. [ ] Merlin (sources à bit haut, colonnes étiquette / opcode /
   opérande / commentaire) et AppleWriter.

Limites connues : CPMW un extent (16 Ko) et volume vide refusé ; CPM
`CPAM40B.dsk` / `CPM.DSK` refusés ; PASCALW sans Krunch ; IMGPUT sans
tree (> 128 Ko) ni extension de répertoire.

## Plus tard

Favoris de programmes ; PT3 sous pression, ANIMATE ; Fantavision 8 bits
(films `M.*` BIN `$8400`, format non documenté, moteur d'interpolation
coûteux ; échantillons nombreux) ; Beagle « Double Scrunch » (routine de
469 octets, mais aucune image compressée trouvée) ;
DIRSORT, BACKUP, SHRINK ; NIBCOPY reprise de piste **ou** `.NIB` (pas
les deux, pas de 3½) ; XMODEM, ADTPro blocs, TFTP ; PASSWORD ;
`GISTDATA.hdv` ; CPMW à plusieurs extents si la fenêtre se libère.

## Écarté

- Hors de portée : NuFX 5 en 16 bits, Squeeze NuFX, Teach, a2dgrx.
- Sans documents ni spécification trouvés : Bank Street Writer, Fontrix
  GRAFFILE, The New Print Shop (`$F5`).
