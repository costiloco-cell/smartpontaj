print("APP REAL INCARCAT")

import os
import io
import pandas as pd

from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

from models import db, User, Muncitor, Pontaj

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


# =====================================================
# CONFIG
# =====================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = "smartpontaj_secret"

database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=7)

db.init_app(app)


# =====================================================
# LOGIN MANAGER
# =====================================================

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.session_protection = "strong"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =====================================================
# CREATE ADMIN
# =====================================================

def create_admin():

    admin = User.query.filter_by(username="admin").first()

    if not admin:

        admin = User(
            username="admin",
            password=generate_password_hash("admin123"),
            role="admin"
        )

        db.session.add(admin)
        db.session.commit()


# =====================================================
# INIT DB
# =====================================================

with app.app_context():

    db.create_all()
    create_admin()


# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():
    return redirect(url_for("login"))


# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if not user:
            flash("Utilizator inexistent")
            return redirect(url_for("login"))

        if check_password_hash(user.password, password):

            login_user(user)

            return redirect(url_for("dashboard"))

        flash("Parola incorecta")

    return render_template("login.html")


# =====================================================
# LOGOUT
# =====================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(url_for("login"))


# =====================================================
# DASHBOARD
# =====================================================

@app.route("/dashboard")
@login_required
def dashboard():

    luna = request.args.get("luna")

    if not luna:
        luna = datetime.now().strftime("%Y-%m")

    total = db.session.query(
        db.func.coalesce(db.func.sum(Pontaj.ore), 0),
        db.func.coalesce(db.func.sum(Pontaj.plata), 0)
    ).filter(Pontaj.data.like(f"{luna}%")).first()

    total_ore = float(total[0])
    total_plata = float(total[1])

    date_luna = db.session.query(
        Pontaj.data,
        db.func.sum(Pontaj.ore),
        db.func.sum(Pontaj.plata)
    ).filter(
        Pontaj.data.like(f"{luna}%")
    ).group_by(
        Pontaj.data
    ).order_by(
        Pontaj.data
    ).all()

    zile = [d[0][-2:] for d in date_luna]
    ore_pe_zi = [float(d[1]) for d in date_luna]
    plata_pe_zi = [float(d[2]) for d in date_luna]

    muncitori = Muncitor.query.all()

    return render_template(
        "dashboard.html",
        total_ore=total_ore,
        total_plata=total_plata,
        zile=zile,
        ore_pe_zi=ore_pe_zi,
        plata_pe_zi=plata_pe_zi,
        luna=luna,
        muncitori=muncitori
    )


# =====================================================
# PONTAJ
# =====================================================

@app.route("/pontaj", methods=["GET", "POST"])
@login_required
def pontaj():

    data_selectata = request.args.get("data")

    if not data_selectata:
        data_selectata = datetime.now().strftime("%Y-%m-%d")

    muncitori = Muncitor.query.all()

    pontaje_existente = {
        p.muncitor_id: p
        for p in Pontaj.query.filter_by(data=data_selectata).all()
    }

    def calc_interval(start, stop):

        if not start or not stop:
            return 0

        t1 = datetime.strptime(start, "%H:%M")
        t2 = datetime.strptime(stop, "%H:%M")

        if t2 < t1:
            t2 += timedelta(days=1)

        return (t2 - t1).total_seconds() / 3600

    if request.method == "POST":

        for m in muncitori:

            start1 = request.form.get(f"start1_{m.id}")
            stop1 = request.form.get(f"stop1_{m.id}")

            start2 = request.form.get(f"start2_{m.id}")
            stop2 = request.form.get(f"stop2_{m.id}")

            tip_zi = request.form.get(f"tip_{m.id}")
            observatii = request.form.get(f"obs_{m.id}")

            ore = calc_interval(start1, stop1) + calc_interval(start2, stop2)

            if tip_zi == "Concediu":
                ore = 8

            plata = ore * m.tarif_ora

            existent = pontaje_existente.get(m.id)

            if existent:

                existent.start1 = start1
                existent.stop1 = stop1
                existent.start2 = start2
                existent.stop2 = stop2
                existent.ore = ore
                existent.plata = plata
                existent.observatii = observatii

            else:

                nou = Pontaj(
                    data=data_selectata,
                    muncitor_id=m.id,
                    start1=start1,
                    stop1=stop1,
                    start2=start2,
                    stop2=stop2,
                    ore=ore,
                    plata=plata,
                    observatii=observatii
                )

                db.session.add(nou)

        db.session.commit()

        return redirect(url_for("pontaj", data=data_selectata))

    return render_template(
        "pontaj.html",
        muncitori=muncitori,
        data_selectata=data_selectata,
        pontaje=pontaje_existente
    )


# =====================================================
# MUNCITORI
# =====================================================

@app.route("/muncitori", methods=["GET", "POST"])
@login_required
def muncitori():

    if request.method == "POST":

        nume = request.form.get("nume")
        tarif = request.form.get("tarif")

        muncitor = Muncitor(
            nume=nume,
            tarif_ora=float(tarif)
        )

        db.session.add(muncitor)
        db.session.commit()

        return redirect(url_for("muncitori"))

    return render_template(
        "muncitori.html",
        muncitori=Muncitor.query.all()
    )


# =====================================================
# RAPORT LUNAR
# =====================================================

@app.route("/raport_lunar")
@login_required
def raport_lunar():

    luna = request.args.get("luna")

    if not luna:
        luna = datetime.now().strftime("%Y-%m")

    rezultate = db.session.query(
        Muncitor.nume,
        db.func.sum(Pontaj.ore),
        db.func.sum(Pontaj.plata)
    ).join(
        Pontaj, Pontaj.muncitor_id == Muncitor.id
    ).filter(
        Pontaj.data.like(f"{luna}%")
    ).group_by(
        Muncitor.nume
    ).all()

    return render_template(
        "raport_lunar.html",
        rezultate=rezultate,
        luna=luna
    )


# =====================================================
# EXPORT EXCEL
# =====================================================

@app.route("/export_lunar")
@login_required
def export_lunar():

    luna = request.args.get("luna")

    date = db.session.query(
        Pontaj.data,
        Muncitor.nume,
        Pontaj.ore,
        Pontaj.plata
    ).join(
        Muncitor, Pontaj.muncitor_id == Muncitor.id
    ).filter(
        Pontaj.data.like(f"{luna}%")
    ).all()

    df = pd.DataFrame(date)

    buffer = io.BytesIO()

    df.to_excel(buffer, index=False)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"pontaj_{luna}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    app.run(debug=True)
