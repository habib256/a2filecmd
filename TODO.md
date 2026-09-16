# A2 File Cmd — feuille de route

[0.8.7](https://github.com/habib256/a2filecmd/releases/tag/v0.8.7)
([qualification](docs/history/RELEASE-0.8.7.md), [CHANGELOG](CHANGELOG.md)).
Mini (II+ 48 Ko, DOS 3.3) et ProDOS (IIe 128 Ko), même numéro.
`make mini` ne partage pas `src/a2fc.c`.

Préserver les données prime. Ne pas relever les plafonds
([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)) ; MAIN 65C02 ≥ 256 octets
(429 aujourd’hui). **💾** = lecteurs physiques.

Le Commander (arbres, MOVE, retour au programme) est **clos**. Ce qui
reste n’est plus une fonction manquante, c’est la preuve que les
écritures tiennent.

## Maintenant : les trous de préservation

[DATA-SAFETY.md](docs/DATA-SAFETY.md). Une erreur de lecture, métadonnées
ou fermeture n’est ni une EOF ni un chemin libre.

- [x] **Conversions** — comparer le résultat relu, pas seulement les
  écritures et fermetures. Fait pour TXTCONV, IMGCONV, COPY, SYNC, EDIT,
  CFG, et le 14 septembre 2026 pour DOSGET, BINARY2, IMGFS et UNSHRINK
  (tests hôtes : octet faux, sortie illisible, lecture courte, source
  perdue en seconde passe). IMGFS est devenue une grande surcouche, l’état
  d’UNSHRINK est monté à `$3E00` : les deux ont plus de 1 500 octets.
- [ ] **Pannes combinées** — couvertes par les harnais hôtes de COPY, EDIT,
  CFG, GOTO, SYNC, TXTCONV, IMGCONV, BATCH, DOSGET, BINARY2, UNSHRINK,
  IMGFS et DISKIMG (fermeture + collision + annulation, taille périmée,
  renommage, restauration et nettoyage en échec). Les séquences entre
  outils ont leur banc depuis le 14 septembre 2026 (`bench/sequences.py`,
  deux CPU, en CI). Reste 💾 DOSWRITE sur disque réel : le harnais hôte et
  le banc Disk II de POM2 couvrent chaque écriture, pas le fer.
- [x] **Autres chemins** — revue du 14 septembre 2026 des décisions
  « fichier absent » du résident : la création exclusive garde chaque
  chemin (éditeur, copie, mkdir) même quand `GET_FILE_INFO` échoue ; le seul
  cas qui confondait une erreur d’E/S avec une disparition, le contrôle de
  fin du déplacement d’arbre par lot, exige désormais le `$46` positif.

Sans ça, chaque nouveau média dilue la preuve. Ne pas ouvrir
SHRINK, l’écriture dans une image, un journal de coupure, Pascal/CP/M
ni un format neuf tant que la dernière case n’est pas close.

## En continu : les séquences

États, ressources et octets, pas le seul code de retour.

- [x] **Séquences** — image → musique → copie ; annulation → reprise ;
  changement de disque : `bench/sequences.py`, 21 contrôles, octets relus
  après la sortie, deux CPU.
- [ ] **`bench/plugins.py`** — relire les messages depuis la 0.8.5
  (ils passent, ce n’est pas une relecture).
- [x] **`bench/shk.py` sur disquette 6502** — le 14 septembre 2026, les
  bancs d’archives amorcent `build-6502/A2FILECMD-full.po`
  (`make benchfloppy ARCH=6502`, `A2FC_BUILD=build-6502
  A2FC_IMG=A2FILECMD-full`) : 30/30 sur les deux CPU.
- [x] **Mutations** — le 16 septembre 2026 : `tools/fuzz_prodos.py` pour
  FIXIT/REPAIR (15 000 cas sur trois graines ; il a valu le refus du plan
  entier sur `XLINK`, docs/FIXIT.md §5 et §7) et `tools/fuzz_archives.py`
  pour UNSHRINK (pilote C et cœur assembleur sous sim65, deux CPU),
  BINARY2, IMGFS et DOS33 (20 000 cas sur deux graines, cinq invariants :
  aucun fichier préexistant touché, chaque fichier gardé égal à la
  référence hôte, verdict honnête). Les deux ont leur tranche dans
  `make test` ; `tools/fuzz_images.py` couvre toujours les lecteurs
  d'images.
- [ ] **Images XL** — `bench/run.py` 6502 et 65C02.
- [ ] **Banc //c** — session, pile, disquette, souris.
- [ ] **💾 IIgs** — premier boot (SmartPort, `$C000`) ; documenter Disk II.
- [ ] **💾 REPAIR sur fer** — une disquette réellement abîmée : les harnais
  et les bancs POM2 couvrent chaque écriture, pas le lecteur.

## Ensuite, pas avant

**Services de fichiers** ([FILE-SERVICES.md](docs/FILE-SERVICES.md)) —
rendement décroissant, extraire sans grossir `src/a2fc.c` :

- [ ] contrat unique (création exclusive, original récupérable, nettoyage
  limité aux fichiers créés, collisions refusées) ;
- [ ] IMGFS / DOS33 / DOSGET, CRC et métadonnées NuFX, relecture des extraits.

Puis **un seul** :

- [ ] 💾 **NIBCOPY** — IIe et //c, un et deux lecteurs, 300 tr/min et
  accélérateur ; ensuite **un** gain (reprise de piste **ou** `.NIB`).
  Pas de 3½ avant le 5¼ mesuré sur fer.
- [ ] 💾 **ADTPro blocs** — dossiers, envoi/réception, CRC, NAK.
  Nibble seulement après NIBCOPY fer.

Une petite surcouche (DELETE, COPY, IMGFS, ATTR, OPEN) ne bouge que si
on doit la modifier : alors extraire un service partagé, mesurer au
lien. OPEN ne retombe pas à quelques octets.

## Mini — indépendante

[MINI-DOS33.md](docs/MINI-DOS33.md). Pas de remplacement sur place, de
copie à un seul lecteur ni de formatage.

- [ ] **💾 II+ physique** — les bancs POM2 ne remplacent pas le fer.
- [x] **Changements de lecteur** — `copy_side` copie aussi `ent_slot`,
  donc `=` et le second panneau au boot sont une identité complète.
  Le moteur de copie n’emprunte pas les tables de noms : un lot marqué
  en a besoin jusqu’au dernier fichier. Tests hôtes : copie avec slot,
  noms sans slot refusés, `ent_name` intact après `execute`.
- [x] **Relecture groupée** — après une écriture, seul le disque écrit
  est relu ; deux panneaux sur ce disque partagent un catalogue
  (`copy_side`) au lieu de le payer deux fois. Ctrl-R relit encore
  les deux. La relecture par secteur à la copie est conservée.

## Plus tard

Favoris de programmes (liste comme GOTO, sans toucher config ni préfixe).
Médias restants (PT3 sous pression, a2dgrx, Fantavision, ANIMATE, bitmap
hôte, documents). Disques (journal de coupure à étudier sans promettre
l’atomicité, DISKIMG reprise, VERIFY, DIRSORT, BACKUP, DOS33W, images
montées, SHRINK). Transferts (XMODEM, VDrive après ADTPro, TFTP).
Confort (DATE, TAGPAT, PASSWORD…). Corpus : `GISTDATA.hdv`,
[SAMPLE-MEDIA.md](docs/SAMPLE-MEDIA.md).

Clos et sortis de cette page : arbres itératifs, MOVE d’arbre, LAUNCHER
(retour épelé), FIXIT et REPAIR ([FIXIT.md](docs/FIXIT.md) : diagnostic
sans écriture, réparations relues et restaurées, seconde passe). Détail
dans le changelog.

## Livraison

[AGENTS.md](AGENTS.md). `/RAM` : confirmer **avant**. Jetables pour les
essais destructifs. Deux CPU, pile, BSS, overlays.
[config/packages.mk](config/packages.mk). Avant release : `make test`,
sept supports, `tools/check_images.py`, `bench/extras.py`. Une coupure
peut laisser deux entrées sur les mêmes blocs ; la restauration traite
les erreurs **signalées**, pas la perte d’alimentation.
