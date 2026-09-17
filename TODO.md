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

Deux niveaux de preuve, distingués partout : **qualifié POM2** (harnais
hôtes sur le vrai C, fuzzers, bancs POM2 sur les deux CPU) et **qualifié
sur matériel** (💾). Un chantier se ferme au premier niveau ; le second
reste ouvert à part, marqué 💾, sans bloquer la suite.

## Maintenant : les trous de préservation

[DATA-SAFETY.md](docs/DATA-SAFETY.md). Une erreur de lecture, métadonnées
ou fermeture n’est ni une EOF ni un chemin libre.

- [x] **Conversions** — comparer le résultat relu, pas seulement les
  écritures et fermetures. Fait pour TXTCONV, IMGCONV, COPY, SYNC, EDIT,
  CFG, et le 14 septembre 2026 pour DOSGET, BINARY2, IMGFS et UNSHRINK
  (tests hôtes : octet faux, sortie illisible, lecture courte, source
  perdue en seconde passe). IMGFS est devenue une grande surcouche, l’état
  d’UNSHRINK est monté à `$3E00` : les deux ont plus de 1 500 octets.
- [x] **Pannes combinées** (qualifié POM2) — couvertes par les harnais hôtes de COPY, EDIT,
  CFG, GOTO, SYNC, TXTCONV, IMGCONV, BATCH, DOSGET, BINARY2, UNSHRINK,
  IMGFS et DISKIMG (fermeture + collision + annulation, taille périmée,
  renommage, restauration et nettoyage en échec). Les séquences entre
  outils ont leur banc depuis le 14 septembre 2026 (`bench/sequences.py`,
  deux CPU, en CI). Le harnais hôte et le banc Disk II de POM2 couvrent
  chaque écriture de DOSWRITE.
- [ ] **💾 DOSWRITE sur disque réel** — en attente de matériel ; ne bloque
  plus rien.
- [x] **Autres chemins** — revue du 14 septembre 2026 des décisions
  « fichier absent » du résident : la création exclusive garde chaque
  chemin (éditeur, copie, mkdir) même quand `GET_FILE_INFO` échoue ; le seul
  cas qui confondait une erreur d’E/S avec une disparition, le contrôle de
  fin du déplacement d’arbre par lot, exige désormais le `$46` positif.

Décision du 16 septembre 2026 : la règle est assouplie. Les cases
qualifiées POM2 suffisent pour avancer, et les Services de fichiers
sont ouverts, parce qu’ils renforcent justement la préservation.
SHRINK, l’écriture dans une image, un journal de coupure, Pascal/CP/M
et les formats neufs restent fermés tant que les Services de fichiers
ne sont pas clos.

## En continu : les séquences

États, ressources et octets, pas le seul code de retour.

- [x] **Séquences** — image → musique → copie ; annulation → reprise ;
  changement de disque : `bench/sequences.py`, 21 contrôles, octets relus
  après la sortie, deux CPU.
- [x] **`bench/plugins.py`** — le 16 septembre 2026, les 18 bancs de
  surcouches relisent le message final mot pour mot (`wait_note`,
  `note_blank` dans `bench/xplug.py`), deux CPU, 558 contrôles chacun ;
  deux libellés de TXTCONV avaient changé depuis la 0.8.5 sans que les
  bancs le voient.
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
- [x] **Images XL** — le 16 septembre 2026, `bench/run.py --xl 6502|65C02`
  joue la session complète sur les deux XL publiées (74 et 66 contrôles,
  en CI) : le volume XL est rebâti avec les fichiers de travail, après
  vérification qu’il redonne le `.2mg` octet à octet.
- [x] **Banc //c** — le 16 septembre 2026, `bench/iic.py` (20 contrôles,
  en CI) : disquette 6502 et disque SmartPort (copies vers /RAM et vers le
  SmartPort relues), XL 65C02 amorcée par le SmartPort, pile, souris. La
  copie disquette → SmartPort a révélé un défaut de POM2, corrigé dans
  POM2 (7dc429b) : le séquenceur Disk II n'était pas remis à zéro quand le
  moteur démarrait sur le lecteur 2 vide.
- [ ] **💾 IIgs** — premier boot (SmartPort, `$C000`) ; documenter Disk II.
- [ ] **💾 REPAIR sur fer** — une disquette réellement abîmée : les harnais
  et les bancs POM2 couvrent chaque écriture, pas le lecteur.
- [x] **FIXIT/REPAIR sur disque dur** — le 17 septembre 2026 : l'arbre est
  parcouru une fois, les réclamations au-delà de 4 096 blocs vivent en AUX
  (`src/plugins/fixit_bits.inc`, question /RAM avant, /RAM reconstruit
  après, S3,D2 refusé) ; FIXIT propose Q (répertoires seuls) ou F. 32 Mo :
  69 min → 2 min 15 s (complet), 8 s (rapide). `bench/bigvol.py` (S5,D2 par
  `pom2_playtest --hd2`), `tools/test_fixit_bits.py` (sim65, deux CPU),
  docs/FIXIT.md §4.
- [ ] **💾 FIXIT/REPAIR en AUX sur fer** — la bascule RAMRD avec le miroir
  du code n'est prouvée que sous POM2 (IIe enhanced et non enhanced) : un
  disque dur de plus de 4 096 blocs sur un vrai IIe et sur un //c, /RAM
  relu après.

## Maintenant aussi : les Services de fichiers

**Services de fichiers** ([FILE-SERVICES.md](docs/FILE-SERVICES.md)),
ouverts le 16 septembre 2026 : ils renforcent la préservation. Extraire
sans grossir `src/a2fc.c` :

- [ ] contrat unique (création exclusive, original récupérable, nettoyage
  limité aux fichiers créés, collisions refusées) ;
- [ ] IMGFS / DOS33 / DOSGET, CRC et métadonnées NuFX, relecture des extraits.

## Ensuite, pas avant

Après les Services de fichiers, **un seul** :

- [ ] 💾 **NIBCOPY** — IIe et //c, un et deux lecteurs, 300 tr/min et
  accélérateur ; ensuite **un** gain (reprise de piste **ou** `.NIB`).
  Pas de 3½ avant le 5¼ mesuré sur fer.
- [ ] 💾 **ADTPro blocs** — dossiers, envoi/réception, CRC, NAK.
  Nibble seulement après NIBCOPY fer.

Une petite surcouche (DELETE, COPY, IMGFS, ATTR, OPEN) ne bouge que si
on doit la modifier : alors extraire un service partagé, mesurer au
lien. OPEN ne retombe pas à quelques octets.

## Mini — indépendante

[MINI-DOS33.md](docs/MINI-DOS33.md). Pas de remplacement sur place, ni de
copie ou de formatage à un seul lecteur.

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
