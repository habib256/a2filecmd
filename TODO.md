# A2 File Cmd — feuille de route

État réconcilié le **25 octobre 2026**. Dernière version publiée :
[0.9.8](https://github.com/habib256/a2filecmd/releases/tag/v0.9.8),
18 octobre 2026. Mini et ProDOS partagent le numéro de version ;
`make mini` ne partage pas `src/a2fc.c`.

Les réalisations et leurs preuves sont dans le [CHANGELOG](CHANGELOG.md),
les qualifications [0.9.6](docs/QUALIFICATION-0.9.6.md),
[0.9.7](docs/QUALIFICATION-0.9.7.md), [0.9.8](docs/QUALIFICATION-0.9.8.md)
et l'[audit POM2 du 25 octobre](bench/README.md#compatibilité-pom2--audit-du-25-octobre-2026).
Une case cochée signifie que son périmètre précis est terminé ; elle ne
vaut pas qualification des variantes ou du matériel physique.

Préserver les données prime ([AGENTS.md](AGENTS.md)). Ne pas relever
les plafonds ([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)). Une correction
se ferme avec un oracle hôte et un banc POM2 sur images jetables.

## Versions visées

- **1.0** : stabilisation, qualification complète et recette physique des
  fonctions existantes. Les sept lecteurs retenus sont implémentés dans les
  XL ; leurs profils et limites restent ceux de [V1-FORMATS](docs/V1-FORMATS.md).
- **1.1** : extensions des lecteurs et formats supplémentaires, choisis à
  partir du corpus mesuré et sous réserve des budgets mémoire.
- **1.2** : impression, encore à implémenter.

## État vérifié au 25 octobre 2026

- [x] Quatre distributions reconstruites et contrôlées : DOS 3.3 Mini,
  ProDOS 800 Ko, XL 6502 et XL 65C02 enhanced. La 800 Ko est une sélection
  explicite de **98 surcouches**, avec **190 blocs libres** ; les XL gardent
  les **129 surcouches**, avec 60 040 / 60 042 blocs libres (6502 / 65C02).
  L'inventaire est dans `config/800k.mk` ; les nouveaux lecteurs spécialisés
  ne sont pas automatiquement ajoutés à la disquette.
- [x] Les sept lecteurs de la 1.0 sont intégrés ; IDENT rétablit en 0.9.8
  les routes de Retour, y compris SYS, Applesoft et Integer BASIC.
- [x] Hôte reconstruit avec POM2 `f6d8a146` après ses releases 0.9.8/0.9.9.
  L'ancien plantage isolé « mutex lock failed » n'a pas été reproduit.
  Mode Disk II/IWM et numéro interne du contrôleur slot 5 corrigés ; les
  erreurs de sauvegarde et arrêts forcés font échouer les bancs.
- [x] Validation ciblée POM2 : session 73/73, //c 20/20, RGB 18/18 ;
  DOSWRITE slot 5 17/17, sécurité des données 16/16 et protection des
  imprimantes 19/19 sur chaque CPU ; VDrive 13/13. NIBCOPY passe sur DSK
  et WOZ avec les deux CPU, secteurs exacts, sources, AUX et pile préservés.
  Les huit nouvelles régressions de l'hôte passent. Ce passage ciblé
  ne remplace pas `make qualify`.
- [x] Gardes mémoire actives sur les deux constructions. Réserves
  **65C02 / 6502** : MAIN **1 / 388 octets**, carte langage **8 / 6**,
  LOWRAM **87 / 112**, écart sous la pile C réservée **18 / 594** ;
  OPEN **0 / 0**. Ces zones ne s'additionnent pas ; l'écart sous la pile
  n'est pas une mesure de sa consommation. Le Mini a MAIN et LOW pleins.

## 1.0 — travail restant, par ordre

1. **Dégager de la marge mémoire sans relâcher les gardes.**
   - [ ] Réexaminer le partage résident/surcouches, particulièrement en
     65C02 ; objectif de réserve MAIN : 256 octets. Mesurer tout gain sur
     les deux CPU avec les contrôles de disposition et de pile.
   - [x] Cache des informations de volume : prototype écarté pour préserver
     les marges ; étude reportée après la 1.0.
2. **Fermer les vérifications fonctionnelles restantes.**
   - [ ] Vérifier la progression et les pauses à 1 MHz : catalogue, copie,
     vérification et chargement. Les tests ciblés ne ferment pas cette recette.
   - [ ] Documenter le jeu autonome PCS « Make Game » : un fichier B à
     `$177D`, `$7783` octets, `JMP` en tête ; Retour/B dans le Mini et X
     sous ProDOS en BIN `$06`, aux `$177D`. Les trois chemins ont été vus
     sous POM2 ; le joystick reste nécessaire.
3. **Qualifier une même révision candidate complète.**
   - [ ] Exécuter `make test`, `make qualify` et `tools/check_images.py`
     sur les quatre images et les deux CPU, avec l'hôte POM2 corrigé.
     Documenter les corpus manquants et les scénarios ignorés.
   - [ ] Confirmer les protections et les limites de chaque lecteur ;
     aucun défaut connu pouvant perdre des données ne doit rester ouvert.
4. **Faire la recette sur matériel réel.**
   - [ ] Suivre [HARDWARE-CHECKLIST.md](docs/HARDWARE-CHECKLIST.md) sur IIe
     6502, IIe enhanced et //c : copies, protections, /RAM, souris, musique,
     FIXIT/REPAIR, chargement et retour des surcouches.
   - [ ] Mesurer les temps sur Disk II et 800 Ko physiques, sur les deux
     CPU. Les mesures des contrôleurs POM2 à 1 MHz restent des simulations.
   - [ ] Reproduire chaque défaut trouvé sur une image jetable et corriger
     avant de refaire la qualification du candidat.
5. **Finaliser la documentation et publier la 1.0.**
   - [ ] Actualiser captures, manuel, PDF et liens de téléchargement pour
     la révision qualifiée. Écrire les limites restantes, y compris celles
     des machines non testées ; ne promettre aucune atomicité ProDOS.
   - [ ] Taguer seulement après les étapes précédentes.

Rappels : `/RAM` occupé se confirme **avant** d'y toucher ; `/RAM` vide
vérifié ne pose pas la question. Les essais destructifs restent sur supports
jetables. Le //c+, les accélérateurs et les restaurations de sessions POM2
ne sont pas qualifiés par l'audit ciblé ; la recette IIgs reste distincte.

## Expériences de distribution — hors blocage de la 1.0

La distribution 800 Ko tient déjà avec sa sélection explicite. L'objectif
historique « tout mettre sur 800 Ko » est distinct des XL complètes.

- [x] ZX02 isolé : gain mesuré de 44,2 % sur les overlays ; essai du
  programme principal avec 27/34 blocs libres sur 800 Ko (6502/65C02),
  socle 140 Ko avec 34 blocs libres, contrôles d'E/S, bornes, CRC et AUX.
  Voir [ZX02-EXPERIMENT](docs/ZX02-EXPERIMENT.md).
- [x] Décodeur assembleur borné : 18 mesures POM2 à 1 MHz, surcoût de
  3,85/3,44 s sur Disk II (6502/65C02), +2,06 s sur Sony 800 Ko ;
  résultats dans `docs/ZX02-TIMINGS.json`.
- [ ] Qualifier sur matériel réel avant de décider d'intégrer le lanceur
  ZX02 aux distributions habituelles.
- [ ] Décider d'une éventuelle édition ProDOS 140 Ko réduite : prototype
  à 246/280 blocs, outils et compléments à sélectionner. Elle n'est pas
  une cinquième image publiée.

## 1.1 — formats

Lecture directe DOS 3.3 : T/H forcent DOSVIEW ; I et Retour passent par IDENT, livré dans
la 800 Ko et les XL. Texte, hex, lo-res brut
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

Les budgets du relevé du 25 octobre ci-dessus priment sur les anciens
chiffres. OPEN est plein ; le résident 65C02 n'a qu'un octet de réserve.
Les nouvelles fonctions doivent rester en surcouches, avec identification
par les étapes IDENT quand nécessaire et contrôles des deux compilateurs.
Les XL contiennent tous les lecteurs ; la sélection 800 Ko est explicite.
L'édition ProDOS 140 Ko reste expérimentale, hors distribution publiée.

- [ ] **Prioriser les prochains formats à partir du corpus existant.**
  Actualiser le classement des inconnus après les nouveaux raccordements
  DOS et choisir les variantes à étendre ; ne pas confondre candidat IDENT
  et lecteur entièrement qualifié.
- [x] **Premier recensement mesuré** : `tools/corpus_census.py` applique
  le vrai C IDENT et son routage DOS à 1 907 sources, 37 777 occurrences
  classées, 27 408 contenus distincts avec type/aux/système identiques.
  Résultats, périmètre et refus dans [CORPUS-CENSUS](docs/CORPUS-CENSUS.md).
  C'est une sélection locale, pas toute la production Apple II.

Méthode pour les prochaines extensions :

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
estimations historiques ; le recensement du 10 octobre les complète sans
mesurer une popularité mondiale. Le classement de développement reste à
réviser à partir des contenus et variantes réellement récupérables.
Les formats propres au IIgs sont laissés de côté pour l'instant
(voir « Plus tard »).

### Faits

Implémentés dans les versions 0.9.5 à 0.9.8 ; le détail est dans le
[CHANGELOG](CHANGELOG.md) et la spécification de chaque format.
Les limites ci-dessous restent ouvertes malgré l'existence du lecteur.

- [x] **The Newsroom** (Springboard) : photos `PH.*`, bannières `BN.*` et
  disquettes de clip art (NRCLIP), [spécification](docs/NEWSROOM-FORMAT.md).
  `NEWSPAN` et `NEWSPAGE` lisent aussi le texte des panneaux `PN.*` et
  la structure des pages `PG.*`. Restent le rendu typographique et
  l'assemblage complet (n° 9 ci-dessous), puis NRCLIP sur vraie disquette.
- [x] **Movie Maker** : décors `.BKG`, planches `.SHP` et aperçu des films
  `.MVM` par MVMOVIE. L'aperçu couleur 40×48 et la navigation sont couverts ;
  transparence, sprites HGR et cadence originale restent hors profil.
  Voir [V1-FORMATS](docs/V1-FORMATS.md).
- [x] **Epistole** (Version Soft), calculs, en-têtes et bas de page
  compris ; **Papyrus** (Ediciel) et **HomeWord** (Sierra) ; **Bank Street
  Writer** — tous dans DOCVIEW. Reste : Epistole, les fins de page de
  l'imprimante (72 lignes, pied à la 60e) ne sont pas simulées,
  `AND`/`OR`/`NOT` non reconnus (champ laissé tel quel), avec `_ND0` un
  négatif calculé s'imprime décalé d'une unité chez Epistole (5-8 → -2),
  DOCVIEW montre -3 ; Papyrus, `$18`/`$1A`/`$1C` = â/î/û seulement supposés,
  autres codes à confirmer sur plus de documents ; Bank Street Writer, à
  vérifier contre l'affichage de BSW sous POM2, `$8E` jamais vu.
  **MultiScribe** : `MULTISCR` lit les variantes TXT/WPF reconnues en texte
  paginé, styles/règles contrôlés ; fontes proportionnelles et autres variantes
  restent à qualifier. Voir [format](docs/WORD-PROCESSORS.md).
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

### Lecteurs livrés et extensions restantes

1. [x] **Textes Apple Pascal** : PASTEXT lit les textes UCSD avec en-tête
   de 1 Ko, indentation DLE, pages et validation complète, par `!` après
   extraction. Le raccordement automatique depuis le navigateur Pascal
   reste à faire.
2. [x] **Sources tokenisées S-C Assembler et LISA** : SCASM, LISAV2,
   LISAV3 et LISAV4 sont implémentés, avec tests du vrai code et bancs sur
   les deux CPU. La 0.9.8 accepte aussi les répétitions de contrôles S-C.
   Restent les dialectes non qualifiés, dont ANIX.EQUATES, et la comparaison
   complète au rendu original. [Détails](docs/NEXT-TEXT-FORMATS.md).
3. [x] **Apple Writer et Merlin** : MERLIN et APPLEWR sont des lecteurs
   spécialisés ; Apple Writer lit marges, retrait et alignement en DOS 3.3
   et ProDOS. Restent justification complète et paramètres imprimante.
4. [x] **Bordures et polices Print Shop / Companion BIN** : `PSBORDER`
   affiche les trois motifs 24×14 des BIN 144/148 octets ; `PSFONT` permet
   de parcourir les glyphes et leurs lignes. DOS 3.3 et ProDOS, sans AUX.
   77 bordures et 36 polices, comparaison avec l'original et banc natif
   10/10 par CPU. [Spécification et limites](docs/PRINTSHOP-FORMAT.md).
   ProDOS `$F5` aux $2000/$1000 est maintenant pris en charge.
   Restent assemblage/options/masques et texte composé.
5. [x] **Polices Fontrix** : `FONTRIX`, aperçu monochrome sur écran texte
   par `!`, testé sur 21 polices réelles et les deux CPU. Les caractères de
   plus de 20 lignes combinent deux lignes ; pas de rendu HGR à taille réelle.
   Restent aussi les variantes non qualifiées. Références : `FontrixFont.cs` et
   `Fontrix-notes.md` de CiderPress II.
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
   ≤ 12 bits) : `tools/lzc_ref.py` fournit la référence hôte dans
   `make test`, mais le décodeur natif reste à implémenter et qualifier.
   Le placement d'un second cœur en AUX est une piste, pas du code livré.
