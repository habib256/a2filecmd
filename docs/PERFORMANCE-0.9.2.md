# Mesures de la préparation 0.9.2

Comparaison avec les binaires publiés en 0.9.1, le 20 septembre 2026.
POM2, Apple IIe non enhanced, NMOS 6502, Disk II ; copies jetables des
images 140K, écriture désactivée. Ce sont des cycles émulés, pas des
chronométrages sur matériel physique ni des mesures de toutes les éditions.

| Action | Cycles 0.9.1 | Cycles 0.9.2 | Réduction |
| --- | ---: | ---: | ---: |
| Démarrage jusqu’aux panneaux prêts | 32 713 892 | 26 489 912 | 19,0 % |
| Premier déplacement du curseur | 77 673 | 68 803 | 11,4 % |
| Première ouverture de A2FILE | 3 557 976 | 3 474 565 | 2,3 % |
| Curseur, moyenne de 17 déplacements | 146 574 | 125 216 | 14,6 % |
| Défilement, moyenne de 3 déplacements | 702 609 | 554 301 | 21,1 % |

À 1 MHz nominal, le démarrage correspond à 32,714 → 26,490 secondes.
Le banc arrête chaque mesure au retour à la lecture clavier, après le
dessin des panneaux. Il conserve les échantillons et les empreintes SHA256
de l’image et des symboles dans son JSON. Une exécution déterministe par
version ; les moyennes représentent des actions différentes, pas une
distribution statistique d’essais matériels.

## Les cinq pistes

1. Construction des images : PRODOS, lanceur, puis répertoire A2FILE ;
   NAV, OPEN et MENU précèdent CODE et les autres outils fréquents.
   Le générateur conserve son ordre alphabétique par défaut pour les autres
   usages. Les tests comparent contenus, métadonnées et espace alloué.
2. Affichage : remplacement des formats génériques par des routines natives
   pour les libellés et le comptage des tags. Tests du véritable assembleur
   sur les deux CPU, sans écriture AUX ni modification des sélections.
3. Chargeur : lectures de 8192 octets au lieu de 1024 directement dans la
   destination, sans nouveau tampon et avec les mêmes bornes mémoire.
4. Catalogues : les entrées précédant la page restent lues et validées,
   mais leurs métadonnées ne sont plus décodées. Un index de blocs reste à
   concevoir avec une invalidation sûre lors des changements de disque.
   Préparation 1.0 : les blocs entièrement avant la page sont désormais
   comptés sans valider les noms ; l'index a été mesuré et écarté (voir
   plus bas).
5. Extraction d’images : un comptage des tags par opération au lieu d’un
   comptage par entrée. Le prototype de réutilisation des informations de
   volume a été abandonné pour son coût mémoire. Aucun cache persistant.

## Validation et coûts

Les deux builds passent les contrôles de disposition sans relever les
plafonds. MAIN enhanced reste serré : 83 octets libres, objectif 256 encore
ouvert. Voir [les budgets](MEMORY-BUDGETS.md).

La campagne ciblée couvre démarrage, panneaux, grands catalogues, erreurs
de lecture, opérations, mémoire et chargement : 22/22 scénarios POM2.
Les extractions ProDOS/DOS passent 4/4 scénarios supplémentaires.
Le banc `recovery` vérifie séparément l’aide et la récupération sur les
deux CPU, avec comparaison des octets après fermeture de l’émulateur.
Résultat : 2/2 scénarios, 14/14 contrôles. La suite hôte finale `make test`
passe : 1 168 tests dans 111 suites, plus les campagnes de fuzz intégrées.
La [qualification automatisée complète](QUALIFICATION-0.9.2.md) est également
terminée : 100/100 scénarios au bilan consolidé, aucun ignoré. Les essais
sur matériel physique restent à effectuer.

