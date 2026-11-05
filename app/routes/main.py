from flask import Blueprint, abort, jsonify, render_template, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import DemandeContact

main = Blueprint("main", __name__)

APPS = [
    {"slug": "expert", "name": "Datensis Expert", "category": "Comptabilité et gestion", "description": "La plateforme centrale des cabinets et de leurs clients.", "features": ["Dossiers et missions", "Suivi des tâches et temps de mission", "Documents et échanges clients", "Pilotage de l'activité"], "color": "#0E2433"},
    {"slug": "safe", "name": "Datensis Safe", "category": "Sécurité et identifiants", "description": "Un coffre-fort numérique pour organiser les accès et leur partage.", "features": ["Coffre-fort et dossiers", "Générateur de mots de passe", "Envoi temporaire sécurisé", "Partage entre comptes et extension navigateur"], "color": "#007F89"},
    {"slug": "juris", "name": "Datensis Juris", "category": "Juridique", "description": "Une application de suivi des dossiers juridiques, en développement.", "features": ["Portefeuille des sociétés", "Questionnaires de mission", "Documents et signatures", "Formalités et validations"], "color": "#D99841"},
    {"slug": "configuration", "name": "Datensis Configuration", "category": "Personnalisation", "description": "Un outil lié à Expert pour gérer les articles et la charte graphique.", "features": ["Catalogue des articles", "Réglages des sociétés", "Choix des couleurs", "Prévisualisation"], "color": "#E96148"},
    {"slug": "fitensis", "name": "Fitensis", "category": "Fitness et bien-être", "description": "Une application indépendante pour les entraînements et la nutrition.", "features": ["Séances et exercices", "Recettes", "Performances", "Assistant IA local via Ollama"], "color": "#4DAA51"},
]


def _get_app(slug):
    application = next((item for item in APPS if item["slug"] == slug), None)
    if application is None:
        abort(404)
    return application


@main.get("/")
def accueil():
    return render_template("public/accueil.html", apps=APPS)


@main.get("/applications")
def applications():
    return render_template("public/applications.html", apps=APPS)


@main.get("/applications/<slug>")
def application_detail(slug):
    return render_template("public/application_detail.html", app=_get_app(slug))


@main.get("/acces/<slug>/")
def sous_site(slug):
    # Page de transition tant que le sous-site autonome n'est pas branché.
    # Remplacer par une redirection vers l'application réelle lorsqu'elle existe.
    return render_template("public/application_detail.html", app=_get_app(slug))


@main.post("/contact")
def contact():
    data = {key: (request.form.get(key) or "").strip() for key in ("nom", "structure", "email", "telephone", "type", "objet", "message")}
    if not all(data[key] for key in ("nom", "structure", "email", "type", "objet")) or request.form.get("consentement") != "on":
        return jsonify(message="Complétez les champs obligatoires et le consentement."), 400
    if "@" not in data["email"] or "." not in data["email"].split("@")[-1]:
        return jsonify(message="Adresse e-mail invalide."), 400
    limits = {"nom": 150, "structure": 200, "email": 254, "telephone": 30, "type": 100, "objet": 100, "message": 4000}
    if any(len(data[key]) > limit for key, limit in limits.items()):
        return jsonify(message="Un champ dépasse la longueur autorisée."), 400
    try:
        db.session.add(DemandeContact(**data))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(message="Impossible d'enregistrer votre demande pour le moment."), 500
    return jsonify(message="Demande enregistrée. Nous reviendrons vers vous."), 201


@main.get("/mentions-legales")
def mentions_legales():
    return render_template("public/legal.html", title="Mentions légales")


@main.get("/confidentialite")
def confidentialite():
    return render_template("public/legal.html", title="Confidentialité")


@main.get("/cookies")
def cookies():
    return render_template("public/legal.html", title="Cookies")
