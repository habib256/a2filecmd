# Les sept lecteurs retenus pour la 1.0

Les lecteurs sont intégrés au menu et au routage automatique IDENT, dans
les éditions ProDOS 6502 et 65C02. Le numéro publié reste 0.9.6 : ce travail
ne publie pas une version 1.0 et n'annonce pas encore une qualification de
release complète. Les fichiers d'entrée sont ouverts uniquement en lecture.

| Format | Module | Profil couvert | Limites |
|---|---|---|---|
| WordPerfect Apple II | WORDPERF | ProDOS $A0/$0000, texte paginé, notes et groupes de commandes connus | Texte sans mise en page ; groupes multioctets inconnus refusés, contrôles simples non interprétés rendus visibles. Pas WordPerfect GS. |
| MouseWrite | MOUSEWR | ProDOS $F1/$0000 ou import BIN/$0000 intact, en-têtes MW 1/4/5, largeur de ligne enregistrée | Texte ; polices et dessins non reproduits. |
| Bank Street Filer | BSFILER | AFILER 1.0 extrait en BIN : formulaire, enregistrements, textes, flottants et dates | Flottants à trois décimales tronquées ; valeurs extrêmes montrées en hexadécimal. Champs calculés signalés, pas exécutés. |
| Multiplan | MULTPLAN | Sauvegarde normale v1.06 extraite intacte en ProDOS $F4 ou BIN : coordonnées, valeurs BCD et tokens de formules | Pas de recalcul, de sauvegarde Symbolic ni de lecture directe DOS R. Ne pas retirer un prétendu en-tête LISA des fichiers R. |
| Films Movie Maker | MVMOVIE | BIN aux $6000 ou import intact aux $0000, séquence 01/02/03/06/05/00/07, aperçu couleur 40×48, image suivante/précédente et redémarrage au clavier | Rectangles de formes opaques, masque transparent et cadence originale absents. Ce n'est pas une reproduction HGR fidèle du film. Commande de code machine et autres modes refusés. |
| Graphics Magician DHGR | DGMAGI | .DPC 560 points, lignes, pinceaux, remplissages et 256 motifs ; deux banques DHGR | Police de remplacement pour le texte ; ligne de couleur transitoire (commande 7) refusée. |
| Pinball Construction Set | PCSVW | .PB : fond HGR enregistré, remplissage des polygones et contours LIB ; O bascule entre fond original et aperçu complet | Aperçu statique ; pas les sprites exacts des objets LIB, la physique ou les scripts. Aucun code du jeu exécuté. |

Ces profils prennent des fichiers ProDOS. Les données DOS des originaux
peuvent être extraites avant lecture ; la reconnaissance d'un candidat DOS
n'est pas une promesse de décodage direct. Les deux architectures ont les
mêmes limites. Une extension ou un type produit un candidat, le lecteur
vérifie ensuite la structure entière et la fin physique du fichier.

Les tables PCS ProDOS BIN/$4000 renommées peuvent également être ouvertes
par Entrée/I sans suffixe `.PB`. L'identification contrôle la table complète
des longueurs d'objets, au moins un objet entier et tous les autres objets
entiers présents dans l'échantillon de 512 octets. Types, couleurs, nombres
de sommets et coordonnées doivent respecter les bornes du lecteur ; la
taille réellement lue doit laisser assez de place pour le fond compressé.
Il s'agit d'un candidat : le lecteur vérifie encore les objets restants,
le fond et la fin du fichier avant toute demande d'effacement de `/RAM`.

Qualification du 12 octobre : les six tables PCS originales sont reconnues
sous un nom neutre par les véritables étapes C, sur les deux processeurs
avec cc65 2.19 et HEAD. L'identification du corpus donne le même résultat.
Les cas négatifs couvrent couleurs/types invalides, coordonnées hors bornes,
objets incomplets, tailles de panneau périmées et plusieurs objets dans
l'échantillon. Le cas de 255 objets contrôle aussi le cumul des longueurs.
Le lecteur refuse les objets malformés avant consentement et toute écriture
AUX ; les tests d'ouverture, lecture, recherche, fermeture et refus restent
actifs. Chaque source est comparée octet pour octet après exécution.

