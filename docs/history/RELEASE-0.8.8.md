# Qualification de la 0.8.8

Publiée le 17 septembre 2026, tag `v0.8.8`. Elle apporte FIXIT et REPAIR
sur la disquette DISKTOOLS, et, dans la Mini DOS 3.3, le formatage d’une
disquette amorçable (F), l’entrelacement 2:1 sur tous les accès disque et
la reproduction de la Mini sur une disquette vierge. Le détail est dans le
[CHANGELOG](../../CHANGELOG.md).

Niveau de preuve : **qualifiée POM2** (harnais hôtes, fuzzers, bancs POM2
sur les deux CPU). Pas de qualification sur matériel réel de cette
version (voir TODO.md, lignes 💾).

## Validation locale

- `make test` : 947 tests hôtes dans 68 suites unittest, plus les
  campagnes de mutation (FIXIT/REPAIR, archives, images), sans cas en
  échec.
- `tools/check_images.py` : 7/7 images, avec la nouvelle garde de place
  pour `A2FILE.CFG` ; `release_notes.py --check-tag v0.8.8`.
- Le job bancs de `ci.yml` rejoué commande par commande sur les deux CPU
  (l’exécuteur auto-hébergé n’existe pas, ce job est sauté sur GitHub),
  sur les images finales : smoke, complément 2/2, six 16/16, un lecteur
  4/4, arbres 4/4, outils de blocs 25/25, VOLINFO 22/22, FORMAT 36/36,
  images 20/20, BOOTBLK 11/11, DOSWRITE 17/17 en slots 6 et 5, images DOS
  20/20, NIBCOPY 7/7, sûreté des données 14/14, arbres 15/15, catalogues
  5/5 et 6/6, grands répertoires 9/9, session complète 73/73, séquences
  21/21, XL 11/11, //c 20/20, surcouches 18/18 sur chaque CPU, budget de
  pile (145 octets sur 192).
- Nouveau : la session complète sur les deux XL publiées
  (`bench/run.py --xl`), 74/74 en 65C02 et 66/66 en 6502 (sans la souris).
  Sur les images finales, deux passages 65C02 ne sont pas allés au bout
  pour des raisons de banc : l’un est resté bloqué sur une requête HTTP à
  POM2 dans la section souris (A2FC affichait ses panneaux), l’autre a été
  coupé par le délai de 50 minutes au 52e contrôle, sans échec ; le passage
  sans délai a donné 74/74.
- VDrive 13/13 sur la BOOT publiée. Mini : sim65 et les six bancs POM2
  (`mini33`, `mini33_ops`, `mini33_write`, `mini33_review`, `mini33_brun`,
  `mini33_format`).
- Réserves au lien (65C02/6502) : MAIN 361/790, LC 34/26. BOOT et
  disquettes de banc à 3 blocs libres.

## Défaut trouvé pendant la qualification

Nommer FIXIT et REPAIR dans le menu avait fait passer la surcouche MENU
6502 de 11 octets au-delà d’un bloc : la BOOT n’avait plus que 2 blocs
libres. Sur une copie de la BOOT publiable, trois sorties de suite dans
POM2 l’ont montré : les préférences s’enregistraient une fois, puis
`A2FILE.TMP` obligeait ProDOS à étendre le dossier `A2FILE` plein avec le
dernier bloc libre, et chaque sortie suivante avertissait en gardant
l’ancien fichier (rien de perdu, mais plus rien d’enregistré). Deux
chaînes du menu ont été raccourcies (MENU 3595 → 3582 octets), la BOOT
retrouve ses 3 blocs, et `check_images.py` refuse désormais une image
amorçable qui n’a pas la place d’enregistrer `A2FILE.CFG` deux fois. Le
premier raccourcissement du titre avait retiré `the overlays`, que dix
bancs attendent : le rejeu l’a vu tout de suite, le titre le garde.

La disquette Mini de `dist/` précédait le commit du formatage ; elle a été
reconstruite (`make mini-disk` sur la disquette 0.8.7 comme maître) avant
les bancs.

## Publication

CI de `main` puis du tag : sept images, manuel et empreintes. La
disquette A2FileCmd Mini DOS3.3 est construite localement et jointe avec
`SHA256SUMS-0.8.8.txt` complété.
