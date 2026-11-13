# Commandes du bot

Ce fichier consigne les commandes de Telegram du bureau d'idées : celles qui existent, la règle
qui s'applique à un message sans commande, et celles qu'il reste à concevoir. Il se met à jour
avec chaque commande ajoutée ou décidée.

Seul le propriétaire est servi. Une commande inconnue est ignorée sans réponse. Les commandes
`/newidea` et `/prete` sont aussi enregistrées dans le menu `/` de Telegram au démarrage.

## Commandes en place

| Commande | Où | Effet |
|---|---|---|
| `/newidea` | n'importe où | Crée un fil nommé « New idea » et y invite à écrire l'idée. Le message suivant dans ce fil devient l'idée. Sans le Threaded mode du bot, répond comment l'activer. |
| `/newidea <texte>` | n'importe où | Crée directement la fiche avec ce texte, dans son propre fil, comme une idée écrite hors de tout fil. |
| `/prete` | dans le fil d'une idée | Passe la fiche au statut « prête » et renvoie son lien. Hors du fil d'une idée, explique où l'utiliser. |

`/newidea@nom_du_bot` est reconnu comme `/newidea`.

## Message sans commande

| Où il arrive | Effet |
|---|---|
| Hors de tout fil | Nouvelle idée : le bot crée un fil, enregistre le brouillon, accuse réception avec le lien, puis envoie les objections. |
| Dans un fil sans fiche (par exemple celui que le propriétaire vient de créer, ou celui ouvert par `/newidea`) | Nouvelle idée rattachée à ce fil, sans créer d'autre fil. |
| Dans le fil d'une fiche | Réponse : elle est intégrée à la fiche, qui est mise à jour. Si le challenge avait échoué, il est relancé d'abord. |

## Langue

La langue d'une fiche (français ou anglais) est choisie selon le **sujet** : français si l'idée
concerne la France, anglais sinon, quelle que soit la langue dans laquelle le propriétaire écrit.
L'accusé de réception est bilingue, car il part avant ce choix.

## À concevoir

Pistes issues de la conversation, **non décidées**. Chacune garde sa question ouverte.

| Piste | À trancher |
|---|---|
| `/lang fr` ou `/lang en` | Forcer la langue d'une fiche quand le choix automatique ne convient pas. Dans le fil d'une fiche seulement ? Réécrit-elle les sections déjà écrites ? |
| `/rechallenge` | Relancer à la main le challenge d'une fiche. Aujourd'hui, une réponse sur un challenge raté le relance seulement. |
| `/brouillons` | Lister les brouillons sans réponse, avec leur lien. Lien avec le digest hebdomadaire reporté. |
| `/chercher <question>` | Recherche conversationnelle dans la bibliothèque, reportée avec ce plan. Renvoie-t-elle les fiches sources ? |
| `/lier` | Rapprocher la fiche d'autres fiches existantes (reporté). Automatique à la création ou sur demande ? |
| `/construire` | Lancer le travail à partir d'une fiche prête (moteur d'action, reporté). Où tourne-t-il : Onyxia ou cloud Claude ? Qui valide ? |
| `/explorer` | Exploration autonome sous plafond de quota (reportée). Plafond, droits d'écriture, format du compte rendu. |
| `/archiver` | Retirer une fiche de la liste sans la supprimer. Statut de plus, ou suppression ? |

Une piste devient une commande quand elle reçoit une ligne dans « Commandes en place », un test,
et son entrée dans le menu `/` de Telegram.
