# A2 File Cmd — feuille de route

[0.8.6](https://github.com/habib256/a2filecmd/releases/tag/v0.8.6)
([qualification](docs/history/RELEASE-0.8.6.md), [CHANGELOG](CHANGELOG.md)).
Mini (II+ 48 Ko, DOS 3.3) et ProDOS (IIe 128 Ko), même numéro.
`make mini` ne partage pas `src/a2fc.c`.

Préserver les données prime. Ne pas relever les plafonds
([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)) ; MAIN 65C02 ≥ 256 octets
(299 aujourd’hui). **💾** = lecteurs physiques.

Le Commander (arbres, MOVE, retour au programme) est **clos**. Ce qui
reste n’est plus une fonction manquante, c’est la preuve que les
écritures tiennent.

## Maintenant : les trous de préservation

[DATA-SAFETY.md](docs/DATA-SAFETY.md). Une erreur de lecture, métadonnées
ou fermeture n’est ni une EOF ni un chemin libre.

- [ ] **Conversions** — comparer le résultat relu, pas seulement les
  écritures et fermetures. Fait pour TXTCONV, IMGCONV, COPY, SYNC, EDIT,
  CFG, et le 14 septembre 2026 pour DOSGET et BINARY2 (tests hôtes : octet
  faux, sortie illisible, lecture courte). Restent IMGFS et UNSHRINK, dont
  les surcouches n’ont plus de place (5 et 9 octets) : faire de la marge
  avant (chantier 6).
- [ ] **Pannes combinées** — couvertes par les harnais hôtes de COPY, EDIT,
  CFG, GOTO, SYNC, TXTCONV, IMGCONV, BATCH, DOSGET, BINARY2, UNSHRINK et
  DISKIMG (fermeture + collision + annulation, taille périmée, renommage,
  restauration et nettoyage en échec). Restent IMGFS et DOSWRITE sur
  disque réel, et les séquences entre outils (chantier 7).
- [x] **Autres chemins** — revue du 14 septembre 2026 des décisions
  « fichier absent » du résident : la création exclusive garde chaque
  chemin (éditeur, copie, mkdir) même quand `GET_FILE_INFO` échoue ; le seul
  cas qui confondait une erreur d’E/S avec une disparition, le contrôle de
  fin du déplacement d’arbre par lot, exige désormais le `$46` positif.

Sans ça, chaque nouveau média ou FIXIT dilue la preuve. Ne pas ouvrir
SHRINK, l’écriture dans une image, un journal de coupure, Pascal/CP/M
ni un format neuf tant que ces trois cases ne sont pas closes.

## En continu : les séquences

États, ressources et octets, pas le seul code de retour.

- [ ] **Séquences** — image → musique → copie ; annulation → reprise ;
  changement de disque.
- [ ] **`bench/plugins.py`** — relire les messages depuis la 0.8.5
  (ils passent, ce n’est pas une relecture).
- [ ] **`bench/shk.py` sur disquette 6502** — UNSHRINK est sur FILES ; le
  banc met son disque cible en lecteur 2 et attend « Insert A2FILES6502 »
  au lieu de l’avis AUX (`bny.py` a reçu FILES en lecteur 2 le 14/09).
- [ ] **Mutations** — `tools/fuzz_images.py` : UNSHRINK, BINARY2, IMGFS,
  DOS33 ; CI.
- [ ] **Images XL** — `bench/run.py` 6502 et 65C02.
- [ ] **Banc //c** — session, pile, disquette, souris.
- [ ] **💾 IIgs** — premier boot (SmartPort, `$C000`) ; documenter Disk II.

## Ensuite, pas avant

**Services de fichiers** ([FILE-SERVICES.md](docs/FILE-SERVICES.md)) —
rendement décroissant, extraire sans grossir `src/a2fc.c` :

- [ ] contrat unique (création exclusive, original récupérable, nettoyage
  limité aux fichiers créés, collisions refusées) ;
- [ ] IMGFS / DOS33 / DOSGET, CRC et métadonnées NuFX, relecture des extraits.

**FIXIT** — après la preuve ci-dessus, pas avant :

- [ ] diagnostic sans écriture (allocation, références, pointeurs,
  compteurs, blocs perdus) ;
- [ ] corrections seulement après un plan choisi, original conservé,
  chaque écriture vérifiée.

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
- [ ] Changements de lecteur (~20/copie) : ne pas emprunter les tables
  de noms sans `reload()`.
- [ ] Relecture groupée (~7 s) : trancher et documenter, ou laisser.

## Plus tard

Favoris de programmes (liste comme GOTO, sans toucher config ni préfixe).
Médias restants (PT3 sous pression, a2dgrx, Fantavision, ANIMATE, bitmap
hôte, documents). Disques (journal de coupure à étudier sans promettre
l’atomicité, DISKIMG reprise, VERIFY, DIRSORT, BACKUP, DOS33W, images
montées, SHRINK). Transferts (XMODEM, VDrive après ADTPro, TFTP).
Confort (DATE, TAGPAT, PASSWORD…). Corpus : `GISTDATA.hdv`,
[SAMPLE-MEDIA.md](docs/SAMPLE-MEDIA.md).

Clos et sortis de cette page : arbres itératifs, MOVE d’arbre, LAUNCHER
(retour épelé). Détail dans le changelog.

## Livraison

[AGENTS.md](AGENTS.md). `/RAM` : confirmer **avant**. Jetables pour les
essais destructifs. Deux CPU, pile, BSS, overlays.
[config/packages.mk](config/packages.mk). Avant release : `make test`,
sept supports, `tools/check_images.py`, `bench/extras.py`. Une coupure
peut laisser deux entrées sur les mêmes blocs ; la restauration traite
les erreurs **signalées**, pas la perte d’alimentation.
