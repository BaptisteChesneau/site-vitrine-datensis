from datetime import datetime, timezone
from app.extensions import db

class DemandeContact(db.Model):
    __tablename__='demandes_contact'
    id=db.Column(db.Integer,primary_key=True)
    nom=db.Column(db.String(150),nullable=False)
    structure=db.Column(db.String(200),nullable=False)
    email=db.Column(db.String(254),nullable=False)
    telephone=db.Column(db.String(30))
    type=db.Column(db.String(100),nullable=False)
    objet=db.Column(db.String(100),nullable=False)
    message=db.Column(db.Text)
    date_creation=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),nullable=False)
