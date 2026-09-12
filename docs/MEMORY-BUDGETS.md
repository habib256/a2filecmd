# Consolidation : budgets mémoire

Premier relevé du 12 septembre 2026, code natif de `af84617`, après reconstruction
forcée des deux architectures. `tools/check_layout.py` affiche maintenant les
réserves à chaque lien réussi, en complément des contrôles bloquants existants.
Les chiffres ci-dessous sont un point de départ, pas des constantes à recopier
dans un futur rapport de qualification.

## Mesures et objectifs du premier chantier

Les réserves sont en octets. Les objectifs sont des seuils de travail proposés,
pas des garanties déjà obtenues ni des plafonds assouplis.

| Zone | 65C02 | 6502 | Réserve visée sur chaque architecture |
| --- | ---: | ---: | ---: |
| MAIN, jusqu'à `$BEE0` | 5 | 542 | ≥ 256 |
| Carte langage, jusqu'à `$E000` | 0 | 4 | ≥ 128 |
| LOWRAM, BSS compris, jusqu'à `$1B00` | 290 | 315 | ≥ 256 |
| Espace entre code persistant et pile C | 33 | 759 | ≥ 128 |
| BSS FORMAT, jusqu'au tampon `$3E00` | 147 | 147 | ≥ 128 |

La pile C réserve 192 octets : l'espace avant la pile ne mesure **pas** sa
consommation dynamique et ne justifie pas de réduire sa taille. MAIN contient
aussi le code ONCE jetable ; ses octets libres ne s'ajoutent pas à cet espace.
Les surcouches se recouvrent et leurs réserves ne s'additionnent pas non plus.

| Surcouche liée au résident | 65C02 | 6502 |
| --- | ---: | ---: |
| BATCH | 2797 | 2814 |
| NAV | 230 | 296 |
| OPEN | 74 | 110 |
| COPY | 33 | 25 |
| FORMAT | 428 | 428 |
| IMAGE | 113 | 116 |
| TEXT | 61 | 33 |
| HEX | 49 | 42 |
| DELETE | 4 | 3 |
| HELP | 219 | 183 |
| RUN | 2190 | 2202 |
| ATTR | 26 | 26 |
| EDIT | 370 | 358 |
| MENU | 2241 | 2184 |
| DISKIMG | 328 | 283 |
| IMGFS | 5 | 13 |
| DOS33 | 59 | 84 |
| UNSHRINK | 122 | 137 |
| BASLIST | 1863 | 1856 |
| COMPARE | 86 | 111 |
| SEARCH | 335 | 338 |
| BINARY2 | 1968 | 1992 |
| AWP | 216 | 197 |

Viser au moins 64 octets dans chaque petite surcouche modifiée ; traiter DELETE,
IMGFS, COPY et ATTR en priorité avant de les enrichir. Les plugins SDK liés
séparément ne figurent pas dans ce relevé : leurs limites code/BSS et tampons
restent imposées par leurs configurations de lien, à contrôler aussi lors des
extractions. BINARY2 utilise ici sa grande fenêtre sur les deux architectures.

## Premier gain : diagnostics résidents

Les diagnostics ProDOS sont extraits dans `src/errors.h`, toujours en carte
langage. Une table de douze codes remplace le switch, et le diagnostic n'est
recherché qu'une fois par affichage. Le message sans appelant de l'ancien
lecteur Mockingboard est retiré ; le message « SYS, BIN or BAS only. » rejoint
RUNRO, dont RUN est l'unique utilisateur, sans chargement supplémentaire.

| Zone après modification | 65C02 | 6502 | Évolution |
| --- | ---: | ---: | --- |
| MAIN | 27 | 564 | +22 sur les deux |
| Carte langage | 71 | 74 | +71 / +70 |
| LOWRAM | 287 | 312 | −3 sur les deux |
| Espace avant pile C | 55 | 781 | +22 sur les deux |
| RUN | 2168 | 2180 | −22 sur les deux |

