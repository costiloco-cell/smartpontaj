print("APP REAL INCARCAT")

import os
from flask import Flask, render_template, redirect, request, url_for
from flask_login import LoginManager, login_user, login_required, logout_user
from flask_login import current_user
from models import db, User, Muncitor, Pontaj
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "fallback_secret")

database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def calc_ore(start, stop):
    t1 = datetime.strptime(start, "%H:%M")
    t2 = datetime.strptime(stop, "%H:%M")
    if t2 < t1:
        t2 += timedelta(days=1)
    return round((t2 - t1).total_seconds() / 3600, 2)


@app.route("/admin")
@login_required
def admin():
    if current_user.role != "admin":
        return "Acces interzis", 403

    return render_template("admin.html")

@app.route("/")
def home():
    return "SmartPontaj Running"


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()

        from werkzeug.security import check_password_hash

        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    total_ore = db.session.query(db.func.sum(Pontaj.ore)).scalar() or 0
    total_plata = db.session.query(db.func.sum(Pontaj.plata)).scalar() or 0

    return render_template(
        "dashboard.html",
        total_ore=total_ore,
        total_plata=total_plata
    )

@app.route("/muncitori", methods=["GET", "POST"])
@login_required
def muncitori():

    if request.method == "POST":
        nume = request.form.get("nume")
        tarif = request.form.get("tarif")

        if nume and tarif:
            m = Muncitor(nume=nume, tarif_ora=float(tarif))
            db.session.add(m)
            db.session.commit()
            return redirect(url_for("muncitori"))

    lista = Muncitor.query.all()
    return render_template("muncitori.html", muncitori=lista)

@app.route("/sterge_muncitor/<int:id>")
@login_required
def sterge_muncitor(id):
    m = Muncitor.query.get_or_404(id)
    db.session.delete(m)
    db.session.commit()
    return redirect(url_for("muncitori"))

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

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/pontaj", methods=["GET", "POST"])
@login_required
def pontaj():

    data_selectata = request.args.get("data")
    if not data_selectata:
        data_selectata = datetime.now().strftime("%Y-%m-%d")

    # Navigare zi
    action = request.args.get("action")
    if action == "prev":
        data_selectata = (
            datetime.strptime(data_selectata, "%Y-%m-%d") - timedelta(days=1)
        ).strftime("%Y-%m-%d")
    elif action == "next":
        data_selectata = (
            datetime.strptime(data_selectata, "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")

    muncitori = Muncitor.query.all()

    pontaje_existente = {
        p.muncitor_id: p
        for p in Pontaj.query.filter_by(data=data_selectata).all()
    }

    if request.method == "POST":
        for m in muncitori:
            start = request.form.get(f"start_{m.id}")
            stop = request.form.get(f"stop_{m.id}")

            if start and stop:
                t1 = datetime.strptime(start, "%H:%M")
                t2 = datetime.strptime(stop, "%H:%M")

                if t2 < t1:
                    t2 += timedelta(days=1)

                ore = round((t2 - t1).total_seconds() / 3600, 2)
                plata = ore * m.tarif_ora

                existent = pontaje_existente.get(m.id)

                if existent:
                    existent.start = start
                    existent.stop = stop
                    existent.ore = ore
                    existent.plata = plata
                else:
                    nou = Pontaj(
                        data=data_selectata,
                        muncitor_id=m.id,
                        start=start,
                        stop=stop,
                        ore=ore,
                        plata=plata
                    )
                    db.session.add(nou)

        db.session.commit()
        return redirect(url_for("pontaj", data=data_selectata))

    # TOTALURI (în interiorul funcției, dar în afara blocului POST)
    total_ore_zi = sum(p.ore for p in pontaje_existente.values())
    total_plata_zi = sum(p.plata for p in pontaje_existente.values())

    return render_template(
        "pontaj.html",
        muncitori=muncitori,
        data_selectata=data_selectata,
        pontaje=pontaje_existente,
        total_ore_zi=total_ore_zi,
        total_plata_zi=total_plata_zi
    )

from openpyxl import Workbook
from flask import send_file
import io

@app.route("/export_lunar")
@login_required
def export_lunar():

    luna = request.args.get("luna")

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

    wb = Workbook()
    ws = wb.active
    ws.append(["Muncitor", "Total Ore", "Total Plata"])

    for r in rezultate:
        ws.append([r[0], r[1] or 0, r[2] or 0])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        download_name=f"raport_{luna}.xlsx",
        as_attachment=True
    )

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password=generate_password_hash("admin123"),
                role="admin"
            )
            db.session.add(admin)

        if not Muncitor.query.first():
            m1 = Muncitor(nume="Ion Popescu", tarif_ora=25)
            m2 = Muncitor(nume="Maria Ionescu", tarif_ora=30)
            db.session.add_all([m1, m2])

        db.session.commit()

    app.run()
