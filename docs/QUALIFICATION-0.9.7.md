# Préparation de la version 0.9.7

Date : 12 octobre 2026. Version préparée localement sur `main`, sans tag ni
publication. Les sources comprennent les modifications locales des lecteurs.

## Paquet préparé

- `make -j4 all disk` : réussi pour les éditions 6502 et 65C02, avec les
  contrôles de disposition mémoire actifs.
- `tools/check_images.py` : quatre images conformes aux constructions.
  800K : 98 surcouches, 187 blocs libres ; XL 6502 : 129 surcouches,
  60 037 blocs libres ; XL enhanced : 129 surcouches, 60 042 blocs libres.
- Manuel anglais 0.9.7 : PDF régénéré, 25 pages et 12 signets. Version,
  références aux quatre images et nom du manifeste vérifiés dans le PDF.
  La capture de couverture conserve sa provenance 0.9.6.
- Notes de release : trois points, avec un lien vers le changelog détaillé.
  `release_notes.py --check-tag v0.9.7` et les huit tests des notes passent.
- `dist/SHA256SUMS-0.9.7.txt` : quatre images et PDF ; cinq empreintes vérifiées.

## Validation des lecteurs

Toutes les commandes de la cible `make test` ont été validées : **2 423
tests unittest dans 189 rapports**, plus les oracles, simulations et
campagnes de mutation intégrés. Après correction des échecs, la dernière
exécution complète a passé toutes les suites précédant Print Shop ; la
suite a repris à `test_printshop_extras.py` via une copie temporaire du
Makefile contenant les commandes restantes inchangées, et s'est terminée
avec le code 0. Journaux : `/tmp/a2fc-097-test.log` (préfixe réussi avant
Print Shop) et `/tmp/a2fc-097-test-remaining.log` (reprise réussie).

Les vérifications ont corrigé un arrêt prématuré de la détection S-C
Assembler qui masquait des panneaux Newsroom, l'affectation manquante de
DOSFONT dans l'inventaire historique et une initialisation périmée du banc
Print Shop. Le test `compress` exige l'exécution hors sandbox. Les images
et leurs empreintes ont été contrôlées à nouveau après les tests.

Les bancs POM2 ciblés suivants passent sur chaque processeur ; les essais
utilisent des images jetables et vérifient les données conservées :

| Lecteur | Contrôles par processeur |
| --- | ---: |
| AppleWorks | 66/66 |
| Epistole / DOCVIEW | 35/35 |
| Fantavision | 43/43 |
| Take 1 | 33/33 |
| Newsroom | 56/56 |
| Pixmaps / DGRVIEW | 137/137 |
| MovieMaker | 83/83 |

## Avant publication

Le rejeu intégral `make qualify` de cette version reste à exécuter ; les
bancs ciblés ci-dessus ne le remplacent pas. La recette sur matériel physique
reste également à faire ([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md)).
Les contrôles automatisés ne garantissent pas l'atomicité d'une écriture
physique ProDOS en cas de coupure.
