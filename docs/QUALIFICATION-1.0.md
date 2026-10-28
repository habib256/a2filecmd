# Préparation et qualification de la version 1.0

Préparation : 27 octobre 2026. Contrôles finaux : 28 octobre 2026. Version publiée : `1.0`, tag `v1.0`.

**Qualification automatisée terminée : 172/172 étapes natives validées,
aucune ignorée, et 2 437 tests hôtes sans échec.** Les corrections et les
rejeux ciblés sont détaillés ci-dessous ; les premiers journaux d’échec
restent conservés. La recette sur matériel physique reste à effectuer.
La release a ensuite été publiée le 28 octobre 2026 ; les contrôles de
publication sont consignés à la fin de ce rapport.

## Périmètre

La 1.0 consolide la 0.9.9 avec les corrections de préservation des données
consignées dans le [changelog](../CHANGELOG.md) : publication des copies,
annulation, validation des répertoires, remplacement de fichiers, écritures
brutes et marges mémoire. La qualification a aussi corrigé le lecteur Multiplan et l’identification VisiCalc/Arlequin/LISA, le routage des
images Purplesoft et la sonde de protection Disk II. Le décodeur Multiplan
et l’identification ne modifient pas les sources ; le décodeur travaille en
MAIN et sur l’écran texte, sans reconstruction de /RAM. La sonde Disk II
agit sur les commutateurs du contrôleur en mode lecture, sans écriture
physique ni accès à AUX.
Les écritures de construction concernent `build/`, `build-6502/`, `build-mini/` et `dist/`.
Les bancs travaillent sur des copies et des volumes jetables.

## Constructions et distribution

- `make disk` puis `make ARCH=6502 xplugins` : quatre images construites,
  avec les gardes de disposition mémoire actifs. Compilateurs locaux :
  cc65 stable 2.19 (Homebrew ; cl65 annonce V2.18) pour apple2enh ;
  cl65 master V2.19, commit `e11fb5c39`, pour
  apple2 (le commit fixé par la CI).
- `python3 tools/check_images.py` : les quatre images correspondent aux
  binaires et à leur disposition. La 800K contient 99 surcouches et
  170 blocs libres ; XL 6502 et enhanced contiennent chacune 130 surcouches,
  avec respectivement 60 020 et 60 024 blocs libres. Mini : pistes de boot
  et fichiers identiques à la construction.
- `tools/check_layout.py` : MAIN conserve 324 octets sur 65C02, 678 sur
  6502 ; LC conserve 40 octets sur chaque architecture. La pile C réservée
  reste de 192 octets. OPEN remplit sa fenêtre ; COPY a 1 octet libre sur
  65C02, TEXT 3 sur 6502. Ces marges ne sont pas additives.
  Mini termine exactement à $9600 (début des buffers DOS) et sa zone basse
  à $2000 : aucune marge dans ces deux zones ; FORMAT garde 5 octets avant
  les vecteurs DOS. Les trois frontières passent leur garde de disposition.
- `python3 tools/release_notes.py --check-tag v1.0` : conforme.
- `dist/RELEASE_NOTES.md` décrit la 1.0, les quatre images et le PDF.
- `shasum -a 256 -c SHA256SUMS-1.0.txt`, depuis `dist/` : les quatre images
  et le manuel passent. Les anciennes images de `dist/` sont exclues du
  manifeste par `tools/release_assets.py`.

## Manuel

Le guide anglais et son PDF portent la version 1.0. Les lecteurs spécialisés
sont regroupés dans le chapitre de lecture : documents et feuilles avant
les images, puis lecteurs graphiques, avant la musique ; les crédits
terminent le guide. Le passage Print Shop en double est supprimé.

La pagination continue remplace les sauts de chapitre forcés. Les paragraphes
se répartissent en lignes entières avec au moins deux lignes de chaque côté ;
les titres restent avec le début du texte et les en-têtes de tableaux avec
leur première ligne, puis se répètent sur les pages suivantes.

Résultat : 19 pages au lieu de 25, sans réduction des caractères (corps
10,3 points). Vérification visuelle des pages rendues, comparaison du texte
extrait (seul le doublon est retiré), 12 signets et 12 liens de sommaire
pointant sur les mêmes chapitres. Un document de contrôle comportant un
paragraphe de 2 400 mots uniques et un tableau de 90 lignes a été rendu sur
9 pages : chaque mot et chaque ligne sont présents exactement une fois.

## Tests et sessions POM2