Les suites détecteur (7), médias (9) et DOS (12) passent avec les deux
compilateurs sur les deux CPU. Le fallback DOS est conservé : aucun accès
direct DOS à PCSVW n'est ajouté. Les compilations natives, quatre images,
relais IDENT et inventaire des bancs passent avec leurs contrôles de
disposition actifs. IDV1 finit à `$3C24` (65C02) / `$3CA8` (6502), PCSVW à
`$327A` / `$32AA`, sous la limite `$4000`. L'analyse de signedness reste
à zéro site. L'identification écrit uniquement son état MAIN et n'emprunte
pas la mémoire auxiliaire.

POM2 passe 10/10 contrôles ciblés par CPU : Entrée et I sur une table
renommée, AUX inchangée avant confirmation et après refus sur `/RAM`
occupé, comparaison des 8192 octets HGR après acceptation, reconstruction
du RAM vide, garde de pile et volume source intégral conservés. Les volumes
et fichiers RAM du banc sont jetables. Le parcours complet des sept lecteurs
n'a pas été relancé pour cette qualification ; le matériel Apple II physique
reste non testé.

Graphics Magician DHGR : les images ProDOS BIN/$4000 renommées sont
également candidates à DGMAGI si les commandes de l'échantillon sont
valides, contiennent un dessin et utilisent une coordonnée au-delà des
280 colonnes classiques. Les bornes 560×192 sont partagées avec le lecteur.
Un fichier entièrement contenu dans l'échantillon doit avoir son
terminateur et un reste nul ; pour les fichiers plus grands, une commande
qui traverse la limite de 512 octets est laissée à la validation complète.
Les coordonnées ambiguës de la moitié gauche gardent leur ancien routage.
Le profil de commandes 7 reste refusé ; aucune lecture DOS directe n'est
ajoutée. L'identification écrit seulement son état MAIN, sans AUX ni source.

Qualification du 12 octobre : palette originale renommée, parité corpus /
véritables étapes C, commandes invalides, caractères hors plage, pinceaux,
coordonnées aux limites, absence de terminateur, données après terminaison,
frontière de l'échantillon et EOF supérieur à 65535. Les suites détecteur
(8), médias (10) et DOS (12) passent avec cc65 2.19 et HEAD sur les deux CPU.
Le lecteur refuse les coordonnées hors limites avant confirmation et
écriture AUX ; les tests existants conservent erreurs I/O et refus.
Les fichiers sources sont comparés octet pour octet après les essais.

Les deux compilations natives et quatre images passent avec tous les
contrôles mémoire actifs. IDV1 finit à `$3EEB` (65C02) / `$3F43` (6502),
DGMAGI à `$3644` / `$3691`, sous `$4000`. Le relais IDENT et l'inventaire
des bancs passent ; l'analyse de signedness reste à zéro site.

POM2 passe 10/10 contrôles DPC ciblés par CPU sur la palette originale
renommée : Entrée/I, AUX préservée avant confirmation et après refus,
comparaison des deux plans de 8192 octets après acceptation, reconstruction
du RAM vide, garde de pile intacte et volume source intégral conservé.
Le banc emploie uniquement un volume et des fichiers RAM jetables. Le
parcours complet des sept lecteurs n'a pas été relancé ; le matériel
Apple II physique reste non testé.

MouseWrite importé en BIN : MOUSEWR et l'identification acceptent désormais
les documents intacts en ProDOS BIN/$0000, en plus de `$F1/$0000`.
L'auxiliary type doit rester nul. Versions MW 1/4/5, indicateur d'en-tête
nul ou 32 et largeur 1–120 sont conservés ; l'identification vérifie aussi
cet indicateur, comme le lecteur. Le lecteur exige toujours les 512 octets
d'en-tête, au moins une ligne complète, des octets de texte autorisés,
la taille maximale et une fermeture réussie avant tout affichage. Aucun
backend DOS n'est ajouté, aucune source ni mémoire AUX n'est écrite.

