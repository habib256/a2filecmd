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
DOCVIEW a ~60/120 octets (6502/65C02) dans sa fenêtre agrandie,
UNSHRINK ~900, SHAPES est plein. Les nouvelles
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
  interprétés (imprimante seule) : `_JD`, `_CC`, `_LP`, `_LF`.
- [x] **Calculs, en-têtes et bas de page Epistole** — faits le 2026-09-29,
  vérifiés contre l'impression d'Epistole 5.06 capturée sous POM2
  (protection contournée en mémoire, carte SSC avec sa ROM) : format des
  nombres (STR$ de |x| + ½ unité, virgule, pas de signe avec décimales),
  `_TD` tabulation décimale, `_ND`, pieds `%$` aux `_SP` et à la fin.
  Reste : les fins de page de l'imprimante (72 lignes, pied à la 60e) ne
  sont pas simulées ; `AND`/`OR`/`NOT` non reconnus (champ laissé tel
  quel) ; avec `_ND0`, un négatif calculé s'imprime décalé d'une unité
  chez Epistole (5-8 → -2), DOCVIEW montre -3.
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
- [ ] **Take 1** (Baudville, 1985) — en cours depuis le 2026-10-03.
  Étude privée faite (30 disques archive.org : 15 films, 176 scènes,
  290 acteurs, 67 décors) : tous les formats (`MV.` `SN.` `AC.` `BK.`
  `CS.`), le dessin des snapshots (liseré noir, registre de palette,
  enroulement, découpage), le texte (XDRAW), l'effacement par listes de
  rectangles (traînées comprises), les 16 fondus, les 18 sons et le
  minutage ; référence privée identique octet pour octet à l'original sous
  émulation sur les ~9 000 images de tous les films réels, modèle de
  cycles à 1,6 % (médiane). Spécification publiée :
  `docs/TAKE1-FORMAT.md`. Lancement côté A2FC fait : Retour sur `MV.*`
  (BIN `$8029`, ou aux 0 dans un catalogue DOS 3.3 ; règle dans
  `src/open.s` + `tools/file_viewer_ref.c`) → RUN → `TAKE1.SYSTEM`, avec
  l'image DOS et la piste/secteur du film, l'unité d'une vraie disquette
  DOS, ou le chemin du fichier extrait (`src/launch.h`,
  `tools/test_launch.py`). Lecteur `TAKE1.SYSTEM` écrit en salle blanche
  (`src/take1/`, 11 522 octets, mêmes octets sur 6502 et 65C02) : les
  8 093 images des 15 films identiques à l'original sous émulation ;
  durée par image / original : médiane 1,03 (p10 0,85, p90 1,41) ; encore
  lents : SHUTTLE DISCOVERY 1,71, ERIC II 1,35 (dessin au trait), mémoire
  quasi pleine (14 octets libres en CODE, 0 en page zéro). Banc POM2
  `bench/take1.py` fait (2026-10-04, deux éditions ; Ctrl-Reset rend la main
  à A2FC). Film de démonstration synthétique : `DEMO/MOVIES/TAKE1.DSK`
  (`tools/mkdemo_take1.py`, 2026-10-06). Reste : mesure sur vraie machine. Limites : un film sur deux disquettes n'est pas géré
  (aucun vu) ; la forme extraite échoue sur 5 films sur 15 (TIPS, ACTORS, BUSINESS,
  SNIPER III, Deluxe MOVIE) : les noms DOS tronqués à 15 caractères y
  collisionnent, ces films ne se jouent que depuis leur disquette ; le bruit des explosions n'est pas celui de l'original (il
  puise dans le code de Take 1).

- [x] **Logo** (2026-10-04) : Apple Logo enregistre ses procédures en
  texte DOS 3.3 (`T`, bit haut, `$8D`), déjà lu par TEXT ; Terrapin Logo
  en BIN `$2000` de texte ASCII (`NAME.LOGO`), ouvert par TEXT grâce au
  suffixe (`fv_ext`), et ses images SAVEPICT font 8 194 octets (page +
  2 octets), acceptées par `page_size`. Échantillons privés dans
  `~/.cache/a2fc/logo/` (Asimov). Le LOGO de `pom2games` n'écrit aucun
  fichier. Integer BASIC (BASLIST/`intbasic.c`) et texte à bit haut (TEXT)
  étaient déjà gérés.