**172/172 étapes natives validées, aucune ignorée.** La campagne couvre
les deux processeurs, le démarrage, les opérations de fichiers, les erreurs
et annulations, les archives, les lecteurs, les médias, les cartes et Mini.
Les 39 bancs de plugins passent sur chaque CPU après les rejeux détaillés
ci-dessous. Movie Maker termine avec 83/83 contrôles sur chacun des deux CPU.
Le passage hôte final `make test` est terminé : 192 suites unittest,
2 437 cas, aucun échec et aucun cas ignoré. Il inclut les régressions du
contrôleur Disk II, de l’horloge monotone et du binaire de production
d’identification, avec la bibliothèque POM2 figée décrite ci-dessous.

```sh
POM2_ROOT=/tmp/a2fc-1.0-pom2-frozen \
A2FC_WILDERNESS_CORPUS=/tmp/a2fc-1.0-wilderness \
ZX02=/tmp/a2fc-1.0-zx02/build/zx02 make test
```

Le journal est conservé dans `full/final-host-tests.log` et son décompte
dans `full/host-test-results.json`. Le premier lancement sous sandbox était
bloqué par `compress` sur `/dev/stdout` ; le passage final ci-dessus a été
rejoué avec les droits nécessaires.

Les journaux et preuves locaux sont conservés dans `build/release-1.0/full/`.
Les résultats de la première sélection de 33 étapes ont été remplacés par
une campagne couvrant l’inventaire entier de `bench/all.py` : 172 étapes.
Le bilan `full/results.json` réunit le passage initial et les derniers
rejeux de chaque étape ; tous les résultats sont des succès. Les journaux
des lanceurs sont archivés dans `full/campaigns/`, avec les journaux enfants
dans les sous-dossiers de `full/`. Les résultats diagnostiques seuls ne
remplacent pas un rejeu final.

Corrections découvertes pendant cette campagne :

- Multiplan : lire les dimensions de la grille aux offsets 250/252 ; les
  mots 628/630 contiennent le curseur enregistré. Des feuilles originales
  valides étaient refusées lorsque le curseur revenait en haut à gauche.
  Les tests hôtes et les deux CPU exécutent le vrai décodeur ; la régression
  native ouvre aussi les cellules éloignées et refuse les dimensions invalides.
- Purplesoft : laisser les noms `.FOTO1`/`.FOTO2` atteindre PURPLE et sa
  validation de la paire complète, avant la reconnaissance HGR générique.
  Les deux plans sont comparés octet par octet ; AUX, pile et sources sont
  contrôlés sur les deux CPU.
- Identification VisiCalc/Arlequin : le compilateur cc65 2.19 réutilisait
  un pointeur temporaire non initialisé ou écrasé sur certains chemins où
  l’échantillon est à l’adresse constante $0E00. Les lectures de préfixes
  fixes passent maintenant par un accesseur isolé ; VisiCalc conserve aussi
  son parcours isolé. La régression compare le vrai binaire livré au C hôte
  sur 4 996 cas par CPU : corpus des tests de formats, données malformées,
  noms et 256 types de fichiers. Les octets de l’échantillon et la pile C
  sont préservés. Le relien de test exporte seulement les symboles privés
  et reste identique octet par octet au binaire livré après scellement.
  Le premier test reproduisait 18 échecs VisiCalc sur l’ancien binaire ;
  le rejeu interactif 65C02 a ensuite révélé le chemin Arlequin analogue.
- LISA 8/16 : reconnaître le source typé INT avant le repli d’exécution
  BASIC. Retour proposait RUN avant d’atteindre la reconnaissance LISA.
  Les deux CPU vérifient les sources originales, les limites d’en-tête et
  la conservation du comportement RUN des vrais programmes BAS/INT.
- DOSWRITE / DOSPUT / DOS33W : sonder la protection lorsque le séquenceur
  Disk II tourne, en activant le mode lecture avant le moteur. Moteur arrêté,
  le registre pouvait conserver des données précédentes. La régression
  exécute l’assembleur livré contre le contrôleur natif : 48 combinaisons
  CPU × slot 5/6 × lecteur 1/2 × moteur froid/actif/arrêté après lecture ×
  protection. Les octets du disque, AUX, la pile et l’état d’interruption
  sont contrôlés ; aucune écriture disque n’est autorisée par cette sonde.