Qualification du 12 octobre : les 41 originaux donnent le même texte en
BIN et F1 avec le vrai lecteur C sur l'hôte et les deux simulateurs CPU.
Les étapes réelles de détection et le classement du corpus concordent.
Les essais couvrent versions et largeurs limites, mauvais indicateurs,
largeurs invalides, lignes tronquées, types/aux incorrects,
tailles de panneau périmées, annulation et erreurs d'ouverture, lecture et
fermeture des deux passes ; les sources sont comparées octet pour octet.
Détecteur (10), lecteurs texte (7) et DOS (12) passent avec cc65 2.19 et HEAD.

Les deux compilations natives et quatre images passent avec les contrôles
de disposition actifs. IDV1 finit à `$3F1A` (65C02) / `$3F86` (6502),
MOUSEWR à `$25BC` / `$25EC`, sous `$4000`. Le relais IDENT et l'inventaire
des bancs passent ; l'analyse de signedness reste à zéro site.

POM2 passe 16/16 contrôles texte ciblés par CPU : les quatre lecteurs texte
existants, imports MouseWrite BIN des versions 1/4/5 par Entrée/I, refus
des lignes tronquées, image Movie Maker, AUX et garde de pile préservées,
volume source intégral inchangé. Le banc utilise uniquement un volume
jetable. Les lecteurs graphiques n'ont pas été relancés dans ce parcours ;
le matériel Apple II physique reste non testé.

Multiplan importé en BIN : MULTPLAN et l'identification acceptent aussi les
sauvegardes normales 1.06 conservées intactes en ProDOS BIN. La signature
de huit octets reste obligatoire ; les modules de code et autres formats
ne sont pas admis par cette règle. Le lecteur vérifie toujours l'espace
de travail de 666 octets, les dimensions, le pool, toutes les cellules,
leurs débuts exacts et les valeurs BCD avant affichage. Les valeurs mises
en cache et tokens de formules sont visibles sans recalcul. Les sources,
volumes et AUX ne sont jamais écrits ; le fallback DOS reste inchangé.

Qualification du 12 octobre : les sept originaux produisent exactement la
même sortie en BIN et F4 avec le vrai C sur l'hôte et les deux simulateurs
CPU. Les étapes réelles et le classement du corpus identifient les imports
BIN. Les essais couvrent signature corrompue, en-tête tronqué, dimensions,
table de pointeurs et pool incohérents, pointeurs au milieu d'un record ou
hors pool, BCD invalide, tailles de panneau périmées et erreurs d'ouverture,
lecture, recherche et fermeture. Chaque source est comparée octet pour octet.

Détecteur (11), lecteurs texte (8) et DOS (12) passent avec cc65 2.19 et HEAD.
Les deux compilations natives, les quatre images, le relais IDENT et
l'inventaire des bancs passent avec leurs contrôles actifs. IDV1 finit à
`$3F2D` (65C02) / `$3F99` (6502), MULTPLAN à `$362A` / `$3639`, sous `$4000`.
L'analyse de signedness reste à zéro site.

POM2 passe 7/7 contrôles Multiplan ciblés par CPU : ouverture de l'import BIN
par Entrée/I, valeurs décimales et jetons de formules visibles, refus d'un
pointeur de cellule invalide, AUX et garde de pile préservées, volume source
intégral inchangé. Le banc utilise uniquement un volume jetable. Le parcours
complet des sept lecteurs n'a pas été relancé pour cette qualification ; le
matériel Apple II physique reste non testé.

## Préservation

