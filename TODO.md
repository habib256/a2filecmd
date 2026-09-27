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

## 0.9.4 — publiée le 26 septembre 2026

Ce qui était prêt depuis la 0.9.3, publié pour être essayé sur machine
réelle : noms d'images PRODOS / DOS3.3, DEMO rangé, README et capture
80 colonnes, ABI gelée, 494 octets libres dans MAIN, grands catalogues,
Haut qui ne saute plus de fenêtre (65C02), VDrive qui laisse les
imprimantes, audit des signes, hexadécimal et signes d'activité RWTS du
Mini. Détail : [CHANGELOG](CHANGELOG.md),
[qualification](docs/QUALIFICATION-0.9.4.md).

## 1.0 — chemin critique

Chaque étape suppose la précédente fermée. Un défaut trouvé aux étapes
4 ou 5 renvoie à l'étape 2, puis à une nouvelle RC.

1. **Gel des fonctionnalités.**
   - [x] Geler les formats : `A2FILE.CFG` et l'ABI des overlays (API v5,
     structures, constantes), [sdk](sdk/README.md) ;
     `tools/test_abi_freeze.py` dans `make test`.
2. **Solder la dette (1.0-rc1).**
   - [x] Grands catalogues : les blocs entiers avant la fenêtre sont
     comptés par `dir_count_block` (asm, ~40 octets), sans état mémorisé,
     donc rien de périmé après un changement de disque. Dernière page de
     1 500 entrées : 6,4 s → 4,1 s (65C02). Un index à points de reprise a
     été mesuré et écarté (488 octets de MAIN, gain limité : ProDOS relit
     les blocs sur SET_MARK). Bancs `paging_swap` 15/15 et `large_nav`
     9/9 sur les deux CPU.
   - [x] Bug 65C02 corrigé au passage : cc65 2.19 compilait
     `target >= pan->count` (int contre unsigned char) en comparaison non
     signée ; Haut près du début d'une fenêtre chargeait la suivante.
   - [x] Audit signé / non signé : cc65 2.19 rend non signée toute
     opération dont un côté l'est (et calcule `uchar - uchar` sur 8 bits).
     768 comparaisons signées différemment selon l'édition, 6 avec un
     opérande qui peut être négatif, toutes tracées : aucun nouveau bug
     visible ; AWDATA durci (tableur piégé), IDENT 6502 corrigé (libellé).
     Piège permanent : `tools/sign_compare.py` + `test_sign_compare.py`
     (arbre syntaxique clang, règles vérifiées sur les deux compilateurs).
   - [x] CI : clang est présent sur l'image Ubuntu (`test_sign_compare`
     analyse le code en CI, 4 tests, aucun sauté).
   - [ ] Mini : Retour sur une table Pinball Construction Set (`*.PB`, B
     chargé en `$4000`) propose `BRUN`, et le BRUN finit dans le moniteur
     (`BRK` en `$4002`, vu sous POM2). Pas de perte de données, mais un
     piège : ouvrir un `*.PB` en hexadécimal, ne jamais proposer BRUN.
   - [ ] Manuel : un jeu autonome PCS (« Make Game » : un seul fichier B,
     `$177D`, `$7783` octets, `JMP` en tête) se lance déjà par Retour/B
     dans le Mini et par X sous ProDOS (copié en BIN `$06`, aux `$177D`) ;
     vérifié sous POM2 par les trois chemins. Il faut un joystick.
   - [ ] Une vraie image Dazzle Draw dans un banc (oracle : `DD.PICLOADER`
     sous POM2) : le manuel l'affirme d'après le code, pas encore d'après
     l'écran.
   - [ ] `make pom2host` a produit une fois un hôte qui plantait au
     démarrage (« mutex lock failed ») pendant que POM2 travaillait sur
     `work/printer-detection` ; un build suivant fonctionnait. Revérifier
     quand POM2 publiera, et rejouer `make qualify` sur cet hôte.
   - [ ] Trancher : cache des informations de volume. Prototype écarté
     pour préserver les marges mémoire ; le fermer ou le reporter en 1.1.
   - [x] MAIN 65C02 : **494 octets libres** (82 avant), 6502 : 885 ;
     413 / 805 après le comptage des blocs de catalogue.
     `pan_at(p)` remplace les 90 `panels[p]` à indice variable, que cc65
     multipliait par 98. LC, pile et douze surcouches y gagnent aussi.
   - [x] VDrive ne lit ni n'écrit plus jamais le slot 1 (IIe et //c).
     Reproduit avant correction : un IIe dont la seule SSC était en slot 1
     recevait 100 octets d'enveloppes et un réglage à 115 200 bauds.
     `bench/vdrive_printer.py` exige zéro accès au slot 1 (8/8, deux CPU),
     `tools/test_vsdrive.py` aussi sous sim65. Restent : un hôte VDrive
     câblé en slot 1 n'est plus servi (le manuel dit de passer en slot 2),
     une imprimante sur le port modem du //c recevrait encore les
     enveloppes, une SSC imprimante en slots 2-7 est encore sondée.
   - [x] VDrive ne prend plus une SSC réglée en imprimante (ni en
     émulation SIC) dans aucun slot : lecture des commutateurs (DIP 1,
     `$C081 + slot × 16`, bits `$03`, `$00` = communications ; MAME
     `a2ssc.cpp`, firmware 341-0065-A) avant toute écriture et sans lire
     le 6551 ; le //c (MACHID) garde son port 2. `vdrive_printer` 19/19 et
     `vdrive` 13/13 sur les deux CPU ; l'ancien pilote écrivait 106 fois
     sur une imprimante en slot 2. Coût : 16 octets de carte langage (62
     libres en 65C02, 53 en 6502). Limites : le IIgs n'est pas testé
     (POM2 ne l'émule pas) ; une imprimante sur le port modem du //c.
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
   - [ ] README et manuel : liens de téléchargement vers la 1.0,
     reprendre `tools/capture_panels.py`, régénérer le PDF.

Rappels de release : `/RAM` se confirme **avant** d'y toucher ; images
jetables pour les essais destructifs ; deux CPU.

## 1.1 — formats

Seulement s'il reste des octets. OPEN a 168/173 octets (65C02/6502)
depuis que son classifieur est en assembleur (`src/open.s`, 26 septembre
2026) : une règle de routage coûte 10 à 20 octets, à écrire dans
`open.s` **et** dans `tools/file_viewer_ref.c`. Le résident 65C02 est à
203 octets (objectif 256) : tout nouveau format vit dans une surcouche.
DOCVIEW a ~120 octets, UNSHRINK ~900, SHAPES est plein. Les nouvelles
surcouches vont sur 800K et XL, pas sur la 140K.

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
- Convertir plutôt qu'afficher quand l'affichage coûte trop ; publier les
  spécifications (CiderPress II, Justsolve) ; lancer un appel à disques
  d'utilisateurs.
- CiderPress II (Apache-2.0) fournit du code et des notes pour plusieurs
  formats ci-dessous (`FileConv/`) : les reprendre avec attribution
  (NOTICE) plutôt qu'en salle blanche.

Analyse du 27 septembre 2026 : les 60 convertisseurs de CiderPress II
(`fadden/CiderPress2`, `FileConv/`) croisés avec ce qu'A2FC lit et avec la
recherche du 25 septembre (File Type Notes, rétro-ingénieries publiques,
échantillons vérifiés sur des images publiques). Les fréquences sont des
estimations tant que le recensement (bloc méthode) n'existe pas : il
validera ou corrigera cet ordre. Les formats propres au IIgs sont laissés
de côté pour l'instant (voir « Plus tard »).

### Faits

- [x] **The Newsroom** (Springboard) : photos `PH.*` et bannières `BN.*`
  **faites** (NEWSROOM, `docs/NEWSROOM-FORMAT.md`, 2026-09-26) : BIN
  `$4000`, reconnus par le nom dans `image_kind` (prédicat en assembleur
  dans `display.s`, 91 octets de MAIN), bitmap pris sur les **L derniers
  octets** — 18 des 93 fichiers distincts ont un `$FF` dans l'historique,
  la règle « premier `$FF` » les décalait. 125 fichiers réels validés par
  `tools/test_newsroom.py` (sim65, deux CPU) ; `bench/newsroom.py` sur de
  vraies photos, 6/6 sur les deux éditions. La suite : n° 11 ci-dessous.
- [x] **Movie Maker** (2026-09-26) : décors `.BKG` (page brute, déjà
  lus) et planches `.SHP` (BIN `$1DF0`, 8 720 octets, en-tête de 528
  octets sauté par IMAGE, décision dans `named_kind`/`sheet_header` de
  `display.s`). `bench/moviemaker.py` sur les vrais fichiers. Les films
  `.MVM` restent en « Plus tard ».
- [x] **Epistole** (Version Soft) — fait le 2026-09-26 : DOCVIEW
  (`src/plugins/docview.c`), ouvert par Retour sur un texte `$04` qui
  commence par `_`. Relevé sur les 21 documents du disque v5.06 : `_CE`
  centre **jusqu'à** `_PC`/`_CL`/`_JD`, `_TDn` tabulation, `#:X=…]`
  affectation muette, `#:?X]` valeur, `#*X=]` saisie, `[` = « ° ». Non
  interprétés (imprimante seule) : `_JD`, `_CC`, `_LP`, `_LF`, `_ND`,
  en-têtes `_EN…__EA` et bas de page `_DB…__BA` montrés comme du texte.
- [x] **Papyrus traitement de texte** (Ediciel) et **HomeWord** (Sierra)
  — même DOCVIEW, texte à bit haut. Codes `$FF c … $FF` : `$06` centre
  la ligne, `$05` saut de page, les autres (`$0D` marges, `$0A`, `$0E n`
  points de plan) ignorés ; `$19` = ê et `$1B` = ô vus sur de vrais
  documents, `$18`/`$1A`/`$1C` = â/î/û supposés. Retour seulement si le
  document commence par un code, sinon `!` DOCVIEW. Échantillons :
  `Papyrus - Le traitement de texte personnel` (Spring 2023) et
  `RIAG_Homeword_Word_Processor_Data_Disk` ; ne pas confondre avec le
  cours de dactylographie (`a2_Ediciel_Papyrus_Side_1/2`). À faire :
  confirmer les autres codes sur plus de documents.
- [x] **Fantavision** (Brøderbund, 1985) — lecteur livré le 2026-09-26/27 :
  `FANTA.SYSTEM` (`src/fanta/`), écrit en salle blanche par un agent qui
  n'a lu que `docs/FANTAVISION-FORMAT.md` ; A2FC le lance par Retour sur
  un BIN `$8400` (`named_kind` 8 → RUN, `src/launch.h`) et il revient par
  `A2FILE.SYSTEM`. Fidélité mesurée hors dépôt contre l'oracle privé :
  141/144 films réels acceptés avant la règle « fin abîmée coupée », écart
  médian 1,4 % des octets d'écran, mêmes nombres d'images. Vitesse
  d'origine par un modèle de cycles de l'original (médiane 10 %), bascule
  Tab. Deuxième tour (2026-09-27) : les fins abîmées sont coupées (les
  144 films réels sont lus : POOL 1 image, PARADIES 40, ENGLISHFONT 9) ;
  vitesse accélérée, médianes simulées sous sim65 : 2,1× l'original sur
  points et lignes, 2,3× sur grandes lignes, 1,7–1,9× sur pleins, 1,8× sur
  formes dessinées. Troisième tour : **décors** (l'image hi-res marquée
  dans le dossier du film, sinon `NOM` à côté de `M.NOM`), écart moyen
  0,2 à 1 % des octets contre l'original sur PARADIES, STREAM,
  CHECKERBOARD ; première image après Tab juste à 1 % près. Reste : pleins
  auto-sécants à 1,7× (il faudrait ~1,5 Ko de plus : réciproques,
  contour tiré du remplissage), un trait tireté de PARADIES (près de
  « STIGMA ») plein chez l'original, mesure sur vraie machine.

### À faire, par ordre

1. [ ] **Textes Apple Pascal** (`TEXT` des volumes Pascal : en-tête de
   1 Ko, blancs compressés par DLE + compte). A2FC lit les volumes Pascal
   mais montre ces fichiers bruts. Gain rapide, fréquent sur les disques
   Pascal ; référence : CiderPress II `ApplePascal_Text.cs`.
2. [ ] **Sources tokenisées S-C Assembler et LISA** : illisibles
   aujourd'hui dans TEXT (jetons), fréquentes sur les disques de
   développeurs. Lister à la manière de BASLIST ; références : CiderPress II
   `SCAsm.cs`, `LisaAsm.cs` et leurs notes.
3. [ ] **Apple Writer** (commandes `.LM`, `.RM`, `.CJ`… en début de ligne)
   dans DOCVIEW, et **Merlin** (sources à bit haut, colonnes étiquette /
   opcode / opérande / commentaire ; CiderPress II `MerlinAsm.cs`). Tous deux
   déjà lisibles dans TEXT : c'est du confort, après 1 et 2. DOCVIEW n'a
   que ~120 octets : Merlin irait plutôt dans une surcouche à part.
4. [ ] **Bordures Print Shop / Print Shop Companion** (BIN, 144 ou
   148 octets, 12 × 12). Disposition des octets à établir avec Print Shop
   sous POM2, puis spécification publiée dans `docs/`. Se greffe sur
   PRINTSHOP. Échantillons : 77 bordures du disque « Gordon's Print Shop
   Borders » (Asimov `productivity/graphics/printshop/`).
5. [ ] **Polices Fontrix** : sortie de « Écarté » : CiderPress II a
   maintenant un convertisseur et des notes (`FontrixFont.cs`,
   `Fontrix-notes.md`). Se greffe sur FONTVIEW ou une petite surcouche.
6. [ ] **Music Construction Set** : le morceau compilé `.OBJ` sur
   Mockingboard, flux déduit du source officiel du lecteur (`MUSIC
   SOURCE`, et [mcs-player](https://github.com/cybernesto/mcs-player),
   MIT) ; en-tête à confirmer. Réutilise l'infrastructure de DUET.
7. [ ] **Images WOZ ouvertes comme un dossier** (IMGFS) : c'est le
   format des archives actuelles (Applesauce, archive.org). Décoder les
   pistes brutes 5,25" (6-et-2) pour lire les blocs ou secteurs. Valeur
   élevée, effort réel ; parcourir plus que visualiser.
8. [ ] **LZC 12 bits dans UNSHRINK** (NuFX 4, et 5 si l'en-tête dit
   ≤ 12 bits). `tools/lzc_ref.py` est dans `make test`. Le cœur actuel
   tient en `$1B00–$1F59` ; PREFIX commence à `$2000`. Le décodeur LZC
   est un second cœur, recopié en AUX `$1B00`.
9. [ ] **Graphics Magician** (Penguin Software). Commandes de tracé HGR de
   1 à 3 octets, documentées par la rétro-ingénierie de
   [McFadden (2025)](https://6502disassembly.com/a2-graphics-magician/).
   Effort moyen : lignes, remplissage, 108 motifs, pinceaux, police.
   Trancher la licence avant de reprendre motifs et police de PICDRAWH.
10. [ ] **Gutenberg** (traitement de texte) : CiderPress II
   `GutenbergWP.cs` et ses notes. Fréquence à mesurer.
11. [ ] **The Newsroom, suite** : le texte des panneaux `PN.*` et pages
   `PG.*` (compris en partie), puis le clip art commercial (index piste 34
   « SSI CLIP » lu, compression non décodée).
12. [ ] **Pinball Construction Set, tables `.PB`** (B, `$4000`, 4 à
   10 secteurs : logique, réglages, objets, image hi-res compressée par
   plages de zéros). Montrer le nom et l'image de la table, décompressée
   par la routine `DECOMPRESS` du source publié par Bill Budge
   ([PCS_AppleII](https://github.com/billbudge/PCS_AppleII), MIT, 2013).
   Deux variantes probables (BudgeCo, EA) à distinguer.
13. [ ] **Dalton's Disk Disintegrator** (`.DDD`), courant à l'époque des
   BBS : trouver une spécification (CiderPress I le lisait).
14. [ ] Dazzle Draw, sections `.SEC` (`$06`/`$F200`, 11 522 octets :
   largeur, hauteur, lignes en flux de 7 bits), déduites de deux fichiers.
   Rares ; les images plein écran sont déjà lues.
15. [ ] **Bank Street Writer, MultiScribe** : aucune spécification trouvée
   (Bank Street déjà dans « Écarté ») ; MultiScribe était très répandu en
   France. À rechercher avant tout travail.

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
- [ ] Bancs : s'appuyer sur ce que POM2 fournit depuis
  `work/printer-detection` : SSC avec commutateurs par slot et firmware
  Apple 341-0065-A, lignes DCD/DSR/CTS selon le câble, Grappler+ hors
  ligne / sans papier / absente commutables en cours de route, Grappler
  1981 et Apple Parallel Interface, journal `/slot-log`, octets imprimés
  et rendu PNG ImageWriter/Epson depuis `libpom2_core_test.a`. Référence :
  `docs/printer-detection.md` de POM2 (ce qui se lit sans effet, ce qui a
  un effet — sur la Grappler 1981, lire `$C0n2/$C0n3` déclenche un strobe
  —, ce qui peut bloquer : la Grappler+ 3.1 sans papier boucle en
  silence). Remplacer `--printer-ssc` de `pom2_playtest` par ces options.
  Tests sim65 avec un pilote bouchon ; section imprimante dans
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

Favoris de programmes ; PT3 sous pression, ANIMATE ; Beagle « Double Scrunch » (routine de
469 octets, mais aucune image compressée trouvée) ; lecteur de films
Movie Maker `.MVM` (lecteur d'origine MMA.OBJ ~4 Ko à désassembler,
oracle AUTOPLAY sous POM2, ~13 films d'éditeur, aucun d'utilisateur) ;
jouer une table
`.PB` seule en y greffant le moteur d'un jeu autonome de l'utilisateur
(rien de redistribué ; chemin LOAD/PLAY d'EDIT/PPAK à rétro-concevoir) ;
DIRSORT, BACKUP, SHRINK ; NIBCOPY reprise de piste **ou** `.NIB` (pas
les deux, pas de 3½) ; XMODEM, ADTPro blocs, TFTP ; PASSWORD ;
`GISTDATA.hdv` ; CPMW à plusieurs extents si la fenêtre se libère.

- **Formats propres au IIgs**, laissés de côté pour l'instant (décision du
  27 septembre 2026, peut-être repris plus tard) : Super Hi-Res (`$C1`,
  `$C0` PackBytes, APF, Paintworks, 3200 couleurs, DreamGrafix), Print Shop
  GS (clip art `$C313`/`$C323`, bordures `$C312`/`$C322`, polices
  `$C316`), icônes Finder `$CA`, polices QuickDraw II `$C8`, animations
  Paintworks `$C2`, AppleWorks GS, Teach, objets OMF, son Ensoniq (`$D8`,
  ASIF, SoundSmith).

## Écarté

- Hors de portée : NuFX 5 en 16 bits, Squeeze NuFX, a2dgrx.
- Sans documents ni spécification trouvés : Bank Street Writer, The New
  Print Shop (`$F5`).
