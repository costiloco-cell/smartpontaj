from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    password = db.Column(db.String(100))


class Muncitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nume = db.Column(db.String(100))
    tarif_ora = db.Column(db.Float)


class Pontaj(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    data = db.Column(db.String(20))

    muncitor_id = db.Column(db.Integer, db.ForeignKey("muncitor.id"))

    start1 = db.Column(db.String(5))
    stop1 = db.Column(db.String(5))

    start2 = db.Column(db.String(5))
    stop2 = db.Column(db.String(5))

    ore = db.Column(db.Float)
    plata = db.Column(db.Float)

    observatii = db.Column(db.String(200))
