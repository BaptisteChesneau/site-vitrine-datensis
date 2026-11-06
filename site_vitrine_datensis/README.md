# DATENSIS — Site vitrine Flask

Site vitrine reprenant la landing HTML fournie et les cinq applications décrites dans la plaquette 2026.

## Démarrage (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m flask --app "app:create_app" shell
```

Dans le shell Flask, exécuter :

```python
from app.extensions import db
db.create_all()
exit()
```

Puis :

```powershell
python -m flask --app "app:create_app" run --debug
```

Ouvrir http://127.0.0.1:5000/ et http://127.0.0.1:5000/applications.

## Contenu

- Landing d'origine : HTML/CSS/JS séparés, animations conservées.
- Pages des applications Expert, Safe, Juris, Configuration et Fitensis.
- Formulaire de contact : validation serveur, CSRF, enregistrement SQLAlchemy.
- SQLite par défaut pour développement, PostgreSQL possible via DATABASE_URL.

## Avant mise en production

- Définir une SECRET_KEY forte et DATABASE_URL PostgreSQL ; créer des migrations et déployer le schéma.
- Compléter les pages légales, mettre en place la politique de conservation des contacts et les notifications.
- Ajouter anti-spam, limitation de débit, journalisation, tests et configuration HTTPS.
- Vérifier toutes les allégations commerciales et de certification de la landing auprès des responsables.
- Relier les applications métier existantes via leurs adresses officielles : les interfaces métier ne sont pas incluses dans ce site vitrine.
- Ne pas intégrer ce dossier tel quel dans un projet DATENSIS existant sans comparer les Blueprints, modèles et extensions.
