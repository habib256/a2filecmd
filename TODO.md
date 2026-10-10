# A2 File Cmd — feuille de route

[0.9.6](https://github.com/habib256/a2filecmd/releases/tag/v0.9.6)
([CHANGELOG](CHANGELOG.md)), publiée le 7 octobre 2026. Mini et ProDOS, même numéro ;
`make mini` ne partage pas `src/a2fc.c`.
Ce qui est fait vit dans le CHANGELOG et les rapports
[0.9.1](docs/QUALIFICATION-0.9.1.md), [0.9.2](docs/QUALIFICATION-0.9.2.md),
[0.9.3](docs/QUALIFICATION-0.9.3.md), [0.9.4](docs/QUALIFICATION-0.9.4.md),
[0.9.5](docs/QUALIFICATION-0.9.5.md),
[0.9.6](docs/QUALIFICATION-0.9.6.md) ; ce fichier ne garde que la suite.

Préserver les données prime ([AGENTS.md](AGENTS.md)). Ne pas relever
les plafonds ([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)). Une étape
se ferme avec un oracle hôte et un banc POM2.

## Deux trains

- **1.0** : la 0.9.3 durcie. Aucune fonctionnalité nouvelle, aucun
  overlay plein retouché sauf pour corriger un défaut.
- **1.1** : les formats et le reste, une fois la 1.0 publiée.

## Publiées

- 0.9.4, 26 septembre 2026 : [CHANGELOG](CHANGELOG.md#094---2026-09-26),
  [qualification](docs/QUALIFICATION-0.9.4.md).
- 0.9.5, 4 octobre 2026 (nouveaux formats : VisiCalc, Graphics Magician,
  Take 1, Fantavision, The Newsroom…) :
  [CHANGELOG](CHANGELOG.md#095---2026-10-04),
  [qualification](docs/QUALIFICATION-0.9.5.md).

## 1.0 — chemin critique

Chaque étape suppose la précédente fermée. Un défaut trouvé aux étapes
4 ou 5 renvoie à l'étape 2, puis à une nouvelle RC.

1. **Gel des fonctionnalités.**
   - [x] Geler les formats : `A2FILE.CFG` et l'ABI des overlays (API v5,
     structures, constantes), [sdk](sdk/README.md) ;
     `tools/test_abi_freeze.py` dans `make test`. Un seul service ajouté
     depuis, en bout de table : `aux_consent`, API v6 (0.9.5, PT3).
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
   - [x] MAIN 65C02 : 494 octets libres en 0.9.4 (82 avant), 6502 : 885 ;
     `pan_at(p)` remplace les 90 `panels[p]` à indice variable, que cc65
     multipliait par 98. Depuis, les formats de la 0.9.5 les ont repris :
     **9 / 389** octets libres (65C02 / 6502) le 7 octobre 2026
     (`check_layout.py`, branche `release-0.9.6`).
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
     libres en 65C02, 53 en 6502 à l'époque ; 13 / 11 le 7 octobre 2026). Limites : le IIgs n'est pas testé
     (POM2 ne l'émule pas) ; une imprimante sur le port modem du //c.
3. **Retour visuel.**
   - [ ] Vérifier que la progression 0.9.3 couvre les pauses à 1 MHz
     (catalogue, copie, vérification, chargement), puis fermer cette ligne.
4. **Qualification (1.0-rc).**
   - [ ] `make test`, `make qualify`, `tools/check_images.py` sur les
     quatre images, les deux CPU.
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

Lecture directe DOS 3.3 : T/H forcent DOSVIEW ; I et Retour passent par IDENT, livré dans
les éditions ProDOS complètes (800K et XL). Texte, hex, lo-res brut
$0400 et HGR brut $2000/$4000 (8192/8184 octets) sont pris en charge.
DOSINT et DOSBAS listent directement Integer BASIC et Applesoft via le menu Programmation.
PN. récupère le texte et les références photos ; PG. expose les mises en page
et composants NEWSROOM. Restent leur rendu typographique/assemblage complet,
les compressions/DHGR,
adaptation des autres lecteurs, images ProDOS et recette physique ; voir
[DOS-VIEWERS.md](docs/DOS-VIEWERS.md). Music Construction Set importe
maintenant les paires fichier principal + `.OBJ` sur ProDOS. DOSMCS lit
directement les exports de 2304 octets et les paires éditeur depuis les
disques DOS réels et DSK/DO/2IMG. Restent les réglages stockés de MCS,
les variantes non reconnues et les autres formats audio.

Seulement s'il reste des octets. Relevé du 7 octobre 2026 (65C02 / 6502,
`check_layout.py` et cartes de `make`) : OPEN 11 / 11 octets libres (168 /
173 quand son classifieur est passé en assembleur, `src/open.s`, le 26
septembre ; les formats de la 0.9.5 les ont pris) ; une règle de routage
coûte 10 à 20 octets, à écrire dans `open.s` **et** dans
`tools/file_viewer_ref.c`. Le résident 65C02 a 9 octets libres
(objectif 256) : tout nouveau format vit dans une surcouche. DOCVIEW a
42 / 41 octets dans sa fenêtre agrandie, UNSHRINK 901 / 888, SHAPES est
plein (3 / 0). Les nouvelles surcouches vont sur 800K et XL ; l’édition ProDOS
140K est retirée de la distribution.

- [ ] **Choisir les prochains formats à partir de fichiers réels.** Recenser
  un corpus, classer les inconnus par fréquence, puis améliorer IDENT avec
  des signatures externes. Cela donnera une priorité mesurée aux lecteurs
  de la 1.1.

Méthode pour réaliser ce choix, avant d'ajouter des formats un par un :
- [ ] **Recensement** (`tools/corpus_survey.py`) : parcourir Asimov et les
  collections archive.org, passer chaque fichier dans une copie Python des
  règles d'identification d'A2FC, publier le taux de couverture et la
  liste des fichiers non reconnus classés par fréquence. Ce classement
  valide ou corrige l'ordre ci-dessous.
- [ ] **Signatures en fichier** lues par IDENT (type, aux, octets à une
  position → format et outil) : reconnaître un format sans octet de code,
  nommer ceux qu'on ne lit pas encore, noter les inconnus pour les
  rapports de bug.
- [ ] **API v7, briques partagées** (la v6 est prise depuis la 0.9.5 par
  `aux_consent`) : lecteur de bits, RLE/PackBytes,
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

Publiés en 0.9.5 ; le détail est dans le [CHANGELOG](CHANGELOG.md) et
la spécification de chaque format. Ne restent ici que les suites.

- [x] **The Newsroom** (Springboard) : photos `PH.*`, bannières `BN.*` et
  disquettes de clip art (NRCLIP), [spécification](docs/NEWSROOM-FORMAT.md).
  Reste : le texte des panneaux `PN.*` et pages `PG.*` (n° 9 ci-dessous) ;
  NRCLIP sur vraie machine et vraie disquette.
- [x] **Movie Maker** : décors `.BKG` et planches `.SHP`. Reste : les films
  `.MVM` (« Plus tard »).
- [x] **Epistole** (Version Soft), calculs, en-têtes et bas de page
  compris ; **Papyrus** (Ediciel) et **HomeWord** (Sierra) ; **Bank Street
  Writer** — tous dans DOCVIEW. Reste : Epistole, les fins de page de
  l'imprimante (72 lignes, pied à la 60e) ne sont pas simulées,
  `AND`/`OR`/`NOT` non reconnus (champ laissé tel quel), avec `_ND0` un
  négatif calculé s'imprime décalé d'une unité chez Epistole (5-8 → -2),
  DOCVIEW montre -3 ; Papyrus, `$18`/`$1A`/`$1C` = â/î/û seulement supposés,
  autres codes à confirmer sur plus de documents ; Bank Street Writer, à
  vérifier contre l'affichage de BSW sous POM2, `$8E` jamais vu.
  **MultiScribe** : aucune spécification trouvée ; très répandu en France,
  à rechercher avant tout travail.
- [x] **Fantavision** (Brøderbund) : `FANTA.SYSTEM`, salle blanche,
  [spécification](docs/FANTAVISION-FORMAT.md). Reste : pleins
  auto-sécants à 1,7× en vitesse accélérée (il faudrait ~1,5 Ko de plus :
  réciproques, contour tiré du remplissage), un trait tireté de PARADIES
  (près de « STIGMA ») plein chez l'original, mesure sur vraie machine.
- [x] **Take 1** (Baudville) : `TAKE1.SYSTEM`, salle blanche,
  [spécification](docs/TAKE1-FORMAT.md) ; film de démonstration
  `DEMO/MOVIES/TAKE1.DSK` (`tools/mkdemo_take1.py`, 2026-10-06). Mémoire
  pleine : 11 565 octets, 1 octet libre dans sa partie basse
  `$0800-$1FFF`, page zéro `$60-$DF` entière (cartes de `make`, 6 octobre
  2026). Reste : mesure sur vraie machine ; encore lents, SHUTTLE DISCOVERY
  1,71 et ERIC II 1,35 fois l'original (dessin au trait). Limites : un
  film sur deux disquettes n'est pas géré (aucun vu) ; la forme extraite
  échoue sur 5 films sur 15 (TIPS, ACTORS, BUSINESS, SNIPER III, Deluxe
  MOVIE) : les noms DOS tronqués à 15 caractères y collisionnent, ces films
  ne se jouent que depuis leur disquette ; le bruit des explosions n'est
  pas celui de l'original (il puise dans le code de Take 1).
- [x] **Logo** (Apple et Terrapin) : procédures et images SAVEPICT, sans
  octet de code.
- [x] **KoalaPad / Micro-Illustrator** : pages hi-res brutes, sans octet de
  code. Reste : Graphics Exhibitor (diaporamas `GE.EXHIBIT.SEQUENCE`) non
  étudié.
- [x] **Écrans texte sauvés** (DGRVIEW). Reste : aucun écran 80 colonnes
  réel en un seul fichier trouvé (le seul vu est en deux moitiés de 1 023
  octets, montrées chacune en 40 colonnes) ; écrans en page 2 (`$0800`)
  non routés par Retour (I les prend s'ils font 1 024).
- [x] **Polices HRCG** (`.SET`, `.FONT`) dans FONTVIEW. Non routés par
  Retour : les `.STS` de Graphics Magician (`$6100`, mêmes données), les
  `*.FNT` de 1 024 octets, Higher Text `*.SF` (choisir FONTVIEW dans `!`).
- [x] **PT3 : le lecteur de GROUiK (French Touch) comme moteur
  principal**, pt3_lib en repli ([ppt3](src/plugins/ppt3/README.md),
  [pt3lib](src/plugins/pt3lib/README.md)). Reste : écoute sur vrai
  matériel ; les paires TurboSound compactes à 1x ; les 15 modules du
  corpus que le garde refuse (13 refusés aussi par pt3_lib, fichiers
  tronqués).
- [x] **VisiCalc** (Software Arts), [spécification](docs/VISICALC-FORMAT.md).
  Reste : puissances et fonctions transcendantes calculées par la ROM
  Applesoft (derniers chiffres différents de VisiCalc : `3^2` vaut 9 et
  non 8,99999995 ; il faudrait reproduire les séries de VisiCalc, en
  mémoire auxiliaire ou une quatrième phase) ; titres et seconde fenêtre
  non montrés ; largeurs par colonne (`/GCC`) et formats d'Advanced
  VisiCalc non vérifiés sur l'original (pas de VisiCalc 80 colonnes qui
  tourne sous POM2) ; fichiers DIF (`/S#`) non lus ; vraie machine non
  essayée.
- [x] **Graphics Magician** (Penguin Software) : GMAGIC, salle blanche,
  [spécification](docs/GRAPHICS-MAGICIAN-FORMAT.md) ; 398/398 images
  réelles et 84/84 calques identiques à l'oracle privé. Reste : texte non
  identique à l'original (police d'A2FC) ; un éclair d'une ou deux trames
  de la zone COLD avant le premier tracé ; les images V84 de The Quest DR
  n'ont aucune commande propre à V84 et s'ouvrent en V82 jusqu'à **D**
  (heuristique possible, non tranchée : PICDRAWL/PICDRAWH dans le même
  dossier). Hors champ : dialecte des jeux Comprehend (Crimson Crown,
  Oo-Topos, Transylvania 1985, Talisman, Spy) dont les images sont dans
  leur propre format de disque, double haute résolution (`.DPC`).

### À faire, par ordre

1. [x] **Textes Apple Pascal** (`PASTEXT`, lancement par `!`, deux CPU ;
   `TEXT` des volumes Pascal : en-tête de
   1 Ko, blancs compressés par DLE + compte). A2FC lit les volumes Pascal
   mais montre ces fichiers bruts. Gain rapide, fréquent sur les disques
   Pascal ; référence : CiderPress II `ApplePascal_Text.cs`. Lecture native
   avec indentation DLE, pages et validation complète. Le choix automatique
   depuis le navigateur Pascal reste à raccorder.
2. [ ] **Sources tokenisées S-C Assembler et LISA** : illisibles
   aujourd'hui dans TEXT (jetons), fréquentes sur les disques de
   développeurs. Lister à la manière de BASLIST ; références : CiderPress II
   `SCAsm.cs`, `LisaAsm.cs` et leurs notes.
   `SCASM` et `LISAV2` sont implémentés par `!`, avec tests du vrai C sur
   les deux CPU. Restent LISA v3/v4/v5 et leur table de symboles.
3. [ ] **Apple Writer** (commandes `.LM`, `.RM`, `.CJ`… en début de ligne)
   dans DOCVIEW, et **Merlin** (sources à bit haut, colonnes étiquette /
   opcode / opérande / commentaire ; CiderPress II `MerlinAsm.cs`). Tous deux
   déjà lisibles dans TEXT : c'est du confort, après 1 et 2. DOCVIEW n'a
   que quelques octets : Merlin irait plutôt dans une surcouche à part.
   `MERLIN` est implémenté par `!` ; Apple Writer reste à faire.
4. [ ] **Bordures Print Shop / Print Shop Companion** (BIN, 144 ou
   148 octets, 12 × 12). Disposition des octets à établir avec Print Shop
   sous POM2, puis spécification publiée dans `docs/`. Se greffe sur
   PRINTSHOP. Échantillons : 77 bordures du disque « Gordon's Print Shop
   Borders » (Asimov `productivity/graphics/printshop/`).
5. [x] **Polices Fontrix** : `FONTRIX`, aperçu monochrome sur écran texte
   par `!`, testé sur 21 polices réelles et les deux CPU. Les caractères de
   plus de 20 lignes combinent deux lignes ; pas de rendu HGR à taille réelle.
   Sortie de « Écarté » : CiderPress II a
   maintenant un convertisseur et des notes (`FontrixFont.cs`,
   `Fontrix-notes.md`). Se greffe sur FONTVIEW ou une petite surcouche.
6. [x] **Music Construction Set** : convertir les partitions de l'éditeur
   `.OBJ` pour le Mockingboard ; exports déduits du source officiel (`MUSIC
   SOURCE`, et [mcs-player](https://github.com/cybernesto/mcs-player),
   MIT). Les partitions et les exports sont deux formats distincts.
   Priorité utilisateur : `MCS` lit maintenant les exports Mockingboard
   de 2304 octets, identiques au lecteur d'origine sur dix morceaux réels,
   validés sous sim65 et POM2 sur les deux CPU. L'import des paires
   partition principale + `.OBJ` est implémenté en lecture seule, avec
   contrôle des deux fichiers avant le son. Restent les réglages stockés
   de l'éditeur et les autres variantes. DOSMCS lit maintenant exports et
   paires éditeur directement depuis les disques DOS 3.3 réels et images.
   Voir `docs/MCS-FORMAT.md`.
7. Exclu par demande utilisateur : **images WOZ ouvertes comme un dossier**
   (IMGFS). Aucun support WOZ ajouté. Étude initiale : c'est le
   format des archives actuelles (Applesauce, archive.org). Décoder les
   pistes brutes 5,25" (6-et-2) pour lire les blocs ou secteurs. Valeur
   élevée, effort réel ; parcourir plus que visualiser.
8. [ ] **LZC 12 bits dans UNSHRINK** (NuFX 4, et 5 si l'en-tête dit
   ≤ 12 bits). `tools/lzc_ref.py` est dans `make test`. Le cœur actuel
   tient en `$1B00–$1F59` ; PREFIX commence à `$2000`. Le décodeur LZC
   est un second cœur, recopié en AUX `$1B00`.
9. [ ] **The Newsroom, suite** : le texte des panneaux `PN.*` et pages
   `PG.*` (compris en partie), à faire.
10. [ ] **Gutenberg** (traitement de texte) : CiderPress II
   `GutenbergWP.cs` et ses notes. Fréquence à mesurer.
   `GUTTEXT` lit le texte déjà extrait par `!` ; le système de fichiers
   Gutenberg et ses polices externes restent à implémenter.
11. Exclu par demande utilisateur : **Pinball Construction Set, tables `.PB`**
   (B, `$4000`, 4 à
   10 secteurs : logique, réglages, objets, image hi-res compressée par
   plages de zéros). Montrer le nom et l'image de la table, décompressée
   par la routine `DECOMPRESS` du source publié par Bill Budge
   ([PCS_AppleII](https://github.com/billbudge/PCS_AppleII), MIT, 2013).
   Deux variantes probables (BudgeCo, EA) à distinguer.
12. [ ] **Dalton's Disk Disintegrator** (`.DDD`), courant à l'époque des
   BBS : trouver une spécification (CiderPress I le lisait).
13. [ ] Dazzle Draw, sections `.SEC` (`$06`/`$F200`, 11 522 octets :
   largeur, hauteur, lignes en flux de 7 bits), déduites de deux fichiers.
   Rares ; les images plein écran sont déjà lues.
14. [ ] **DGR entrelacé de French Touch** (démo *One More Thing*, disque
   DIX, GPLv3) : 22 images 80 × 48, deux pages DGR ($400-$BFF main + aux,
   blocs LZ4 derrière un en-tête de 16 octets) affichées en basculant
   PAGE1/PAGE2 à chaque ligne de balayage, synchronisé sur le VBL : chaque
   bloc mélange deux couleurs (jusqu'à 136 teintes). Décodeur hôte vérifié
   (PNG dans `~/.cache/a2fc/frenchtouch/omt_png/`). Reste : un format de
   fichier (8 Ko bruts ?), la boucle à cycle près dans DGRVIEW (1 MHz exact,
   VBL IIe/IIc/IIgs, repli page 1 sinon), essai POM2 puis vraie machine.
   Pas prioritaire (2026-10-03).

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
- Sans documents ni spécification trouvés : The New Print Shop (`$F5`).