Le guide RECOVER et l’aide occupent 10 blocs supplémentaires sur 140K,
qui conserve 22 blocs libres. La version DOS 3.3 n’a pas reçu ces changements
ProDOS. La préservation des originaux et les vérifications de copie restent
prioritaires ; aucune garantie d’atomicité physique n’est ajoutée.

## Pagination des grands catalogues (1.0)

Mesure du 26 septembre 2026 : `tools/measure_paging.py`, POM2, carte HDV
du slot 5 sans écriture, répertoires de 300, 700 et 1 500 fichiers. La
build 6502 tourne sur un IIe non enhanced (NMOS), la build 65C02 sur un IIe
enhanced. Chaque valeur est le coût de la touche qui charge une fenêtre,
jusqu'au retour à la lecture clavier (dessin compris).

| Mesure | 6502 avant | 6502 après | 65C02 avant | 65C02 après |
| --- | ---: | ---: | ---: | ---: |
| Coût d'une fenêtre sautée (139 entrées) | 431 000 | 247 000 | 485 000 | 246 000 |
| 700 entrées, dernière page | 2 774 556 | 1 885 361 | 3 013 706 | 1 860 042 |
| 700 entrées, de la page 0 à la dernière | 14 002 528 | 11 389 105 | 15 050 652 | 11 652 691 |
| 1 500 entrées, dernière page | 5 835 766 | 4 023 462 | 6 419 278 | 4 066 927 |
| 1 500 entrées, de la page 0 à la dernière | 40 783 739 | 30 974 315 | 44 397 078 | 31 653 954 |
| Ouverture (fenêtre 0) | 1 689 307 | 1 689 965 | 1 758 597 | 1 757 593 |

À 1 MHz, la dernière page de 700 entrées passe de 2,8 à 1,9 s (6502) et de
3,0 à 1,9 s (65C02) ; celle de 1 500 entrées de 5,8 à 4,0 s et de 6,4 à
4,1 s. Ce qui reste par fenêtre sautée est la lecture des blocs par ProDOS
(environ 23 000 cycles par bloc de 13 entrées sur cette carte) ; valider
les noms en C y ajoutait environ 75 %.

Le prototype d'index (points de reprise par fenêtre, SET_MARK puis
vérification du bloc repris) descendait à ~70 000 cycles par fenêtre
sautée : 2 447 162 pour la dernière page de 1 500 entrées en 6502. SET_MARK
sur un répertoire fait suivre la chaîne des blocs à ProDOS, donc la lecture
n'était pas évitée, seulement la copie. Il coûtait 488 octets MAIN même en
assembleur (6 libres en 65C02) et un état à invalider ; il n'est pas livré
(voir [les budgets](MEMORY-BUDGETS.md)). Sur un lecteur 3,5 pouces ou une
Disk II réels, dominés par les accès disque, ni l'un ni l'autre ne
supprime ces lectures : le gain y est moindre que sur la carte HDV, et n'a
pas été mesuré sur matériel.

La même mesure a révélé une erreur de la build 65C02 : Haut ou Gauche près
du haut d'une fenêtre qui en a une suivante chargeait cette suivante
(comparaison signée compilée non signée par cc65 2.19). `move_cursor` teste
désormais le signe d'abord ; `measure_paging.py` signale tout saut dans le
mauvais sens.

```sh
A2FC_BUILD=build-6502 python3 tools/measure_paging.py --out /tmp/p6502.json
A2FC_BUILD=build python3 tools/measure_paging.py --out /tmp/p65c02.json
```

## Reproduire

Conserver ensemble l’image et le fichier `.lbl` de chaque version :

```sh
python3 tools/measure_startup.py \
  --disk dist/A2FILECMD-140K-0.9.2.po \
  --labels build-6502/a2fc.lbl --out /tmp/a2fc-startup.json
```

Le banc demande une compilation POM2 avec `libpom2_core_test.a`, par
défaut dans `~/src/pom2/build`. `--pom2-root` permet un autre emplacement.
