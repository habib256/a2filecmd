# Qualification 0.9.5

Date : 4 octobre 2026. **Qualification automatisée : `make test` vert (aussi
rejoué avec un HOME vide, sans ROM ni échantillons privés, comme la CI) ;
bancs POM2 rejoués sur les deux processeurs, derniers groupes session, xl,
cartes et Mini : 29/29 étapes ; images reproductibles octet pour octet.**
Les essais sur matériel physique restent à faire
([HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md)).

0.9.5 apporte de nouveaux formats ([CHANGELOG](../CHANGELOG.md)) : VisiCalc,
Graphics Magician (salle blanche), films Take 1 et Fantavision, Newsroom
(photos, bannières, disquettes de clip art), Movie Maker, Epistole, Papyrus,
HomeWord, Bank Street Writer, écrans texte, polices HRCG, Terrapin Logo,
KoalaPad ; le lecteur PT3 de GROUiK (French Touch) en moteur principal, pas de
question quand /RAM est vide, Ctrl-Reset sûr après un lancement.

## Ce qui a été vérifié

- **Deux bug hunts** avant la publication : le premier par zones (PT3 et /RAM,
  VisiCalc, aiguillage et visionneuses, Take 1/NRCLIP/DOCVIEW), le second par
  une relecture neuve du diff, la reprise des défauts restants et la rejouée
  complète des bancs. Défauts corrigés, chacun avec un test qui échoue sans le
  correctif : Ctrl-Reset dans TAKE1, FANTA et tout programme lancé ; sept
  défauts de VISICALC ; une image hi-res prise pour un document Bank Street ;
  des programmes envoyés à GMAGIC (295 → 49) ; un fichier texte vide et un
  octet périmé ; une fermeture ratée dans VISICALC ; les messages d'activité
  écrits dans une image affichée.
- **Comparaisons à l'original** (oracles privés, hors dépôt) : GMAGIC 398/398
  images réelles et 84/84 calques identiques aux routines de Penguin ; Take 1
  8 093 images identiques sur les 15 films ; VisiCalc 27 030/27 045 cellules
  identiques sur 67 feuilles réelles ; PT3 : 394/400 modules aux registres
  identiques entre les deux moteurs.
- **Images** : `tools/check_images.py` sur les cinq images 0.9.5 ; la 140K
  garde 21 blocs libres, la 800K 480. Réserves au lien, 65C02/6502 : MAIN
  11/423, carte langage 30/21, OPEN 11/11.
- **Empreintes** (deux constructions identiques) :

```
abd21de2cd195e142c6b504581208bc96d8b417ebe13feb933f352b8b891b803  A2FILECMD-DOS3.3-0.9.5.dsk
f2d294bd4f37dfd1b2de524e4d51aa8b6060716d10e765e9c14fbfb321bc1ad7  A2FILECMD-PRODOS-140K-0.9.5.dsk
2c6342b48b98ceccd979e79b4c4484e872e507fe6737499109cc09e67fabba8a  A2FILECMD-PRODOS-800K-0.9.5.po
3dec2f28664991108b9ee3a98767768f458318fb304ff234f7da10df0fbeb6d0  A2FILECMD-PRODOS-XL-0.9.5.2mg
e2ba2c044e0656e3be30f22ce4dcc3a3e61d015401d55961fa69f1e7c51f8274  A2FILECMD-PRODOS-XL-65C02-enhanced-0.9.5.2mg
```

## Limites connues

- Pas d'écoute ni d'essai sur vrai matériel des nouveautés (PT3 de GROUiK,
  Take 1, GMAGIC, VisiCalc, écrans texte 80 colonnes).
- GMAGIC : les images 1984 de The Quest DR s'ouvrent en 1982 jusqu'à **D** ;
  49 programmes du corpus passent encore la sonde (refus, **H** pour l'hexa).
- VisiCalc : puissances et fonctions transcendantes par la ROM Applesoft
  (derniers chiffres possiblement différents) ; DIF non lu.
- Take 1 extrait sur ProDOS : collisions de noms sur certains disques.
- Coupure de courant pendant une écriture : aucune atomicité promise.
