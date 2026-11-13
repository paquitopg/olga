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
| `/rechallenge` | dans le fil d'une idée | Demande de nouvelles objections sourcées, sans répéter les précédentes. Elles s'ajoutent (numérotation qui continue) : les anciennes objections et vos réponses restent. La langue de la fiche ne change pas. Si ce nouvel essai échoue, le challenge déjà réussi n'est pas défait. |
| `/explore` ou `/explore N` | n'importe où | Dépense le quota Claude restant : Claude propose `N` idées **voisines** de vos 20 fiches les plus récentes (3 par défaut, de 1 à 10), le bot crée un brouillon et un fil pour chacune, puis lance le challenge habituel (benchmark sourcé, regard France). Résumé final avec le quota consommé. Voir « Quota » ci-dessous. |
| `/lang fr` ou `/lang en` | dans le fil d'une idée | Force la langue de la fiche : titres de sections, messages du bot, page du site et textes générés ensuite. Les textes déjà écrits ne sont pas traduits. |

`/newidea@nom_du_bot` est reconnu comme `/newidea`.

## Message sans commande

| Où il arrive | Effet |
|---|---|
| Hors de tout fil | Nouvelle idée : le bot crée un fil, enregistre le brouillon, accuse réception avec le lien, puis envoie les objections. |
| Dans un fil sans fiche (par exemple celui que le propriétaire vient de créer, ou celui ouvert par `/newidea`) | Nouvelle idée rattachée à ce fil, sans créer d'autre fil. |
| Dans le fil d'une fiche | Réponse : elle est intégrée à la fiche, qui est mise à jour. Si le challenge avait échoué, il est relancé d'abord. |

## Quota de `/explore`

Le bot lit votre consommation à chaque appel à Claude : fenêtre de 5 heures et fenêtre de 7 jours
(événement `rate_limit_event` de `claude -p --output-format stream-json`). `/explore` fait d'abord un
appel minimal pour la lire, puis la relit avant chaque nouvelle idée.

- Il s'arrête quand la fenêtre de **5 heures est épuisée** (seuil 100 %) ou quand celle de **7 jours
  atteint 85 %**, ou quand Claude refuse un appel. Réglables : `EXPLORE_MAX_FIVE_HOUR` (défaut `1.0`) et
  `EXPLORE_MAX_SEVEN_DAY` (défaut `0.85`), lus comme les autres réglages (environnement ou `/secrets/app`).
- Il ne démarre pas si un seuil est déjà dépassé, ou si le quota est illisible : il le dit.
- Le quota est partagé avec votre propre usage de Claude : épuiser la fenêtre de 5 heures bloque aussi
  vos autres sessions jusqu'à sa remise à zéro.
- Une seule exploration à la fois, jamais en tâche de fond : elle ne tourne que sur commande.

## Regard « France » du challenge

Le propriétaire vit en France. Le challenge ne traite jamais un concurrent étranger (américain par
exemple) comme un obstacle en soi : il évalue l'ouverture du marché français et européen (langue,
réglementation, canaux de distribution, clients, acteurs français) et dit ce que les concurrents
étrangers laissent ouvert en France. Une objection au moins porte sur cette ouverture.

## Langue

La langue d'une fiche (français ou anglais) est choisie selon le **sujet** : français si l'idée
concerne la France, anglais sinon, quelle que soit la langue dans laquelle le propriétaire écrit.
L'accusé de réception est bilingue, car il part avant ce choix.

## À concevoir

Pistes issues de la conversation, **non décidées**. Chacune garde sa question ouverte.

| Piste | À trancher |
|---|---|
| `/brouillons` | Lister les brouillons sans réponse, avec leur lien. Lien avec le digest hebdomadaire reporté. |
| `/chercher <question>` | Recherche conversationnelle dans la bibliothèque, reportée avec ce plan. Renvoie-t-elle les fiches sources ? |
| `/lier` | Rapprocher la fiche d'autres fiches existantes (reporté). Automatique à la création ou sur demande ? |
| `/construire` | Lancer le travail à partir d'une fiche prête (moteur d'action, reporté). Où tourne-t-il : Onyxia ou cloud Claude ? Qui valide ? |
| Exploration planifiée | `/explore` ne tourne que sur commande. Faut-il aussi une exploration automatique à heure fixe, par exemple avant la remise à zéro hebdomadaire ? |
| `/archiver` | Retirer une fiche de la liste sans la supprimer. Statut de plus, ou suppression ? |

Une piste devient une commande quand elle reçoit une ligne dans « Commandes en place », un test,
et son entrée dans le menu `/` de Telegram.
