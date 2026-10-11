# Essai ZX02 : compression du programme principal

Essai du 10 octobre 2026. Le programme principal est compressé ; les
surcouches restent ordinaires. Les images habituelles, leur lanceur et
l'ABI des plugins restent indépendants de cet essai. Aucune nouvelle
version ni distribution officielle n'est publiée par ces cibles.

## Résultats de place

| Mesure | 6502 | 65C02 |
| --- | ---: | ---: |
| Programme principal brut | 35 155 octets | 35 543 octets |
| Programme ZX02 avec enveloppe | 20 753 octets | 20 965 octets |
| Lanceur avec décodeur assembleur | 5 075 octets | 4 970 octets |
| Image complète 800 Ko | 1 573/1 600 blocs | 1 566/1 600 blocs |
| Blocs libres sur 800 Ko | **27** | **34** |
| Image réduite 140 Ko | 246/280 blocs | 246/280 blocs |
| Blocs libres sur 140 Ko | **34** | **34** |

La réduction du programme principal atteint environ **41 %**, enveloppe
comprise. Le lanceur expérimental a un écran de démarrage simplifié. Les volumes utilisent aussi
le placement et les trous ProDOS déjà disponibles dans `mkvolume.py`.

La 800 Ko conserve tous les outils et les interpréteurs de l'édition
complète, sans les démonstrations de XL. La 140 Ko contient le socle de
banc `BENCH_BOOT_NATIVE` et DOSVIEW, MOVE, VERIFY : **19 surcouches** ;
elle ne contient pas toutes les visionneuses. La sélection d'une future
édition 140 Ko reste à définir.

## Contrat mémoire et erreurs

Le lanceur `src/zxloader.c` s'exécute en MAIN à partir de `$2000`. Le
lieur `src/zxloader.cfg` borne son code, ses données, son initialisation
et toute sa BSS sous `$4000` ; aucun contrôle mémoire n'est désactivé.
La BSS finit à `$3E70` sur 6502, `$3E07` sur 65C02 (adresses exclusives).

La sortie utilise uniquement MAIN : les 3 072 premiers octets en
`$1000-$1BFF`, puis le programme en `$4000-$BEDF`. La pile C du lanceur
reste sous `$BF00`, avec une réserve de 32 octets. Le tampon d'entrée de
2 560 octets (cinq blocs ProDOS) appartient à la BSS du lanceur ; le
tampon ProDOS appartient à MAIN `$0800`. Aucune écriture ne vise AUX : la décompression n'exige
donc pas la destruction ou la reconstruction de `/RAM`.

Les seuls fichiers écrits par la construction sont les nouveaux artefacts
et les images de banc dans `build/` et `build-6502/`. Le lanceur ouvre
son image en lecture seule ; il n'écrit ni fichier ni volume.

L'enveloppe `A2Z2` contient un en-tête de 12 octets : longueur brute,
longueur comprimée, CRC-16/CCITT-FALSE, CPU et octet réservé nul. Les
500 octets suivants doivent tous être nuls ; le flux commence à une
frontière de bloc ProDOS. L'ancien format `A2Z1`, sans ces 500 octets,
reste lisible. Le décodeur vérifie les longueurs, chaque lecture, chaque
référence arrière et chaque écriture
avant de l'effectuer. Le marqueur final ZX02 doit correspondre exactement
à la longueur brute et au CRC ; l'étendue comprimée doit être entièrement
consommée, sans octet supplémentaire. Une erreur de lecture ou de
fermeture interdit le saut vers `$4000`.

Le CRC détecte les corruptions accidentelles ; ce n'est pas une signature
d'authenticité. Une image rejetée peut avoir déjà rempli ses plages MAIN
autorisées : le lanceur quitte vers ProDOS et n'exécute pas cette image.

## Qualification et performances

`tools/test_zx02_boot.py` exécute le vrai lanceur et sa référence C sur
l'hôte avec les sanitizers, et son décodeur assembleur sur les deux CPU
avec sim65. Il compare tous les octets décompressés, vérifie les limites exactes, les flux aléatoires malformés,
les troncatures, tailles, CPU, CRC, octets supplémentaires, les échecs de
lecture/fermeture et la création exclusive de la sortie.

`tools/bench_zx02_boot.py` démarre des copies jetables en POM2 sur disque dur et
sur Disk II, sur IIe NMOS et IIe enhanced. Les deux CPU démarrent, chargent
une surcouche TEXT normale, préservent AUX `$1000-$BFFF` et un témoin sous
la pile du lanceur, et refusent un mauvais CRC. Les images complètes sont
comparées octet par octet après synchronisation des disques. La qualification
finale du démarrage compressé et du contenu affiché par TEXT passe sur
les quatre configurations (deux CPU, Disk II et disque dur), à 100 000
cycles par image ; la comparaison des temps ci-dessous utilise 20 000.

