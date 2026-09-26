# Qualification 0.9.4

Date : 26 septembre 2026. **Qualification automatisée : 105/105 scénarios au
bilan consolidé, aucun ignoré ; `make test` vert (1 182 tests, 115 suites).**
Les essais sur matériel physique restent à faire
([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md)).

0.9.4 publie ce qui était prêt depuis la 0.9.3 ([CHANGELOG](../CHANGELOG.md)) :
noms d'images `A2FILECMD-PRODOS-*` et `A2FILECMD-DOS3.3`, DEMO du XL rangé par
sorte de fichier, README et capture 80 colonnes, ABI des overlays gelée,
résident 65C02 à 415 octets libres, pages des grands catalogues plus rapides,
Haut qui ne charge plus la fenêtre suivante (65C02), VDrive qui ne touche plus
une imprimante, audit des signes entre les deux compilateurs, hexadécimal
lisible et signes d'activité RWTS du Mini.

## Ce qui a été vérifié

- **Hôte** : `make test`, dont les nouveaux `test_abi_freeze`,
  `test_sign_compare` (aussi en CI : clang présent, rien d'ignoré),
  `test_dir_paging`, `test_move_cursor`, et `test_vsdrive` (une SSC en mode
  imprimante ne reçoit aucune écriture).
- **Images** : `tools/check_images.py` sur les cinq images 0.9.4 ; la 140K
  garde 24 blocs libres (22 en 0.9.3), la 800K 612. Réserves au lien,
  65C02/6502 : MAIN 415/821, carte langage 62/53.
- **POM2** : `make qualify` (`bench/all.py --strict`), les deux processeurs,
  les cinq images et le Mini. Nouveaux bancs : `paging_swap` (disquettes
  échangées et répertoire modifié entre deux pages), `vdrive_printer` (zéro
  accès à une SSC imprimante, en slot 1 comme en slot 2), `mini33_lend`
  (appels RWTS et disquettes identiques avec et sans le crochet).

## Déroulement honnête

La passe complète a fini à 103/105. `dosimage` échouait sur les deux
processeurs : en mode `.DSK`, le banc lisait le disque XL réel et y cherchait
`DOS33.DSK` directement dans DEMO, que la 0.9.4 range dans `DEMO/DISKS`. Le
banc construit maintenant, dans ses deux modes, un volume jetable au DEMO à
plat (comme son mode `.2MG` le faisait déjà) ; `hd.py` vérifie le DEMO
réellement livré. Rejoué : 19/19 (`.DSK`) et 20/20 (`.2MG`) sur chaque
processeur. Aucun code du programme n'a changé entre la passe et ce bilan.

Pendant la préparation, un hôte `pom2_playtest` construit contre la
bibliothèque POM2 en cours de travail (`work/printer-detection`) plantait au
démarrage ; l'hôte de cette qualification, reconstruit ensuite, fonctionnait.

## Limites connues

- Aucun essai sur machine réelle pour cette version.
- VDrive sur //c : une imprimante branchée sur le port modem reçoit encore
  les enveloppes (pas de commutateurs à lire) ; le IIgs n'est pas testé.
- Mini : Retour sur une table Pinball Construction Set (`*.PB`) propose
  encore `BRUN`, qui finit dans le moniteur (sans perte de données).
- Une disquette jamais formatée peut encore laisser la case d'activité du
  Mini immobile environ une seconde (démarrage du moteur, recalibrage).
