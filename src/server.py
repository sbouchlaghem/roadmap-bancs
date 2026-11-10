"""Serveur local (bibliothèque standard) : API JSON + interface web dans src/static."""
import csv
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import threading
from contextlib import nullcontext
from datetime import date, datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import releases as R
import store

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
BUILD_PPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ppt", "build_roadmap.py")
EXPORTS = os.path.join(store.DATA, "exports")
MAX_BODY = 5 * 1024 * 1024
VERROU = threading.Lock()  # une écriture à la fois : deux enregistrements rapprochés ne s'écrasent pas


def check_periode(debut, fin):
    for v in (debut, fin):
        if not re.fullmatch(r"\d{4}-\d{2}", v or ""):
            raise store.Invalid("Période : mois attendus au format AAAA-MM")


def garde(p, v, pole="", statut=""):
    """Filtres du Gantt (même règle que visibles() dans app.js) : pôle, statut ou « alerte » = Bloqué ou En retard."""
    if pole and p["pole"] != pole:
        return False
    return not statut or (v["statut"] in ("Bloqué", "En retard") if statut == "alerte" else v["statut"] == statut)


def ppt_export(debut, fin, pole="", statut=""):
    """Génère le PPT avec build_roadmap.py (entrée CSV). debut/fin : AAAA-MM ; pole/statut : filtres du Gantt.
    Renvoie le chemin du fichier."""
    check_periode(debut, fin)
    to_fr = lambda d: "/".join(reversed(d.split("-")))  # 2026-09-15 -> 15/09/2026, 2027-01 -> 01/2027
    os.makedirs(EXPORTS, exist_ok=True)
    out = os.path.join(EXPORTS, f"{date.today():%Y%m%d} - Roadmap {debut} a {fin}.pptx")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["categorie", "nom", "version", "debut", "fin", "statut", "prevu"])
        for p in store.load_all():
            for v in (v for v in p["versions"] if garde(p, v, pole, statut)):
                w.writerow([p["pole"], p["nom"], v["version"]] + [to_fr(v[k]) if v.get(k) else "" for k in ("debut", "fin")]
                           + [v["statut"], to_fr(v["prevu"]) if v.get("prevu") else ""])
        tmp_csv = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(store.config(), f, ensure_ascii=False)  # titres, pôles, couleurs, auteur : même config que l'interface
        tmp_cfg = f.name
    jalons = [a for j in store.load_jalons() for a in ("--jalon", f"{to_fr(j['date'])}={j['label']}")]
    try:
        r = subprocess.run([sys.executable, BUILD_PPT, "--config", tmp_cfg, "--debut", to_fr(debut), "--fin", to_fr(fin),
                            *jalons, tmp_csv, out], capture_output=True, text=True, timeout=120)
    finally:
        os.remove(tmp_csv)
        os.remove(tmp_cfg)
    if r.returncode != 0:
        raise store.Invalid("Export PPT impossible : " + (r.stderr or r.stdout).strip().splitlines()[-1])
    return out, r.stdout


