# A2 File Cmd — feuille de route

[0.8.9](https://github.com/habib256/a2filecmd/releases/tag/v0.8.9)
([CHANGELOG](CHANGELOG.md)). Mini (II+ 48 Ko, DOS 3.3) et ProDOS
(IIe 128 Ko), même numéro. `make mini` ne partage pas `src/a2fc.c`.

Préserver les données prime. Ne pas relever les plafonds
([MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md)) ; MAIN 65C02 ≥ 256 octets
(466 depuis la passe du 18 septembre). **💾** = lecteurs physiques.

Deux niveaux de preuve : **qualifié POM2** et **qualifié sur matériel**.
Un chantier se ferme au premier ; le fer reste ouvert à part, sans
bloquer le reste — mais c’est lui, maintenant.

## Maintenant : le fer 💾

POM2 ne remplace pas le lecteur. La marche à suivre, les images d'essai et
ce que chaque écran doit montrer :
[HARDWARE-CHECKLIST.md](docs/HARDWARE-CHECKLIST.md) et
`python3 tools/hw_media.py --out dist/hw`.

- [ ] **Mini sur II+** — déjà un défaut d’écran vu sur machine ; le reste
  des écritures n’est pas qualifié.
- [ ] **DOSWRITE** sur disque réel.
- [ ] **FIXIT/REPAIR en AUX** — volume > 4 096 blocs, vrai IIe et //c,
  `/RAM` relu après.
- [ ] **REPAIR** sur une disquette réellement abîmée.
- [ ] **IIgs** — premier boot (SmartPort, `$C000`) ; documenter Disk II.

Puis **un seul** : NIBCOPY (IIe et //c, un et deux lecteurs, 300 tr/min
et accélérateur ; ensuite reprise de piste **ou** `.NIB`, pas les deux,
pas de 3½ avant) **ou** ADTPro blocs (dossiers, CRC, NAK).

## Formats — seulement s’il reste des octets

OPEN a 4 octets en 6502, UNSHRINK ~900, SHAPES est plein. Un format
nouveau n’entre que s’il tient sans relever un plafond, avec oracle hôte
et banc POM2. Inventaire CiderPress II du 17 septembre 2026 :

- [ ] Routage Retour `.QQ` / `.ACU` / `.BA3` — d’abord de la place dans
  OPEN.
- [ ] Squeeze et LZC dans UNSHRINK (NuFX 1, 4, 5).
- [ ] AppleWriter / Merlin (textes à bit haut).
- [ ] Bordures Print Shop, Beagle Compress — pas de spec, laisser.

Hors de portée : Teach (fichiers étendus), a2dgrx (pas de fichier propre).
Faits le 17 : ARLEQUIN, MACPAINT, AWDATA, DiskCopy, UNWRAP, SCIIBIN,
SHAPES, FONTVIEW hi-res, BASLIST, Magic Window, UNSQ.

Pas maintenant : Pascal/CP/M, écriture dans une image, DOS33W
(suppression / renommage / remplacement). Ce sont des chemins d’écriture
neufs, pas des lecteurs.

Une petite surcouche (DELETE, COPY, IMGFS, ATTR, OPEN) ne bouge que si
on doit la modifier : extraire un service, mesurer au lien.

## Plus tard

Favoris de programmes. Médias (PT3 sous pression, Fantavision, ANIMATE).
Disques (journal de coupure sans promettre l’atomicité, DISKIMG, VERIFY,
DIRSORT, BACKUP, images montées, SHRINK). Transferts (XMODEM, VDrive
après ADTPro, TFTP). Confort (DATE, TAGPAT, PASSWORD…). Corpus :
`GISTDATA.hdv`, [SAMPLE-MEDIA.md](docs/SAMPLE-MEDIA.md).

Clos (CHANGELOG) : contrat d’écriture, séquences, FIXIT/REPAIR, Mini
entrelacement et relecture, Commander, grille des tableurs AppleWorks.

## Livraison

[AGENTS.md](AGENTS.md). `/RAM` : confirmer **avant**. Jetables pour les
essais destructifs. Deux CPU. Avant release : `make test`, `make qualify`
(toute la table de `bench/all.py`, `--strict`), `tools/check_images.py`.
