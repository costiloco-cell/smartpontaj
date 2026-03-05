from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(50), unique=True)

    password = db.Column(db.String(200))

    role = db.Column(db.String(20), default="user")

    created = db.Column(db.DateTime, default=datetime.utcnow)


class Muncitor(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    nume = db.Column(db.String(100))

    tarif_ora = db.Column(db.Float)


class Pontaj(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    data = db.Column(db.String(20))

    muncitor_id = db.Column(db.Integer)

    start1 = db.Column(db.String(10))

    stop1 = db.Column(db.String(10))

    start2 = db.Column(db.String(10))

    stop2 = db.Column(db.String(10))

    ore = db.Column(db.Float)

    plata = db.Column(db.Float)

    observatii = db.Column(db.String(200))
