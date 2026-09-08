# Les bancs

Ils jouent d'A2 File Cmd comme un utilisateur, dans un Apple IIe emule sans
fenetre, et verifient ce que l'ecran affiche. Rien n'est ajoute au binaire
livre pour cela : les adresses des variables observees viennent de la table de
symboles du lien (`build/a2fc.lbl`), et l'ecran est lu la ou l'Apple II le
range, en `$400-$7FF`.

Ils partent tous de **`dist/A2FILECMD.po` tel qu'il sera telecharge** : ce
qui passe ici est ce que recevra celui qui amorce la disquette.

| | |
|---|---|
| `smoke.py` | la disquette publiee demarre-t-elle sur les panneaux ? |
| `awp.py` | un document AppleWorks (3.0 puis 2.x) se lit page par page, ligne pour ligne ce que tools/mkawp.py a ecrit |
| `subdir.py` | A2FILE.SYSTEM et A2FILE/ copies dans /HD/APPS d'un disque dur, lances de BASIC par `-APPS/A2FILE.SYSTEM` : surcouches, aide, formateur et retour se trouvent depuis ce dossier |
| `vdrive.py` | deux volumes par la ligne serie (VDrive) : le serveur `vsdrive_server.py` sert un .po au pont TCP de la Super Serial Card de POM2 ; attend `pom2_playtest --ssc` |
| `hd.py` | le disque dur `.2mg` publie amorce-t-il, avec son dossier DEMO au complet ; une page brute s'affiche, un `.2MG` s'ouvre comme un dossier |
| `run.py` | la session complete : naviguer, marquer, copier, deplacer, renommer, verrouiller, changer type et auxtype, creer un dossier, supprimer, lire un texte et des octets, editer, afficher les deux formats d'image et les comparer octet a octet, jouer la fanfare, ecrire et relire des images disque (.PO et .DSK) et copier une disquette, ouvrir une image comme un dossier et en extraire un fichier, lire un catalogue DOS 3.3 et en extraire un fichier, ouvrir le formateur, cliquer a la souris (pointeur, bornes, selection, ouverture, changement de panneau, barre de touches), lancer un programme Applesoft (depuis le disque dur, avec le BASIC.SYSTEM de la disquette) et revenir sur les panneaux par -A2FILE.SYSTEM. **70 controles.** |
| `memory.py` | le creux maximal de la pile C, mesure en faisant travailler le programme |
| `pom2.py` | le pilote d'emulateur commun |

## Les faire tourner

Il faut [POM2](https://github.com/habib256/pom2) construit sans interface
graphique, avec son serveur de commande (`--ai-control`) et une option
`--mouse` qui branche une AppleMouse II (HLE AppleWin) en slot 4 -- c'est
`pom2_playtest`, l'hote minimal du depot voisin, qui les a :

```sh
make disk
POM2=/chemin/vers/pom2_headless python3 bench/run.py --out /tmp/bench
POM2=/chemin/vers/pom2_headless python3 bench/memory.py
```

Sans la variable `POM2`, les bancs cherchent l'executable a l'emplacement par
defaut de l'auteur et s'arretent proprement s'il n'y est pas.

`Pom2(..., preset='iie')` est la machine par defaut, un Apple //e Enhanced
avec la carte HDV en slot 5 et un Mockingboard en slot 2. `preset='iic'`
donne un Apple //c (ROM 32 Ko) : son lecteur integre est le Disk II du slot
6, donc `--boot 6` amorce la disquette comme sur le //e, et le disque dur est
une unite SmartPort sur le port arriere, servie par le firmware du //c en
slot 5 (pas de carte, pas de Mockingboard). Les deux presets amorcent
`dist/A2FILECMD.po` jusqu'aux panneaux. `Pom2(..., floppy2=...)` met une
seconde disquette dans le lecteur 2 du meme Disk II des l'amorcage
(`pom2_playtest --disk2`) : un vrai DOS 3.3 dans un lecteur, sans passer par
`/disk` -- ce que le banc des disques physiques attendait.

## En integration continue

L'emulateur n'est pas sur les executeurs de GitHub, et il ne serait pas
raisonnable de l'y construire a chaque commit. Le travail `bench` du
[workflow](../.github/workflows/ci.yml) ne se declenche donc que si la
variable de depot **`POM2_RUNNER`** contient l'etiquette d'un executeur
auto-heberge qui a POM2 ; sinon il est saute, et la publication n'exige que
la construction et les tests hors emulateur. C'est la limite honnete du
dispositif : la compilation, les budgets memoire et la fabrication des images
sont verifies partout, la session complete la ou l'Apple II existe.
