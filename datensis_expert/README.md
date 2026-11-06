# DATENSIS Expert — portail et deux espaces

Projet Flask autonome, prêt pour un **prototype local**, avec le graphisme bleu nuit / turquoise.

## Installation (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Modifiez `.env` : générez une `SECRET_KEY` aléatoire d'au moins 32 caractères, renseignez `CABINET_EMAIL` et un `CABINET_PASSWORD` privé d'au moins 12 caractères. Ne publiez jamais `.env`.

```powershell
python run.py
```

- Portail public client : http://127.0.0.1:5000/portail
- Inscription client : http://127.0.0.1:5000/inscription
- Connexion cabinet **interne uniquement** : http://127.0.0.1:5000/cabinet/connexion

## Fichiers livrés

- `app/templates/client.html` : espace Client (8 onglets)
- `app/templates/cabinet.html` : espace Cabinet (9 onglets)
- `app/templates/portal.html` : portail public
- `app/templates/register.html` et `cabinet_login.html` : authentification
- `app/static/style.css` et `app/static/app.js` : interface responsive et navigation
- `app/__init__.py` : routes Flask, sessions, rôles, SQLite et protection CSRF basique

## Fonctionnalités réellement actives

Inscription et connexion client, connexion cabinet privée, navigation par onglets, recherche locale des clients, création/achèvement des tâches, enregistrement de références documentaires, échanges de messages stockés en SQLite (actualisation manuelle). Les utilisateurs clients ne peuvent pas accéder aux routes cabinet : contrôle des rôles **côté serveur**.

## Limites importantes

Ce prototype **n'est pas prêt pour la production**. L'inscription publique n'est pas reliée à une invitation du cabinet, les documents sont des références texte (pas de transfert de fichiers), les messages ne sont pas temps réel, et plusieurs modules sont explicitement indiqués « en préparation ». Avant toute utilisation avec de vraies données comptables : HTTPS, authentification renforcée et MFA pour le cabinet, limitation des tentatives de connexion, invitations clients, autorisations par dossier, journal d'audit, gestion RGPD, sauvegardes, tests et déploiement sécurisé. Le compte cabinet est défini par variables d'environnement et son URL de connexion n'est pas affichée dans le portail client ; **une URL non affichée n'est pas un contrôle de sécurité**, la vérification de rôle serveur en est un.

## Intégration au site vitrine

Projet autonome pour ne pas écraser les routes et styles de `site-vitrine-datensis`. Le lien du site vitrine vers DATENSIS Expert devra cibler l'URL déployée de ce projet, ou une intégration via blueprint pourra être faite ultérieurement.