Navigation Movie Maker (12 octobre 2026) : Espace/Entrée/Bas/Droite avancent.
S/s active l'avance automatique puis l'arrête sur l'image courante. Une
autre touche arrête l'automatisme et effectue son action habituelle,
sauf 1/2/3 qui choisissent la vitesse rapide/normale/lente, sans avancer
ni désactiver l'automatisme. Un changement relance l'attente courante.
La vitesse est conservée en navigation et réinitialisée à l'ouverture.
L'attente partage la routine clavier du diaporama : environ 0,7/2,9/5,8
secondes à 1 MHz, plus le rendu, plus court sur une machine accélérée. Le film
revient aux panneaux à la fin. Q/q active/désactive la boucle automatique
sans avancer ni interrompre la lecture : après la dernière image, le
parcours vérifié reconstruit la première, avec vitesse, décor et miroirs
conservés. S garde son rôle de pause/reprise. L’avance manuelle à la fin
revient toujours aux panneaux ; une ouverture redémarre en mode manuel,
boucle désactivée.
B/Haut/Gauche reviennent à l'image précédente, R redémarre, L atteint la
dernière image et Échap quitte. Le nombre d'images provient de la validation
initiale complète ; L relit les commandes sans afficher les images
intermédiaires. Un film long peut donc nécessiter une relecture longue.
Les touches +/− avancent/reculent de dix images, sans dépasser la
dernière/première ; les images intermédiaires ne sont pas affichées.
O/o bascule entre le décor seul et l'aperçu avec acteurs, sur la même
image. Ce choix reste actif pendant la navigation ; une nouvelle ouverture
rétablit les acteurs. Le rendu du décor et des acteurs utilise les lectures
et recherches contrôlées existantes, sans AUX ni modification source.
H/V (majuscules ou minuscules) inversent l'aperçu horizontalement ou
verticalement, décor compris. Chaque touche restaure son orientation au
second appui. Les miroirs restent actifs pendant la navigation et sont
réinitialisés à l'ouverture ; seul le tampon de rendu MAIN est transformé.
Revenir avant la première image conserve celle-ci ; les touches sans action
ne font pas avancer. Le retour relit les commandes depuis le début de
l'animation, avec recherches et lectures contrôlées, sans table d'historique
ni banque AUX. La validation complète et la fermeture initiales restent
obligatoires. Les tests du vrai C comparent les pixels de trois images après
avance, retour et redémarrage, ainsi que les refus de recherche/lecture ;
les tests médias couvrent aussi L, les sauts +/− de dix images, un film à
une image, plus de 255 images, les bornes et les erreurs de relecture sur
les deux CPU. Les tests couvrent aussi O/o, les décors colorés, la navigation
avec/sans acteurs, les miroirs H/V, les acteurs coupés aux bords et les
erreurs de redessin, l'avance automatique, sa pause et son interruption.
Les 19 tests médias passent, y compris les changements de vitesse, les
boucles sur films à une ou plusieurs images, leur désactivation, les pauses
et les erreurs de recherche/lecture/fermeture pendant la relecture,
avec cc65 2.19 et HEAD. Le banc Movie Maker complet passe 83/83 contrôles par CPU ;
le parcours temporisation/vitesses/boucles ciblé rassemble 30 contrôles par CPU
et compare les octets de chaque
image après navigation, AUX, garde de pile et volume entier préservés.

Films importés aux $0000 (12 octobre 2026) : l'identification réutilise les
en-têtes de formes et bitmaps, les bornes et l'EOF réel des films aux $6000.
Le lecteur complet est inchangé : pas d'exécution des commandes de code
machine, aperçu opaque 40×48 dans MAIN, aucune écriture AUX ou source.
Les treize films originaux renommés sont reconnus par le vrai relais IDENT
et donnent le même aperçu C sur l'hôte et les deux CPU. Les suites médias
(10), détecteur (14) et DOS (12) passent avec cc65 2.19 et HEAD.
Le fallback DOS est conservé, aucun lecteur direct DOS MVM n'est ajouté.

POM2 `bench/v1viewers.py --movies-only` passe 7/7 contrôles par CPU : Entrée/I,
image couleur visible, refus d'un import tronqué, AUX et garde de pile
préservées, volume source intégral inchangé. Le banc utilise uniquement un
volume jetable. Le parcours complet des sept lecteurs n'a pas été relancé ;
le matériel Apple II physique reste non testé. Les compilations et quatre
images passent avec tous les contrôles mémoire ; IDV1 finit à `$3F41`
(65C02) / `$3FAD` (6502), sous `$4000`. Signedness : zéro site.

