# A2FC : la préservation des données prime

Ces instructions s'appliquent à tout le dépôt et à toute IA qui intervient
sur A2FC. La sécurité des données est une exigence centrale du logiciel,
pas une amélioration facultative. Une fonctionnalité, un gain de vitesse ou
quelques octets économisés ne justifient jamais une perte de données.

## Règles obligatoires

- Avant de modifier une opération, identifier les fichiers, volumes et banques
  mémoire qu'elle peut écrire, directement ou par un appel de bibliothèque.
  La mémoire auxiliaire peut contenir le disque ProDOS RAM : afficher une image,
  lire de la musique ou décompresser peut nécessiter sa reconstruction pour
  libérer de la place. Dans ce cas, avertir clairement que TOUS ses fichiers
  seront perdus et demander confirmation AVANT de toucher cette mémoire.
  Un message après la destruction ne suffit pas.
- Une erreur de lecture, de recherche, de métadonnées ou de fermeture n'est ni
  une fin de fichier normale, ni la preuve qu'un chemin est libre. En cas de
  doute, refuser l'écriture ou la suppression.
- Réserver les nouveaux fichiers par une création exclusive. Ne jamais ouvrir
  un chemin existant en mode tronquant à la suite d'une simple sonde de lecture.
  Ne nettoyer que les fichiers effectivement créés par l'opération en cours.
- Pour remplacer un fichier, conserver l'original récupérable jusqu'à la fin
  de l'écriture, de la fermeture et des contrôles. Traiter aussi les échecs de
  renommage, de restauration et de suppression des sauvegardes. Ne jamais
  écraser une sauvegarde ou un temporaire préexistant.
- Ne supprimer une source déplacée qu'après vérification complète de la copie.
  Une taille de panneau peut être périmée ; comparer un préfixe ne suffit pas.
  Une arborescence partiellement lue, copiée ou ignorée ne doit pas être effacée.
- Respecter les protections ProDOS, les limites des chemins et des buffers,
  les types de stockage, et les identités source/destination. Les écritures
  brutes contournent les protections du système : les contrôler explicitement.
- Pour les opérations volontairement destructrices, identifier précisément la
  cible et obtenir la confirmation dans l'interface avant la première écriture.
  Une confirmation ne dispense pas des contrôles de cohérence et d'erreurs.
- Ajouter des tests de régression pour chaque risque corrigé : erreurs de
  lecture/écriture/fermeture, disque plein, annulation, collisions de noms,
  données malformées, tailles périmées et échecs de renommage selon le cas.
  Exécuter le vrai code C lorsque possible et contrôler les octets conservés,
  pas seulement le message ou le code de retour.
- Valider les deux architectures et leurs limites mémoire après une modification
  native. Un dépassement d'overlay, de pile ou de BSS est aussi un risque pour
  les données. Ne jamais désactiver les contrôles de disposition pour faire
  passer une compilation.
- Utiliser uniquement des images jetables pour les essais destructifs. Ne pas
  tester sur les disques ou fichiers personnels de l'utilisateur.
- Décrire honnêtement les limites restantes, notamment les coupures pendant
  une écriture physique : ne pas promettre une atomicité que ProDOS ne fournit pas.

Ces règles autorisent les corrections et tests dans le périmètre demandé ;
elles n'ajoutent pas une étape de permission pour chaque correction réversible.