9. [ ] **The Newsroom, suite** : compléter le rendu typographique et
   l'assemblage texte/photos des `PN.*` et `PG.*`. NEWSPAN/NEWSPAGE lisent
   déjà texte et structure ; [NEWSROOM-FORMAT](docs/NEWSROOM-FORMAT.md).
10. [ ] **Gutenberg** (traitement de texte) : CiderPress II
   `GutenbergWP.cs` et ses notes. Fréquence à mesurer.
   `GUTTEXT` lit le texte déjà extrait par `!` ; le système de fichiers
   Gutenberg et ses polices externes restent à implémenter.
11. [x] **Pinball Construction Set** : PCSVW fournit l'aperçu statique
   retenu pour la 1.0, fond enregistré et contours/remplissage des objets.
   Les tables renommées BIN/$4000 sont reconnues par IDENT. Le moteur de
   jeu, la physique et les scripts restent hors profil ; l'ancienne
   exclusion d'un lecteur est dépassée par ce profil livré. Voir
   [V1-FORMATS](docs/V1-FORMATS.md).
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

Projet issu de l'étude du 25 septembre 2026 ; aucun PRINT.PLG livré.
Cible envisagée : une grande surcouche lancée par `!`, sans ajout résident,
avec les services de l'API v6. Aucun fichier à modifier hors d'un éventuel
`PRINT.CFG`, soumis aux règles de sauvegarde récupérable.
Pas d'impression intégrée dans le Mini, dont MAIN et LOW sont pleins ;
`PR#1` reste une possibilité depuis BASIC.