Les trois octets LOWRAM servent à l'indice et au pointeur de diagnostic
(locaux statiques cc65). Les autres surcouches et la réserve BSS FORMAT gardent
leurs marges initiales. Les objectifs MAIN, LC et espace avant pile ne sont
**pas encore atteints** sur 65C02 ; LC reste également sous l'objectif sur 6502.

Le service n'écrit aucun fichier ni volume. Il modifie le compteur d'erreurs
en RAM principale, ses locaux statiques, et l'écran texte 80 colonnes
MAIN/AUX `$0400-$07FF` via conio, sans toucher le stockage du disque `/RAM`.
Le message déplacé reste disponible pendant tout son affichage : `message()`
est résident et ne remplace pas la surcouche RUN.

Les tests exécutent le vrai C pour les 256 valeurs de code ProDOS : douze
messages connus, repli numérique pour tous les autres, contenu exact de la
ligne, compteur et conservation de `_oserror`/`errno`.

Validation locale du lot : `make test`, les deux liens et leurs contrôles,
construction des sept supports puis `tools/check_images.py` passent. POM2
valide l'amorçage BOOT sur 6502, les 11 contrôles XL sur 65C02 et mesure
92 octets de pile utilisés sur les 192 réservés dans `bench/memory.py`.
Ces scénarios ne prouvent pas une borne exhaustive pour tous les parcours.

### Après l'extension du lanceur à Integer BASIC

Le chantier demandé ensuite ajoute `src/launch.h`, toujours dans RUN, et
`INTBASIC.SYSTEM` sur DEVTOOLS/XL. Les chemins de lancement vivent à
`$3400-$347F`, séparés du tampon de configuration `$3000-$33FF` ; des contrôles
de taille à la compilation empêchent leur recouvrement. Aucun plafond n'est
relevé. Deux messages de sélection et deux libellés d'erreur sont placés en LC
pour garder RUN dans sept blocs sur la disquette BOOT 6502.

| Réserve du lien après extension | 65C02 | 6502 |
| --- | ---: | ---: |
| MAIN | 62 | 593 |
| Carte langage | 8 | 11 |
| LOWRAM | 280 | 305 |
| Espace avant pile C | 90 | 810 |
| RUN | 1781 | 1795 |
| OPEN | 83 | 119 |

BOOT occupe les 280 blocs : l'échec de sauvegarde d'une nouvelle configuration
y reste signalé avant de proposer de lancer quand même le programme. Les
objectifs de réserve restent ouverts, particulièrement la carte langage.

## Deuxième lot : affichage et saisie

Le lot suivant part de `68c39f5`. Une table compacte remplace le `switch` des
types de fichiers. Un seul en-tête sert aux trois tris ; l'étoile est ajoutée
à sa colonne d'origine. La ligne d'information partage son préfixe entre
fichiers ProDOS et fichiers dans une image. Les questions utilisent `cputs`
et `cputc` pour leur texte fixe, avec les mêmes réponses admises.

`src/display.s` remplace le parseur de barre de touches et la conversion
hexadécimale : mêmes conventions cc65 sur 6502/65C02 et même interface pour
les plugins. Le parseur recharge ses pointeurs après les appels conio ; ses
quatre octets d'état restent résidents. Aucune nouvelle surcouche n'est chargée.

| Réserve après ce lot | 65C02 | 6502 | Gain 65C02 / 6502 |
| --- | ---: | ---: | ---: |
| MAIN | 290 | 835 | +228 / +242 |
| Carte langage | 172 | 169 | +164 / +158 |
| LOWRAM | 281 | 306 | +1 / +1 |
| Espace avant pile C | 318 | 1052 | +228 / +242 |
| BSS FORMAT | 147 | 147 | inchangé |

Les objectifs initiaux sont atteints sur les deux architectures. Les plafonds,
la réserve de pile de 192 octets et les fenêtres des surcouches restent
inchangés. Les réserves de ces dernières n'évoluent pas. BOOT gagne un bloc
libre, et la disquette de banc enhanced passe de huit à neuf blocs libres.

### Écritures et qualification