Les quatre lecteurs texte utilisent MAIN et les pages texte. MVMOVIE utilise
également la page lores MAIN, sans toucher au disque RAM auxiliaire. Leurs
premiers passages lisent, valident et ferment tout le fichier avant affichage.
Les erreurs d'ouverture, lecture, recherche ou fermeture sont des erreurs.
La taille du panneau n'est pas une limite de lecture.

DGMAGI et PCSVW valident et ferment d'abord, puis demandent `aux_consent`
avant la première écriture dans AUX $4000–$7FFF. Une source dans `/RAM` est
refusée : il faut d'abord la copier sur un autre volume. `/RAM` occupé doit
être confirmé dans l'interface avec l'avertissement que **TOUS ses fichiers
seront perdus** ; un disque dont l'en-tête indique zéro fichier ne pose pas
la question. Le refus préserve AUX. Après utilisation, y compris après un
échec du second passage, le petit code de retour reconstruit `/RAM`. Un
échec de reconstruction est affiché explicitement.

L'en-tête, le code de retour et son état tiennent dans MAIN $1B00–$1CFF.
Le C et sa BSS sont bornés à $1D00–$3FFF. Le C a complètement retourné avant
que l'image remplace MAIN $2000–$3FFF. Aucun plafond d'overlay ou de pile
n'est relevé. Les sources et volumes ne sont jamais écrits par ces lecteurs.

## Corpus et vérifications

Le [manifeste](corpus/v1-formats.json) donne les tailles et SHA256 des
**24 documents WordPerfect, 41 MouseWrite, 20 bases AFILER, 7 feuilles
Multiplan, 13 films MVM, 6 tables PCS et une palette DHGR**. Les sept feuilles
Multiplan sont des données de test enregistrées par le programme original
v1.06 : textes, nombres, cellule vide, coordonnées multiples et formule avec
valeur mémorisée. Ce ne sont pas sept documents de gestion trouvés dans une
archive publique. Les [sources téléchargées](corpus/v1-sources.json) ne
redistribuent aucun de leurs fichiers. `tools/v1_corpus.py` reconstruit les
extractions depuis les images locales : il garde le fichier R Multiplan
intact et accepte explicitement la géométrie particulière des disques
AFILER, sans modifier les octets des images. Les sorties sont créées
exclusivement ; une extraction différente préexistante n’est pas écrasée.

`tools/test_v1text.py` et `tools/test_v1media.py` exécutent les vrais
parseurs C sur l'hôte et avec cc65/sim65 pour les deux CPU. Les cas couvrent
les structures malformées, contrôles et pointeurs de cellules, fin de fichier,
tailles périmées, refus AUX et erreurs d'ouverture/lecture/recherche/fermeture.
Les octets de chaque source sont comparés après lecture. Les motifs DHGR,
sans commandes texte, correspondent aux 16384 octets produits par les deux
pilotes Graphics Magician originaux exécutés dans `tools/dgmagi_original.py`.
Le texte utilise une autre police et n'est donc pas inclus dans cet oracle.

`bench/v1viewers.py` charge les vrais overlays dans POM2 : routage des sept
lecteurs, rendu, refus d'effacer `/RAM`, reconstruction, canari de pile,
préservation AUX des lecteurs texte/MVM et comparaison complète du HD jetable.
Les images de référence PCS vérifient la stabilité de notre aperçu : elles ne
constituent pas un oracle du rendu original de tous les objets du jeu.

## Requalification du 27 octobre 2026

Sept feuilles ont été recréées avec Microsoft Multiplan 1.06 original sur
un disque DOS jetable : vide, texte, nombre, formule, grille et deux variantes
à plusieurs cellules. Les valeurs saisies et les feuilles affichées par le
programme original servent d'oracle ; les fichiers ne sont pas produits par
le lecteur A2FC. Le [manifeste](corpus/2026-10-27-multiplan-requalification.json)
porte leurs empreintes. Les sept [fichiers de régression](../tools/fixtures/multiplan)
sont versionnés ; ils ne contiennent pas le programme original. Le manifeste
ne remplace pas les empreintes historiques du
10 octobre, dont les sept fichiers locaux n'étaient plus disponibles.