def publier(debut, fin, vue=""):
    """Page HTML autonome en lecture seule : le Gantt de la période (comme le PPT) et la vue production.
    vue="prod" : page de l'équipe production, sans la roadmap. Renvoie son chemin."""
    check_periode(debut, fin)
    read = lambda n: Path(STATIC, n).read_text(encoding="utf-8")
    cfg = store.config()
    terminees = cfg["publication"]["terminees"]  # versions livrées sur la période (comme le PPT), pas l'historique ancien
    projets, tous = [], store.load_all()
    for p in tous:
        vs = [v for v in p["versions"] if v["statut"] != "Terminé" or (terminees and (v["fin"] or "")[:7] >= debut)]
        if vs:
            projets.append({**p, "depot": "", "versions": vs})  # chemins locaux : inutiles aux lecteurs
    parc = [{k: p[k] for k in ("id", "nom", "pole", "etat", "etat_note", "etat_date", "ressources", "postes")}
            | {"versions": [{k: v[k] for k in ("version", "statut", "debut", "fin", "prod", "notes")} for v in p["versions"]]}
            for p in tous if p["prod_publie"]]  # onglet « En production » : projets choisis, tout l'historique, sans les notes
    data = {"projets": projets, "parc": parc, "poles": store.poles(), "statuts": R.STATUTS, "jalons": store.load_jalons(),
            "config": {k: cfg[k] for k in ("application", "poles", "couleurs")},  # pas le serveur de publication
            "periode": [debut, fin], "vue": vue, "aujourdhui": date.today().isoformat(),
            "publie": f"{datetime.now():%d/%m/%Y à %H:%M}"}
    snap = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")  # un nom contenant </script> ne casse pas la page
    html = read("index.html")
    for a, b in (('<link rel="stylesheet" href="/style.css">', f"<style>\n{read('style.css')}</style>"),
                 ('<script src="/app.js"></script>', f"<script>window.SNAPSHOT = {snap};</script>\n<script>\n{read('app.js')}</script>")):
        if a not in html:
            raise store.Invalid("Publication impossible : index.html a changé")
        html = html.replace(a, b)
    nom = cfg["application"]["titre"] + (" - production" if vue == "prod" else "")
    out = os.path.join(EXPORTS, f"{nom} - lecture seule.html")  # même nom : le lien partagé reste valable
    store.write_atomic(out, html)
    os.chmod(out, 0o644)  # lisible par tous une fois copié sur un partage
    return out


def envoyer_publication(debut, fin):
    """Publie la page sur le serveur de consultation (Raspberry) par scp. Renvoie un message."""
    pub = store.config()["publication"]
    cible = pub["serveur"]
    if not cible or cible.startswith("-"):
        raise store.Invalid("Aucun serveur de publication : renseigne-le dans ⚙ Paramètres")
    # deux pages : tout (roadmap + production) et, à côté, production.html pour l'équipe production
    cible_prod = cible.rsplit("/", 1)[0] + "/production.html"
    for fichier, dest in ((publier(debut, fin), cible), (publier(debut, fin, "prod"), cible_prod)):
        try:  # BatchMode : clé SSH obligatoire, jamais de question de mot de passe qui bloquerait
            r = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", fichier, dest],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            raise store.Invalid(f"Envoi impossible : {e}")
        if r.returncode:
            raise store.Invalid(f"Envoi vers {dest} impossible : {(r.stderr or r.stdout).strip()}")
    lien = pub["lien"]
    lien_prod = (lien.rsplit("/", 1)[0] + "/production.html") if lien else cible_prod
    return f"Publié : {lien or cible} — équipe production : {lien_prod}"


def tester_publication(serveur):
    """Vérifie qu'on peut se connecter au serveur de publication (clé SSH, sans mot de passe). Renvoie un message."""
    hote = str(serveur or "").split(":", 1)[0]
    if not re.fullmatch(r"[\w.-]+@[\w.-]+", hote):
        raise store.Invalid("Serveur de publication : format utilisateur@hôte:/chemin/index.html")
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
                            hote, "true"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        raise store.Invalid(f"Connexion impossible : {e}")
    if r.returncode:
        raise store.Invalid(f"Connexion à {hote} impossible : {(r.stderr or r.stdout).strip() or 'refusée'}"
                            " — serveur installé avec ./installer-serveur.sh ?")
    return f"Connexion à {hote} : OK"


