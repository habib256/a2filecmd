# Les sept lecteurs retenus pour la 1.0

Les lecteurs sont intégrés au menu et au routage automatique IDENT, dans
les éditions ProDOS 6502 et 65C02. Le numéro publié reste 0.9.6 : ce travail
ne publie pas une version 1.0 et n'annonce pas encore une qualification de
release complète. Les fichiers d'entrée sont ouverts uniquement en lecture.

| Format | Module | Profil couvert | Limites |
|---|---|---|---|
| WordPerfect Apple II | WORDPERF | ProDOS $A0/$0000, texte paginé, notes et groupes de commandes connus | Texte sans mise en page ; groupes multioctets inconnus refusés, contrôles simples non interprétés rendus visibles. Pas WordPerfect GS. |
| MouseWrite | MOUSEWR | ProDOS $F1/$0000, en-têtes MW 1/4/5, largeur de ligne enregistrée | Texte ; polices et dessins non reproduits. |
| Bank Street Filer | BSFILER | AFILER 1.0 extrait en BIN : formulaire, enregistrements, textes, flottants et dates | Flottants à trois décimales tronquées ; valeurs extrêmes montrées en hexadécimal. Champs calculés signalés, pas exécutés. |
| Multiplan | MULTPLAN | Sauvegarde normale v1.06 extraite intacte en ProDOS $F4 : coordonnées, valeurs BCD et tokens de formules | Pas de recalcul, de sauvegarde Symbolic ni de lecture directe DOS R. Ne pas retirer un prétendu en-tête LISA des fichiers R. |
| Films Movie Maker | MVMOVIE | Séquence 01/02/03/06/05/00/07, aperçu couleur 40×48, image suivante au clavier | Rectangles de formes opaques, masque transparent et cadence originale absents. Ce n'est pas une reproduction HGR fidèle du film. Commande de code machine et autres modes refusés. |
| Graphics Magician DHGR | DGMAGI | .DPC 560 points, lignes, pinceaux, remplissages et 256 motifs ; deux banques DHGR | Police de remplacement pour le texte ; ligne de couleur transitoire (commande 7) refusée. |
| Pinball Construction Set | PCSVW | .PB : fond HGR enregistré, remplissage des polygones et contours LIB | Aperçu statique ; pas les sprites exacts des objets LIB, la physique ou les scripts. Aucun code du jeu exécuté. |

Ces profils prennent des fichiers ProDOS. Les données DOS des originaux
peuvent être extraites avant lecture ; la reconnaissance d'un candidat DOS
n'est pas une promesse de décodage direct. Les deux architectures ont les
mêmes limites. Une extension ou un type produit un candidat, le lecteur
vérifie ensuite la structure entière et la fin physique du fichier.

## Préservation

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

L'en-tête, le code de retour et son état tiennent dans MAIN $1B00–$1C9F.
Le C et sa BSS sont bornés à $1CA0–$3FFF. Le C a complètement retourné avant
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

## Distribution et compression

Les deux XL se construisent avec les sept lecteurs et IDV1. L'édition 800 Ko
complète dépasse encore sa capacité ; elle doit être corrigée avant la 1.0.
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