Cette reconstruction a révélé une confusion entre les dimensions sauvegardées
(mots aux offsets décimaux 250 et 252) et la position du curseur (628 et 630).
Une grille de 5 lignes et 3 colonnes était refusée après retour du curseur en
R1C1. MULTPLAN utilise maintenant les dimensions de la grille ; les contrôles
de taille, pointeurs de cellules, limites du pool et BCD restent actifs.
Les régressions indépendantes font varier le curseur sans changer les
cellules et refusent des dimensions nulles, excessives ou incohérentes.
Le vrai code C est exécuté sur l'hôte et sous sim65 pour les deux CPU, avec
erreurs d'ouverture, lecture, recherche et fermeture, et sources préservées.

## Distribution et compression

Les deux XL se construisent avec les sept lecteurs et IDV1. Pour la 1.0,
la 800 Ko contient la sélection de `config/800k.mk` (99 surcouches), sans
corpus de démonstration ; les lecteurs spécialisés omis nécessitent XL.
L'essai de trous ProDOS pour les blocs nuls et le placement compact du code
graphique ne suffisent pas, aucun outil n'a été retiré pour masquer cela.

Le [chargeur ZXLOADER.SYSTEM](https://www.colino.net/wordpress/archives/2026/10/10/zxloader-system-a-compressed-binary-loader-for-apple-ii/)
fournit une piste : notre mesure du compresseur ZX02 sur 125 overlays 6502
passe de 581709 à 324869 octets (44,2 %), et de 1327 à 825 blocs ProDOS,
soit 502 blocs économisés. Ce résultat est une mesure de compression, pas
une qualification de chargement. ZXLOADER lance un programme complet ;
A2FC doit adapter son propre chargement et ses relais IDENT, avec limites
sur l'entrée, la sortie, les références arrière et les erreurs. Aucun
chargement compressé n'est encore activé, ni promesse de gain RAM.

Qualification native finale : **15/15 contrôles sur chaque CPU** (IIe 6502
non amélioré et IIe 65C02), avec comparaison complète du HD jetable.
Les extractions reconstruites par `v1_corpus.py` passent également les six
tests texte, dont les comparaisons C/sim65 des deux architectures.

## Étude de la remise en service d’une édition 140 Ko

Le même compresseur, avec décompression hôte et comparaison octet pour octet,
réduit le programme principal 6502 de **35155 à 20241 octets**. Le socle de
l’amorce 140 Ko, mesuré avec les binaires actuels, représente **269 blocs
fichiers avant compression et 195 après**. Avec neuf blocs système et de
répertoires, on passe de 278 à **204 blocs sur 280**, avant ajout du nouveau
chargeur et de son enveloppe de validation : 74 blocs, soit 37 Kio, gagnés.

C’est assez pour envisager une édition 140 Ko réduite et choisir davantage
d’outils. Ajouter les sept lecteurs et les quatre étapes IDENT au socle
mesuré demande déjà **284 blocs fichiers/système**, avant le chargeur, le
répertoire supplémentaire et les licences : la sélection doit donc être
adaptée. Tous les outils de l’édition complète ne tiennent pas sur une
unique 140 Ko, même compressés.

La baisse des blocs lus peut également réduire le chargement Disk II/3,5
pouces. Ce gain dépend du temps de décompression sur 6502/65C02 et du débit
réel du lecteur. La qualification devra mesurer séparément démarrage et
chargement des outils, avec les mêmes fichiers sur images jetables ; aucun
pourcentage de gain de temps n’est annoncé à partir du seul gain de taille.
La décompression devrait utiliser MAIN avec des entrées et sorties bornées,
conserver /RAM et valider intégralement le module avant son exécution.