Ces services ne font aucune opération de fichier ou de volume. Ils écrivent
leurs variables en MAIN, les registres temporaires cc65 en page zéro et
l'écran texte MAIN/AUX `$0400-$07FF`. La saisie écrit dans `input`, comme avant.
La ligne d'information utilise `copy_buf` en MAIN, désormais aussi pour les
fichiers dans une image : ses appelants ont terminé la lecture des répertoires
avant l'affichage. Le préfixe fait au plus 66 caractères, le texte complet
84 avant troncature à 79 ; le tampon en contient 512. Le disque `/RAM` n'est
pas utilisé comme réserve de mémoire par ces services.

`tools/test_display.py` exécute le C réel pour les 256 types, les trois tris
sur les deux panneaux, les attributs maximaux, les limites de ligne/tampon,
les saisies et les 256 touches de confirmation (seuls Y/y, N/n et Échap
terminent la question). Le test de style des questions reste dans
`tools/test_ui.py`. Sur sim65, le véritable assembleur est comparé à l'ancien
parseur C, texte et vidéo inverse compris, avec passage de page et appel par
le pointeur de fonction des plugins. Les 65 536 valeurs hexadécimales sont
vérifiées sur chacun des deux processeurs.

Validation locale : `make test`, les deux constructions natives et la relecture
des sept supports passent. POM2 valide les 11 contrôles XL sur 6502. Le parcours
`bench/memory.py` sur enhanced (visionneuses, édition abandonnée, copie
récursive sur volumes jetables) mesure toujours 92 octets de pile utilisés
sur 192. Cette mesure n'est pas une borne exhaustive pour tous les parcours.

## Suite de la consolidation

Poursuivre avec les contrats de buffers et les services de fichiers sûrs,
en mesurant séparément le gain MAIN et carte langage. Déplacer un service dans
une surcouche demande de vérifier tous ses appelants : charger cette surcouche
peut écraser celle qui appelle le service. Une réserve dans MENU ou BATCH n'est
donc pas automatiquement disponible pour un service partagé.

Avant toute modification native, établir les fichiers, volumes, buffers et
banques écrits par les fonctions concernées et leurs appels. Conserver les
garanties de création exclusive, copie vérifiée et remplacement récupérable.
Ne pas emprunter AUX pour gagner de la place sans le consentement préalable
requis pour la destruction de `/RAM`.

L'outil de mesure lit les symboles et tailles des fichiers construits sans
modifier les volumes ProDOS ni les banques mémoire.

## Reproduire

```sh
make -B all ARCH=enh
make -B all ARCH=6502
python3 tools/check_layout.py --big BINARY2
python3 tools/check_layout.py --lbl build-6502/a2fc.lbl --bin build-6502/A2FILE.CODE.BIN --big BINARY2
make test
```

Outils observés : `cc65 V2.18 - N/A` pour enhanced et `cc65 V2.19 - Git e11fb5c`
pour 6502. Relever les versions réellement utilisées plutôt que déduire leur
version des commentaires du Makefile. Ce relevé local ne constitue pas un test
sur émulateur ou matériel.

## PT3 : grands modules et TurboSound

Le lecteur accepte 65 535 octets, conteneur TurboSound compris, sans AUX.
La fenêtre BIG reste `$1B00–$3FFF` et les bornes de lien sont conservées.

| Zone PT3 | Adresses | Taille |
| --- | --- | ---: |
| Code, données, BSS | `$1B00–$36FF` | 7 168 |
| Deux en-têtes | `$3700–$3AFF` | 1 024 |
| Cache initial | `$3B00–$3DFF` | 768 |
| Tables du second module | `$3E00–$3FBF` | 448 |

Les premières tables empruntent 448 octets de `copy_buf`. Après initialisation,
deux pages entières de code devenu mort sont réutilisées ; une assertion de
lien vérifie leurs bornes. Les pages d'en-tête inutilisées peuvent aussi être
récupérées : cinq à huit pages de cache. Les opérandes d'initialisation ne
sont plus modifiés ensuite, ce que vérifie un test avec pages empoisonnées.
Le cache donne une seconde chance aux pages de samples et d'ornements ;
les lectures de patterns ne promeuvent pas les pages froides. Le bit 6 de la
table des pages porte cette référence et est masqué avant tout accès mémoire.
Le BSS PT3 finit à `$36AB` / `$36ED` (65C02/6502), laissant
84 / 18 octets avant les en-têtes.
Aucune donnée AUX, pile ou zone résidente n'est utilisée comme cache.

