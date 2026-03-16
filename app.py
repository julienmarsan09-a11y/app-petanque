"""
🎯 Pétanque - Salles sur l'Hers — v5
"""

from flask import (Flask, render_template, request, redirect, url_for,
                   jsonify, flash, Response, session, send_file)
from dataclasses import dataclass, field, asdict
import json, random, hashlib, os
from pathlib import Path
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "petanque_salles_hers_2024")

DATA_FILE   = Path("concours_data.json")
USERS_FILE  = Path("users.json")
ARCHIVE_DIR = Path("archives")
ARCHIVE_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}

def has_logo():
    """Vérifie si un logo est présent sur le disque."""
    for ext in ALLOWED_EXTENSIONS:
        if Path(f"logo{ext}").exists():
            return True
    return False

# ✅ Enregistré ICI, au niveau module, avant toute route
app.jinja_env.globals['has_logo'] = has_logo


# ═══════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════

def hasher_mdp(mdp):
    return hashlib.sha256(mdp.encode()).hexdigest()

def charger_users():
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    users = {"admin": {"mdp_hash": hasher_mdp("petanque"), "role": "admin", "nom": "Administrateur"}}
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✅ Compte créé  →  admin / petanque")
    return users

def sauvegarder_users(users):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

def login_requis(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "utilisateur" not in session:
            flash("🔐 Connectez-vous pour accéder à cette page.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def admin_requis(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "utilisateur" not in session:
            return redirect(url_for("login"))
        users = charger_users()
        if users.get(session["utilisateur"], {}).get("role") != "admin":
            flash("🚫 Accès réservé aux administrateurs.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════════════════════
# MODÈLES
# ═══════════════════════════════════════════════════════════

@dataclass
class Equipe:
    id: int
    nom: str
    joueurs: list
    club: str = ""
    points: float = 0.0
    buchholz: float = 0.0
    paniers_marques: int = 0
    paniers_encaisses: int = 0
    forfait: bool = False

    @property
    def difference_paniers(self):
        return self.paniers_marques - self.paniers_encaisses


@dataclass
class Match:
    id: int
    equipe1_id: int
    equipe2_id: int
    score1: object = None
    score2: object = None
    tour: int = 1
    terrain: int = 1
    termine: bool = False
    est_finale: bool = False
    label: str = ""
    est_rematche: bool = False
    est_forfait: bool = False
    forfait_equipe_id: int = 0

    @property
    def gagnant_id(self):
        if not self.termine:
            return None
        if self.est_forfait:
            return self.equipe1_id if self.forfait_equipe_id == self.equipe2_id else self.equipe2_id
        return self.equipe1_id if self.score1 > self.score2 else self.equipe2_id

    @property
    def est_nul(self):
        if not self.termine or self.est_forfait:
            return False
        return self.score1 == self.score2


@dataclass
class Concours:
    nom: str = "Concours de Pétanque"
    association: str = "Pétanque de Salles sur l'Hers"
    lieu: str = "Salles sur l'Hers"
    date_concours: str = ""
    heure_debut: str = "09h00"
    contact: str = ""
    description: str = ""
    lots: list = field(default_factory=list)
    format: str = "suisse"
    type_equipe: str = "doublette"
    score_poules: int = 7
    score_finale: int = 9
    score_grande_finale: int = 13
    nb_tours: int = 5
    tour_actuel: int = 0
    statut: str = "inscription"
    avec_finale: bool = True
    nb_qualifies: int = 16
    tirage_aleatoire: bool = True
    restriction_club: bool = False
    equipes: list = field(default_factory=list)
    matchs: list = field(default_factory=list)
    date_creation: str = field(default_factory=lambda: datetime.now().strftime("%d/%m/%Y %H:%M"))
    _prochain_id_equipe: int = 1
    _prochain_id_match: int = 1

    @property
    def avertissement_rematche(self):
        n = len(self.equipes)
        if n < 2:
            return None
        tours_max = n - 1
        if self.nb_tours > tours_max:
            return (f"Avec {n} équipes, des rematchs sont inévitables à partir du tour "
                    f"{tours_max + 1}. Maximum recommandé : {tours_max} tours.")
        return None

    @property
    def lots_tries(self):
        return sorted(self.lots, key=lambda l: l["place"] if isinstance(l, dict) else l.place)


# ═══════════════════════════════════════════════════════════
# PERSISTENCE
# ═══════════════════════════════════════════════════════════

def charger_concours():
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            c = Concours()
            for attr in ["nom","association","lieu","date_concours","heure_debut",
                         "contact","description","format","type_equipe",
                         "score_poules","score_finale","score_grande_finale",
                         "nb_tours","tour_actuel","statut","avec_finale",
                         "nb_qualifies","tirage_aleatoire","restriction_club",
                         "date_creation","_prochain_id_equipe","_prochain_id_match"]:
                if attr in data:
                    setattr(c, attr, data[attr])
            c.lots = data.get("lots", [])
            for e in data.get("equipes", []):
                c.equipes.append(Equipe(
                    id=e["id"], nom=e["nom"], joueurs=e["joueurs"],
                    club=e.get("club",""),
                    points=e.get("points", 0.0), buchholz=e.get("buchholz", 0.0),
                    paniers_marques=e.get("paniers_marques", 0),
                    paniers_encaisses=e.get("paniers_encaisses", 0),
                    forfait=e.get("forfait", False),
                ))
            for m in data.get("matchs", []):
                c.matchs.append(Match(
                    id=m["id"], equipe1_id=m["equipe1_id"], equipe2_id=m["equipe2_id"],
                    score1=m.get("score1"), score2=m.get("score2"),
                    tour=m.get("tour",1), terrain=m.get("terrain",1),
                    termine=m.get("termine",False), est_finale=m.get("est_finale",False),
                    label=m.get("label",""), est_rematche=m.get("est_rematche",False),
                    est_forfait=m.get("est_forfait",False),
                    forfait_equipe_id=m.get("forfait_equipe_id",0),
                ))
            return c
        except Exception as ex:
            print(f"Erreur chargement: {ex}")
    return Concours()


def sauvegarder_concours(c):
    data = {a: getattr(c, a) for a in
            ["nom","association","lieu","date_concours","heure_debut",
             "contact","description","format","type_equipe",
             "score_poules","score_finale","score_grande_finale",
             "nb_tours","tour_actuel","statut","avec_finale",
             "nb_qualifies","tirage_aleatoire","restriction_club",
             "date_creation","_prochain_id_equipe","_prochain_id_match"]}
    data["lots"]    = c.lots
    data["equipes"] = [asdict(e) for e in c.equipes]
    data["matchs"]  = [asdict(m) for m in c.matchs]
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def archiver_concours(c):
    if not c.nom:
        return
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_fichier = f"{horodatage}_{c.nom[:40].replace(' ','_')}.json"
    dest = ARCHIVE_DIR / nom_fichier
    data = {a: getattr(c, a) for a in
            ["nom","association","lieu","date_concours","heure_debut",
             "contact","description","format","type_equipe",
             "score_poules","score_finale","nb_tours","tour_actuel","statut",
             "date_creation"]}
    data["lots"]    = c.lots
    data["equipes"] = [asdict(e) for e in c.equipes]
    data["matchs"]  = [asdict(m) for m in c.matchs]
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return nom_fichier


def charger_archives():
    archives = []
    for f in sorted(ARCHIVE_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            archives.append({
                "fichier": f.name,
                "nom": data.get("nom","?"),
                "date_concours": data.get("date_concours","?"),
                "lieu": data.get("lieu","?"),
                "nb_equipes": len(data.get("equipes", [])),
                "statut": data.get("statut","?"),
                "date_creation": data.get("date_creation","?"),
            })
        except Exception:
            pass
    return archives


def charger_archive(fichier):
    f = ARCHIVE_DIR / fichier
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


concours = charger_concours()


# ═══════════════════════════════════════════════════════════
# FONCTIONS MÉTIER
# ═══════════════════════════════════════════════════════════

def get_equipe(eid):  return next((e for e in concours.equipes if e.id == eid), None)
def get_match(mid):   return next((m for m in concours.matchs  if m.id == mid), None)

def classement():
    return sorted(
        [e for e in concours.equipes if not e.forfait],
        key=lambda e: (e.points, e.buchholz, e.difference_paniers, e.paniers_marques),
        reverse=True,
    )

def matchs_du_tour(tour):   return [m for m in concours.matchs if m.tour == tour and not m.est_finale]
def matchs_finale_actifs(): return [m for m in concours.matchs if m.est_finale]

def recalculer_buchholz():
    for e in concours.equipes:
        adv_ids = []
        for m in concours.matchs:
            if m.termine and not m.est_finale:
                if m.equipe1_id == e.id:   adv_ids.append(m.equipe2_id)
                elif m.equipe2_id == e.id: adv_ids.append(m.equipe1_id)
        e.buchholz = sum(get_equipe(a).points for a in adv_ids if get_equipe(a))

def meme_club(id1, id2):
    if not concours.restriction_club:
        return False
    e1, e2 = get_equipe(id1), get_equipe(id2)
    if not e1 or not e2 or not e1.club or not e2.club:
        return False
    return e1.club.strip().lower() == e2.club.strip().lower()


def generer_tour_suisse():
    concours.tour_actuel += 1
    tour = concours.tour_actuel
    recalculer_buchholz()

    deja_joue = set()
    for m in concours.matchs:
        deja_joue.add(tuple(sorted([m.equipe1_id, m.equipe2_id])))

    equipes_actives = [e for e in concours.equipes if not e.forfait]

    if tour == 1 and concours.tirage_aleatoire:
        equipes_triees = list(equipes_actives)
        random.shuffle(equipes_triees)
    else:
        equipes_triees = sorted(equipes_actives,
            key=lambda e: (e.points, e.buchholz, e.difference_paniers), reverse=True)

    non_apparies = list(equipes_triees)
    terrain = 1
    rematchs = []

    while len(non_apparies) >= 2:
        e1 = non_apparies.pop(0)
        adversaire = None
        est_rematche = False

        for i, e in enumerate(non_apparies):
            paire = tuple(sorted([e1.id, e.id]))
            if paire not in deja_joue and not meme_club(e1.id, e.id):
                adversaire = non_apparies.pop(i)
                break

        if adversaire is None:
            for i, e in enumerate(non_apparies):
                paire = tuple(sorted([e1.id, e.id]))
                if paire not in deja_joue:
                    adversaire = non_apparies.pop(i)
                    break

        if adversaire is None and non_apparies:
            adversaire = non_apparies.pop(0)
            est_rematche = True
            rematchs.append(f"{e1.nom} vs {adversaire.nom}")

        if adversaire:
            concours.matchs.append(Match(
                id=concours._prochain_id_match,
                equipe1_id=e1.id, equipe2_id=adversaire.id,
                tour=tour, terrain=terrain, est_rematche=est_rematche,
            ))
            concours._prochain_id_match += 1
            terrain += 1

    if rematchs:
        flash(f"⚠️ Rematche(s) inévitable(s) : {', '.join(rematchs)}", "warning")
    if non_apparies:
        ex = non_apparies[0]
        ex.points += 1
        flash(f"⚠️ {ex.nom} est exemptée (nombre impair) — +1 point", "warning")


def generer_phase_finale():
    recalculer_buchholz()
    qualifies = classement()[:concours.nb_qualifies]
    n = len(qualifies)

    def label_tour(nb):
        if nb == 2:  return ["Finale"]
        if nb == 4:  return ["Demi-finale A", "Demi-finale B"]
        if nb == 8:  return ["Quart A","Quart B","Quart C","Quart D"]
        if nb == 16: return [f"Huitième {i+1}" for i in range(8)]
        return [f"Match {i+1}" for i in range(nb//2)]

    labels = label_tour(n)
    for i in range(n // 2):
        concours.matchs.append(Match(
            id=concours._prochain_id_match,
            equipe1_id=qualifies[i].id,
            equipe2_id=qualifies[n - 1 - i].id,
            tour=concours.tour_actuel + 1,
            terrain=i + 1,
            est_finale=True,
            label=labels[i] if i < len(labels) else f"Match {i+1}",
        ))
        concours._prochain_id_match += 1


def score_requis_pour_match(match):
    if not match.est_finale:
        return concours.score_poules
    if "finale" in match.label.lower() and "demi" not in match.label.lower() \
       and "quart" not in match.label.lower() and "huitième" not in match.label.lower():
        return concours.score_grande_finale
    return concours.score_finale


def enregistrer_score(match_id, score1, score2):
    m = get_match(match_id)
    if not m or m.termine:
        return False
    m.score1, m.score2, m.termine = score1, score2, True
    e1, e2 = get_equipe(m.equipe1_id), get_equipe(m.equipe2_id)
    if e1 and e2:
        e1.paniers_marques += score1;  e1.paniers_encaisses += score2
        e2.paniers_marques += score2;  e2.paniers_encaisses += score1
        if not m.est_finale:
            if score1 > score2:    e1.points += 1
            elif score2 > score1:  e2.points += 1
            else:
                e1.points += 0.5
                e2.points += 0.5
    return True


def declarer_forfait(match_id, equipe_forfait_id):
    m = get_match(match_id)
    if not m or m.termine:
        return False
    m.termine = True
    m.est_forfait = True
    m.forfait_equipe_id = equipe_forfait_id
    if equipe_forfait_id == m.equipe1_id:
        m.score1, m.score2 = 0, score_requis_pour_match(m)
        gagnant = get_equipe(m.equipe2_id)
    else:
        m.score1, m.score2 = score_requis_pour_match(m), 0
        gagnant = get_equipe(m.equipe1_id)
    if gagnant and not m.est_finale:
        gagnant.points += 1
    return True


def tous_matchs_termines(tour):
    ms = matchs_du_tour(tour)
    return bool(ms) and all(m.termine for m in ms)

def tous_matchs_finale_termines():
    ms = matchs_finale_actifs()
    return bool(ms) and all(m.termine for m in ms)


# ═══════════════════════════════════════════════════════════
# EXPORT IMPRESSION
# ═══════════════════════════════════════════════════════════

def generer_html_impression():
    recalculer_buchholz()
    cl = classement()
    lots_dict = {}
    for lot in concours.lots:
        if isinstance(lot, dict):
            lots_dict[lot["place"]] = lot["description"]

    lignes = ""
    for i, e in enumerate(cl, 1):
        med = {1:"🥇",2:"🥈",3:"🥉"}.get(i, str(i))
        diff = ("+" if e.difference_paniers > 0 else "") + str(e.difference_paniers)
        pts_str = str(int(e.points)) if e.points == int(e.points) else str(e.points)
        lot_html = f"<br><small style='color:#F5A623;'>🎁 {lots_dict[i]}</small>" if i in lots_dict else ""
        lignes += f"<tr><td class='pos'>{med}</td><td class='nom'>{e.nom}{lot_html}<br><small>{', '.join(e.joueurs) or '—'}</small></td><td>{pts_str}</td><td>{e.buchholz}</td><td>{e.paniers_marques}</td><td>{e.paniers_encaisses}</td><td>{diff}</td></tr>"

    matchs_html = ""
    for t in range(1, concours.tour_actuel + 1):
        tms = matchs_du_tour(t)
        if tms:
            matchs_html += f"<h3>Tour {t}</h3><table class='mt'><tr><th>Équipe 1</th><th>Score</th><th>Équipe 2</th><th>Terrain</th></tr>"
            for m in tms:
                e1, e2 = get_equipe(m.equipe1_id), get_equipe(m.equipe2_id)
                if m.est_forfait:
                    score = f"Forfait ({get_equipe(m.forfait_equipe_id).nom if get_equipe(m.forfait_equipe_id) else '?'})"
                elif m.termine:
                    score = f"{m.score1} – {m.score2}"
                else:
                    score = "—"
                flag = " ⚠️" if m.est_rematche else ""
                matchs_html += f"<tr><td>{e1.nom if e1 else '?'}{flag}</td><td class='score'>{score}</td><td>{e2.nom if e2 else '?'}</td><td>{m.terrain}</td></tr>"
            matchs_html += "</table>"

    lots_html = ""
    if concours.lots:
        lots_html = "<h2>🎁 Lots</h2><table><tr><th>Place</th><th>Lot</th></tr>"
        for lot in sorted(concours.lots, key=lambda l: l["place"] if isinstance(l,dict) else 0):
            p = lot["place"] if isinstance(lot,dict) else lot.place
            d = lot["description"] if isinstance(lot,dict) else lot.description
            med = {1:"🥇",2:"🥈",3:"🥉"}.get(p, f"{p}e")
            lots_html += f"<tr><td>{med}</td><td>{d}</td></tr>"
        lots_html += "</table>"

    date_str = f" · {concours.date_concours}" if concours.date_concours else ""
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<title>{concours.nom}</title><style>
@page{{size:A4;margin:1.5cm}}*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Georgia,serif;color:#111;font-size:12px}}
.entete{{text-align:center;margin-bottom:1.5rem;border-bottom:3px double #1A3A5C;padding-bottom:1rem}}
h1{{font-size:22px;color:#1A3A5C;margin-bottom:4px}}.meta{{color:#555;font-size:11px}}
h2{{font-size:15px;color:#1A3A5C;margin:1.5rem 0 .5rem}}h3{{font-size:12px;color:#555;margin:1rem 0 .3rem}}
table{{width:100%;border-collapse:collapse;margin-bottom:1rem}}
th{{background:#1A3A5C;color:white;padding:5px 8px;text-align:center;font-size:10px;text-transform:uppercase}}
td{{padding:5px 8px;border-bottom:1px solid #ddd;text-align:center}}
.pos{{font-weight:bold;font-size:14px}}.nom{{text-align:left;font-weight:bold}}
.nom small{{font-weight:normal;color:#666;font-size:10px}}.score{{font-weight:bold}}
tr:nth-child(even) td{{background:#f5f5f5}}.mt th,.mt td{{font-size:10px}}
.footer{{text-align:center;margin-top:2rem;font-size:10px;color:#999;border-top:1px solid #ddd;padding-top:.5rem}}
@media print{{.no-print{{display:none}}}}
</style></head><body>
<div class="no-print" style="text-align:center;padding:1rem;background:#1A3A5C;color:white;">
<button onclick="window.print()" style="padding:.6rem 2rem;font-size:1rem;cursor:pointer;background:#F5A623;border:none;border-radius:6px;color:#111;font-weight:bold;">🖨️ Imprimer / PDF</button>
&nbsp;<a href="/" style="color:rgba(255,255,255,.7);text-decoration:none;font-size:.9rem;">← Retour</a></div>
<div class="entete"><h1>🎯 {concours.nom}</h1>
<div class="meta">{concours.association} · {concours.lieu}{date_str} · {concours.heure_debut}</div>
<div class="meta">{concours.type_equipe.title()}s · {concours.nb_tours} tours · Poules à {concours.score_poules} pts · {len(concours.equipes)} équipes · {datetime.now().strftime("%d/%m/%Y à %H:%M")}</div>
</div>
{lots_html}
<h2>🏆 Classement {"final" if concours.statut=="termine" else f"après le tour {concours.tour_actuel}"}</h2>
<table><tr><th>Pos.</th><th>Équipe / Joueurs</th><th>Points</th><th>Buchholz</th><th>Paniers +</th><th>Paniers −</th><th>Diff.</th></tr>{lignes}</table>
<h2>📋 Résultats</h2>{matchs_html}
<div class="footer">{concours.association} · {datetime.now().strftime("%d/%m/%Y")}</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════
# ROUTES LOGO
# ═══════════════════════════════════════════════════════════

@app.route("/logo")
def serve_logo():
    for ext in ALLOWED_EXTENSIONS:
        f = Path(f"logo{ext}")
        if f.exists():
            return send_file(f)
    return "", 404

@app.route("/logo/upload", methods=["POST"])
@admin_requis
def upload_logo():
    if "logo" not in request.files:
        flash("❌ Aucun fichier sélectionné.", "error")
        return redirect(url_for("configurer"))
    f = request.files["logo"]
    if not f.filename:
        flash("❌ Fichier invalide.", "error")
        return redirect(url_for("configurer"))
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        flash(f"❌ Format non supporté ({', '.join(ALLOWED_EXTENSIONS)})", "error")
        return redirect(url_for("configurer"))
    for old_ext in ALLOWED_EXTENSIONS:
        old = Path(f"logo{old_ext}")
        if old.exists():
            old.unlink()
    dest = Path(f"logo{ext}")
    f.save(str(dest))
    flash("✅ Logo mis à jour !", "success")
    return redirect(url_for("configurer"))

@app.route("/logo/supprimer", methods=["POST"])
@admin_requis
def supprimer_logo():
    for ext in ALLOWED_EXTENSIONS:
        f = Path(f"logo{ext}")
        if f.exists():
            f.unlink()
    flash("✅ Logo supprimé.", "success")
    return redirect(url_for("configurer"))


# ═══════════════════════════════════════════════════════════
# ROUTES AUTH
# ═══════════════════════════════════════════════════════════

@app.route("/login", methods=["GET","POST"])
def login():
    if "utilisateur" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username","").strip().lower()
        mdp      = request.form.get("mdp","")
        users    = charger_users()
        user     = users.get(username)
        if user and user["mdp_hash"] == hasher_mdp(mdp):
            session["utilisateur"] = username
            session["role"]        = user.get("role","saisie")
            session["nom"]         = user.get("nom", username)
            flash(f"👋 Bienvenue, {user.get('nom', username)} !", "success")
            return redirect(request.form.get("next") or url_for("index"))
        flash("❌ Identifiant ou mot de passe incorrect.", "error")
    return render_template("login.html", next=request.args.get("next",""))

@app.route("/logout")
def logout():
    session.clear()
    flash("👋 Déconnecté.", "info")
    return redirect(url_for("login"))

@app.route("/comptes", methods=["GET","POST"])
@admin_requis
def comptes():
    users = charger_users()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "ajouter":
            username = request.form.get("username","").strip().lower()
            nom      = request.form.get("nom","").strip()
            mdp      = request.form.get("mdp","").strip()
            role     = request.form.get("role","saisie")
            if not username or not mdp:
                flash("❌ Identifiant et mot de passe obligatoires.", "error")
            elif username in users:
                flash(f"❌ L'identifiant « {username} » existe déjà.", "error")
            elif len(mdp) < 4:
                flash("❌ Minimum 4 caractères.", "error")
            else:
                users[username] = {"mdp_hash": hasher_mdp(mdp), "role": role, "nom": nom or username}
                sauvegarder_users(users)
                flash(f"✅ Compte « {username} » créé.", "success")
        elif action == "supprimer":
            username = request.form.get("username","")
            if username == session.get("utilisateur"):
                flash("❌ Impossible de supprimer votre propre compte.", "error")
            elif username in users:
                del users[username]; sauvegarder_users(users)
                flash(f"✅ Compte « {username} » supprimé.", "success")
        elif action == "changer_mdp":
            username = request.form.get("username","")
            nouveau  = request.form.get("nouveau_mdp","").strip()
            if len(nouveau) < 4:
                flash("❌ Minimum 4 caractères.", "error")
            elif username in users:
                users[username]["mdp_hash"] = hasher_mdp(nouveau)
                sauvegarder_users(users)
                flash(f"✅ Mot de passe de « {username} » modifié.", "success")
        return redirect(url_for("comptes"))
    return render_template("comptes.html", concours=concours, users=users, moi=session.get("utilisateur"))

@app.route("/mon_compte", methods=["GET","POST"])
@login_requis
def mon_compte():
    if request.method == "POST":
        users    = charger_users()
        username = session["utilisateur"]
        actuel   = request.form.get("actuel","")
        nouveau  = request.form.get("nouveau","").strip()
        confirm  = request.form.get("confirmation","").strip()
        if users.get(username,{}).get("mdp_hash") != hasher_mdp(actuel):
            flash("❌ Mot de passe actuel incorrect.", "error")
        elif len(nouveau) < 4:
            flash("❌ Minimum 4 caractères.", "error")
        elif nouveau != confirm:
            flash("❌ La confirmation ne correspond pas.", "error")
        else:
            users[username]["mdp_hash"] = hasher_mdp(nouveau)
            sauvegarder_users(users)
            flash("✅ Mot de passe modifié !", "success")
    return render_template("mon_compte.html", concours=concours)


# ═══════════════════════════════════════════════════════════
# ROUTES PRINCIPALES
# ═══════════════════════════════════════════════════════════

@app.route("/")
@login_requis
def index():
    return render_template("index.html", concours=concours)

@app.route("/configurer", methods=["GET","POST"])
@admin_requis
def configurer():
    global concours
    if request.method == "POST":
        concours = Concours()
        concours.nom                = request.form.get("nom","Concours de Pétanque")
        concours.association        = request.form.get("association","Pétanque de Salles sur l'Hers")
        concours.lieu               = request.form.get("lieu","Salles sur l'Hers")
        concours.date_concours      = request.form.get("date_concours","")
        concours.heure_debut        = request.form.get("heure_debut","09h00")
        concours.contact            = request.form.get("contact","")
        concours.description        = request.form.get("description","")
        concours.type_equipe        = request.form.get("type_equipe","doublette")
        concours.score_poules       = int(request.form.get("score_poules",7))
        concours.score_finale       = int(request.form.get("score_finale",9))
        concours.score_grande_finale= int(request.form.get("score_grande_finale",13))
        concours.nb_tours           = int(request.form.get("nb_tours",5))
        concours.tirage_aleatoire   = "tirage_aleatoire" in request.form
        concours.restriction_club   = "restriction_club" in request.form
        concours.avec_finale        = "avec_finale" in request.form
        concours.nb_qualifies       = int(request.form.get("nb_qualifies",16))
        places = request.form.getlist("lot_place")
        descs  = request.form.getlist("lot_desc")
        concours.lots = [{"place": int(p), "description": d}
                         for p, d in zip(places, descs) if p and d.strip()]
        sauvegarder_concours(concours)
        flash("✅ Concours configuré !", "success")
        return redirect(url_for("inscriptions"))
    return render_template("configurer.html", concours=concours)

@app.route("/inscriptions")
@login_requis
def inscriptions():
    return render_template("inscriptions.html", concours=concours,
                           avertissement=concours.avertissement_rematche)

@app.route("/ajouter_equipe", methods=["POST"])
@admin_requis
def ajouter_equipe():
    nom = request.form.get("nom","").strip()
    if not nom:
        flash("❌ Le nom est obligatoire.", "error")
        return redirect(url_for("inscriptions"))
    joueurs = [j.strip() for j in request.form.get("joueurs","").replace("\n",",").split(",") if j.strip()]
    club    = request.form.get("club","").strip()
    nb_req  = 2 if concours.type_equipe == "doublette" else 3
    if joueurs and len(joueurs) != nb_req:
        flash(f"⚠️ Une {concours.type_equipe} doit avoir {nb_req} joueurs.", "warning")
    concours.equipes.append(Equipe(id=concours._prochain_id_equipe, nom=nom, joueurs=joueurs, club=club))
    concours._prochain_id_equipe += 1
    sauvegarder_concours(concours)
    flash(f"✅ Équipe « {nom} » inscrite !", "success")
    return redirect(url_for("inscriptions"))

@app.route("/supprimer_equipe/<int:equipe_id>", methods=["POST"])
@admin_requis
def supprimer_equipe(equipe_id):
    if concours.statut != "inscription":
        flash("❌ Impossible après le début du concours.", "error")
        return redirect(url_for("inscriptions"))
    concours.equipes = [e for e in concours.equipes if e.id != equipe_id]
    sauvegarder_concours(concours)
    flash("✅ Équipe supprimée.", "success")
    return redirect(url_for("inscriptions"))

@app.route("/demarrer")
@admin_requis
def demarrer():
    if len(concours.equipes) < 2:
        flash("❌ Il faut au moins 2 équipes.", "error")
        return redirect(url_for("inscriptions"))
    concours.statut = "en_cours"
    generer_tour_suisse()
    sauvegarder_concours(concours)
    label = "🎲 Tirage au sort ! " if concours.tirage_aleatoire else ""
    flash(f"🎯 {label}Tour {concours.tour_actuel} généré.", "success")
    return redirect(url_for("matchs_tour", tour=concours.tour_actuel))

@app.route("/tour/<int:tour>")
@login_requis
def matchs_tour(tour):
    return render_template("matchs.html", concours=concours, tour=tour,
        matchs=matchs_du_tour(tour), equipes={e.id: e for e in concours.equipes},
        tous_termines=tous_matchs_termines(tour),
        score_requis=concours.score_poules)

@app.route("/score/<int:match_id>", methods=["POST"])
@login_requis
def saisir_score(match_id):
    m = get_match(match_id)
    action = request.form.get("action","score")
    if action == "forfait":
        equipe_forfait_id = int(request.form.get("equipe_forfait_id", 0))
        if declarer_forfait(match_id, equipe_forfait_id):
            eq = get_equipe(equipe_forfait_id)
            flash(f"🏳️ Forfait enregistré pour {eq.nom if eq else '?'}.", "warning")
            sauvegarder_concours(concours)
        return redirect(url_for("phase_finale") if m and m.est_finale
                        else url_for("matchs_tour", tour=concours.tour_actuel))
    try:
        score1 = int(request.form.get("score1",0))
        score2 = int(request.form.get("score2",0))
    except ValueError:
        flash("❌ Scores invalides.", "error")
        return redirect(url_for("matchs_tour", tour=concours.tour_actuel))
    score_max = score_requis_pour_match(m) if m else concours.score_poules
    if max(score1, score2) != score_max:
        flash(f"❌ Le gagnant doit marquer exactement {score_max} points.", "error")
        return redirect(url_for("phase_finale") if m and m.est_finale
                        else url_for("matchs_tour", tour=concours.tour_actuel))
    if enregistrer_score(match_id, score1, score2):
        flash("🤝 Égalité — 0.5 pt chacun." if score1 == score2 else "✅ Score enregistré !", 
              "info" if score1 == score2 else "success")
        sauvegarder_concours(concours)
    return redirect(url_for("phase_finale") if m and m.est_finale
                    else url_for("matchs_tour", tour=concours.tour_actuel))

@app.route("/prochain_tour")
@admin_requis
def prochain_tour():
    if not tous_matchs_termines(concours.tour_actuel):
        flash("❌ Tous les matchs du tour actuel doivent être terminés.", "error")
        return redirect(url_for("matchs_tour", tour=concours.tour_actuel))
    if concours.tour_actuel >= concours.nb_tours:
        if concours.avec_finale:
            generer_phase_finale()
            concours.statut = "finale"
            sauvegarder_concours(concours)
            flash(f"🏆 Phase finale ! {concours.nb_qualifies} équipes qualifiées.", "success")
            return redirect(url_for("phase_finale"))
        concours.statut = "termine"
        archiver_concours(concours)
        sauvegarder_concours(concours)
        flash("🏆 Concours terminé et archivé !", "success")
        return redirect(url_for("classement_final"))
    generer_tour_suisse()
    sauvegarder_concours(concours)
    flash(f"✅ Tour {concours.tour_actuel} généré !", "success")
    return redirect(url_for("matchs_tour", tour=concours.tour_actuel))

@app.route("/finale")
@login_requis
def phase_finale():
    return render_template("finale.html", concours=concours,
        matchs=matchs_finale_actifs(),
        equipes={e.id: e for e in concours.equipes},
        tous_termines=tous_matchs_finale_termines(),
        score_requis_fn=score_requis_pour_match)

@app.route("/terminer_finale")
@admin_requis
def terminer_finale():
    if not tous_matchs_finale_termines():
        flash("❌ Tous les matchs de la finale doivent être terminés.", "error")
        return redirect(url_for("phase_finale"))
    concours.statut = "termine"
    archiver_concours(concours)
    sauvegarder_concours(concours)
    flash("🏆 Concours terminé et archivé !", "success")
    return redirect(url_for("classement_final"))

@app.route("/classement")
@login_requis
def classement_final():
    recalculer_buchholz()
    lots_dict = {l["place"]: l["description"] for l in concours.lots if isinstance(l,dict)}
    return render_template("classement.html", concours=concours,
        equipes=classement(), matchs_finaux=matchs_finale_actifs(), lots=lots_dict)

@app.route("/imprimer")
@login_requis
def imprimer():
    return Response(generer_html_impression(), mimetype="text/html")

@app.route("/archives")
@login_requis
def archives():
    return render_template("archives.html", concours=concours, archives=charger_archives())

@app.route("/archives/<fichier>/supprimer", methods=["POST"])
@admin_requis
def supprimer_archive(fichier):
    """Supprime définitivement un concours archivé."""
    f = ARCHIVE_DIR / fichier
    if f.exists():
        f.unlink()
        flash("✅ Concours supprimé des archives.", "success")
    else:
        flash("❌ Archive introuvable.", "error")
    return redirect(url_for("archives"))

@app.route("/archives/<fichier>")
@login_requis
def voir_archive(fichier):
    data = charger_archive(fichier)
    if not data:
        flash("❌ Archive introuvable.", "error")
        return redirect(url_for("archives"))
    return render_template("archive_detail.html", concours=concours, data=data, fichier=fichier)

@app.route("/archives/<fichier>/imprimer")
@login_requis
def imprimer_archive(fichier):
    data = charger_archive(fichier)
    if not data:
        flash("❌ Archive introuvable.", "error")
        return redirect(url_for("archives"))
    equipes = sorted(data.get("equipes",[]),
        key=lambda e: (-e.get("points",0), -(e.get("paniers_marques",0)-e.get("paniers_encaisses",0))))
    lignes = ""
    for i, e in enumerate(equipes, 1):
        med = {1:"🥇",2:"🥈",3:"🥉"}.get(i, str(i))
        pts = e.get("points",0)
        pts_str = str(int(pts)) if pts == int(pts) else str(pts)
        diff = e.get("paniers_marques",0) - e.get("paniers_encaisses",0)
        lignes += f"<tr><td>{med}</td><td style='text-align:left;font-weight:bold'>{e['nom']}</td><td>{pts_str}</td><td>{e.get('paniers_marques',0)}</td><td>{e.get('paniers_encaisses',0)}</td><td>{'+' if diff>0 else ''}{diff}</td></tr>"
    lots_html = ""
    for lot in sorted(data.get("lots",[]), key=lambda l: l.get("place",99)):
        med = {1:"🥇",2:"🥈",3:"🥉"}.get(lot["place"], f"{lot['place']}e")
        lots_html += f"<tr><td>{med}</td><td>{lot['description']}</td></tr>"
    if lots_html:
        lots_html = f"<h2>🎁 Lots</h2><table><tr><th>Place</th><th>Lot</th></tr>{lots_html}</table>"
    html = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>{data.get('nom','')}</title>
<style>@page{{size:A4;margin:1.5cm}}*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:Georgia,serif;font-size:12px}}
.entete{{text-align:center;border-bottom:3px double #1A3A5C;padding-bottom:1rem;margin-bottom:1.5rem}}
h1{{font-size:22px;color:#1A3A5C}}h2{{font-size:15px;color:#1A3A5C;margin:1.5rem 0 .5rem}}
table{{width:100%;border-collapse:collapse;margin-bottom:1rem}}
th{{background:#1A3A5C;color:white;padding:5px 8px;text-align:center;font-size:10px;text-transform:uppercase}}
td{{padding:5px 8px;border-bottom:1px solid #ddd;text-align:center}}
@media print{{.no-print{{display:none}}}}</style></head><body>
<div class="no-print" style="text-align:center;padding:1rem;background:#1A3A5C;color:white;">
<button onclick="window.print()" style="padding:.6rem 2rem;background:#F5A623;border:none;border-radius:6px;color:#111;font-weight:bold;cursor:pointer;">🖨️ Imprimer</button>
&nbsp;<a href="/archives" style="color:rgba(255,255,255,.7);text-decoration:none;">← Archives</a></div>
<div class="entete"><h1>🎯 {data.get('nom','')}</h1>
<div style="color:#555;font-size:11px">{data.get('association','')} · {data.get('lieu','')} · {data.get('date_concours','')} · {len(equipes)} équipes</div></div>
{lots_html}
<h2>🏆 Classement final</h2>
<table><tr><th>Pos.</th><th>Équipe</th><th>Points</th><th>Paniers +</th><th>Paniers −</th><th>Diff.</th></tr>{lignes}</table>
</body></html>"""
    return Response(html, mimetype="text/html")

@app.route("/reset", methods=["POST"])
@admin_requis
def reset():
    global concours
    if concours.equipes and concours.statut != "inscription":
        archiver_concours(concours)
    concours = Concours()
    if DATA_FILE.exists(): DATA_FILE.unlink()
    flash("🔄 Nouveau concours créé.", "info")
    return redirect(url_for("configurer"))

@app.route("/api/stats")
@login_requis
def api_stats():
    return jsonify({
        "nb_equipes": len(concours.equipes),
        "tour_actuel": concours.tour_actuel,
        "nb_matchs_joues": sum(1 for m in concours.matchs if m.termine),
        "statut": concours.statut,
    })


if __name__ == "__main__":
    charger_users()
    print("\n🎯 Pétanque - Salles sur l'Hers v5")
    print("👉 http://localhost:5000")
    print("🔐 admin / petanque\n")
    app.run(debug=True, host="0.0.0.0", port=5000)

# ═══════════════════════════════════════════════════════════
# RESET MOT DE PASSE PAR EMAIL
# ═══════════════════════════════════════════════════════════

import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Fichier de config SMTP (éditable sans toucher au code)
SMTP_CONFIG_FILE = Path("smtp_config.json")
# Tokens temporaires en mémoire {token: {username, expire}}
_reset_tokens: dict = {}


def charger_smtp_config() -> dict:
    """Charge la config SMTP depuis smtp_config.json."""
    if SMTP_CONFIG_FILE.exists():
        try:
            return json.loads(SMTP_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Config par défaut (Gmail)
    default = {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",           # Ton adresse Gmail
        "smtp_password": "",       # Mot de passe d'application Gmail
        "from_email": "",          # Même adresse
        "from_name": "Pétanque Salles sur l'Hers"
    }
    SMTP_CONFIG_FILE.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    return default


def envoyer_email_reset(dest_email: str, username: str, token: str) -> bool:
    """Envoie l'email de réinitialisation. Retourne True si succès."""
    cfg = charger_smtp_config()
    if not cfg.get("smtp_user") or not cfg.get("smtp_password"):
        return False

    lien = f"http://localhost:5000/reset-mdp/{token}"
    corps_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;">
      <h2 style="color:#1A3A5C;">Réinitialisation de mot de passe</h2>
      <p>Bonjour <strong>{username}</strong>,</p>
      <p>Une demande de réinitialisation de mot de passe a été effectuée pour votre compte.</p>
      <p style="margin:1.5rem 0;">
        <a href="{lien}" style="background:#F5A623;color:#111;padding:.75rem 1.5rem;border-radius:8px;text-decoration:none;font-weight:bold;">
          Réinitialiser mon mot de passe
        </a>
      </p>
      <p style="color:#666;font-size:.85rem;">Ce lien est valable 30 minutes. Si vous n'avez pas fait cette demande, ignorez cet email.</p>
      <hr style="border:none;border-top:1px solid #eee;margin:1.5rem 0;">
      <p style="color:#999;font-size:.8rem;">{cfg.get('from_name','Pétanque')}</p>
    </div>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Réinitialisation de mot de passe — Pétanque"
        msg["From"]    = f"{cfg['from_name']} <{cfg['from_email'] or cfg['smtp_user']}>"
        msg["To"]      = dest_email
        msg.attach(MIMEText(corps_html, "html", "utf-8"))

        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
            server.starttls()
            server.login(cfg["smtp_user"], cfg["smtp_password"])
            server.send_message(msg)
        return True
    except Exception as ex:
        print(f"Erreur envoi email: {ex}")
        return False


@app.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def mot_de_passe_oublie():
    """Page de demande de reset."""
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        users = charger_users()
        user = users.get(username)

        if user and user.get("email"):
            # Générer token valable 30 min
            token = secrets.token_urlsafe(32)
            expire = datetime.now().timestamp() + 1800  # 30 min
            _reset_tokens[token] = {"username": username, "expire": expire}

            if envoyer_email_reset(user["email"], username, token):
                flash(f"✅ Email envoyé à l'adresse enregistrée pour « {username} ».", "success")
            else:
                flash("❌ Erreur d'envoi. Vérifiez la configuration SMTP dans smtp_config.json.", "error")
        else:
            # Même message pour ne pas révéler si le compte existe
            flash("✅ Si ce compte existe et a une adresse email, un lien a été envoyé.", "info")

        return redirect(url_for("login"))
    return render_template("mdp_oublie.html")


@app.route("/reset-mdp/<token>", methods=["GET", "POST"])
def reset_mdp_token(token):
    """Page de saisie du nouveau mot de passe via token."""
    # Vérifier token
    token_data = _reset_tokens.get(token)
    if not token_data or datetime.now().timestamp() > token_data["expire"]:
        flash("❌ Lien expiré ou invalide. Faites une nouvelle demande.", "error")
        _reset_tokens.pop(token, None)
        return redirect(url_for("login"))

    if request.method == "POST":
        nouveau  = request.form.get("nouveau", "").strip()
        confirm  = request.form.get("confirmation", "").strip()
        if len(nouveau) < 4:
            flash("❌ Minimum 4 caractères.", "error")
        elif nouveau != confirm:
            flash("❌ Les mots de passe ne correspondent pas.", "error")
        else:
            users = charger_users()
            username = token_data["username"]
            if username in users:
                users[username]["mdp_hash"] = hasher_mdp(nouveau)
                sauvegarder_users(users)
                _reset_tokens.pop(token, None)
                flash("✅ Mot de passe modifié ! Vous pouvez vous connecter.", "success")
                return redirect(url_for("login"))

    return render_template("reset_mdp.html", token=token)


@app.route("/smtp-config", methods=["GET", "POST"])
@admin_requis
def smtp_config():
    """Page de configuration SMTP (admin)."""
    cfg = charger_smtp_config()
    if request.method == "POST":
        cfg["smtp_host"]     = request.form.get("smtp_host", "smtp.gmail.com")
        cfg["smtp_port"]     = int(request.form.get("smtp_port", 587))
        cfg["smtp_user"]     = request.form.get("smtp_user", "")
        cfg["smtp_password"] = request.form.get("smtp_password", "")
        cfg["from_email"]    = request.form.get("from_email", "")
        cfg["from_name"]     = request.form.get("from_name", "Pétanque")
        SMTP_CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        flash("✅ Configuration SMTP sauvegardée.", "success")
        return redirect(url_for("comptes"))
    return render_template("smtp_config.html", concours=concours, cfg=cfg)


@app.route("/ajouter_email_compte", methods=["POST"])
@admin_requis
def ajouter_email_compte():
    """Ajoute/met à jour l'email d'un compte."""
    users = charger_users()
    username = request.form.get("username", "")
    email    = request.form.get("email", "").strip()
    if username in users:
        users[username]["email"] = email
        sauvegarder_users(users)
        flash(f"✅ Email de « {username} » mis à jour.", "success")
    return redirect(url_for("comptes"))
