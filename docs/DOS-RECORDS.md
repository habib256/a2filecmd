# Texte DOS : enregistrements à accès aléatoire

`DOSREC` est un inspecteur en lecture seule pour les fichiers texte DOS 3.3.
Sélectionner le fichier, puis `!` → Files → DOSREC. Return garde le lecteur
texte habituel : la longueur d’un enregistrement n’est pas enregistrée dans
le fichier DOS et ne peut pas être déduite sans connaître son application.

La longueur se saisit en décimal, de 1 à 4096 ; Return sans chiffre choisit
256. N/P changent d’enregistrement ; Space/B changent de page dans un
même enregistrement ; R revient au premier ; L change la longueur.
Les enregistrements sont numérotés depuis zéro, les offsets sont hexadécimaux.

L’écran distingue `--` (secteur absent, `~` côté ASCII) de `00` (octet NUL
réel dans un secteur alloué). Les contrôles deviennent des points ; les
caractères sont affichés sans leur bit haut. Aucun NUL ne termine la lecture.
La limite est la fin du dernier secteur alloué : elle comprend le remplissage
et **ne représente pas un EOF exact**. Un dernier enregistrement peut être
partiel. Les plages logiques sautées par une chaîne T/S restent des trous.

## Bornes et préservation

Les VTOC, catalogues et chaînes T/S sont relus ; identité, nom, type,
cycles, secteurs invalides et alias sont contrôlés. Les offsets de listes
T/S doivent être des multiples croissants de 122, sans chevauchement.
Le lecteur couvre 560 secteurs logiques (143 360 octets), pas tous les
fichiers DOS creux qui pourraient adresser un espace logique plus grand.
Les autres lecteurs conservent leur validation séquentielle existante.

Tous les secteurs alloués sont lus et la source est fermée avant la saisie
de longueur. Chaque page est ensuite relue, validée et fermée avant son
nouvel affichage. Erreur de lecture, recherche ou fermeture : refus, jamais
fin normale. Le lecteur écrit seulement dans MAIN et l’écran texte ; il
ne reconstruit pas `/RAM`, n’écrit pas de disque et ne crée aucun temporaire.

Les tests exécutent le vrai C sur l’hôte et sous sim65 pour les deux CPU :
NUL, trous, T/S sautées, limites, dernier enregistrement partiel, navigation,
annulation, tailles de panneau périmées, structures invalides et injections
d’erreurs. Les bancs POM2 vérifient Disk II, DSK et 2MG jetables, la mémoire
auxiliaire, la garde de pile et les octets complets des volumes synchronisés.
Le cas natif vérifie aussi les `--` : le compilateur cc65 2.18 nécessitait
un test de bit explicitement réduit à un octet pour ce chemin d’affichage.

```sh
python3 tools/test_dos_records.py
A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/dos_records.py
A2FC_BUILD=build A2FC_PRESET=iie python3 bench/dos_records.py
```

Référence primaire : [CiderPress II, RandomText.cs](https://github.com/fadden/CiderPress2/blob/main/FileConv/Doc/RandomText.cs).
EOF exact, schémas des champs et interprétation métier restent inconnus.
