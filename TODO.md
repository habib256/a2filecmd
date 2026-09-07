# A2 Retro Cmd — ce qui reste à faire

`🟠 haute · 🟡 moyenne · 🟢 basse`, effort indicatif en *italique*, fichier en
`backticks`. Les mesures datent du 2026-09-07, sur la 1.0.

## La place disponible

| Zone | État mesuré |
| --- | --- |
| Fenêtre principale `$4000`-plancher de la pile | ~1 130 octets libres |
| `LOWEXE` `$1C00-$1FFF` | 671 octets sur 1 024 |
| Carte langage `$D400-$DFFF` | 26 octets |
| Pile C | 86 octets utilisés sur 256 réservés |
| Disquette | 60 blocs libres sur 280 |

## Étude 2026-09-07 — la souris

**Verdict : faisable, ~0,7 Ko de code, et il faut d'abord ouvrir la place.**
🟡 moyenne · *2 à 3 jours*

**Le matériel.** Carte Apple Mouse II (341-0270). Ne jamais supposer un
slot : POM2 la met en **slot 2** par défaut (`mouseaw`, la carte AppleWin
haut niveau ; la carte MC68705 `mouse` existe aussi) et le **slot 4 est
occupé par la Mockingboard**. Balayage des slots 7→1 sur la signature du
firmware (`$Cn05=$38`, `$Cn07=$18`, `$Cn0B=$01`, `$Cn0C=$20`, `$CnFB=$D6`).
Les points d'entrée se lisent dans la table d'offsets `$Cn12..$Cn1B`
(SETMOUSE, SERVEMOUSE, READMOUSE, CLEARMOUSE, POSMOUSE, CLAMPMOUSE,
HOMEMOUSE, INITMOUSE) ; l'appel se fait `SEI`, ROM en lecture, `X=$n0` et
`Y=$Cn` comme le firmware l'exige, et il faut relâcher `$C800` par `$CFFF`
après coup — le firmware 80 colonnes du //e s'en sert aussi.

**Mode passif, aucune interruption.** `SETMOUSE` mode `$01` : la carte
compte toute seule, `READMOUSE` à chaque tour de boucle suffit. On évite
`ALLOC_INTERRUPT` (ProDOS n'a que quatre entrées et la musique en prend
une) et tout risque dans les temps critiques du Disk II. `CLAMPMOUSE` à
0..79 et 0..23 rend la position directement en cases de l'écran 80
colonnes : aucun calcul. L'état arrive dans les *screen holes* de la page
texte principale (`$0478+s`, `$0578+s`, `$04F8+s`, `$05F8+s`, statut
`$0778+s`).

**Ce que ça change dans le programme.** La boucle principale attend sur `cgetc()`,
bloquant : il faut une attente `kbhit()` + scrutation qui sorte sur touche
ou sur clic, dans la boucle principale et dans les visionneuses. Le curseur
est un caractère inversé (on est en texte, pas de sprite) : un octet
sauvegardé, réécrit à chaque déplacement. Actions : clic sur une ligne =
sélection, et changement de panneau actif si c'est l'autre ; double-clic =
Entrée ; clic sur la barre de touches ligne 23 = la commande ; clic sur la
ligne de titre = tri.

**Le prix.** Détection et init ~80 o, scrutation et curseur ~200 o,
cartographie des clics ~300 à 500 o : **0,6 à 0,8 Ko**. La place existe
désormais : le segment `LOWEXE` (`$1C00-$1FFF`, ouvert le 2026-09-07 pour
loger le décodeur d'images et payer le reformatage de `/RAM`) garde **~350
octets libres**, et la fenêtre principale **~1 100** sous le plancher de la
pile. De quoi tenir sans rien sacrifier — la carte langage, elle, reste
pleine à 26 octets près.

**Le banc.** POM2 émule les deux cartes et son API AI-control a un point
`/mouse` (déplacements et boutons, deltas accumulés) : un
`validate_mouse.py` cliquera comme les autres bancs frappent des touches.

**Étapes.** (1) `mouse.s` : détection, init, clamp, `READMOUSE`, curseur
texte, un `M` dans la ligne de statut quand la souris est vue ;
(2) scrutation dans la boucle principale ; (3) clic = sélection,
double-clic = ouvrir ; (4) barre de touches cliquable ; (5) le banc. Tout doit rester intégralement au
clavier : la majorité des machines n'a pas de souris.

---
