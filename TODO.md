# A2 File Cmd — feuille de route

[0.9.0](https://github.com/habib256/a2filecmd/releases/tag/v0.9.0)
([CHANGELOG](CHANGELOG.md)). Mini (II+ 48 Ko, DOS 3.3) et ProDOS
(IIe 128 Ko), même numéro. `make mini` ne partage pas `src/a2fc.c`.

Préserver les données prime ([AGENTS.md](AGENTS.md)). Ne pas relever
les plafonds ([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)). Un chantier
se ferme avec un oracle hôte et un banc POM2.

## Formats — seulement s’il reste des octets

OPEN a 28 octets en 6502 (43 en 65C02), UNSHRINK ~900, SHAPES est plein.
Un format nouveau n’entre que s’il tient sans relever un plafond.

- [ ] **LZC 12 bits dans UNSHRINK** (NuFX 4, et 5 quand l’en-tête dit
  ≤ 12 bits). `tools/lzc_ref.py` est écrit et dans `make test`. Le cœur
  actuel tient en `$1B00–$1F59`, PREFIX commence à `$2000` — 166 octets
  de marge —, donc le décodeur LZC est un second cœur, stocké ailleurs
  dans la surcouche et recopié en AUX `$1B00` selon le format du thread.
- [ ] AppleWriter / Merlin (textes à bit haut).

Laissé, pas de spec : bordures Print Shop, Beagle Compress.
Hors de portée : NuFX 5 en 16 bits (192 Ko de tables, 128 Ko de machine),
NuFX 1 Squeeze (jamais servi ; UNSQ lit le Squeeze autonome), Teach
(fichiers étendus), a2dgrx (pas de fichier propre).

Une petite surcouche (DELETE, COPY, IMGFS, ATTR, OPEN) ne bouge que si
on doit la modifier : extraire un service, mesurer au lien.

## Limites qui restent

- **CPMW** : un extent, 16 Ko — la fenêtre, pas la sûreté. Volume vide
  refusé (l’ordre des secteurs ne se mesure pas sans répertoire).
- **CPM** : `CPAM40B.dsk` et `CPM.DSK` refusés, répertoire ailleurs.
  À éclaircir si quelqu’un en a besoin.
- **PASCALW** : pas de Krunch. Un trou au milieu refuse ; le filer
  ramène la place au bout.
- **IMGPUT** : pas de fichier tree (> 128 Ko), pas d’extension de
  répertoire.

## Plus tard

Favoris de programmes. Médias (PT3 sous pression, Fantavision, ANIMATE).
Disques (journal de coupure sans promettre l’atomicité, DIRSORT, BACKUP,
SHRINK). NIBCOPY : reprise de piste **ou** `.NIB`, pas les deux, pas de
3½ avant. Transferts (XMODEM, ADTPro blocs — dossiers, CRC, NAK —, TFTP).
PASSWORD. Corpus : `GISTDATA.hdv`, [SAMPLE-MEDIA.md](docs/SAMPLE-MEDIA.md).
CPMW à plusieurs extents si la fenêtre se libère.

## Livraison

`/RAM` : confirmer **avant**. Jetables pour les essais destructifs.
Deux CPU. Avant release : `make test`, `make qualify` (toute la table
de `bench/all.py`, `--strict`), `tools/check_images.py`.