Le décodeur `src/zx02_decode.s` est en assembleur NMOS 6502, commun aux
deux CPU. Les boucles de lecture, copie et CRC sont intégrées ; les bits,
le compteur de copie, le CRC et les pointeurs utilisent les emplacements
scratch de la page zéro du runtime. Tout état vivant est sauvegardé lors
des appels C de remplissage. Aucun octet de page zéro supplémentaire ni
aucune banque auxiliaire n'est réservé.

Le banc sim65 du lanceur complet mesure **7 190 146 cycles** sur 6502 et
**7 279 383 cycles** sur 65C02, contre **40 561 392 / 40 285 508** avec
la référence C. Ces comptes comprennent le lanceur, les E/S simulées et
les contrôles du banc, sans la copie finale dans un fichier de sortie.
Un budget de **8 millions de cycles** sur les programmes actuels est
vérifié par le test de régression.

Les mesures de référence utilisent maintenant `tools/zx02_timing.cpp` :
CPU et contrôleurs POM2 exécutés instruction par instruction, sans vitesse
murale ni carte disque dur. Le Disk II utilise sa ROM et le séquenceur LSS ;
le Sony utilise la ROM réelle du //c+, MIG, IWM et GCR à zones. Le //c+ est
exécuté entièrement à **1 022 727 Hz**, correspondant ici au mode lent ;
ces résultats ne décrivent pas son mode accéléré 4 MHz.

Chaque variante démarre trois fois à froid. Les deux images d'une paire
contiennent les mêmes 19 surcouches du socle réduit, avec le même nom de
volume ; seules le lanceur et la représentation du programme changent.
L'image Sony fait exactement 800 Ko. La complète non compressée dépassant
800 Ko, elle ne peut pas servir de référence à contenu identique.

Le compteur donne le temps du démarrage jusqu'à l'affichage **des deux
panneaux**. Le saut vers `$4000` est repéré à l'instruction près ; l'écran
est échantillonné toutes les 1 024 cycles (environ 1 ms). Les trois mesures
de chaque variante sont identiques. AUX `$1000-$BFFF` et toute l'image de
volume sont comparés après vidage des écritures du contrôleur : **18/18
mesures réussies**. Les mesures et empreintes des binaires sont dans
[ZX02-TIMINGS.json](ZX02-TIMINGS.json).

| Démarrage dans POM2 à 1,022727 MHz | Brut | Compressé | Surcoût |
| --- | ---: | ---: | ---: |
| Disk II, IIe NMOS | 32,18 s | 36,03 s | **+3,85 s** |
| Disk II, IIe enhanced | 31,73 s | 35,17 s | **+3,44 s** |
| Sony 800 Ko, //c+ à 1 MHz | 36,52 s | 38,58 s | **+2,06 s** |

| Lecture du programme et décompression, depuis « Loading » jusqu'à `$4000` | Brut | Compressé |
| --- | ---: | ---: |
| Disk II, IIe NMOS | 6,99 s | 11,58 s |
| Disk II, IIe enhanced | 7,25 s | 11,64 s |
| Sony 800 Ko, //c+ à 1 MHz | 9,04 s | 11,89 s |

Le surcoût total respecte la marge acceptée de 3 à 4 secondes. Les
anciennes mesures murales Disk II (30,75/30,09 s compressé, contre
27,36/27,17 s brut) utilisaient 20 000 cycles par image et un hôte POM2
avec une carte HD supplémentaire : leur cadence et leur configuration
étaient différentes. Les tableaux ci-dessus constituent désormais la
référence pour comparer la compression à 1 MHz.

Ce sont des **mesures de l'émulation des lecteurs**, pas des mesures sur
des lecteurs physiques. Elles incluent les limites du modèle POM2.

## Reproduction

Le compresseur externe est celui de
[dmsc/zx02](https://github.com/dmsc/zx02), avec ses options par défaut
(flux avant, offset initial 1, polarité Elias normale). Il n'est pas
téléchargé automatiquement et aucun compresseur n'est nécessaire sur
l'Apple II.

```sh
make ARCH=6502 ZX02=/chemin/vers/zx02 zx02-800 zx02-140
make ARCH=enh ZX02=/chemin/vers/zx02 zx02-800 zx02-140
ZX02=/chemin/vers/zx02 python3 tools/test_zx02_boot.py
python3 tools/bench_zx02_boot.py --build build-6502 --disk-ii
python3 tools/bench_zx02_boot.py --build build --disk-ii
SOURCE=tools/zx02_timing.cpp sh bench/pom2_playtest/build.sh build/zx02_timing
python3 tools/measure_zx02_boot.py --output build/nouvelle-mesure-zx02.json
```

Construire les architectures successivement : certains intermédiaires du
résident sont communs. Les sorties sont `build[-6502]/A2FC-ZX02-800.po`
et `build[-6502]/A2FC-ZX02-140.po`.

La suite consiste à mesurer sur de vrais lecteurs et à intégrer ce
lanceur dans les distributions après sélection des outils 140 Ko. La
compression des surcouches demande un autre emplacement de décompression
et un chargement compatible avec la marge résidente actuelle ; elle
n'est pas intégrée dans cet essai.