class Handler(BaseHTTPRequestHandler):
    server_version = "Roadmap/1.0"

    def log_message(self, fmt, *args):  # console silencieuse
        pass

    # ---- réponses ----
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise store.Invalid("Requête trop volumineuse")
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            raise store.Invalid("JSON invalide")
        if not isinstance(data, dict):
            raise store.Invalid("Objet JSON attendu")
        return data

    def _download(self, path_or_text, name, ctype):
        data = open(path_or_text, "rb").read() if os.path.exists(path_or_text) else path_or_text.encode("utf-8")
        self._send(200, data, ctype, {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})

    def _route(self, method):
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/projets/([a-z0-9-]+)(?:/(import|export|changelog|release|livrer))?", path)
        # une autre page web (ou un nom DNS piégé) ne doit pas piloter l'outil : export, commit, tag…
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host.rsplit(":", 1)[0] not in ("127.0.0.1", "localhost") or (
                method != "GET" and origin and urlparse(origin).netloc != host):
            return self._send(403, {"erreur": "Requête refusée : elle ne vient pas de l'application"})
        with VERROU if method != "GET" else nullcontext():
            return self._traiter(method, path, m)

    def _traiter(self, method, path, m):
        try:
            if method == "GET" and path == "/api/projets":
                return self._send(200, {"projets": store.load_all(), "poles": store.poles(), "statuts": R.STATUTS,
                                        "config": store.config(), "config_chemin": store.CONFIG,
                                        "jalons": store.load_jalons(),
                                        "aujourdhui": date.today().isoformat()})
            if method == "POST" and path == "/api/git/identifiants":
                d = self._json()
                return self._send(200, {"message": store.git_identifiants(d.get("url", ""), d.get("utilisateur"), d.get("secret"))})
            if method == "GET" and path == "/api/git/cle":
                return self._send(200, store.cle_ssh())
            if method == "GET" and path == "/api/branches":
                return self._send(200, store.branches(parse_qs(urlparse(self.path).query).get("url", [""])[0]))
            if method == "PUT" and path == "/api/config":
                return self._send(200, {"config": store.save_config(self._json())})
            if method == "POST" and path == "/api/config/test-publication":
                return self._send(200, {"message": tester_publication(self._json().get("serveur"))})
            if method == "PUT" and path == "/api/jalons":
                return self._send(200, {"jalons": store.save_jalons(self._json().get("jalons"))})
            if method == "POST" and path == "/api/projets":
                return self._send(201, store.save(self._json()))
            if method == "POST" and path == "/api/publier":
                d = self._json()
                return self._send(200, {"message": envoyer_publication(d.get("debut"), d.get("fin"))})
            if method == "GET" and path == "/api/publier":
                q = parse_qs(urlparse(self.path).query)
                out = publier(q.get("debut", [""])[0], q.get("fin", [""])[0])
                return self._download(out, os.path.basename(out), "text/html; charset=utf-8")
            if method == "POST" and path == "/api/export/ppt":
                d = self._json()
                out, log = ppt_export(d.get("debut"), d.get("fin"), d.get("pole") or "", d.get("statut") or "")
                return self._download(out, os.path.basename(out),
                                      "application/vnd.openxmlformats-officedocument.presentationml.presentation")
            if m:
                pid, action = m.group(1), m.group(2)
                if store.get(pid) is None:
                    return self._send(404, {"erreur": "Projet introuvable"})
                if method == "PUT" and not action:
                    return self._send(200, store.save(self._json(), pid))
                if method == "DELETE" and not action:
                    store.delete(pid)
                    return self._send(200, {"ok": True})
                if method == "POST" and action == "import":
                    p, msg = store.import_depot(pid)
                    return self._send(200, {"projet": p, "message": msg})
                if method == "POST" and action == "livrer":
                    p, msg = store.livrer(pid, str(self._json().get("version", "")))
                    return self._send(200, {"projet": p, "message": msg})
                if method == "POST" and action == "export":
                    return self._send(200, {"chemin": store.export_depot(pid, self._json().get("cible"))})
                if method == "GET" and action in ("changelog", "release"):
                    p = store.get(pid)
                    text = R.to_changelog(p["nom"], p["versions"]) if action == "changelog" else R.fmt(p["nom"], p["versions"])
                    return self._download(text, ("CHANGELOG" if action == "changelog" else "ROADMAP") + f" - {p['nom']}.md",
                                          "text/markdown; charset=utf-8")
            if method == "GET" and not path.startswith("/api/"):
                return self._static(path)
            return self._send(404, {"erreur": "Introuvable"})
        except store.Invalid as e:
            return self._send(400, {"erreur": str(e)})
        except Exception as e:  # erreur inattendue : message lisible plutôt qu'une connexion coupée
            return self._send(500, {"erreur": f"Erreur interne : {e}"})

    def _static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.realpath(os.path.join(STATIC, rel))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            return self._send(404, {"erreur": "Introuvable"})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, open(full, "rb").read(), ctype)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")


def run(port, host="127.0.0.1"):
    """Démarre le serveur (port suivant si occupé). Renvoie (serveur, url)."""
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer((host, p), Handler)
            return srv, f"http://{host}:{p}/"
        except OSError:
            continue
    raise SystemExit(f"Aucun port libre entre {port} et {port + 19}")
