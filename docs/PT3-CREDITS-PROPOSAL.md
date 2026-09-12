# Titre et crédits PT3 — implémenté

    ProTracker 3 - YAZZIE.PT3
    Title: Yazzie - Ending
    Artist / module credit: n1k-o 30.11.2019
    Player: Vince Weaver - A2FC adapter

    Left/Right Track  P Pause/resume  ESC Back

Le titre (32 octets à l'offset 30) et le crédit (32 octets à l'offset 66)
sont affichés après validation du module. Les espaces et contrôles de bord
sont retirés ; les contrôles internes deviennent des espaces. Un champ vide
utilise le nom du fichier pour le titre et « Not specified » pour l'artiste.
Ce crédit libre peut contenir plusieurs auteurs, un arrangeur ou une date ;
aucune identité n'est déduite du nom du fichier ou de son répertoire.

Le crédit fixe du moteur est fondé sur les sources conservées dans
[src/plugins/pt3lib/README.md](../src/plugins/pt3lib/README.md) :
Vince Weaver, pt3_lib 0.5, option de licence 0BSD. « Adaptation A2FC » désigne
les bornes mémoire, la validation, l'interface et l'adaptation matérielle.
Les autres crédits d'optimisation restent dans les sources.

L'affichage est fourni par le service `music_info` du cœur, ajouté à l'API 4.
Le décodeur conserve sa fenêtre de code et ses 4 608 octets de module.
Aucun octet du module, fichier ou banque AUX n'est écrit par cet affichage.
Les tests C couvrent les champs vides, sans NUL, et les caractères de contrôle ;
`bench/media.py` vérifie les crédits réellement affichés sous POM2.