PURPLE reste sous `$2000` (fenêtre de 1 280 octets), ses lectures vont dans
MAIN `$2000–$3FFF`, puis AUXMOVE copie la première page vers AUX pour les
modes étendus. Le consentement précède le chargement ; toute sortie après
AUXMOVE reconstruit `/RAM`, y compris en cas d'erreur de lecture/fermeture.

Après intégration Purplesoft, les réserves résidentes sont : MAIN 145/682,
LC 168/163, LOWRAM 278/303, espace avant pile C 173/899, OPEN 4/42 octets
(65C02/6502). La pile C réservée reste de 192 octets. MAIN enhanced demeure
sous la réserve de travail visée de 256 octets ; OPEN enhanced est presque
plein. Les contrôles de disposition restent obligatoires.

Les bancs PT3 vérifient le plancher de pile, la mémoire AUX hors écran texte
et le volume source octet par octet sur des images jetables. Le lecteur
Purplesoft vérifie ses deux plans, les sorties et le consentement par session
sur les deux architectures. Ce sont des validations en émulation, pas des
mesures sur matériel physique.


## Consolidation du routage média

La correction des transitions ajoute un écran `Loading <cible>` préparé dans
MAIN/AUX `$0400–$07FF` dès la flèche, avant le nettoyage du lecteur. La relecture
des tables de panneaux attend son retour : elles partagent sa mémoire. Aucun
fichier ni octet AUX à partir de `$0800` n'est écrit par cette coordination.
Le parcours HGR/DHGR brut utilise la même annonce et redessine les panneaux
après relecture ; il n'a plus besoin des anciennes empreintes d'écran.
Les réserves après cette correction sont MAIN 365/885, LC 117/110,
LOWRAM 281/306 et espace avant pile C 393/1102 octets (65C02/6502),
avec une pile C réservée de 192 octets et les mêmes plafonds.

Les identifiants de `src/viewer_ids.h` indexent une seule table résidente de
noms. OPEN renvoie un octet plutôt qu'un pointeur vers ses propres chaînes ;
le feuilletage compare cet identifiant. Zéro reste une erreur de sonde et ne
sélectionne jamais un lecteur de repli. Les suffixes musicaux ne sont évalués
qu'une fois par candidat. La priorité des types explicites est conservée.

Le contrôle de taille HGR/DHGR regroupe les tailles exactes et leurs variantes
sans les huit derniers octets invisibles. Un test du vrai C couvre les 65 536
valeurs du mot bas, avec mot haut nul et non nul (393 216 vérifications pour
les deux configurations). Il conserve exactement 8 184, 8 192, 16 376 et
16 384 octets et refuse les tailles plus grandes ayant le même mot bas.

| Réserve | 65C02 avant → après | 6502 avant → après |
| --- | ---: | ---: |
| MAIN | 145 → 259 | 682 → 779 |
| OPEN | 4 → 185 | 42 → 215 |
| LC | 168 → 168 | 163 → 163 |
| LOWRAM | 278 → 277 | 303 → 302 |
| Espace avant pile C | 173 → 287 | 899 → 996 |

La réserve de travail MAIN de 256 octets est de nouveau atteinte sur 65C02.
Aucune limite de lien, taille de pile, API de plugin ou autorisation AUX n'est
modifiée. Les sondes n'écrivent que le buffer principal de lecture ; les
lecteurs conservent leur contrôle de consentement avant toute utilisation AUX.

Validation : 428 tests automatisés, compilations et limites des deux CPU ;
109 contrôles POM2 par architecture (`open_images.py`, `media.py`, `purple.py`),
avec écrans relus octet par octet, flèches, Échap, refus AUX et conservation du
volume source. Les essais utilisent uniquement des images jetables.
