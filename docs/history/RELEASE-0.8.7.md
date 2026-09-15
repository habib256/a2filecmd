# Qualification de la 0.8.7

Publiée le 15 septembre 2026 depuis le commit `262060d`, tag `v0.8.7`. Elle
suit une chasse aux bugs sur tout le code : chaque défaut relevé a été
vérifié, corrigé avec un test qui échouait sur la 0.8.6, puis contrôlé sur
les deux CPU. Le détail est dans le [CHANGELOG](../../CHANGELOG.md).

## Validation locale

- `make test` : 731 tests hôtes dans 62 suites, dont le vrai cœur
  UNSHRINK, le pilote VDrive, le lanceur et la chaîne de page 3 sous sim65.
- `tools/check_images.py` : 7/7 images ; `release_notes.py --check-tag v0.8.7`.
- Le job bancs de `ci.yml` rejoué commande par commande sur les deux CPU
  (l’exécuteur auto-hébergé n’existe pas, ce job est sauté sur GitHub) :
  smoke, complément 2/2, six 16/16, arbres 4/4, outils de blocs 25/25,
  VOLINFO 22/22, FORMAT 36/36, images 20/20, BOOTBLK 11/11, DOSWRITE 17/17
  en slots 6 et 5, images DOS 20/20, NIBCOPY 7/7, sûreté des données 14/14,
  catalogues et grands répertoires, session complète 73/73, séquences
  21/21, XL 11/11, plugins 16/16 sur chaque CPU, budget de pile.
- VDrive 13/13 sur la BOOT publiée et les deux disquettes de banc ; Mini :
  sim65 26 + 57 et les trois bancs POM2 (`mini33_ops`, `mini33_write`,
  `mini33_review`).
- Réserves au lien (65C02/6502) : MAIN 361/790, LC 34/26. BOOT et
  disquettes de banc à 3 blocs libres, ce qu’il faut pour enregistrer
  `A2FILE.CFG` à la sortie.

## Bancs remis en état

Trois bancs étaient rouges sur la 0.8.6 publiée, pour des raisons de banc :
VOLINFO (course avant l’invite de disque, BOOT jamais remise, disquette de
banc sans VOLINFO), sûreté des données (W ne prend plus qu’un vrai nom
d’image) et budget de pile (le seuil « moitié » précédait la garde
`tree_stack_ok` des parcours non récursifs ; la copie profonde utilise 145
octets sur 192, 47 de marge, contrôle ramené à 32 octets de marge).

## Publication

CI de `main` puis du tag : sept images, manuel et empreintes. Les huit
empreintes de la CI (sept images et le manuel) sont identiques au lien local. La disquette
A2FileCmd Mini DOS3.3 est construite localement (`make mini-disk` sur la
disquette 0.8.6 comme maître) et jointe avec `SHA256SUMS-0.8.7.txt`
complété.

## Non refait

Pas de qualification sur matériel réel de cette révision. Le délai d’envoi
de VDrive (câble absent, CTS bas) n’est vérifié que sous sim65.
