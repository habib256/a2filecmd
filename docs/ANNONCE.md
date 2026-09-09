# Annonce — brouillon pour les groupes Apple II

*Écrit pour la 1.0. Le programme s'appelait alors « Apple IIe Total
Commander » ; le texte a été repris au nouveau nom, les captures et le lien
de téléchargement sont ceux de la Release.*

## Post pour le groupe Facebook « Apple II Enthusiasts »

**A2 File Cmd 0.5 – a two-panel file manager for the Apple IIe (ProDOS 8, free software)**

Hi everyone! I'd like to share a new utility for the Apple IIe: **A2 File Cmd**, a two-panel file manager for ProDOS 8 in the spirit of the good old Total Commander / Norton Commander, written in C and 6502 assembly with cc65.

What it does, from an 80-column screen with a 128 KB IIe:
- two panels, TAB to switch, sort by name, size or type, tag several files with the space bar;
- copy, move, rename, delete, make directories (whole directories too), with a progress bar and an Overwrite / Skip / All / None question when a file already exists;
- a text viewer, a hex viewer, and a small full-screen text editor;
- an image viewer that recognises HGR and DHGR pictures, raw or RLE-compressed, and steps through the pictures of a folder with the arrow keys;
- a Mockingboard player: RETURN on a .MB file plays it while you keep browsing;
- lock/unlock, change file type and auxtype, mark the files that differ from the other panel;
- a disk formatter for ProDOS (Disk II 5.25", SmartPort, /RAM disk) with a very explicit confirmation: it names the drive and its current volume, and you have to type the word ERASE;
- it remembers your two folders between sessions, and shows the free space of the volume.

It runs under ProDOS 2.4.3 (Bitsy Bye launches it), and it is **free software under the GNU GPL v3**, by Arnaud Verhille. The floppy image (140 KB, .po and .dsk) boots straight into it and comes with a DEMO folder: two test cards, a Mockingboard tune, a text and an Applesoft program, all generated rather than borrowed. It was born inside a Scorpion Swamp gamebook port for the Apple II, which still carries it on its own disk.

The disk formatter reuses the public-domain ProDOS Hyper-FORMAT routines (Jerry Hewett, 1985) as integrated in ADTPro, so thanks to those authors. Everything was tested in the POM2 emulator, including formatting a blank floppy in an emulated Disk II; feedback from real hardware is very welcome, especially on 5.25" drives and SmartPort devices.

Download and sources: https://github.com/habib256/a2filecmd — the release carries `A2FILECMD-6502.po` and `.dsk` with their SHA-256 sums, and `make disk` rebuilds them from source with nothing but cc65 and Python 3.

Enjoy, and tell me what you'd like to see next!

---

Version française, si vous préférez la poster telle quelle :

**A2 File Cmd 0.5 – un gestionnaire de fichiers à deux panneaux pour l'Apple IIe (ProDOS 8, logiciel libre)**

Bonjour à tous ! Je vous présente **A2 File Cmd**, un gestionnaire de fichiers à deux panneaux pour ProDOS 8, dans l'esprit de Total Commander et de Norton Commander, écrit en C et en assembleur 6502 avec cc65, pour l'Apple IIe 128 Ko en 80 colonnes.

Au menu : deux panneaux, tri, marquage de plusieurs fichiers ; copie, déplacement, renommage, suppression, dossiers entiers, barre de progression et question Écraser / Passer / Tout / Aucun ; visionneuses texte et hexadécimale, petit éditeur de texte ; visionneur d'images HGR et DHGR, brutes ou compressées RLE, avec les flèches pour feuilleter un dossier ; lecteur Mockingboard ; verrou, type et auxtype, comparaison des deux panneaux ; et un formateur ProDOS (Disk II, SmartPort, /RAM) avec une confirmation très explicite : il nomme le lecteur et son volume, et il faut taper le mot ERASE.

Il tourne sous ProDOS 2.4.3, se lance depuis Bitsy Bye, et c'est un logiciel libre sous GNU GPL v3, d'Arnaud Verhille. L'image de disquette 140 Ko démarre directement dessus, avec un dossier DEMO -- deux mires, une fanfare, un texte, un programme Applesoft, tous calculés et non empruntés -- pour tout essayer. Testé dans l'émulateur POM2, formatage compris ; vos retours sur vraies machines sont les bienvenus.

Téléchargement et sources : https://github.com/habib256/a2filecmd
