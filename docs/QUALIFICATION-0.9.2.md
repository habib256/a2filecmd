# Qualification 0.9.2

État au 20 septembre 2026 : **qualification automatisée terminée, 100/100
scénarios validés au bilan consolidé, aucun ignoré**. La version 0.9.2 n'est
pas encore publiée. Les essais physiques restent à effectuer.

La première passe complète a terminé à **96/100 scénarios, aucun ignoré**.
Les quatre scénarios concernés par les corrections de banc passent après
relance. Ce bilan assemble la première passe et les relances ; ce n'est pas
une seconde exécution intégrale de `make qualify` devenue verte.

## Périmètre

`make qualify` couvre 100 scénarios dans 71 bancs, sur les deux architectures
et les cinq images. Les deux scénarios `plugins` exécutent chacun 31 bancs
d'extensions. Les essais d'écriture utilisent des images jetables ; le corpus
média externe est lu sans modification.

```sh
make qualify > /tmp/a2fc-qualify-0.9.2.log 2>&1
```

Les scénarios sont exécutés un par un pour éviter que la concurrence entre
émulateurs ne fausse les délais des tests. Les journaux détaillés sont dans
`build/bench/`, avec les sous-répertoires `plugins-6502/` et `plugins-enh/`.

## Mise à jour des bancs de session

La première passe a rencontré trois attentes périmées et une image de test
trop petite :

- `run:enh` cherchait encore le titre d'aide de la version 0.7. Le banc
  vérifie désormais le titre actuel, le renvoi vers RECOVER et le libellé
  de retour aux panneaux.
- `run:xl-6502` et `run:xl-65c02` reconstruisaient les XL dans l'ancien ordre
  alphabétique. Leur reconstruction utilise maintenant `--a2fc-layout`, comme
  la distribution. La comparaison octet par octet avec chacune des deux XL
  est conservée et réussit.
- `move:entries` dépassait les 1 000 blocs de son image jetable avant même
  de lancer POM2. Le volume de test passe à 1 600 blocs pour contenir la
  distribution et les fichiers d'essai. Le répertoire cible conserve ses
  12 entrées : il doit toujours gagner un bloc pendant le déplacement.

Ces corrections touchent uniquement le banc : elles ne changent ni le code
natif, ni les images, ni les délais et exigences des opérations testées.
Les trois sessions complètes et MOVE ont été rejoués avec succès après la
première passe.

## Résultats et preuves

| Vérification | Résultat |
| --- | --- |
| `make test` sur le code natif final | 1 168 tests, 111 suites ; fuzz intégré réussi |
| Inventaire POM2 consolidé | 100/100 scénarios, correspondance exacte avec `bench/all.py`, aucun ignoré |
| Relances | 4/4 scénarios |
| Sessions enhanced / XL 6502 / XL enhanced | 73/73, 66/66 et 74/74 contrôles |
| MOVE, relance | 13/13 contrôles |
| Campagne ciblée de performance et sécurité | 22/22 scénarios POM2 |
| Extractions ProDOS et DOS | 4/4 scénarios POM2 |
| Récupération, deux CPU | 2/2 scénarios, 14/14 contrôles avec comparaison des octets |
| Extensions, campagne complète | 31/31 bancs par CPU |
| Corpus média | 118/118 contrôles |
| DOS3.3 | 7/7 scénarios |
| `tools/check_images.py` | 5/5 images conformes aux binaires et inventaires |
| Audit ProDOS en lecture seule | 4/4 volumes, parcours complets, aucun constat |
| Disposition mémoire au lien | Deux CPU valides, aucun plafond relevé |
| Pile C, `memory:stack` | 145/192 octets utilisés, 47 de marge sur les parcours testés |
| Manuel | 11 pages, 12 entrées de sommaire ; DOS3.3 en premier et captures 0.9.2 |
| Sommes SHA-256 | Cinq images et manuel conformes au manifeste |

Les [mesures de performance](PERFORMANCE-0.9.2.md) décrivent le protocole et
ses limites. Les sommes des livrables sont dans `dist/SHA256SUMS-0.9.2.txt`.

Commande de relance :

```sh
python3 bench/all.py --only run:enh run:xl-6502 run:xl-65c02 move:entries \
  --strict --jobs 1 --out build/qualification-0.9.2/rechecks
```

`build/qualification-0.9.2/` conserve les journaux des deux passes, les
sous-bancs d'extensions, les tests hôte, les dispositions mémoire, les audits
de volumes et les mesures de vitesse. `results.json` associe chacun des
100 scénarios à son dernier verdict et à son journal. Les empreintes des
sources et des symboles sont dans `source-sha256.json`, celles des livrables
dans une copie du manifeste. Ces preuves locales disparaissent avec un
nettoyage de build.

## Limites avant la 1.0

- La [recette sur matériel](HARDWARE-CHECKLIST.md) reste à faire. POM2 ne
  remplace pas les essais sur Apple II, lecteurs et cartes réels.
- MAIN enhanced conserve seulement **83 octets libres**, sous l'objectif
  de confort de 256 ; MAIN 6502 en conserve 491. Les contrôles de disposition
  restent actifs. Carte langage : 66/57 octets libres ; écart avant pile :
  111/708 octets (enhanced/6502).
- Les grands catalogues relisent encore les blocs précédant la page. Aucun
  cache persistant n'a été ajouté. Les pauses des appels disque bloquants
  restent à mesurer sur matériel à 1 MHz.
- Les tests de panne et comparaisons d'octets ne garantissent pas l'atomicité
  d'une écriture physique ProDOS lors d'une coupure d'alimentation.
