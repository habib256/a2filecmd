# Qualification de la version 0.9.9

Date : 25 octobre 2026. Rapport associé à `v0.9.9`.

## Périmètre

Cette version ajoute DIRSORT, qui réordonne les entrées d'un répertoire
ProDOS sur le disque (issue #2), et refait l'affichage de TREE en
arborescence dans l'ordre du disque. DIRSORT écrit des blocs de répertoire
par WRITE_BLOCK : sa qualification porte d'abord sur la conservation des
données.

## Constructions et contrôles

- `make BOTH_EDITIONS=1 disk` puis `make xplugins ARCH=6502` : quatre images
  construites, gardes de disposition mémoire actifs. La 6502 est construite
  avec cc65 master `e11fb5c`, le commit que fixe la CI ; la 65C02 avec le
  cc65 de la machine.
- `python3 tools/check_images.py` : quatre images conformes. La 800K
  contient 99 surcouches et 174 blocs libres ; XL 6502 et enhanced
  contiennent chacune 130 surcouches et respectivement 60 024 et 60 026
  blocs libres.
- DIRSORT : 6 816 octets en 6502 (16 octets libres sous `$4000`), 6 681 en
  65C02 (151 libres).
- Manuel PDF régénéré : 25 pages, 12 signets.
- `make test` : 208 commandes, aucun échec, y compris le vrai C et
  l'assembleur des deux architectures.
- `release_notes.py --check-tag v0.9.9` conforme ; `SHA256SUMS-0.9.9.txt`
  vérifié pour les quatre images et le manuel.

## DIRSORT

- `tools/test_dirsort.py` :
  - 26 tests sur l'hôte, avec la BSS et les variables locales empoisonnées
    comme sur l'Apple II : tris, déplacements, sous-répertoires, refus,
    disque changé, erreurs de lecture, pannes d'écriture et de
    restauration, disque protégé, sous-répertoire verrouillé. Les octets
    de l'image sont comparés.
  - 6 tests du binaire cc65 des deux éditions sous sim65, y compris les
    stubs d'écran.
  - Un fuzz de 600 scénarios (volumes `mkvolume`, touches et pannes
    aléatoires, oracle `prodos_check.py`). Une campagne de 19 graines,
    soit 11 400 scénarios, n'a trouvé aucune violation.
- Deux chasses aux bugs indépendantes ont trouvé une variable non
  initialisée dans l'annulation (fausses alertes et écritures inutiles
  après un premier échec d'écriture). Le fuzz a trouvé une fausse alerte
  quand un périphérique écrit puis signale une erreur. Les deux sont
  corrigées et couvertes par des tests de régression.
- `bench/dirsort.py`, sur le vrai ProDOS 8 sous POM2, en 6502 (IIe non
  enhanced) et en 65C02 : 9/9 contrôles chacun.
  - DIRSORT déplace un sous-répertoire d'un bloc à l'autre et place
    B.SYSTEM avant A.SYSTEM.
  - ProDOS ajoute ensuite une treizième entrée au sous-répertoire déplacé,
    ce qui l'agrandit par le lien parent réécrit.
  - Le volume est sans constat pour `prodos_check.py`, chaque fichier est
    identique, et l'amorçage lance B.SYSTEM.

## Sessions POM2 ciblées

Treize bancs passent, sans scénario ignoré : `smoke`, `extras`, `six`,
`tree`, `tree_safety` et `dirsort` sur 6502 et 65C02, et
`menu:categories`, qui compte DIRSORT dans la catégorie Disks.

Ces résultats ne constituent pas un passage intégral de `make qualify` ;
les changements de la 0.9.9 sont couverts par les tests et les bancs
ci-dessus.

## Limites restantes

- La recette sur matériel physique reste à faire
  ([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md)).
- Une coupure de courant pendant les écritures de DIRSORT peut laisser une
  entrée en double ou absente : ProDOS ne fournit pas d'écriture atomique
  de plusieurs blocs. Le manuel conseille une sauvegarde avant de trier.
- DIRSORT traite au plus 4 blocs de répertoire (51 entrées).
