# Qualification de la 0.8.7

Publiée le 15 septembre 2026 depuis le commit `262060d`, tag `v0.8.7`. Elle
suit une chasse aux bugs sur tout le code : chaque défaut relevé a été
vérifié, corrigé avec un test qui échouait sur la 0.8.6, puis contrôlé sur
les deux CPU. Le détail est dans le [CHANGELOG](../../CHANGELOG.md).

## Validation locale

- `make test` : 731 tests hôtes dans 62 suites, dont le vrai cœur
  UNSHRINK, le pilote VDrive, le lanceur et la chaîne de page 3 sous sim65.
- `tools/check_images.py` : 7/7 images ; `release_notes.py --check-tag v0.8.7`.
- Le job bancs de `ci.yml` rejoué commande par commande sur les deux CPU
  (l’exécuteur auto-hébergé n’existe pas, ce job est sauté sur GitHub) :
  smoke, complément 2/2, six 16/16, arbres 4/4, outils de blocs 25/25,
  VOLINFO 22/22, FORMAT 36/36, images 20/20, BOOTBLK 11/11, DOSWRITE 17/17
  en slots 6 et 5, images DOS 20/20, NIBCOPY 7/7, sûreté des données 14/14,
  catalogues et grands répertoires, session complète 73/73, séquences
  21/21, XL 11/11, plugins 16/16 sur chaque CPU, budget de pile.
- VDrive 13/13 sur la BOOT publiée et les deux disquettes de banc ; Mini :
  sim65 26 + 57 et les trois bancs POM2 (`mini33_ops`, `mini33_write`,
  `mini33_review`).
- Réserves au lien (65C02/6502) : MAIN 361/790, LC 34/26. BOOT et
  disquettes de banc à 3 blocs libres, ce qu’il faut pour enregistrer
  `A2FILE.CFG` à la sortie.

## Bancs remis en état

Trois bancs étaient rouges sur la 0.8.6 publiée, pour des raisons de banc :
VOLINFO (course avant l’invite de disque, BOOT jamais remise, disquette de
banc sans VOLINFO), sûreté des données (W ne prend plus qu’un vrai nom
d’image) et budget de pile (le seuil « moitié » précédait la garde
`tree_stack_ok` des parcours non récursifs ; la copie profonde utilise 145
octets sur 192, 47 de marge, contrôle ramené à 32 octets de marge).

## Publication

CI de `main` puis du tag : sept images, manuel et empreintes. Les huit
empreintes de la CI (sept images et le manuel) sont identiques au lien local. La disquette
A2FileCmd Mini DOS3.3 est construite localement (`make mini-disk` sur la
disquette 0.8.6 comme maître) et jointe avec `SHA256SUMS-0.8.7.txt`
complété.

## Après le tag

La disquette A2FileCmd Mini DOS3.3 de la release a été remplacée le même
jour, à la demande : sur une vraie machine, un caractère disparaissait en
colonne 8 (`COPY 5 M RKED?`) et une lettre isolée apparaissait plus bas.
La Mini sauvait et restaurait autour de chaque appel RWTS les trous d’écran
du Disk II à `$0478+slot×16`, des cases visibles, au lieu de `$0478+slot`
où DOS 3.3 garde la piste courante (vérifié dans le RWTS de la disquette
maître : `TXA`, quatre `LSR`, `TAY`, puis `$0478,Y`). Le banc
`mini33_ops` lit désormais la bannière de copie en continu : il reproduit
la capture sur l’ancien binaire et passe sur le nouveau. La même disquette
ajoute RETURN et B pour lancer un binaire par BRUN (`bench/mini33_brun.py`,
depuis HELLO et depuis l’invite DOS). Le manuel PDF de la release a été
régénéré pour ces touches, et `SHA256SUMS-0.8.7.txt` avec lui.

Elle a été remplacée une seconde fois le même jour pour simplifier le bas
de l’écran : panneaux de 19 lignes, lignes d’état et de nom descendues
d’une ligne sur l’ancienne ligne de résultat, et une dernière ligne de
touches en inverse suivies de leur action abrégée (`TAB`PAN `C`OPY
`D`EL `B`RUN `/`DRV `?`HELP `Q`UIT), sans répéter la lettre de la touche
(`Y`ES `N`O `ESC`ANCEL, et non `Y`YES `N`NO `ESC`CANCEL vu sur la machine). Le résultat d’une opération prend
la ligne du nom jusqu’à la touche suivante. `mini33`, `mini33_ops`,
`mini33_write`, `mini33_review` et `mini33_brun` suivent la nouvelle
disposition et passent, avec sim65 26 + 57 et `make test`.

Troisième remplacement, le même jour : RETURN ouvre un fichier selon son
contenu. Il lit le premier secteur de données : un binaire dont l’en-tête
DOS correspond à sa taille est une image s’il charge 8 Ko en `$2000` ou
`$4000`, de l’hexadécimal s’il ne peut pas tourner (vide, sous `$0800`,
jusqu’aux tampons DOS en `$9600`), du texte si ses octets en sont, sinon
un programme (`BRUN NOM?`) ; sans en-tête valide, une image brute à 32–34
secteurs, sinon de l’hexadécimal ; un fichier T qui n’est pas du texte
s’ouvre en hexadécimal. Le programme s’appelle désormais `A2FC` sur la
disquette (`BRUN A2FC`). `mini33_brun` couvre six nouveaux cas ; les cinq
bancs POM2, `mini33_time`, sim65 26 + 57 et `make test` passent.

## Non refait

Pas de qualification sur matériel réel de cette révision. Le délai d’envoi
de VDrive (câble absent, CTS bas) n’est vérifié que sous sim65.
