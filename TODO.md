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

## 1.0 — chemin critique

Chaque étape suppose la précédente fermée. Un défaut trouvé aux étapes
4 ou 5 renvoie à l'étape 2, puis à une nouvelle RC.

1. **Gel des fonctionnalités.**
   - [x] Geler les formats : `A2FILE.CFG` et l'ABI des overlays (API v5,
     structures, constantes), [sdk](sdk/README.md) ;
     `tools/test_abi_freeze.py` dans `make test`.
   - [x] Noms d'images : `A2FILECMD-PRODOS-{140K,800K,XL,XL-65C02-enhanced}`
     et `A2FILECMD-DOS3.3` ; la séparation est « enhanced ou non ».
   - [ ] DEMO du XL rangé par sorte de fichier, sans dossier CIDERPRESS,
     l'album HGR dans `PICTURES/ALBUM` (`tools/stage_demo.py`).
2. **Solder la dette (1.0-rc1).**
   - [ ] Indexer les grands catalogues sans état périmé après changement
     de disque ; le parcours relit encore les blocs précédents
     ([mesures](docs/PERFORMANCE-0.9.2.md)).
   - [ ] Trancher : cache des informations de volume. Prototype écarté
     pour préserver les marges mémoire ; le fermer ou le reporter en 1.1.
   - [ ] Trancher : MAIN 65C02 à 82 octets, objectif 256. Bloquant 1.0,
     ou condition d'entrée d'un format 1.1.
3. **Retour visuel.**
   - [x] Mini : la case d'activité tourne pendant les tentatives RWTS sur
     une disquette jamais formatée (4,8 s → 1,4 s d'immobilité ; banc
     `mini33_lend` : appels et disquettes identiques octet à octet).
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
- The Newsroom : le clip art n'est pas dans des fichiers DOS ou ProDOS
  (faux catalogue, pistes entières occupées).
- Sans documents ni spécification trouvés : Bank Street Writer, Fontrix
  GRAFFILE, The New Print Shop (`$F5`).
