import os
from urllib.parse import urlsplit, urlunsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
)
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import DemandeContact

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

# Ports de développement :
#
# Site vitrine : http://127.0.0.1:5000
# Expert       : http://127.0.0.1:5000/expert/portail
#
# Les autres applications seront raccordées
# lorsqu'elles disposeront de leur propre URL.
#
# En production, utiliser des URL HTTPS.


SOUS_SITES = {
    "expert": (
        "DATENSIS_EXPERT_URL",
        "http://127.0.0.1:5000/expert",
    ),
    "safe": (
        "DATENSIS_SAFE_URL",
        None,
    ),
    "juris": (
        "DATENSIS_JURIS_URL",
        None,
    ),
    "configuration": (
        "DATENSIS_CONFIGURATION_URL",
        None,
    ),
    "fitensis": (
        "FITENSIS_URL",
        None,
    ),
}


# ============================================================
# VALIDATION DES URL DES APPLICATIONS
# ============================================================


def _url_application(nom_variable, valeur_defaut=None):
    """
    Récupère et valide l'URL d'une application secondaire.

    Les URL doivent utiliser HTTP ou HTTPS.
    Les identifiants intégrés aux URL sont refusés.
    """

    valeur = current_app.config.get(nom_variable)

    if valeur is None:
        valeur = os.getenv(
            nom_variable,
            valeur_defaut,
        )

    if not isinstance(valeur, str):
        return None

    valeur = valeur.strip().rstrip("/")

    if not valeur:
        return None

    try:
        parsed = urlsplit(valeur)

        if parsed.scheme not in ("http", "https"):
            return None

        if not parsed.hostname:
            return None

        if parsed.username or parsed.password:
            return None

        if parsed.query or parsed.fragment:
            return None

        # Vérifie que le port éventuel est valide.
        _ = parsed.port

        # Évite les URL avec des caractères de contrôle.
        if any(ord(char) < 32 for char in valeur):
            return None

        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path.rstrip("/"),
                "",
                "",
            )
        )

    except ValueError:
        current_app.logger.warning(
            "URL invalide pour %s",
            nom_variable,
        )
        return None


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================


def _get_app(slug):
    """
    Recherche une application dans le catalogue.
    """

    application = next(
        (item for item in APPS if item["slug"] == slug),
        None,
    )

    if application is None:
        abort(404)

    return application


def _destination_application(slug):
    """
    Retourne la destination d'une application DATENSIS.

    DATENSIS Expert fonctionne sur le même serveur
    que le site vitrine, sous le préfixe /expert.

    Les autres applications utilisent leur URL configurée.
    """

    if slug == "expert":
        return "/expert/portail"

    configuration = SOUS_SITES.get(slug)

    if configuration is None:
        return None

    nom_variable, valeur_defaut = configuration

    return _url_application(
        nom_variable,
        valeur_defaut,
    )


# ============================================================
# ACCUEIL DU SITE VITRINE
# ============================================================


@main.get("/")
def accueil():
    """
    Page d'accueil principale de DATENSIS.
    """

    return render_template(
        "public/accueil.html",
        apps=APPS,
    )


# ============================================================
# CATALOGUE DES APPLICATIONS
# ============================================================


@main.get("/applications")
def applications():
    """
    Présentation de toutes les applications DATENSIS.
    """

    return render_template(
        "public/applications.html",
        apps=APPS,
    )


# ============================================================
# FICHE DE PRÉSENTATION D'UNE APPLICATION
# ============================================================


@main.get("/applications/<slug>")
def application_detail(slug):
    """
    Présentation détaillée d'une application.
    """

    application = _get_app(slug)

    return render_template(
        "public/application_detail.html",
        app=application,
    )


# ============================================================
# ACCÈS AUX APPLICATIONS SECONDAIRES
# ============================================================


@main.get("/acces/<slug>/")
def sous_site(slug):
    """
    Point d'entrée des applications depuis
    le site vitrine DATENSIS.

    Si l'application est configurée :
    redirection vers son serveur.

    Sinon :
    affichage de sa fiche de présentation.
    """

    application = _get_app(slug)

    destination = _destination_application(application["slug"])

    if destination:
        return redirect(
            destination,
            code=302,
        )

    return render_template(
        "public/application_detail.html",
        app=application,
    )


# ============================================================
# DATENSIS EXPERT - PORTAIL CLIENT PUBLIC
# ============================================================


@main.get("/expert")
@main.get("/expert/")
@main.get("/expert/portail")
@main.get("/expert/client")
def expert_portail():
    """
    Redirection vers le portail client
    de DATENSIS Expert.

    La connexion et les autorisations
    sont gérées par DATENSIS Expert.

    Aucune session d'authentification
    n'est partagée avec le site vitrine.
    """

    destination = _destination_application("expert")

    if not destination:
        abort(503)

    return redirect(
        destination,
        code=302,
    )


# ============================================================
# FORMULAIRE DE CONTACT
# ============================================================


@main.post("/contact")
def contact():
    """
    Enregistre une demande de contact
    dans la base de données du site vitrine.
    """

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

    # --------------------------------------------------------
    # Vérification des champs obligatoires
    # --------------------------------------------------------

    if (
        not all(data[key] for key in champs_obligatoires)
        or request.form.get("consentement") != "on"
    ):
        return jsonify(
            message=("Complétez les champs obligatoires et le consentement.")
        ), 400

    # --------------------------------------------------------
    # Validation de l'adresse e-mail
    # --------------------------------------------------------

    email = data["email"]

    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify(message="Adresse e-mail invalide."), 400

    # --------------------------------------------------------
    # Limites des champs
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Enregistrement en base de données
    # --------------------------------------------------------

    try:
        demande = DemandeContact(**data)

        db.session.add(demande)
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        current_app.logger.exception(
            "Erreur lors de l'enregistrement d'une demande de contact."
        )

        return jsonify(
            message=("Impossible d'enregistrer votre demande pour le moment.")
        ), 500

    return jsonify(message=("Demande enregistrée. Nous reviendrons vers vous.")), 201


# ============================================================
# MENTIONS LÉGALES
# ============================================================


@main.get("/mentions-legales")
def mentions_legales():
    return render_template(
        "public/legal.html",
        title="Mentions légales",
    )


# ============================================================
# CONFIDENTIALITÉ
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
