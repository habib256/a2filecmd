# Qualification 0.9.1

État au 20 septembre 2026 : **qualification automatisée terminée, 98/98
scénarios validés au bilan consolidé, aucun ignoré**. Essais physiques restant
à effectuer ; qualification de la release 0.9.1.

La première passe complète a terminé à **91/98**. Après corrections, les
24 scénarios de relance et les 2 scénarios MB4c passent. Ce bilan assemble
la passe complète et les relances ; ce n’est pas une seconde exécution
intégrale de `make qualify` devenue verte.

## Périmètre

`make qualify` : 98 scénarios dans 70 bancs, deux architectures, cinq images.
Les scénarios `plugins` exécutent chacun 31 bancs d'extensions. Les essais
d'écriture portent sur des images jetables ; le corpus externe est lu sans
modification. Cette qualification POM2 ne remplace pas la matrice matérielle.

Commande de première passe :

```sh
make qualify > /tmp/a2fc-qualify-0.9.1.log 2>&1
```

Journaux par scénario : `build/bench/`. Journaux des extensions :
`build/bench/plugins-6502/` et `build/bench/plugins-enh/`.

## Corrections des bancs

- VOLINFO : le banc 6502 attendait encore BOOT + DISKTOOLS. Les deux CPU
  utilisent désormais une image autonome jetable contenant leur VOLINFO.
  Les contrôles d'intégrité des volumes, de mémoire et de diagnostic restent.
- Menu : la liste explicite de la catégorie Disks omettait CPM, CPMW,
  DOS33W, DOSREPL, IMGPUT, PASCAL et PASCALW. Les contrôles de noms, nombre,
  ordre, pagination et retours restent actifs.
- Sessions : l'assertion de création de dossier doit chercher `NEUF/`,
  conformément à l'affichage actuel, et conserver la vérification `<DIR>`.
- Cadence du pilote : après le test musical `1x`, restaurer le budget initial
  `p.speed`, plutôt que `max`, qui ralentit les requêtes de contrôle. La
  première session `run:enh` a été interrompue proprement après 920 secondes
  puis a été rejouée entièrement avec succès. Les assertions et délais ne sont pas
  assouplis. Même correction de restauration dans sequences, formats et media.

Ces corrections des bancs ne modifient pas les opérations sur les données.

## Correction native : Mockingboard 4c

La première passe a révélé un défaut réel sur les deux CPU : le probe lisait
les timers avant toute écriture, alors que la carte dort derrière la ROM du
//c jusqu’à une écriture dans sa fenêtre. La correction expose temporairement
la ROM pour identifier le //c, écrit zéro dans DDRA `$C403` (entrées), puis
restaure la carte langage avant de revenir au programme.

La carte réveillée peut masquer la ROM souris `$C400`. Sur enhanced, le
programme cesse alors d’appeler cette ROM et conserve la navigation clavier.
Sans carte, la ROM reste visible et la souris reste disponible. Le manuel
explicite cette limite. Référence indépendante du comportement matériel :
[MAME, apple2e.cpp, c400_w / c400_int_r](https://github.com/mamedev/mame/blob/master/src/mame/apple/apple2e.cpp).

Écritures de la correction : DDRA de la carte et, sur enhanced si sa ROM est
masquée, l’indicateur souris en MAIN. Les lectures des commutateurs de carte
langage changent son mappage, sans modifier son contenu. Aucune écriture AUX
ou disque. Le probe de timer reste obligatoire avant d’accepter une carte.

Le nouveau test exécute le vrai assembleur sous sim6502 et sim65c02 : absence
de carte, signatures ROM //c et autres machines, écritures limitées à la bonne
adresse, préservation de la souris sans carte. POM2 couvre les timers émulés,
les sorties AY, pause, sortie, fin naturelle, et compare AUX et volume source
octet par octet. Le pilote MB4c restaure aussi la cadence de navigation et
revient à 1 MHz avant la relecture, pour observer le lecteur avant sa fin.

## Résultats et reproduction

| Vérification | Résultat |
| --- | --- |
| `make test` sur la correction finale | 1 162 tests, 111 suites unittest ; contrôles autonomes également réussis |
| Inventaire POM2 consolidé | 98/98 scénarios, correspondance exacte avec `bench/all.py`, 0 ignoré |
| Extensions, première passe | 31/31 bancs par CPU |
| Corpus média, première passe | 118/118 contrôles |
| Relances des scénarios corrigés et affectés | 24/24 |
| MB4c, relance finale | 2/2 ; par CPU, 7 contrôles sans carte et 15 avec carte |
| Sessions complètes enhanced / XL 6502 / XL enhanced | 73/73, 66/66, 74/74 contrôles |
| `tools/check_images.py` | 5/5 images conformes à leurs binaires et inventaires |
| Audit ProDOS en lecture seule | 4/4 volumes, parcours complet, aucun constat |
| Disposition mémoire au lien | Deux CPU valides, aucun plafond modifié |
| Pile C, banc `memory:stack` | 145/192 octets utilisés ; 47 de marge sur les parcours testés |
| Manuel et sommes SHA-256 | PDF régénéré ; cinq images et manuel vérifiés |

Relances effectuées :

```sh
make test
python3 bench/all.py --only volinfo menu run smoke extras machine iic memory data_safety overlay_load music pt3 pt3_dual pt3_large media sequences duet --strict --out /tmp/a2fc-qualification-rechecks
python3 bench/all.py --only mb4c --strict --out /tmp/a2fc-qualify-mb4c
python3 tools/check_images.py
```

Les journaux des relances, des tests hôte et du lien final sont conservés dans
`build/qualification-0.9.1/`. Son `results.json` associe chacun des 98 scénarios
à son dernier verdict et à son journal ; les journaux initiaux restent dans
`build/bench/`. Ces preuves locales disparaissent avec un nettoyage de build.
Les sommes des livrables sont dans `dist/SHA256SUMS-0.9.1.txt`.

## Limites et passage vers la 1.0

- La [recette sur matériel](HARDWARE-CHECKLIST.md) reste à faire : Apple II+
  DOS 3.3, IIe, //c, IIgs, vrais lecteurs et carte MB4c. Aucun de ces essais
  physiques n’a été effectué pendant cette qualification.
- MAIN enhanced : **91 octets libres**, sous l’objectif de confort de 256.
  Carte langage : 66/57 octets ; écart avant pile : 119/711 octets
  (enhanced/6502). Les contrôles passent, mais ces réserves limitent les ajouts.
- Les indicateurs d’activité ne peuvent pas avancer pendant un appel disque
  bloquant. Mesurer encore les pauses à 1 MHz sur vrais supports.
- Les comparaisons d’octets et tests de panne ne garantissent pas l’atomicité
  d’une écriture physique ProDOS lors d’une coupure d’alimentation.
