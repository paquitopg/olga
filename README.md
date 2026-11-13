# Bureau d'idées sur Telegram

Un bot Telegram qui reçoit une idée brute, l'enregistre en brouillon, la challenge avec des
objections sourcées par une recherche web, intègre vos réponses dans une fiche structurée, et
publie la bibliothèque sur un site privé. Les fiches vivent dans un dépôt Git privé distinct
(`idea-library`).

Plan complet : `docs/plans/2026-11-13-1652-feat-telegram-idea-desk-plan.md`.

## Utilisation

La langue d'une fiche (français ou anglais) est choisie selon le sujet : français si l'idée concerne la France, anglais sinon, quelle que soit la langue dans laquelle vous écrivez.

- Envoyez une idée au bot : accusé immédiat avec le lien de la fiche, puis les objections.
- Répondez dans le fil de l'idée : la fiche est mise à jour, vous recevez le lien.
- `/prete` dans le fil marque la fiche « prête ».
- Si le challenge a échoué, répondre dans le fil le relance.

## Mise en route (étapes manuelles, aucune valeur secrète dans Git)

1. **Bot Telegram** : créez-le avec BotFather (`/newbot`), puis activez le **Threaded mode** dans
   les réglages du bot, depuis la Mini App de BotFather (le menu texte ne l'a pas). Sans lui, Telegram
   répond `the chat is not a forum` : l'idée est gardée mais sans fil, et vos réponses ne peuvent pas
   être rattachées à la fiche. Le repli par réponse chaînée n'est pas construit.
2. **Dépôt des fiches** : créez un dépôt GitHub privé `idea-library` et un jeton limité à ce seul
   dépôt (lecture et écriture du contenu).
3. **Jeton Claude** : lancez `claude setup-token` sur votre poste. L'usage scripté d'un abonnement
   n'est pas explicitement autorisé par Anthropic : relisez leur page d'assistance avant le
   lancement. Le repli est `ANTHROPIC_API_KEY` (clé API payante) à la place du jeton.
4. **Mot de passe du site** : `PYTHONPATH=app python -m ideadesk.web hash` (saisie sans écho)
   affiche le hachage à placer dans `SITE_PASSWORD_HASH`.
5. **Secret Kubernetes** (sans écho, jamais dans Git) :

   ```bash
   NS=user-pgoze
   for name in TELEGRAM_BOT_TOKEN OWNER_TELEGRAM_ID SITE_PASSWORD_HASH SESSION_SECRET \
               CLAUDE_CODE_OAUTH_TOKEN LIBRARY_GIT_TOKEN; do
     read -rsp "$name : " v && echo
     args+=("--from-literal=$name=$v"); unset v
   done
   kubectl create secret generic ideadesk-app -n "$NS" "${args[@]}"; unset args
   ```

   `SESSION_SECRET` : une longue valeur aléatoire (`openssl rand -hex 32`). `OWNER_TELEGRAM_ID` :
   mettez `0` au premier démarrage, écrivez au bot, lisez l'identifiant dans le journal
   (« expéditeur inconnu ignoré : <id> »), puis recréez le Secret et redémarrez.
6. **Image** : le workflow GitHub Actions construit `ghcr.io/<propriétaire>/second-brain:latest`
   à chaque push sur `main`. Rendez le paquet public (il ne contient aucun secret) et vérifiez qu'il
   se tire sans identifiants.
7. **Déploiement** (service VSCode lancé en rôle admin) :

   ```bash
   helm template ideadesk k8s/ideadesk -n user-pgoze | kubectl apply --dry-run=server -n user-pgoze -f -
   helm install ideadesk k8s/ideadesk -n user-pgoze
   curl https://ideas-pgoze.user.lab.sspcloud.fr/healthz   # 200 sans authentification
   ```

   Mise à jour de l'image : `kubectl rollout restart deployment/ideadesk -n user-pgoze`.

## Développement

```bash
uv sync
uv run pytest
```