Les attentes des bancs smoke, ROI, IDENT et RENAME sont adaptées à l’ordre
et aux descriptions actuels. GOTO parcourt maintenant suffisamment d’entrées
pour retrouver ses temporaires après les 130 surcouches de XL. Graphics
Magician et Arlequin attendent le contenu complet avant de le comparer.
Les comparaisons de contenu et les scénarios d’erreur restent actifs.
Le composite des 39 bancs de plugins respecte désormais l’exécution en
série du lanceur et bénéficie d’un délai global adapté à cette durée :
trois heures par composite par défaut, avec les mêmes assertions. Les
premiers passages mesurés prennent 95 et 115 minutes, veille de l’hôte comprise. Le
[délai du job](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes)
CI de qualification est porté à 12 heures sur le runner auto-hébergé pour
l’inventaire complet en série.

### Traçabilité des rejeux natifs

Le premier passage des 39 surcouches en série sur 6502 passe intégralement
(`full/final-native/plugins-6502.log`). Sur 65C02, le premier essai Arlequin
par Retour a révélé le second chemin du défaut de pointeur décrit plus haut.
Le contrôle ciblé après correction passe 21/21 ; son journal diagnostique
est conservé dans `full/arlequin-diagnostic.log`.

DOSREPL a aussi atteint un délai de chargement du menu après remplacement
par une disquette presque pleine. Le journal système permet de l’expliquer :
le banc commence à 18:12:09 ; le Mac entre en veille à 18:13:07, reprend à
18:41:20, et le timeout est écrit exactement à 18:41:20. Le délai utilisait
`time.time()` : l’heure civile avait avancé pendant que l’émulateur était
suspendu. Les autres longues durées affichées dans les premiers journaux
incluent également des périodes de veille.

Les délais des bancs et leur mesure de durée utilisent maintenant
`time.monotonic()` (`mach_absolute_time()` sur cet hôte). Les mêmes budgets
de temps actif et toutes les assertions restent en place. Deux régressions
simulent un saut d’une heure civile sans expiration prématurée, et vérifient
qu’un émulateur réellement bloqué expire toujours. Le diagnostic DOSREPL
identique passe 25/25, y compris le refus de disque plein sans écriture
(`full/dosrepl-diagnostic.log`). Les rejeux finaux en série passent sur les deux CPU, 25/25 contrôles chacun.
Un rejeu 6502 supplémentaire a exposé une attente trop large : un message
partiellement redessiné était pris pour un refus terminé. Le banc attend
maintenant la question complète ou le refus exact de manque de secteurs ;
le contrôle du disque plein confirme que tous ses octets sont préservés.
Le journal de veille est conservé dans `full/host-suspend-events.log`.

Seul `IDFORMATS.PLG` a changé sur chaque CPU après le correctif général de
préfixes ; les 135 autres produits binaires par architecture sont identiques.
Les ouvertures affectées (Arlequin, IDENT, VisiCalc et Purplesoft) ont
repassé en série sur les deux CPU, ainsi que les sources LISA 8/16.
Les 39 bancs de plugins sont couverts sur chaque CPU par le passage initial
et les rejeux ciblés ; les corrections tardives ne modifient que
`IDFORMATS.PLG`, sans changement du résident ni des autres lecteurs. Les journaux
d’échec ne sont pas réécrits : `full/results.json` distingue les succès
obtenus après ces rejeux et conserve le chemin des premiers résultats.

Le premier banc ShrinkIt 6502 a manqué deux observations de progression :
l’extraction était déjà terminée lors de la capture, et les fichiers extraits
étaient tous exacts. Le banc synchronise désormais le départ sur la question
AUX d’un /RAM jetable non vide, observe la progression à vitesse réelle puis
rétablit sa vitesse normale. Les deux CPU repassent avec les mêmes contrôles
de progression, de contenu, de source et de pile.

Le diagnostic des deux échecs Movie Maker montre la file de touches du banc :
à 1 MHz, le surlignage NAVFILM passait ensuite sur PALETTE puis TABLE sans
nouvel envoi de touche. Les touches Bas avaient été envoyées pendant les
redessins précédents. Le banc navigue désormais dans les panneaux à sa
vitesse normale puis revient à 1 MHz avant chaque ouverture pour contrôler
les temporisations du lecteur. Les comparaisons de chaque image et les
contrôles AUX, pile et disque source restent inchangés. Les deux rejeux
finaux passent chacun 83/83 contrôles : navigation, miroirs, acteurs,
lecture automatique, pause, trois vitesses, boucle et sortie. AUX, la pile
et tous les octets du volume source sont conservés.

### Corpus et dépendances

