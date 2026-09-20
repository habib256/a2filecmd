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
Ces campagnes ne remplacent pas la qualification complète avant release.

Le guide RECOVER et l’aide occupent 10 blocs supplémentaires sur 140K,
qui conserve 22 blocs libres. La version DOS 3.3 n’a pas reçu ces changements
ProDOS. La préservation des originaux et les vérifications de copie restent
prioritaires ; aucune garantie d’atomicité physique n’est ajoutée.

## Reproduire

Conserver ensemble l’image et le fichier `.lbl` de chaque version :

```sh
python3 tools/measure_startup.py \
  --disk dist/A2FILECMD-140K-0.9.2.po \
  --labels build-6502/a2fc.lbl --out /tmp/a2fc-startup.json
```

Le banc demande une compilation POM2 avec `libpom2_core_test.a`, par
défaut dans `~/src/pom2/build`. `--pom2-root` permet un autre emplacement.
