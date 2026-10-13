# Qualification de la version 0.9.7

Date : 13 octobre 2026. Rapport associé à la version `v0.9.7`.
Qualification automatisée achevée après un passage complet et des reprises ciblées.

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

La [CI du code natif final, commit 24dc327](https://github.com/habib256/a2filecmd/actions/runs/38368937710)
est verte : cible `make test` complète, constructions 6502 et 65C02,
gardes mémoire et contrôles des quatre images. Les corpus externes absents
sur GitHub sont explicitement distingués des tests synthétiques, erreurs
d'E/S et contrôles de préservation qui restent obligatoires.

Les vérifications ont notamment corrigé le repli booléen OPEN, la détection
VisiCalc avec bit haut et colonnes à deux lettres, ainsi que la conservation
des résultats VOLNAME. La relecture de ses panneaux est différée jusqu'au
retour de la surcouche pour éviter l'écrasement de ses DATA/BSS.
Les essais du vrai C et de l'assembleur
contrôlent aussi les sources, volumes et préfixes conservés.
Les détails et limites mémoire figurent dans [MEMORY-BUDGETS.md](MEMORY-BUDGETS.md).

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

## Qualification complète et reprises

Le passage intégral `make qualify` a exécuté **169 scénarios, sans aucun
scénario ignoré**. Son premier résultat était **147/169**, avec un retour
non nul. Les 22 échecs ont été examinés et rejoués après correction :
la couverture finale est **169/169**, sans échec restant. Ce résultat
combine le passage complet et les reprises ; il ne décrit pas un premier
passage intégral réussi.

Les deux groupes d'outils atteignent **39/39 bancs par processeur** après
reprise. VisiCalc passe 49/49 contrôles, VOLNAME 20/20, DOS MCS 49/49,
les lecteurs V1 37/37 et MovieMaker 83/83 sur chaque architecture.
Les sessions finales passent 73 contrôles sur la disquette enhanced,
66 sur XL 6502 et 74 sur XL 65C02.

Les corrections natives après le passage complet ne modifient que
IDFORMATS et VOLNAME sur chaque CPU : **258 des 262 binaires restent
identiques**. Les quatre binaires modifiés ont leurs tests C/assembleur
et leurs reprises POM2 sur les deux CPU. Les **262 binaires finaux**
correspondent octet par octet à la construction isolée utilisée pour ces
reprises ; les quatre images sont relues et leurs empreintes régénérées.

Les preuves locales sont conservées sous `build/bench/` : journaux du
passage complet, `retry-097/`, `final-097/`, journaux `*-final.log`,
`run-enh-last.log` et `qualification-0.9.7-audit.json`. L'audit recoupe
la table des 169 scénarios et l'inventaire des 39 outils.

## Limites restantes

La recette sur matériel physique
reste également à faire ([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md)).
Les contrôles automatisés ne garantissent pas l'atomicité d'une écriture
physique ProDOS en cas de coupure.