- [ ] **Version minimale** (~1 à 1,5 semaine) : catalogue ou dossier,
  texte (dont l'export de DISASM), vidage hexadécimal. Grappler+ et SSC /
  ports //c en accès direct au matériel, attente bornée, Échap, barre de
  progression, message « imprimante pas prête » ; autres cartes Pascal 1.1
  par leur firmware, avec avertissement. Refuser le slot de VDrive.
- [ ] Bancs : exploiter les périphériques présents dans POM2 0.9.9 et
  revérifier leurs API au démarrage du chantier : SSC avec commutateurs
  par slot et firmware Apple 341-0065-A, lignes DCD/DSR/CTS selon le câble, Grappler+ hors
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
  choix des API POM2 pour injecter les pannes d'imprimante.

## Plus tard

FAVRUN est déjà livré pour les favoris de programmes ; ses extensions
éventuelles restent à définir. Travaux différés : cache des informations
de volume (prototype écarté en 1.0), PT3 sous pression, ANIMATE ; Beagle
« Double Scrunch » (routine de 469 octets, sans image compressée trouvée) ;
lecture Movie Maker `.MVM` fidèle à l'original au-delà de l'aperçu actuel
(MMA.OBJ, oracle AUTOPLAY sous POM2) ; jouer une table
`.PB` seule en y greffant le moteur d'un jeu autonome de l'utilisateur
(rien de redistribué ; chemin LOAD/PLAY d'EDIT/PPAK à rétro-concevoir) ;
BACKUP, SHRINK ; NIBCOPY reprise de piste **ou** `.NIB` (pas
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

## Recensement des lecteurs (2026-10-10)

[51 familles et variantes à couvrir](docs/FORMATS-A-COUVRIR.md), avec priorités,
état réel des lecteurs et disponibilité dans l’inventaire public ;
[recensement mesuré du corpus](docs/CORPUS-CENSUS.md). Les candidats IDENT
ne sont pas comptés comme des fichiers entièrement validés par leur lecteur.

Magic Window : `MAGWIN` implémenté en lecture seule, DOS 3.3 et ProDOS,
avec contrôles imprimante visibles (`^A`, `^[`…), en-tête omis, texte paginé.
Six documents réels testés, banc natif 10/10 sur chaque CPU. Restent le rendu
imprimé, l'en-tête/pied de page et les variantes non qualifiées.


Texte DOS à accès aléatoire : `DOSREC` implémenté en lecture seule,
avec longueur d’enregistrement choisie (1–4096), navigation, octets NUL
et trous distincts. NUL ne termine jamais le fichier ; la limite affichée
est le dernier secteur alloué, pas un EOF exact. DSK, 2MG et Disk II ;
560 secteurs logiques au maximum. Schémas de champs métier restent ouverts.
[Usage, qualification et limites](docs/DOS-RECORDS.md).

PFS:Write : `PFSWRITE` lit en ProDOS les documents $16 aux $0002, texte
paginé et contrôles visibles. Huit contenus réels qualifiés ; restent
mise en forme, fusion File et variantes anciennes. Le lot supplémentaire
contient aussi deux bases File et six feuilles Plan, désormais couvertes
par les lecteurs spécialisés décrits ci-dessous.
[Structure et inventaire séparé](docs/PFS-WRITE.md).

PFS:File : `PFSFILE` lit en ProDOS A2CD00 le formulaire et les fiches
actives ; 49 fiches de STAFF/COSTFILE qualifiées. Restent rapports,
anciennes éditions et autres signatures. [Limites](docs/PFS-FILE.md).

PFS:Plan : `PFSPLAN` lit les six feuilles B00 ProDOS $16/$0004 en lecture
seule : libellés principaux, valeurs enregistrées et formules de lignes/colonnes.
Restent formats, titres de groupes, formules de cellules et autres profils.
[Limites](docs/PFS-PLAN.md).
