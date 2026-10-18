# Qualification de la version 0.9.8

Date : 18 octobre 2026. Rapport associé à `v0.9.8`.

## Périmètre

Cette version reprend les deux corrections depuis 0.9.7 : la reconnaissance
des textes S-C Assembler contenant des répétitions d'un caractère de contrôle,
et l'aiguillage de Return par IDENT, y compris pour les programmes SYS,
Applesoft et Integer BASIC. Les tests vérifient aussi les formats ambigus,
les erreurs d'E/S et la conservation des octets source.

## Constructions et contrôles

- `make -j4 disk` : quatre images construites pour les éditions 6502,
  65C02 enhanced et DOS 3.3 ; gardes de disposition mémoire actifs.
- `python3 tools/check_images.py` : quatre images conformes. La 800K contient
  98 surcouches et 190 blocs libres ; XL 6502 et enhanced contiennent
  chacune 129 surcouches et respectivement 60 040 et 60 042 blocs libres.
- Manuel PDF régénéré à partir de la version 0.9.8 du guide : 25 pages,
  12 signets. La capture de couverture conserve sa provenance 0.9.6.
- `make test` : réussi hors bac à sable, y compris les tests du vrai C et de
  l'assembleur sur les deux architectures. Les régressions spécifiques
  `test_retrotext.py` (13 tests), `test_merlin_ident.py` (19 tests) et
  `test_format_repair.py` (13 tests) passent aussi séparément. Certains tests
  facultatifs de corpus externe restent ignorés par cette cible ; les neuf
  bancs POM2 ciblés ci-dessous n'ont aucun scénario ignoré.
- `release_notes.py --check-tag v0.9.8` : version du tag conforme à la
  construction. `SHA256SUMS-0.9.8.txt` vérifié pour les quatre images et
  le manuel PDF.

## Sessions POM2 ciblées

Les bancs utilisent des images jetables. La session `run:enh` passe 73/73
contrôles et `run:xl-6502` passe 66/66 contrôles, dont l'ouverture et
l'exécution confirmée d'un programme Applesoft par Return. Le banc
`formats:repair` passe et préserve les sources de ses opérations.
Les neuf bancs ciblés passent finalement, sans scénario ignoré :
`formats:repair`, puis `dosint`, `dosbas`, `dosscasm` et `retrotext` sur
6502 et 65C02. Les listings sont relus ; les sources DOS, le volume ProDOS,
AUX et le plancher de pile restent inchangés selon le banc. Chacun des deux
bancs `retrotext` passe 15/15 contrôles.

Le premier passage de `retrotext` attendait encore qu'un fichier S-C
tronqué soit automatiquement routé vers SCASM. IDENT l'écarte désormais
avant ce routage, conformément à son contrôle de structure. Le banc a été
mis à jour pour forcer SCASM par le menu et constater son refus du fichier
tronqué ; ses deux reprises passent et conservent les octets du volume.

Ces résultats ne constituent pas un nouveau passage intégral des 169 scénarios
de qualification de la 0.9.7 ; les corrections 0.9.8 sont couvertes par les
tests ciblés et la construction des quatre images.

## Limites restantes

La recette sur matériel physique reste à faire
([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md)). Les contrôles automatisés
ne garantissent pas l'atomicité d'une écriture physique ProDOS en cas de coupure.
