print("APP REAL INCARCAT")

import os
import io
from flask import Flask, render_template, redirect, request, url_for, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, Muncitor, Pontaj
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "fallback_secret")

database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()
    
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# =====================================================
# LOGIN
# =====================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/")
def home():
    return "SmartPontaj Running"


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()

        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# =====================================================
# DASHBOARD CU COMPARARE LUNI
# =====================================================

@app.route("/dashboard")
@login_required
def dashboard():

    luna = request.args.get("luna")
    muncitor_id = request.args.get("muncitor", type=int)

    if not luna:
        luna = datetime.now().strftime("%Y-%m")

    def total_luna(luna_target):
        q = db.session.query(
            db.func.coalesce(db.func.sum(Pontaj.ore), 0),
            db.func.coalesce(db.func.sum(Pontaj.plata), 0)
        ).filter(Pontaj.data.like(f"{luna_target}%"))

        if muncitor_id:
            q = q.filter(Pontaj.muncitor_id == muncitor_id)

        return q.first()

    total_curent = total_luna(luna)

    data_curenta = datetime.strptime(luna, "%Y-%m")
    luna_anterioara = (data_curenta - timedelta(days=1)).strftime("%Y-%m")

    total_anterior = total_luna(luna_anterioara)

    ore_curent = float(total_curent[0])
    plata_curent = float(total_curent[1])

    ore_anterior = float(total_anterior[0])
    plata_anterior = float(total_anterior[1])

    diferenta_proc = 0
    if ore_anterior > 0:
        diferenta_proc = round(
            ((ore_curent - ore_anterior) / ore_anterior) * 100, 2
        )

    # ===== GRAFIC PE ZILE =====
    query = db.session.query(
        Pontaj.data,
        db.func.coalesce(db.func.sum(Pontaj.ore), 0),
        db.func.coalesce(db.func.sum(Pontaj.plata), 0)
    ).filter(Pontaj.data.like(f"{luna}%"))

    if muncitor_id:
        query = query.filter(Pontaj.muncitor_id == muncitor_id)

    date_luna = query.group_by(
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
        total_ore=ore_curent,
        total_plata=plata_curent,
        ore_anterior=ore_anterior,
        plata_anterior=plata_anterior,
        diferenta_proc=diferenta_proc,
        zile=zile,
        ore_pe_zi=ore_pe_zi,
        plata_pe_zi=plata_pe_zi,
        luna=luna,
        muncitori=muncitori,
        muncitor_selectat=muncitor_id
    )


# =====================================================
# PONTAJ 24H + OBSERVATII
# =====================================================

@app.route("/pontaj", methods=["GET", "POST"])
@login_required
def pontaj():

    data_selectata = request.args.get("data")
    if not data_selectata:
        data_selectata = datetime.now().strftime("%Y-%m-%d")

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

            ore1 = calc_interval(start1, stop1)
            ore2 = calc_interval(start2, stop2)

            total_ore = ore1 + ore2

            if tip_zi in ["Concediu", "Boala"]:
                total_ore = 8
            elif tip_zi == "Liber":
                total_ore = 0

            ore_normale = min(total_ore, 8)
            ore_suplimentare = max(total_ore - 8, 0)

            plata = (
                ore_normale * m.tarif_ora +
                ore_suplimentare * m.tarif_ora * 1.5
            )

            if total_ore > 12:
                observatii = (observatii or "") + " ⚠ Peste 12h"

            existent = pontaje_existente.get(m.id)

            if existent:
                existent.start1 = start1
                existent.stop1 = stop1
                existent.start2 = start2
                existent.stop2 = stop2
                existent.tip_zi = tip_zi
                existent.ore = total_ore
                existent.ore_normale = ore_normale
                existent.ore_suplimentare = ore_suplimentare
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
                    tip_zi=tip_zi,
                    ore=total_ore,
                    ore_normale=ore_normale,
                    ore_suplimentare=ore_suplimentare,
                    plata=plata,
                    observatii=observatii
                )
                db.session.add(nou)

        db.session.commit()
        return redirect(url_for("pontaj", data=data_selectata))

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


# =====================================================
# FLUTURAS SALARIU
# =====================================================

@app.route("/fluturas")
@login_required
def fluturas():

    luna = request.args.get("luna")
    muncitor_id = request.args.get("muncitor", type=int)

    if not muncitor_id:
        return "Selectează un angajat."

    muncitor = Muncitor.query.get(muncitor_id)

    date_luna = db.session.query(
        db.func.coalesce(db.func.sum(Pontaj.ore), 0),
        db.func.coalesce(db.func.sum(Pontaj.plata), 0)
    ).filter(
        Pontaj.muncitor_id == muncitor.id,
        Pontaj.data.like(f"{luna}%")
    ).first()

    total_ore = float(date_luna[0])
    total_plata = float(date_luna[1])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph(f"Fluturaș salariu - {luna}", styles["Title"]))
    elements.append(Spacer(1, 20))

    data = [
        ["Angajat", muncitor.nume],
        ["Total ore", f"{total_ore}"],
        ["Total plată", f"{total_plata} lei"]
    ]

    table = Table(data)
    elements.append(table)

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"fluturas_{muncitor.nume}_{luna}.pdf",
        mimetype="application/pdf"
    )


# =====================================================
# INIT
# =====================================================

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

        db.session.commit()

    app.run()
