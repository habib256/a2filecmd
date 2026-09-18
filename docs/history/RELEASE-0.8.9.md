# Qualification de la 0.8.9

Publiée le 18 septembre 2026, tag `v0.8.9`. Elle apporte onze formats de
CiderPress II et d'AppleWorks, lus chacun avec son oracle hôte et son banc
POM2 : ARLEQUIN, MACPAINT, AWDATA, DiskCopy 4.2, UNWRAP, SCIIBIN, SHAPES,
les polices hi-res de FONTVIEW, BASLIST en Business BASIC, Magic Window
dans MDVIEW et UNSQ. Le détail est dans le [CHANGELOG](../../CHANGELOG.md).

Niveau de preuve : **qualifiée POM2** (harnais hôtes, fuzzers, bancs POM2
sur les deux CPU). Pas de qualification sur matériel réel de cette version
(voir TODO.md, lignes 💾).

## Le défaut que la rejoue a trouvé

`bench/dosimage.py` a refusé une image DOS 3.3 enfermée dans un `.2MG` :
« Not a ProDOS disk image (or DOS 3.3) ». La logique était juste, le code
produit ne l'était pas. Écrit juste après `if (copy_buf[0x0C] > 1)`,
l'énoncé `img_dsk = copy_buf[0x0C] == 0;` a été compilé par cc65 en
`cmp #$02 / bcs bad / jsr booleq` : le booléen était fabriqué avec les
indicateurs de la **première** comparaison, il signifiait donc « format
vaut 2 » et restait faux. Toute image en ordre DOS était lue en ordre
ProDOS.

La 0.8.8 reconstruite dans un arbre séparé passait 20/20 : la régression
venait bien de cette version, et le nouveau jeu de démonstration était
hors de cause. L'octet d'ordre est maintenant lu dans une variable et
testé une seule fois ; `tools/test_flag_reuse.py`, dans `make test`,
compile le résident dans les deux éditions et refuse tout `jsr boolXX`
dont les indicateurs viennent d'une comparaison déjà consommée par un
branchement.

## Validation locale

- `make test` : 41 suites, sans cas en échec, campagnes de mutation
  comprises ; `make test-mini` : 17 tests.
- `tools/check_images.py` : 7/7 images ; `release_notes.py --check-tag
  v0.8.9`. La disquette BOOT garde 12 blocs libres, comme en 0.8.8.
- Le job bancs de `ci.yml` rejoué commande par commande sur les images
  finales (l'exécuteur auto-hébergé n'existe pas, ce job est sauté sur
  GitHub) : 20 étapes sur 20, toutes vertes. Amorçage, complément 12/12,
  8/8 et 2/2, six 16/16, un lecteur 4/4, arbres 4/4, outils de blocs
  25/25, VOLINFO 22/22, FORMAT 36/36, images 20/20, BOOTBLK 11/11,
  DOSWRITE 17/17 en slots 6 et 5, images DOS 19/19 et 20/20, NIBCOPY 7/7
  et 7/7, sûreté des données 14/14, arbres 15/15, catalogues 5/5 et 6/6,
  grands répertoires 9/9, session complète 73/73, séquences 21/21, XL
  13/13, sessions XL 74/74 et 66/66, //c 20/20, surcouches 25/25 sur
  chaque CPU, pile 145 octets sur 192 (47 de marge).
- Les 25 bancs de surcouches comprennent les sept nouveaux : arlequin,
  awdata, diskcopy, macpaint, shapes, squeeze et wrappers, ajoutés à
  `bench/plugins.py` pour que la CI les joue aussi.
- Réserves au lien (6502/65C02) : MAIN 677/276, LC 26/34, OPEN 4/26,
  CATALOG 44/30.

## Publication

Images produites par la CI sur le tag ; la disquette
`A2FC-MINI-DOS33-0.8.9.dsk` est construite localement
(`make mini-disk MINI_MASTER=dist/A2FC-MINI-DOS33-0.8.8.dsk`) et jointe à
la main avec un `SHA256SUMS-0.8.9.txt` complété de sa ligne.