Les sources publiques manquantes ont été rétablies et leurs empreintes
comparées aux inventaires historiques : PFS, WordPro, WordPerfect, MouseWrite,
BS Filer, Print Shop, Apple Writer, Magic Window et MultiScribe notamment.
Les originaux MCS, Movie Maker et Pinball Construction Set sont utilisés.
La référence Dazzle Draw est produite par l’exécution du pilote original
6502 ; les images PCS servent à la comparaison hôte/native et ne constituent
pas une référence indépendante du rendu de l’application originale.

Les sept feuilles Multiplan historiques n’ont pas été retrouvées. Sept
nouvelles feuilles ont été créées au clavier avec Microsoft Multiplan 1.06
original sur un disque jetable, puis relues dans le programme original.
Le [manifeste de requalification](corpus/2026-10-27-multiplan-requalification.json)
distingue ces nouvelles empreintes des historiques, qui restent inchangées.
Les sept fichiers sont conservés dans `tools/fixtures/multiplan/` ; leurs
empreintes et leurs cellules attendues sont contrôlées par le vrai décodeur.
Le disque et le journal de relecture sont conservés avec les preuves locales.

Les bibliothèques POM2 nécessaires à Mini ont été construites ; les hôtes
macOS lient CoreFoundation. Les sources du dépôt POM2 local évoluant pendant
la campagne, une copie figée dans `/tmp/a2fc-1.0-pom2-frozen` sert aux derniers
passages. `POM2_ROOT` désigne cette copie ; l’inventaire SHA-256 de ses
1 469 fichiers se trouve dans `full/pom2-frozen-sources.json`. Une archive locale des sources figées est aussi conservée avec les preuves.
Les bibliothèques et les hôtes de test sont reconstruits ensemble pour éviter un mélange
entre en-têtes et bibliothèque de versions différentes.
Le compresseur ZX02 expérimental et le corpus Wilderness sont également
présents pour exécuter leurs tests optionnels.

### Campagnes supplémentaires

- ProDOS : 1 500 scénarios, graine 27102026, zéro échec ; 295 écritures
  exercées et les 28 familles de contrôles couvertes.
- Archives : 2 500 scénarios, graine 27102026, zéro échec ; 5 451 sorties
  conservées et vérifiées contre les références.
- DIRSORT : 2 000 scénarios supplémentaires, graine 27102026, réussite.
- Deux constructions natives indépendantes : 136 produits binaires par
  architecture, tous identiques aux produits utilisés dans les images finales.
  Mini est également reconstruit dans un répertoire indépendant : binaire
  identique, version 1.0 et gardes mémoire valides.

## Limites restantes

- La recette sur matériel physique reste à faire, notamment le port série
  VDrive ([checklist](HARDWARE-CHECKLIST.md)). Les médias de recette jetables
  et leurs références sont préparés dans `dist/release-1.0/hw/`.
- ProDOS ne fournit pas d’atomicité des écritures physiques : une coupure
  pendant la publication ou des mises à jour de répertoire peut encore
  endommager les métadonnées. Conserver une sauvegarde avant une opération
  destructive et suivre [la récupération](MANUAL.md#recover-after-an-incident).
- Les contrôles de changement de volume ne distinguent pas toujours deux
  disques de même nom, ni deux disques sans volume ProDOS reconnu ; voir le
  changelog et le manuel avant les copies physiques.

## Publication du 28 octobre 2026

La [release 1.0](https://github.com/habib256/a2filecmd/releases/tag/v1.0)
est publiée comme version stable et dernière release. Le tag annoté `v1.0`
pointe sur le commit `70d60f4449857016d14150433fe7f2e652250b23`.

Le [workflow de publication](https://github.com/habib256/a2filecmd/actions/runs/40639049572)
est terminé avec succès : contrôle du tag, tests hôtes sous Linux,
construction des quatre images, gardes mémoire, relecture des images,
calcul des empreintes et publication. Le job POM2 GitHub est ignoré car la
variable `POM2_RUNNER` n’est pas configurée ; les 172 étapes POM2 ont été
qualifiées localement comme décrit ci-dessus.

Les six pièces jointes sont disponibles : quatre images, le manuel PDF et
`SHA256SUMS-1.0.txt`. Les cinq fichiers ont été retéléchargés depuis la
release et leurs empreintes vérifiées ; ils sont tous identiques octet
par octet aux artefacts qualifiés localement. Les preuves sont conservées
dans `build/release-1.0/publication-ci.json`, `publication-artifacts.json`
et `published/`.

Le README pointe vers les téléchargements 1.0. La démo Web utilise la copie
exacte de l’image 800K publiée, sous `web/A2FILECMD-PRODOS-800K-1.0.po`.
