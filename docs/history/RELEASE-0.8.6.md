# Qualification de la 0.8.6

Publiée le 14 septembre 2026 depuis le commit `40ce339`, tag `v0.8.6`. Elle
clôt la partie Commander de la feuille de route : dossiers marqués et
sélectionnés déplacés entre volumes, parcours d’arbres sans récursion,
retour depuis BASIC épelé, surcouche CATALOG, VOLNAME sur DISKTOOLS.

## Validation locale

- `make test` : 653 tests hôtes dans 72 suites.
- `tools/check_images.py` : 7/7 images ; `release_notes.py --check-tag v0.8.6`.
- POM2, sur les deux CPU, avec l’hôte de banc corrigé le 14 septembre
  (écriture différée du disque dur activée et vidée à l’arrêt : les
  comparaisons d’octets du `.hdv` sont réelles pour la première fois) :
  déplacement marqué 37/37, arbres 15/15, catalogue 6/6, catalogues
  malformés 5/5, sûreté des données 14/14, six 16/16, images DOS 19/19 et
  20/20, XL 11/11, grands répertoires 9/9, complément 12/12, 8/8 et 2/2,
  GOTO 53/53, lot sans point d’entrée 3/3, smoke ; session complète 73/73,
  retour depuis BASIC.SYSTEM compris.
- Réserves au lien (65C02/6502) : MAIN 299/742 ; BOOT à 4 blocs libres.

## Publication

CI de `main` puis du tag : sept images, manuel et empreintes. La disquette
A2FileCmd Mini DOS3.3 est construite localement (`make mini-disk` sur la
disquette 0.8.5 comme maître) et jointe avec `SHA256SUMS-0.8.6.txt`
complété ; les huit empreintes de la CI sont identiques au lien local.

## Après le tag

Le manuel PDF de la release a été remplacé après le tag (commit qui suit
`40ce339`) : A2FileCmd Mini DOS3.3 y a sa propre section, séparée de
l’édition ProDOS ; `SHA256SUMS-0.8.6.txt` a été régénéré en conséquence.

## Non refait

Les bancs de `bench/plugins.py` hors GOTO n’ont pas été relus contre les
messages actuels ; pas de qualification sur matériel réel de cette révision.
