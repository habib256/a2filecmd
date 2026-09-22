# Qualification 0.9.3

Date : 22 septembre 2026. **Qualification automatisée : 100/100 scénarios au
bilan consolidé, aucun ignoré ; `make test` vert.** Les essais sur matériel
physique restent à faire ([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md)).

0.9.3 publie la préparation 0.9.2 ([rapport](QUALIFICATION-0.9.2.md)) et y
ajoute la progression visible : toute opération qui peut durer plusieurs
secondes à 1 MHz montre une barre ou fait tourner un signe d'activité.

## Ce qui a été vérifié

- **Hôte** : `make test`, 111 suites. Les harnais enregistrent chaque appel
  de barre et chaque signe d'activité : une boucle longue sans eux échoue
  (UNSQ, UNWRAP, SCIIBIN, DISASM, IMGCONV, MOVE, SYNC, RESCUE, IMGPUT, CPM,
  CPMW, PASCAL, PASCALW, DOSWRITE, DOSIMAGE, BINARY2, COMPARE, SEARCH, la
  remise à zéro du compteur « n/m » avant chaque surcouche, le parcours
  d'album).
- **POM2** : `bench/all.py`, 100 étapes sur les deux processeurs et les
  cinq images. Nouveaux contrôles d'écran, qui échouent sans les
  corrections : `bench/progress.py` (la cellule d'activité alterne pendant
  un CRC de 48 Ko et un VERIFY de 4 000 blocs), `bench/mini33_write.cpp`
  (la dernière case de la barre tourne pendant une copie DOS 3.3),
  `bench/mini33_ops.cpp` (la question Y/N quitte l'écran dès la réponse).
- **Images** : `tools/check_images.py` ; la 140K garde 22 blocs libres, la
  disquette de banc 2, comme en 0.9.2.

## Déroulement honnête

La première passe parallèle a fini à 94/100. Écarts corrigés puis rejoués :

- `open_images`, `disasm`, `dosrepl` : trois contrats d'écran voyaient le
  nouveau signe d'activité (ligne 21, dernière colonne) ou le message
  « Checking DOS 3.3 disk... » ; les bancs l'excluent désormais, rien
  d'autre.
- `launch:6502` : disques compagnons `build-6502/legacy` périmés (surcouches
  d'avant le nouveau résident) ; reconstruits par `make benchpackages`.
- `run:enh` : DELETE et IMGFS franchissaient une frontière de bloc et la
  disquette de banc n'avait plus de bloc libre pour la configuration ;
  les deux surcouches ont été réduites sous leur bloc.
- Les deux séries `plugins` échouent en masse quand elles partagent la
  machine (connexions POM2 coupées) ; rejouées une à une : 31/31 sur les
  deux processeurs, `mdview` 6502 compris après une relance seule
  (délai de 60 s atteint sur la page 13 d'une ligne logique géante,
  chemin non modifié).

Ce bilan assemble la passe complète et ces relances.

## Limites connues

- Le FORMAT RWTS du Mini (environ 18 s dans un seul appel DOS) et un appel
  disque bloquant isolé (démarrage moteur, relectures d'un secteur abîmé)
  restent sans mouvement à l'écran.
- La barre de copie du Mini avance par lot de 32 secteurs ; le signe RWTS
  prouve l'activité entre deux.
- MAIN 65C02 : 82 octets libres ; l'objectif de 256 reste ouvert.