- [x] **KoalaPad** (2026-10-04) : Micro-Illustrator (Island Graphics,
  Steven Dompier, 1983 ; « Koala Painter » sur certains disques, même
  programme) enregistre une page hi-res brute, sans compression :
  `BSAVE PICTR.nom,A$4000,L$1FF8` (lu dans son menu de stockage en
  Applesoft, « STANDARD DOS 3.3 PICTURE », et vérifié sur 40 images de 15
  disques archive.org gardés dans `~/.cache/a2fc/koala/`, 2 sauvegardes
  abîmées refusées par DOSGET). Copiées par **C**, ce sont des BIN `$4000`
  de 8 184 octets, déjà ouverts par IMAGE (`page_size`) : aucun octet de
  code. `tools/test_koala.py` (DOSGET réel, classifieur sur les deux CPU,
  échantillons privés sautés s'ils manquent), `bench/koala.py` 11/11 sur
  les deux éditions. Le format C64/Atari « Koala » (10 003 octets, `$6000`)
  n'a rien à voir et reste en hexadécimal. La page de 8 191 octets
  (`L$1FFF`, disques « Koala-ty Art ») est acceptée depuis le 2026-10-04
  (décision de l'utilisateur) : `page_size` prend 8 184 à 8 199 et
  16 376 à 16 391 octets, 0 octet de code. Reste : Graphics Exhibitor
  (diaporamas `GE.EXHIBIT.SEQUENCE`) non étudié.

- [x] **Écrans texte sauvés** (2026-10-04) : un BIN `$0400` de ≤ 2 048
  octets est une page d'écran, lo-res **ou** texte (écrans de titre, de
  crack, de BBS) ; DGRVIEW décide sur le contenu (≥ 25 % d'espaces `$A0`/
  `$20`/`$E0` visibles et plus d'espaces que d'octets « pleins » à deux
  quartets égaux) et l'affiche dans le vrai mode texte (40 colonnes jeu
  primaire, 80 colonnes jeu alternatif), **T** bascule texte ↔ lo-res,
  **A** le jeu de caractères. Corpus privé `~/.cache/a2fc/textscreen/`
  (1 892 disquettes Asimov lues : 77 écrans texte et 18 images lo-res
  distincts) + 27 demi-pages lo-res/DGR de French Touch : 0 erreur, marges
  33 % / 23 % d'espaces. Longueurs réelles : 1 024, 1 023, 1 016, 976 (la
  dernière ligne manque). Seuls les 960 octets visibles sont écrits (les
  trous d'écran gardent l'état des cartes — DGRVIEW les écrasait avant),
  AUX seulement en `$0400-$07FF` pour 80 colonnes ; le jeu de caractères
  des panneaux est rendu. Au passage : cc65 master compilait
  `*(unsigned char*)(c ? 0xC055 : 0xC054) = 0` en écriture à l'adresse `c`
  (page zéro `$00/$01`) : le double lo-res de l'édition 6502 n'avait jamais
  basculé PAGE2. Tests : `tools/test_textscreen.py` (le vrai .PLG des deux
  éditions dans un IIe émulé : chaque écriture, chaque commutateur),
  `test_dgrview.py`, `bench/textscreen.py` (19/19 sur les deux éditions,
  écran comparé point par point à la ROM de caractères). Reste : aucun
  écran 80 colonnes réel en un seul fichier trouvé (le seul vu est en deux
  moitiés de 1 023 octets, montrées chacune en 40 colonnes) ; écrans en
  page 2 (`$0800`) non routés par Retour (I les prend s'ils font 1 024).
- [x] **Polices HRCG** (DOS Tool Kit, 2026-10-04) : Retour sur un BIN de
  768 ou 1 024 octets nommé `.SET` ou `.FONT` (copies Beagle) ouvre
  FONTVIEW. Sur le même corpus : 244 `.SET` et 116 `.FONT`, tous de 768
  octets, aucun autre fichier à la fois de ce suffixe et de cette taille
  (le suffixe seul prendrait 29 fichiers étrangers, la taille seule 218).
  Adresses de chargement trop variées (`$8100`, `$8B00`, `$6700`, `$4000`…)
  pour servir. Coût : 48 octets d'OPEN (reste 15/20). Non routés : les
  `.STS` de Graphics Magician (`$6100`, mêmes données), les `*.FNT` de 1 024
  octets, Higher Text `*.SF` (choisir FONTVIEW dans `!`).

### À faire, par ordre

1. [x] **PT3 : le lecteur de Grouik (French Touch) comme moteur principal**
   (demande du 2026-10-03, fait le même jour, non commité). `ppt3.a` du
   disque DIX (GPLv3), traduction du lecteur Z80 de S.V. Bulba, vendu tel
   quel dans `src/plugins/ppt3/original/` et porté en ca65
   (`src/plugins/ppt3/ppt3.s`, identique octet pour octet au binaire ACME
   sans `PPT3_A2FC` : `tools/test_ppt3_port.py`). Moteur dans
   `A2FILE/PPT3.BIN` (800K et XL, mêmes octets pour les deux éditions),
   chargé en AUX `$2000`, module entier en AUX `$4000-$BFFF` (32 Ko au
   plus), trampoline au même endroit dans les deux banques, pilote lié dans
   PT3.PLG à `$3B00`. Consentement : nouveau service `aux_consent` (API v6),
   pas de question si /RAM est vide ; refus = pt3_lib, AUX intacte. /RAM
   reconstruit et annoncé après usage. Le fichier source est fermé avant la
   première note. Chaque lecture du module gardée (48 sites), budget de
   255 lectures par appel, au plus 4 commandes différées réelles par
   décodage ; écritures auditées (`tools/test_ppt3_engine.py`, émulateur
   6502 qui note chaque accès). pt3_lib reste le repli (02TS, > 32 Ko, refus,
   PPT3.BIN absent). Comparaison des deux moteurs : `tools/pt3_compare.py`
   et `src/plugins/ppt3/README.md` (348 modules sur 400 identiques une fois
   la table de notes ZX imposée, avant les corrections du 2026-10-03).
   **Suite du 2026-10-03 (décisions de l'utilisateur, faites)** : les deux
   moteurs calculent en unités ZX et convertissent chaque période (tons
   12 bits, bruit 5 bits, enveloppe) vers l'horloge de 1,0227 MHz du
   Mockingboard : (P × 1181 + 1024) >> 11, soit 1,0227/1,7734 à 0,09 cent
   près (`conv_mb` dans pt3_lib, `mb_scale` dans le moteur de GROUiK) ;
   références dans `tools/pt3_frequency_reference.json` (tables
   « mockingboard »), à moins de 2,5 cents de la hauteur ZX pour toute
   période ≥ 290. GROUiK copie les tables ZX au lieu de les générer
   (fin du ton ÷ 1,7734 et de la note 23 de la table ST à $02FD) ; le port
   sans `PPT3_A2FC` reste identique à ACME. pt3_lib : motifs de plus de
   64 lignes, décalage d'enveloppe signé (et sa retenue de trop), effet
   on/off, et glissement d'amplitude qui passait par 0 corrigés
   (`tools/test_pt3_fixes.py`). Comparaison : 394 modules sur 400
   identiques registre par registre ; restent l'échantillon par défaut
   (sample 1 contre échantillon vide de Bulba, 4 modules) et la fin des
   portamentos de 256 périodes et plus chez Bulba (2 modules). Reste :
   écoute sur vrai matériel ; les paires TurboSound compactes à 1x
   (voir `src/plugins/pt3lib/README.md`) ; les 15 modules du corpus que le
   garde refuse (13 refusés aussi par pt3_lib, fichiers tronqués).
2. [x] **VisiCalc** (Software Arts, 1979, né sur Apple II) — demandé le
   2026-10-04, fait le même jour (non commité). Surcouche VISICALC : Retour
   sur un texte qui commence par `>` (les deux formes de l'octet) ; la
   feuille est recalculée une fois, dans son ordre, comme VisiCalc au
   chargement (une formule qui lit une formule pas encore calculée vaut
   ERROR), avec l'arithmétique décimale de VisiCalc (six chiffres en base
   100, tout tronqué, de gauche à droite) et ses règles d'affichage
   (format général, `$`, `I`, `L`, `R`, `*`, débordement `>`), relevées
   sur VisiCalc 1.93 sous POM2 : 27 045 cellules de 67 feuilles réelles
   (Home and Office Companion, disques VisiCalc) et 7 000 de feuilles
   d'essai écrites pour l'occasion identiques à la référence
   `tools/visicalc_ref.py`, sauf les écarts listés dans
   `docs/VISICALC-FORMAT.md`. Tout en assembleur, en quatre morceaux : une
   partie qui reste et trois phases échangées (lecture, recalcul,
   affichage ; `VISICALC.BIN` à côté de la surcouche). Table des valeurs
   en mémoire principale (~240 valeurs), sinon en mémoire auxiliaire avec
   l'accord de l'utilisateur quand /RAM contient des fichiers (pas de
   question si /RAM est vide), /RAM reconstruit et annoncé ensuite.
   Tests : `tools/test_visicalc.py` (cœur décimal et surcouche entière
   sous sim65, deux CPU, fichiers hostiles, oracle), `bench/visicalc.py`
   (POM2, deux éditions). Reste : puissances et fonctions
   transcendantes calculées par la ROM Applesoft (derniers chiffres
   différents de VisiCalc : `3^2` vaut 9 et non 8,99999995 ; il faudrait
   reproduire les séries de VisiCalc, en mémoire auxiliaire ou une
   quatrième phase) ; titres et seconde fenêtre non montrés ; largeurs
   par colonne (`/GCC`) et formats d'Advanced VisiCalc non vérifiés sur
   l'original (pas de VisiCalc 80 colonnes qui tourne sous POM2) ;
   fichiers DIF (`/S#`) non lus ; vraie machine non essayée.
3. [ ] **Textes Apple Pascal** (`TEXT` des volumes Pascal : en-tête de
   1 Ko, blancs compressés par DLE + compte). A2FC lit les volumes Pascal
   mais montre ces fichiers bruts. Gain rapide, fréquent sur les disques
   Pascal ; référence : CiderPress II `ApplePascal_Text.cs`.
4. [ ] **Sources tokenisées S-C Assembler et LISA** : illisibles
   aujourd'hui dans TEXT (jetons), fréquentes sur les disques de
   développeurs. Lister à la manière de BASLIST ; références : CiderPress II
   `SCAsm.cs`, `LisaAsm.cs` et leurs notes.
5. [ ] **Apple Writer** (commandes `.LM`, `.RM`, `.CJ`… en début de ligne)
   dans DOCVIEW, et **Merlin** (sources à bit haut, colonnes étiquette /
   opcode / opérande / commentaire ; CiderPress II `MerlinAsm.cs`). Tous deux
   déjà lisibles dans TEXT : c'est du confort, après 1 et 2. DOCVIEW n'a
   que ~60 octets : Merlin irait plutôt dans une surcouche à part.
6. [ ] **Bordures Print Shop / Print Shop Companion** (BIN, 144 ou
   148 octets, 12 × 12). Disposition des octets à établir avec Print Shop
   sous POM2, puis spécification publiée dans `docs/`. Se greffe sur
   PRINTSHOP. Échantillons : 77 bordures du disque « Gordon's Print Shop
   Borders » (Asimov `productivity/graphics/printshop/`).
7. [ ] **Polices Fontrix** : sortie de « Écarté » : CiderPress II a
   maintenant un convertisseur et des notes (`FontrixFont.cs`,
   `Fontrix-notes.md`). Se greffe sur FONTVIEW ou une petite surcouche.
8. [ ] **Music Construction Set** : le morceau compilé `.OBJ` sur
   Mockingboard, flux déduit du source officiel du lecteur (`MUSIC
   SOURCE`, et [mcs-player](https://github.com/cybernesto/mcs-player),
   MIT) ; en-tête à confirmer. Réutilise l'infrastructure de DUET.
9. [ ] **Images WOZ ouvertes comme un dossier** (IMGFS) : c'est le
   format des archives actuelles (Applesauce, archive.org). Décoder les
   pistes brutes 5,25" (6-et-2) pour lire les blocs ou secteurs. Valeur
   élevée, effort réel ; parcourir plus que visualiser.
10. [ ] **LZC 12 bits dans UNSHRINK** (NuFX 4, et 5 si l'en-tête dit
   ≤ 12 bits). `tools/lzc_ref.py` est dans `make test`. Le cœur actuel
   tient en `$1B00–$1F59` ; PREFIX commence à `$2000`. Le décodeur LZC
   est un second cœur, recopié en AUX `$1B00`.
11. [x] **Graphics Magician** (Penguin Software). Commandes de tracé HGR de
   1 à 3 octets, documentées par la rétro-ingénierie de
   [McFadden (2025)](https://6502disassembly.com/a2-graphics-magician/).
   **Phase 1 faite le 2026-10-04** (étude privée + spécification
   publique, même méthode que Take 1) : `docs/GRAPHICS-MAGICIAN-FORMAT.md`.
   Oracle : les routines d'origine (six versions) dans POM2 ; moteur de
   référence Python privé (`~/.cache/a2fc/gmagic/`, jamais dans le dépôt)
   identique octet pour octet à l'oracle sur **398 images réelles**
   distinctes (The Quest 110, sa réédition 102, Ring Quest 94,
   Transylvania 72, groupes d'exemple 20) avec la routine de leur propre
   disque, 84/84 surcouches tracées par-dessus, et 2 800 images
   synthétiques aléatoires (6 799 tracés identiques sur 6 800). Résultats clés :
   - **deux dialectes** : V82 (PICDRAW/PICDRAWF 1982, recopiés dans les
     jeux 1982-84) et V84 (PICDRAWH/PICDRAWL). Le remplissage a été
     réécrit en 1984 et ne donne pas les mêmes pixels (pages identiques
     pour 93 images sur 398 seulement) : le lecteur doit choisir le
     dialecte (V84 si `$1x/$3x/$5x`, sinon V82 par défaut, touche pour
     basculer) ;
   - lignes = routines HPOSN/HGLIN de la ROM Applesoft (modèle exact
     décrit ; la couleur ne change qu'au prochain « début de ligne ») ;
     bizarreries reproduites et décrites : remplissage V82 sur la ligne 0
     qui commence à la ligne X mod 7, milieu calculé sur 8 bits, V84 qui
     remplit la ligne sous un point non blanc, pinceaux non découpés au
     bord (colonnes 40-41, lignes 192+ lues après les tables, dont une
     partie hors de l'écran) ;
   - identification sans en-tête : analyse stricte du premier dessin
     (0 faux positif sur 1 607 fichiers d'autres formats, 0 raté sur 378) ;
   - aucune image réelle n'utilise le texte ; le pinceau 7 (« spray ») est
     le plus utilisé ; 99 des 108 motifs servent.
   **Licence tranchée le 2026-10-04 (option 2)** : les 108 motifs (27
   lignes de 4 octets + 108 paires) et les 8 pinceaux 16 × 14 sont dans la
   spec (annexe A, données observées à l'écran, revérifiées en
   reconstruisant les tables depuis le texte : 398/398 images réelles
   identiques) ; la police de Penguin n'est **pas** reprise : le texte
   (V84) sera tracé avec une police 7 × 8 d'A2FC, donc pas à l'identique
   (aucune image réelle n'a de texte). La spec contient aussi le résumé
   des exigences du lecteur (§17 : reconnaissance, refus, V82 par défaut
   et touche V84, plusieurs dessins par fichier, temps de tracé) et
   l'annexe B : 60 images aléatoires définies par un générateur décrit,
   12 images faites main, un groupe et une surcouche, avec le SHA-256 de
   la page attendue en V82 et V84 (152/152 confirmées par les routines
   d'origine sous POM2).
   **Phase 2 faite le 2026-10-04** (salle blanche : un agent qui n'a lu
   que la spec, non commité) : **GMAGIC** (`src/plugins/gmagic.s`, tout
   en assembleur, `sdk/gmagic.cfg` sur le modèle de NRCLIP : fenêtre
   `$1B00-$1FFF`, partie `GMLOW` + `GMBSS` recopiée en `$0C00`, entrée et
   contrôles `COLD` en `$2000`). Entrée sur un BIN dont les premiers
   octets sont des commandes (règle `@gm` d'`open.s`, `gm_prefix` de
   `file_viewer_ref.c` ; place faite dans OPEN en sortant son état dans
   `copy_buf`, en vidant la description cachée et en passant
   `open_entry` en assembleur), aussi dans le menu `!` (Images). Toutes
   les images du fichier sont vérifiées avant le premier point (règles 2-4
   du §3 et table du §11) ; la même routine relit chaque commande au
   tracé ; rien n'est écrit hors de `$2000-$3FFF` (lignes hors écran
   jetées comme le §11 le dit). V82 par défaut, **D** pour V84 (V84
   imposé si `$1x/$3x/$5x`), **N**/Espace image suivante (page effacée,
   retour à la première), **O** image suivante par-dessus (pièces et
   calques), Gauche/Droite, **S**, Échap. Lignes : modèle du §6 (pas de
   ROM). Police : BOLD.SET d'A2FC (STANDARD de CiderPress II en gras),
   rangée avec les lignes de motifs dans les têtes de 112 octets des blocs
   de la page texte principale une fois l'écran HGR allumé (trous d'écran
   et `$06F7` intacts) ; motifs et pinceaux dans `copy_buf`. Lecture
   seule, pas d'AUX. Mémoire : fenêtre 9 octets libres (65C02) / 6
   (6502), `$0C00` 12 ; OPEN 5/5, MAIN 6/418, LC 30/21, MENU 220/169.
   Tests : `tools/gmagic_ref.py --selftest` (152/152 pages de l'annexe B),
   `tools/test_gmagic.py` (sim65, deux CPU : les 152 pages, refus,
   erreurs de lecture, clés, texte), `tools/test_gmagic_writes.py` (le
   PLG 6502 livré dans `tools/mos6502.py`, chaque écriture contrôlée,
   annexe B en SHA), routage dans `tools/test_file_viewers.py`, groupe du
   DEMO (`HOUSE.GMAGIC`), `bench/gmagic.py` (port 6867) 20/20 sur les deux
   éditions. Pages pour l'oracle : `tools/gmagic_pages.py PICS OUT`.
   Reste : comparer les pages de GMAGIC avec l'oracle privé sur les 398
   images réelles (`tools/gmagic_pages.py` puis
   `~/.cache/a2fc/gmagic/public/compare_cleanroom.py`), par quelqu'un
   d'autre que l'agent de salle blanche ; texte non identique à
   l'original (police) ; un éclair d'une ou deux trames de la zone COLD
   avant le premier tracé.
   **Comparaison faite le 2026-10-04** : 398/398 images réelles et 84/84
   calques identiques à l'oracle (sim65 6502, 65C02, mos6502). Règle 5
   du §3 ajoutée ensuite (l'image doit tracer : au moins un `$Ax`, `$Cx`
   ou `$Ex` ; sans elle 23 fichiers sur 1 607 passaient, dont `26 00`) :
   GMAGIC l'applique à chaque image (une image suivante qui ne trace rien
   clôt la liste), OPEN n'en prend que la part bon marché (octet de fin
   avant l'octet 3 : refus) — OPEN tombe à 0 octet libre.
   - Les images V84 de The Quest DR n'ont aucune commande propre à V84 :
     elles s'ouvrent en V82 jusqu'à **D** (heuristique possible, non
     tranchée : PICDRAWL/PICDRAWH dans le même dossier).
   - Des images réelles avec texte existent sur les disques de l'outil
     (PLOT TEST.SPC, PAL280.SPC) : tracées avec la police A2FC.
   Hors champ : dialecte des jeux Comprehend (Crimson Crown, Oo-Topos,
   Transylvania 1985, Talisman, Spy) dont les images sont dans leur propre
   format de disque, double haute résolution (`.DPC`).
12. [ ] **Gutenberg** (traitement de texte) : CiderPress II
   `GutenbergWP.cs` et ses notes. Fréquence à mesurer.
13. [ ] **The Newsroom, suite** : le texte des panneaux `PN.*` et pages
   `PG.*` (compris en partie), à faire. Le clip art commercial est
   **fait** (2026-10-03) : NRCLIP (menu `!`, Images) enregistre chaque
   page d'une disquette de clip art (image `.DSK`/`.DO`/`.2MG` DOS ou
   vraie disquette) comme une page HGR (BIN `$2000`, 8 192 octets) dans
   le répertoire ProDOS d'en face, création exclusive, page abîmée
   ignorée, écriture ratée retirée ; format dans
   `docs/NEWSROOM-FORMAT.md`, `tools/test_nrclip.py` (sim65, deux CPU,
   12 images réelles : 391 des 393 pages distinctes, les deux de la
   Collection 3 face A refusées). Code en partie à `$0C00` (second tampon
   ProDOS, `sdk/nrclip.cfg`), donc un seul fichier ouvert à la fois.
   `bench/nrclip.py` (POM2, les deux éditions : l'image d'une vraie
   disquette de clip art ouverte depuis le disque dur, puis une autre dans
   le lecteur 2 du Disk II lue par `READ_BLOCK` : 65/65). Reste : une
   mesure sur vraie machine et vraie disquette.
14. [ ] **Pinball Construction Set, tables `.PB`** (B, `$4000`, 4 à
   10 secteurs : logique, réglages, objets, image hi-res compressée par
   plages de zéros). Montrer le nom et l'image de la table, décompressée
   par la routine `DECOMPRESS` du source publié par Bill Budge
   ([PCS_AppleII](https://github.com/billbudge/PCS_AppleII), MIT, 2013).
   Deux variantes probables (BudgeCo, EA) à distinguer.
15. [ ] **Dalton's Disk Disintegrator** (`.DDD`), courant à l'époque des
   BBS : trouver une spécification (CiderPress I le lisait).
16. [ ] Dazzle Draw, sections `.SEC` (`$06`/`$F200`, 11 522 octets :
   largeur, hauteur, lignes en flux de 7 bits), déduites de deux fichiers.
   Rares ; les images plein écran sont déjà lues.
17. [x] **Bank Street Writer** — fait le 2026-10-03 dans DOCVIEW : relevé sur
   ~60 documents réels (archive.org : disques de données, d'activités,
   tutoriels, 368 « Side 1 » ProDOS), texte à bit haut dans un BIN (`$0840`
   ou `$63D0` en DOS 3.3, 0 en ProDOS), `$8D` par paragraphe, `$83` en tête
   de ligne la centre, `$89` tabulation de 4 colonnes (le code du programme
   compte 4 positions), le texte s'arrête au premier `$00` (restes du
   tampon après). Aiguillage dans `src/open.s` + `tools/file_viewer_ref.c`,
   tests `test_docview.py` (documents réels si présents) et
   `test_file_viewers.py`. Reste : vérifier contre l'affichage de BSW sous
   POM2 (son menu se pilote à la Pomme ouverte, non scriptée ici) ; `$8E`,
   que le programme traite comme spécial, jamais vu dans un document.
   **MultiScribe** : aucune spécification trouvée ; très répandu en France,
   à rechercher avant tout travail.
18. [ ] **DGR entrelacé de French Touch** (démo *One More Thing*, disque
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

- [x] **`make BOTH_EDITIONS=1 disk` bouclait** : corrigé le 2026-10-04
  (`BOTH_EDITIONS=` dans les sous-appels), `tools/test_make_editions.py`.

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
