import os

from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
)
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import DemandeContact

main = Blueprint("main", __name__)


# ============================================================
# CATALOGUE DES APPLICATIONS DATENSIS
# ============================================================

APPS = [
    {
        "slug": "expert",
        "name": "Datensis Expert",
        "category": "Comptabilité et gestion",
        "description": ("La plateforme centrale des cabinets et de leurs clients."),
        "features": [
            "Dossiers et missions",
            "Suivi des tâches et temps de mission",
            "Documents et échanges clients",
            "Pilotage de l'activité",
        ],
        "color": "#0E2433",
    },
    {
        "slug": "safe",
        "name": "Datensis Safe",
        "category": "Sécurité et identifiants",
        "description": (
            "Un coffre-fort numérique pour organiser les accès et leur partage."
        ),
        "features": [
            "Coffre-fort et dossiers",
            "Générateur de mots de passe",
            "Envoi temporaire sécurisé",
            "Partage entre comptes et extension navigateur",
        ],
        "color": "#007F89",
    },
    {
        "slug": "juris",
        "name": "Datensis Juris",
        "category": "Juridique",
        "description": (
            "Une application de suivi des dossiers juridiques, en développement."
        ),
        "features": [
            "Portefeuille des sociétés",
            "Questionnaires de mission",
            "Documents et signatures",
            "Formalités et validations",
        ],
        "color": "#D99841",
    },
    {
        "slug": "configuration",
        "name": "Datensis Configuration",
        "category": "Personnalisation",
        "description": (
            "Un outil lié à Expert pour gérer les articles et la charte graphique."
        ),
        "features": [
            "Catalogue des articles",
            "Réglages des sociétés",
            "Choix des couleurs",
            "Prévisualisation",
        ],
        "color": "#E96148",
    },
    {
        "slug": "fitensis",
        "name": "Fitensis",
        "category": "Fitness et bien-être",
        "description": (
            "Une application indépendante pour les entraînements et la nutrition."
        ),
        "features": [
            "Séances et exercices",
            "Recettes",
            "Performances",
            "Assistant IA local via Ollama",
        ],
        "color": "#4DAA51",
    },
]


# ============================================================
# CONFIGURATION DES APPLICATIONS SECONDAIRES
# ============================================================

# Chaque application peut disposer de son propre serveur.
#
# Site vitrine : http://127.0.0.1:5000
# Expert       : http://127.0.0.1:5001
#
# En production, les URL sont définies dans .env.


def _url_application(nom_variable, valeur_defaut=None):
    valeur = os.getenv(nom_variable, valeur_defaut)

    if not valeur:
        return None

    return valeur.strip().rstrip("/")


SOUS_SITES = {
    "expert": _url_application(
        "DATENSIS_EXPERT_URL",
        "http://127.0.0.1:5001",
    ),
    "safe": _url_application("DATENSIS_SAFE_URL"),
    "juris": _url_application("DATENSIS_JURIS_URL"),
    "configuration": _url_application("DATENSIS_CONFIGURATION_URL"),
    "fitensis": _url_application("FITENSIS_URL"),
}


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================


def _get_app(slug):
    application = next(
        (item for item in APPS if item["slug"] == slug),
        None,
    )

    if application is None:
        abort(404)

    return application


def _destination_application(slug):
    """
    Retourne l'URL d'accès à une application secondaire.

    Pour DATENSIS Expert, le visiteur arrive
    systématiquement sur le portail public.
    """

    base_url = SOUS_SITES.get(slug)

    if not base_url:
        return None

    if slug == "expert":
        return f"{base_url}/portail"

    return base_url


# ============================================================
# ACCUEIL DU SITE VITRINE
# ============================================================


@main.get("/")
def accueil():
    return render_template(
        "public/accueil.html",
        apps=APPS,
    )


# ============================================================
# CATALOGUE DES APPLICATIONS
# ============================================================


@main.get("/applications")
def applications():
    return render_template(
        "public/applications.html",
        apps=APPS,
    )


# ============================================================
# FICHE DE PRESENTATION D'UNE APPLICATION
# ============================================================


@main.get("/applications/<slug>")
def application_detail(slug):
    application = _get_app(slug)

    return render_template(
        "public/application_detail.html",
        app=application,
    )


# ============================================================
# ACCES AUX APPLICATIONS SECONDAIRES
# ============================================================


@main.get("/acces/<slug>/")
def sous_site(slug):
    application = _get_app(slug)

    destination = _destination_application(application["slug"])

    if destination:
        return redirect(destination, code=302)

    # Si l'application n'est pas encore raccordée,
    # afficher sa fiche de présentation.
    return render_template(
        "public/application_detail.html",
        app=application,
    )


# ============================================================
# DATENSIS EXPERT - PORTAIL PUBLIC
# ============================================================


@main.get("/expert")
@main.get("/expert/")
@main.get("/expert/portail")
def expert_portail():
    """
    Redirection vers le portail public DATENSIS Expert.

    Le visiteur peut accéder à la connexion client,
    mais pas directement à l'espace Cabinet.
    """

    destination = _destination_application("expert")

    if not destination:
        abort(503)

    return redirect(destination, code=302)


# ============================================================
# DATENSIS EXPERT - ACCES CLIENT
# ============================================================


@main.get("/expert/client")
def expert_client():
    """
    Redirection vers le portail de DATENSIS Expert.

    L'authentification est gérée dans l'application
    secondaire, et non dans le site vitrine.
    """

    destination = _destination_application("expert")

    if not destination:
        abort(503)

    return redirect(destination, code=302)


# ============================================================
# FORMULAIRE DE CONTACT
# ============================================================


@main.post("/contact")
def contact():
    champs = (
        "nom",
        "structure",
        "email",
        "telephone",
        "type",
        "objet",
        "message",
    )

    data = {key: (request.form.get(key) or "").strip() for key in champs}

    champs_obligatoires = (
        "nom",
        "structure",
        "email",
        "type",
        "objet",
    )

    if (
        not all(data[key] for key in champs_obligatoires)
        or request.form.get("consentement") != "on"
    ):
        return jsonify(
            message=("Complétez les champs obligatoires et le consentement.")
        ), 400

    email = data["email"]

    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify(message="Adresse e-mail invalide."), 400

    limites = {
        "nom": 150,
        "structure": 200,
        "email": 254,
        "telephone": 30,
        "type": 100,
        "objet": 100,
        "message": 4000,
    }

    if any(len(data[key]) > limite for key, limite in limites.items()):
        return jsonify(message=("Un champ dépasse la longueur autorisée.")), 400

    try:
        demande = DemandeContact(**data)

        db.session.add(demande)
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        return jsonify(
            message=("Impossible d'enregistrer votre demande pour le moment.")
        ), 500

    return jsonify(message=("Demande enregistrée. Nous reviendrons vers vous.")), 201


# ============================================================
# MENTIONS LEGALES
# ============================================================


@main.get("/mentions-legales")
def mentions_legales():
    return render_template(
        "public/legal.html",
        title="Mentions légales",
    )


# ============================================================
# CONFIDENTIALITE
# ============================================================


@main.get("/confidentialite")
def confidentialite():
    return render_template(
        "public/legal.html",
        title="Confidentialité",
    )


# ============================================================
# COOKIES
# ============================================================


@main.get("/cookies")
def cookies():
    return render_template(
        "public/legal.html",
        title="Cookies",
    )
