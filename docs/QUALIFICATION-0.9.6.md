# Qualification de la version 0.9.6

Date : 7 octobre 2026. Branche `release-0.9.6`, sources natives au commit
`b4cd129`. Qualification terminée avant publication du tag `v0.9.6`.
La recette sur matériel physique reste à faire
([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md)).

Cette version corrige les défauts relevés par deux audits de l’ensemble du
programme, sans ajouter de format ; elle réorganise les démonstrations et
actualise les documents ([CHANGELOG](../CHANGELOG.md#096-in-detail)).

## Vérifications automatisées

- `make test` : code de sortie 0 ; 1 646 tests unittest dans 144 rapports
  de suites, plus les oracles, exécutions sim65 et campagnes de mutation
  intégrés à la cible. Journal : `/tmp/a2fc-096-test.log`.
- `make qualify` : **119/119 étapes, aucune sautée**, les 82 entrées de banc
  de `bench/all.py`, `--setup --strict --jobs 1`. Les 39 bancs de surcouches
  passent sur chaque processeur. Résultats par étape dans `build/bench/`,
  résumé du parcours réussi dans
  `build/bench/qualification-0.9.6-summary.log`. Les essais exigeant des ports
  locaux et `compress` ont été exécutés hors sandbox.
- `make disk` : cinq images 0.9.6. Une seconde construction neuve à partir
  des mêmes sources, dans `/tmp/a2fc-096-clean`, produit les cinq images
  identiques octet pour octet ; les contrôles mémoire restent actifs.
- `python3 tools/check_images.py` : 5/5 images ; fichiers, lanceurs et
  surcouches comparés aux builds. 140K : 18 surcouches, 18 blocs libres ;
  800K : 87 surcouches, 476 libres ; XL : 87 surcouches, 60 642 libres.
- `check_layout.py` : deux architectures valides. Réserves 65C02 / 6502 :
  MAIN 9 / 389 octets, LC 13 / 11, LOWRAM 84 / 109, OPEN 11 / 11,
  COPY 13 / 10, DISKIMG 206 / 161. Mini : 3 octets sous DOS, 5 sous
  la zone de travail, 5 sous les vecteurs DOS pour FORMAT.
  Le banc `memory:stack` mesure 145 octets utilisés sur 192, soit 47 de marge.
  [Table complète](MEMORY-BUDGETS.md).
- `release_notes.py --check-tag v0.9.6` : accepté. Notes générées dans
  `dist/RELEASE_NOTES.md` ; cinq images et PDF seulement dans le manifeste.
- Manuel : version et noms d’images 0.9.6 ; capture depuis une copie jetable
  de la XL enhanced, image originale inchangée, empreinte et preset dans
  [la provenance](screenshots/prodos-panels-0.9.6.json).
  PDF régénéré : 21 pages A4, 12 signets, couverture et sommaire contrôlés,
  DOS3.3 en premier chapitre.

## Bancs POM2

| Groupe | Étapes validées |
| --- | ---: |
| boot | 6/6 |
| core | 18/18 |
| dos | 10/10 |
| safety | 21/21 |
| session | 10/10 |
| xl | 5/5 |
| plugins | 2/2 |
| readers | 11/11 |
| archives | 4/4 |
| media | 18/18 |
| cards | 6/6 |
| mini | 8/8 |

Les essais destructifs utilisent des volumes et disquettes jetables.
Copies et extractions contrôlent leurs octets ; les refus de REPAIR, IMGPUT
et des échanges DISKIMG contrôlent aussi les images conservées. Les
contrôles de pile, de tags, de consentement AUX et de Ctrl-Reset passent.

Le contrôle final du manifeste a détecté une modification de 602 octets
sur quatre blocs de la XL enhanced dans `dist/`, avec une entrée
`BK.MEADOW` ajoutée à la racine. Son origine n’a pas été établie ; aucun
émulateur ne tournait lors du contrôle. Cette image a été conservée à part
dans `/tmp/a2fc-096-enhanced-altered.2mg`, puis remplacée par celle de la
construction neuve. Les cinq images du paquet final sont de nouveau
identiques à cette construction et passent `check_images.py`. Ce constat
justifie de vérifier les empreintes après les essais, même si les bancs
et le contrôle des fichiers livrés passent.

## Empreintes de la construction locale

Le manifeste `dist/SHA256SUMS-0.9.6.txt` couvre les cinq images et le PDF :

```
e1dfa8de0660edab53b9ebe1a68ab100fc11a4cecabd3fc91593cd8fb4020f2b  A2FILECMD-PRODOS-XL-0.9.6.2mg
d8a58c2560f52a36571956b8f0cde445c1f0bb0b8943c375f35a9f58e6e49b63  A2FILECMD-PRODOS-XL-65C02-enhanced-0.9.6.2mg
3fc881e9b85cf908b0545ba44992b4db27a82ed5d603d8e021394206a8398087  A2FILECMD-DOS3.3-0.9.6.dsk
2bc07a481a5f3de6b3e2f8173e092c9a844a73091c4b8ed35f9149e423639b47  A2FILECMD-PRODOS-800K-0.9.6.po
4452384cec4db32ff41b423907e52c95d8884ee3aa6a2c62f54b4a739998c9c1  A2FILECMD-PRODOS-140K-0.9.6.dsk
d2c5374654d56f70ac09368a6e27959716dfd6ae162f32681de85fd630af6036  A2FILECMD-MANUAL-EN-0.9.6.pdf
```

## Limites restantes

- La qualification émulateur ne constitue pas une recette matérielle.
  VDrive à 115 200 bauds, les formats de la 0.9.5 et les lecteurs physiques
  restent à vérifier sur les machines de la checklist.
- Un échange de disque avec un bloc d’identité identique, ou après le début
  des écritures, n’est pas couvert par les contrôles d’identité.
- REPAIR ne peut pas distinguer un bloc perdu après suppression interrompue
  d’un bloc qui appartenait à un fichier endommagé ; `FREE` est une
  décision explicite de l’utilisateur, pas une preuve d’absence de données.
- Aucune atomicité promise pendant une coupure d’alimentation ou une
  écriture physique interrompue. Garder les originaux et suivre
  [les consignes de récupération](MANUAL.md#recover-after-an-incident).

## Publication

Le paquet local `dist/release-0.9.6/` contient les cinq images, le PDF,
`SHA256SUMS-0.9.6.txt` et `RELEASE_NOTES.md` comme description. Les huit
fichiers sont ceux du candidat, sans anciennes images de `dist/`. Le workflow `.github/workflows/ci.yml`
reconstruit les images et publie lors du push du tag `v0.9.6` ; ne le pousser
qu’après qualification terminée. Les téléchargements du README ciblent
la 0.9.6. Les empreintes jointes à la release sont celles de la construction
CI publiée ; celles ci-dessus identifient la construction locale qualifiée.
