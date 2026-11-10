"""Stockage dans $ROADMAP_DATA (installé : ~/.local/share/roadmap-bancs ; sinon ./data) :
projets.json (liste des projets) + releases/<id>.md (un ROADMAP.md par projet) + jalons.json."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from urllib.parse import urlparse
from datetime import date

import releases as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("ROADMAP_DATA") or os.path.join(ROOT, "data")
REL_DIR = os.path.join(DATA, "releases")
PROJETS = os.path.join(DATA, "projets.json")
JALONS = os.path.join(DATA, "jalons.json")
# ---------- configuration (rien en dur dans le code) ----------
# Lue dans cet ordre, chaque fichier complétant / remplaçant le précédent :
#   1. src/config.defaut.json            valeurs par défaut livrées avec l'application (ne pas modifier)
#   2. /etc/roadmap-bancs/config.json     facultatif : réglages communs à tous les utilisateurs du poste
#   3. $ROADMAP_CONFIG, sinon $ROADMAP_DATA/config.json   réglages de l'utilisateur, écrits par « ⚙ Paramètres »
CONFIG_DEFAUT = os.path.join(ROOT, "src", "config.defaut.json")
CONFIG_SYSTEME = "/etc/roadmap-bancs/config.json"
CONFIG = os.environ.get("ROADMAP_CONFIG") or os.path.join(DATA, "config.json")
THEMES = ("sombre", "clair")
ETATS = ("", "ok", "maj", "degrade", "panne")  # état d'un banc / outil en production (vide = non renseigné ; maj = en mise à jour)


class Invalid(ValueError):
    """Donnée refusée (message affiché tel quel à l'utilisateur)."""


def _lire_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise Invalid(f"Configuration illisible : {path} ({e})")
    if not isinstance(data, dict):
        raise Invalid(f"Configuration illisible : {path} (objet JSON attendu)")
    if "publier_vers" in data or "publier_url" in data:  # ancien format (1.1.x) : clés à la racine
        pub = data.setdefault("publication", {})
        pub.setdefault("serveur", data.pop("publier_vers", ""))
        pub.setdefault("lien", data.pop("publier_url", ""))
    return data


def _fusion(base, extra):
    out = dict(base)
    for k, v in extra.items():
        out[k] = _fusion(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def config():
    """Configuration effective (défauts + /etc + utilisateur)."""
    cfg = {}
    for path in (CONFIG_DEFAUT, CONFIG_SYSTEME, CONFIG):
        cfg = _fusion(cfg, _lire_json(path))
    return cfg


def poles():
    return [p["nom"] for p in config()["poles"]]


def save_config(data):
    """Valide et enregistre la configuration de l'utilisateur. Renvoie la configuration effective."""
    if not isinstance(data, dict):
        raise Invalid("Configuration : objet JSON attendu")
    cfg = _fusion(config(), data)
    app, pub, ppt, coul = (cfg.get(k) if isinstance(cfg.get(k), dict) else {}
                           for k in ("application", "publication", "ppt", "couleurs"))
    if app.get("theme") not in THEMES:
        raise Invalid("Thème : « sombre » ou « clair »")
    if not isinstance(app.get("port"), int) or not 1024 <= app["port"] <= 65535:
        raise Invalid("Port : nombre entre 1024 et 65535")
    serveur = _texte(pub.get("serveur", ""), "Serveur de publication", 200, True)
    if serveur and not re.fullmatch(r"[\w.-]+@[\w.-]+:/\S+", serveur):
        raise Invalid("Serveur de publication : format utilisateur@hôte:/chemin/index.html")
    lien = _texte(pub.get("lien", ""), "Lien de publication", 200, True)
    if lien and not re.fullmatch(r"https?://\S+", lien):
        raise Invalid("Lien de publication : adresse http://… ou https://…")
    couleur = lambda v, nom: v if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v) else _err(f"{nom} : couleur #rrggbb attendue")
    ps = cfg.get("poles")
    if not isinstance(ps, list) or not ps:
        raise Invalid("Pôles : au moins un pôle")
    propres = []
    for i, p in enumerate(ps, 1):
        p = p if isinstance(p, dict) else {}
        nom = _texte(p.get("nom"), f"Pôle n°{i} : nom", 60)
        propres.append({"nom": nom, "court": _texte(p.get("court"), f"Pôle « {nom} » : abréviation", 12),
                        "couleur": couleur(p.get("couleur"), f"Pôle « {nom} »")})
    noms = [p["nom"] for p in propres]
    if len(set(noms)) != len(noms):
        raise Invalid("Pôles : deux pôles portent le même nom")
    utilises = {p.get("pole") for p in _read_list()} - set(noms) - {""}
    if utilises:
        raise Invalid(f"Pôle « {sorted(utilises)[0]} » encore utilisé par des projets : change d'abord leur pôle")
    sup = coul.get("supplementaires")
    propre = {
        "application": {"titre": _texte(app.get("titre"), "Titre", 80), "titre_court": _texte(app.get("titre_court"), "Titre court", 40),
                        "theme": app["theme"], "port": app["port"],
                        "qui_travaille": _booleen(app.get("qui_travaille"), "Qui travaille sur quoi")},
        "poles": propres,
        "couleurs": {k: couleur(coul.get(k), f"Couleur « {k} »") for k in ("aujourdhui", "jalon", "retard")}
                    | {"supplementaires": [couleur(c, "Couleurs supplémentaires") for c in (sup if isinstance(sup, list) else [None])]},
        "publication": {"serveur": serveur, "lien": lien, "terminees": _booleen(pub.get("terminees"), "Versions terminées")},
        "equipe": _check_ressources(cfg.get("equipe", []), maxi=200),  # annuaire : choix en un clic dans les fiches
        "ppt": {"auteur": _texte(ppt.get("auteur", ""), "Auteur du PPT", 60, True),
                "mention": _texte(ppt.get("mention", ""), "Mention du PPT", 60, True)},
    }
    write_atomic(CONFIG, json.dumps(propre, ensure_ascii=False, indent=2) + "\n")
    return config()


def _booleen(v, nom):
    if not isinstance(v, bool):
        raise Invalid(f"{nom} : oui ou non attendu")
    return v


def _err(msg):
    raise Invalid(msg)


def _texte(v, nom, n, vide=False):
    v = " ".join(str(v if v is not None else "").split())
    if (not v and not vide) or len(v) > n:
        raise Invalid(f"{nom} : obligatoire, {n} caractères maximum" if not vide else f"{nom} : {n} caractères maximum")
    return v


def slug(nom):
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "projet"


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)  # jamais de fichier à moitié écrit


def _read_list():
    if not os.path.exists(PROJETS):
        return []
    with open(PROJETS, encoding="utf-8") as f:
        return json.load(f)


def release_path(pid):
    return os.path.join(REL_DIR, f"{pid}.md")


def load_all():
    out = []
    for p in _read_list():
        path = release_path(p["id"])
        text = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                text = f.read()
        versions = R.parse(text)
        equipes = p.get("equipes", {})  # équipe propre à une version (sinon : celle du projet)
        prods = p.get("prods", {})      # date de mise en production d'une version livrée
        for v in versions:
            v["ressources"] = equipes.get(_cle_version(v["version"]), [])
            v["prod"] = prods.get(_cle_version(v["version"]), "")
        out.append({"ressources": [], "etat": "", "etat_note": "", "etat_date": "", "prod_publie": True, "postes": [], **{k: x for k, x in p.items() if k not in ("equipes", "prods")}, "versions": versions})
    return out


def get(pid):
    return next((p for p in load_all() if p["id"] == pid), None)


def _check_versions(versions):
    if not isinstance(versions, list):
        raise Invalid("versions : liste attendue")
    clean = []
    for i, v in enumerate(versions, 1):
        if not isinstance(v, dict):
            raise Invalid(f"version n°{i} invalide")
        ver = str(v.get("version", "")).strip()
        if not ver or "]" in ver or "\n" in ver:
            raise Invalid(f"version n°{i} : numéro de version obligatoire (sans « ] »)")
        st = str(v.get("statut", "")).strip()
        if st and st not in R.STATUTS:
            raise Invalid(f"{ver} : statut inconnu « {st} »")
        motif = " ".join(str(v.get("motif", "") or "").split()) if st == "Bloqué" else ""
        if any(c in motif for c in "()→") or len(motif) > 80:
            raise Invalid(f"{ver} : motif du blocage trop long ou avec ( ) →")
        prod = str(v.get("prod", "") or "").strip()
        if prod and (len(R.norm_date(prod)) != 10 or st != "Terminé"):
            raise Invalid(f"{ver} : mise en production = une date AAAA-MM-JJ, pour une version livrée (Terminé)")
        dates = {"prod": R.norm_date(prod) if prod else ""}
        for f in ("debut", "fin", "prevu"):
            raw = str(v.get(f, "") or "").strip()
            d = R.norm_date(raw) if raw not in ("", "?") else ""
            if raw not in ("", "?") and not d:
                raise Invalid(f"{ver} : date « {raw} » invalide (AAAA-MM-JJ, AAAA-MM ou JJ/MM/AAAA)")
            dates[f] = d
        if dates["debut"] and dates["fin"] and dates["fin"] < dates["debut"][:len(dates["fin"])]:
            raise Invalid(f"{ver} : la fin ({dates['fin']}) est avant le début ({dates['debut']})")
        clean.append({"version": ver, "statut": st, **dates, "notes": str(v.get("notes", "") or ""), "motif": motif,
                      "ressources": _check_ressources(v.get("ressources", []))}
                     | {k: v[k] for k in ("decalage", "prevu_efface") if isinstance(v.get(k), bool)})  # choix faits à l'écran
    return clean


def _cle_version(version):
    """« v2.1 » et « 2.1.0 » : même version, même équipe."""
    k = R.vkey(version)
    return ".".join(map(str, k)) if k else str(version)


def _check_ressources(val, maxi=30):
    """Équipe du projet : liste de noms (ou texte « A, B »), sans doublon, dans l'ordre saisi."""
    noms = val.split(",") if isinstance(val, str) else val
    if not isinstance(noms, list):
        raise Invalid("Équipe : liste de noms attendue")
    out = []
    for n in noms:
        n = " ".join(str(n or "").split())
        if len(n) > 60:
            raise Invalid(f"Équipe : nom trop long ({n[:20]}…)")
        if n and n.lower() not in (x.lower() for x in out):
            out.append(n)
    if len(out) > maxi:
        raise Invalid(f"Équipe : {maxi} personnes maximum")
    return out


def _etat(src, ancien, nom):
    """État en production (du projet, ou d'un de ses postes) : validé ; date notée si l'état change sans date choisie."""
    etat = str(src.get("etat", "") or "")
    if etat not in ETATS:
        raise Invalid(f"{nom} : opérationnel, en mise à jour, dégradé, en panne, ou vide")
    note = _texte(src.get("etat_note", "") if etat else "", f"{nom} : commentaire", 120, True)
    d = str(src.get("etat_date", "") or "").strip()  # « opérationnel depuis le … » choisi à l'écran
    if d and (not etat or len(R.norm_date(d)) != 10):
        raise Invalid(f"{nom} : date AAAA-MM-JJ, avec un état renseigné")
    if not d and etat:  # pas de date donnée : inchangée si même état, sinon aujourd'hui
        d = ancien.get("etat_date", "") if etat == ancien.get("etat", "") else date.today().isoformat()
    return {"etat": etat, "etat_note": note, "etat_date": d}


def _postes(val, anciens, maxi=20):
    """Postes qui font tourner le banc (vide = le projet est un seul banc) : nom, état et version installée propres à chacun."""
    if not isinstance(val, list):
        raise Invalid("Postes : liste attendue")
    old = {a["nom"].lower(): a for a in anciens}
    out = []
    for x in val:
        x = x if isinstance(x, dict) else {"nom": x}
        nom = _texte(x.get("nom"), "Nom du poste", 40, True)
        if not nom:
            continue
        if nom.lower() in (o["nom"].lower() for o in out):
            raise Invalid(f"Poste en double : {nom}")
        ancien = old.get(nom.lower(), {})
        # version installée sur ce poste (deux postes peuvent tourner sur des versions différentes) ; absente = inchangée
        version = _texte(x.get("version", ancien.get("version", "")), f"Poste {nom} : version", 40, True)
        vdate = str(x.get("version_date", ancien.get("version_date", "")) or "").strip() if version else ""
        if vdate and len(R.norm_date(vdate)) != 10:
            raise Invalid(f"Poste {nom} : date de mise en production AAAA-MM-JJ")
        out.append({"nom": nom, **_etat(x, ancien, f"Poste {nom}"), "version": version, "version_date": vdate})
    if len(out) > maxi:
        raise Invalid(f"Postes : {maxi} maximum")
    return out


def save(data, pid=None):
    """Crée (pid=None) ou met à jour un projet. Renvoie le projet enregistré."""
    nom = str(data.get("nom", "")).strip()
    if not nom:
        raise Invalid("Le nom du projet est obligatoire")
    pole = str(data.get("pole", "")).strip()
    depot = str(data.get("depot", "") or "").strip()
    branche = str(data.get("branche", "") or "").strip()
    if est_url(depot):
        _check_url(depot)
        if branche and not re.fullmatch(BRANCHE_RE, branche):
            raise Invalid(f"Branche invalide : {branche}")
    else:
        depot, branche = os.path.expanduser(depot), ""  # un dossier local : on lit ses fichiers tels quels
        if depot and not os.path.isdir(depot):
            raise Invalid(f"Dossier du dépôt introuvable : {depot}")
    ressources = _check_ressources(data.get("ressources", []))
    prod_publie = data.get("prod_publie", True)
    if not isinstance(prod_publie, bool):
        raise Invalid("Affichage en production : oui ou non attendu")
    versions = _check_versions(data.get("versions", []))
    old = {R.vkey(v["version"]) or v["version"]: v for v in (get(pid) or {}).get("versions", [])} if pid else {}
    for v in versions:  # fin prévue initiale : gardée quand la fin bouge, sauf correction d'une erreur de saisie
        o = old.get(R.vkey(v["version"]) or v["version"], {})
        efface = v.pop("prevu_efface", False)  # date prévue elle-même fausse : on l'oublie
        decalage = v.pop("decalage", True)     # sans réponse (import, livraison) : vrai décalage du planning
        v["prevu"] = "" if efface else (v["prevu"] or o.get("prevu", ""))
        if not v["prevu"] and o.get("fin") and v["fin"] != o["fin"] and decalage:
            v["prevu"] = o["fin"]
    lst = _read_list()
    if pid is None:
        pid = slug(nom)
        base, n = pid, 2
        while any(p["id"] == pid for p in lst):
            pid, n = f"{base}-{n}", n + 1
        lst.append({"id": pid})
    entry = next((p for p in lst if p["id"] == pid), None)
    if entry is None:
        raise Invalid("Projet introuvable")
    entry.update({**_etat(data, entry, "État"), "prod_publie": prod_publie,
                  "postes": _postes(data.get("postes", []), entry.get("postes", []))})
    entry.update({"nom": nom, "pole": pole, "depot": depot, "branche": branche, "ressources": ressources,
                  "equipes": {_cle_version(v["version"]): v["ressources"] for v in versions if v["ressources"]},
                  "prods": {_cle_version(v["version"]): v["prod"] for v in versions if v["prod"]}})
    write_atomic(release_path(pid), R.fmt(nom, R.sort_versions(versions)))
    write_atomic(PROJETS, json.dumps(lst, ensure_ascii=False, indent=2) + "\n")
    return get(pid)


def delete(pid):
    lst = [p for p in _read_list() if p["id"] != pid]
    write_atomic(PROJETS, json.dumps(lst, ensure_ascii=False, indent=2) + "\n")
    if os.path.exists(release_path(pid)):
        os.replace(release_path(pid), release_path(pid) + ".supprime")  # récupérable à la main


def load_jalons():
    if not os.path.exists(JALONS):
        return []
    with open(JALONS, encoding="utf-8") as f:
        return json.load(f)


def save_jalons(jalons):
    """Jalons communs (salon, audit…) : [{date, label}], affichés sur le Gantt et le PPT."""
    if not isinstance(jalons, list):
        raise Invalid("jalons : liste attendue")
    clean = []
    for j in jalons:
        d = R.norm_date(str((j or {}).get("date", "")))
        label = " ".join(str((j or {}).get("label", "")).split())
        if len(d) != 10 or not label or len(label) > 60 or "=" in label:
            raise Invalid("Jalon : date AAAA-MM-JJ et libellé (60 caractères max, sans « = ») obligatoires")
        clean.append({"date": d, "label": label})
    clean.sort(key=lambda j: j["date"])
    write_atomic(JALONS, json.dumps(clean, ensure_ascii=False, indent=2) + "\n")
    return clean


# ---------- dépôt Git ----------
# ---------- dépôt distant (lien Git + branche) ----------
URL_RE = r"(?:https?|ssh)://[\w.@:%~+=-]+(?:/[\w.@:%~+=/-]*)?|file:///[\w.@%~+=/-]+|git@[\w.-]+:[\w.~+=/-]+"
BRANCHE_RE = r"\w[\w./-]{0,199}"
# jamais de question bloquante (mot de passe, empreinte) : le serveur local n'a pas de terminal
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=15"}


def est_url(depot):
    return bool(re.match(r"(?:https?|ssh|file)://|git@", depot or ""))


def _check_url(url):
    if not re.fullmatch(URL_RE, url):
        raise Invalid(f"Lien Git invalide : {url} (https://…, ssh://… ou git@serveur:groupe/projet.git)")


def _git_distant(*args):
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=180, env=GIT_ENV)
    except (OSError, subprocess.SubprocessError) as e:
        raise Invalid(f"Git impossible : {e}")
    if r.returncode:
        err = (r.stderr or r.stdout).strip().splitlines()
        raise Invalid("Git : " + (err[-1] if err else "erreur") +
                      " — accès au dépôt ? (bouton 🔑 Identifiants de la fiche projet)")
    return r.stdout


def branches(url):
    """Branches d'un dépôt distant : {"branches": [...], "defaut": "main"} (sans rien télécharger)."""
    _check_url(url)
    defaut, noms = "", []
    for line in _git_distant("ls-remote", "--symref", url).splitlines():
        ref, _, nom = line.partition("\t")
        if ref.startswith("ref: refs/heads/") and nom == "HEAD":
            defaut = ref[len("ref: refs/heads/"):]
        elif nom.startswith("refs/heads/"):
            noms.append(nom[len("refs/heads/"):])
    return {"branches": sorted(noms), "defaut": defaut}


def _git_cred(action, champs):
    """git credential approve / reject : passe par le gestionnaire d'identifiants configuré dans Git."""
    entree = "".join(f"{k}={v}\n" for k, v in champs.items()) + "\n"
    subprocess.run(["git", "credential", action], input=entree, text=True, capture_output=True, timeout=15, env=GIT_ENV)


def git_identifiants(url, utilisateur, secret):
    """Enregistre l'identifiant d'un serveur Git (lien https) dans le gestionnaire d'identifiants de Git, puis teste
    l'accès ; refusé = rien n'est gardé. L'application ne stocke jamais le mot de passe elle-même."""
    _check_url(url)
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname:
        raise Invalid("Identifiants : seulement pour un lien https://… (lien git@… : clé SSH du poste)")
    for v, nom in ((utilisateur, "Utilisateur"), (secret, "Mot de passe ou jeton")):
        if not isinstance(v, str) or not v or any(c in v for c in "\r\n\0"):
            raise Invalid(f"{nom} : obligatoire, sur une seule ligne")
    if not subprocess.run(["git", "config", "--get", "credential.helper"], capture_output=True, text=True).stdout.strip():
        # aucun gestionnaire : celui de base de Git (fichier ~/.git-credentials, lisible par l'utilisateur seul)
        subprocess.run(["git", "config", "--global", "credential.helper", "store"], capture_output=True, timeout=15)
    hote = u.hostname + (f":{u.port}" if u.port else "")
    _git_cred("reject", {"protocol": "https", "host": hote})  # oublie l'ancien identifiant de ce serveur
    champs = {"protocol": "https", "host": hote, "username": utilisateur, "password": secret}
    _git_cred("approve", champs)
    try:
        _git_distant("ls-remote", "--heads", url)
    except Invalid as e:
        _git_cred("reject", champs)
        raise Invalid(f"Identifiants refusés ou serveur injoignable ({e}) : rien n'a été enregistré")
    return f"Identifiants enregistrés pour {hote} : accès OK"


def cle_ssh():
    """Clé SSH publique du poste (créée si absente), à ajouter dans le profil du serveur Git pour les liens git@…"""
    cle = os.path.expanduser("~/.ssh/id_ed25519")
    if not os.path.exists(cle + ".pub"):
        os.makedirs(os.path.dirname(cle), mode=0o700, exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", cle], capture_output=True, timeout=30, check=True)
    with open(cle + ".pub", encoding="utf-8") as f:
        return {"cle": f.read().strip(), "chemin": cle + ".pub"}


def _cache(p):
    """Copie locale légère (bare, sans le contenu des fichiers) du dépôt distant, mise à jour. Renvoie son chemin."""
    cache = os.path.join(DATA, "depots", p["id"] + ".git")
    if os.path.isdir(cache) and _git_distant("-C", cache, "config", "remote.origin.url").strip() != p["depot"]:
        shutil.rmtree(cache)  # le lien a changé : nouvelle copie
    if os.path.isdir(cache):
        _git_distant("-C", cache, "fetch", "--prune", "--tags", "--force", "origin", "+refs/heads/*:refs/heads/*")
    else:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        _git_distant("clone", "--quiet", "--bare", "--filter=blob:none", "--", p["depot"], cache)
    return cache


def _source(p):
    """(lire, tags, origine) du dépôt d'un projet : dossier local, ou lien Git + branche.
    lire(["ROADMAP.md", "RELEASE.md"]) -> (nom trouvé, texte) ou None (noms insensibles à la casse)."""
    if not p or not p.get("depot"):
        raise Invalid("Renseigne d'abord le dépôt du projet (dossier local ou lien Git)")
    if not est_url(p["depot"]):
        if not os.path.isdir(p["depot"]):
            raise Invalid(f"Dossier du dépôt introuvable : {p['depot']}")
        def lire(names):
            f = _depot_file(p["depot"], names)
            if f:
                with open(f, encoding="utf-8") as fh:
                    return os.path.basename(f), fh.read()
        return lire, tag_dates(p["depot"]), p["depot"]
    cache = _cache(p)
    branche = p.get("branche") or _git_distant("-C", cache, "symbolic-ref", "--short", "HEAD").strip()
    if not re.fullmatch(BRANCHE_RE, branche) or subprocess.run(
            ["git", "-C", cache, "rev-parse", "-q", "--verify", f"refs/heads/{branche}"], capture_output=True).returncode:
        raise Invalid(f"Branche « {branche} » introuvable dans {p['depot']}")
    fichiers = {f.lower(): f for f in _git_distant("-C", cache, "ls-tree", "--name-only", f"refs/heads/{branche}").splitlines()}
    def lire(names):
        for n in names:
            if n.lower() in fichiers:
                return fichiers[n.lower()], _git_distant("-C", cache, "show", f"refs/heads/{branche}:{fichiers[n.lower()]}")
    return lire, tag_dates(cache), f"{p['depot']} ({branche})"


def _depot_file(depot, names):
    """Fichier du dépôt (insensible à la casse : Changelog.md / CHANGELOG.md)."""
    files = {f.lower(): f for f in os.listdir(depot)}
    for n in names:
        if n.lower() in files:
            return os.path.join(depot, files[n.lower()])
    return None


def tag_dates(depot):
    """{(1, 2, 0): '2026-04-27'} à partir des tags Git du dépôt."""
    try:
        out = subprocess.run(["git", "-C", depot, "for-each-ref", "--format=%(refname:short) %(creatordate:short)",
                              "refs/tags"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    res = {}
    for line in out.splitlines():
        tag, _, d = line.partition(" ")
        k = R.vkey(tag)
        if k:
            res[k] = d
    return res


def import_depot(pid):
    """Fusionne ROADMAP.md (ou RELEASE.md) / CHANGELOG.md du dépôt + dates des tags Git. Renvoie (projet, message)."""
    p = get(pid)
    lire, tags, origine = _source(p)
    # ROADMAP.md (ou l'ancien nom RELEASE.md) = le prévu, prioritaire ; CHANGELOG.md = le livré, complète les champs vides
    roadmap, changelog = lire(["ROADMAP.md", "RELEASE.md"]), lire(["CHANGELOG.md"])
    files = [f for f in (roadmap, changelog) if f]
    livre = R.parse(changelog[1]) if changelog else []
    unreleased = next((v for v in livre if v["version"].lower() == "unreleased"), None)  # pas une version : le travail en cours
    livre = [v for v in livre if v is not unreleased]
    dates_livraison = {R.vkey(v["version"]): v["fin"] for v in livre if v["statut"] == "Terminé" and v["fin"] and R.vkey(v["version"])}
    imported = R.merge(R.parse(roadmap[1]) if roadmap else [], livre)
    known = {R.vkey(v["version"]) for v in imported}
    for k, d in tags.items():  # versions taguées absentes du changelog
        if k not in known:
            imported.append({"version": "v" + ".".join(map(str, k)), "statut": "Terminé", "debut": "", "fin": d, "notes": ""})
    for v in imported:
        k = R.vkey(v["version"])
        if k:
            v["version"] = "v" + ".".join(map(str, k))  # numérotation homogène : v1.0.0
        if k in tags:  # une version taguée est livrée : date du tag si le fichier n'en donne pas
            v["statut"] = v["statut"] or "Terminé"
            v["fin"] = v["fin"] or tags[k]
    avant = {R.vkey(v["version"]) or v["version"] for v in p["versions"]}
    p["versions"] = R.merge(p["versions"], imported)
    livrees = []
    for v in p["versions"]:  # livrée (tag Git, sinon date du CHANGELOG) : plus « en cours », « planifiée » ou « en retard »
        k = R.vkey(v["version"])
        d = tags.get(k) or dates_livraison.get(k)
        if d and v["statut"] != "Terminé":
            if v["fin"] and v["fin"] != d and not v.get("prevu"):
                v["prevu"] = v["fin"]  # fin prévue du ROADMAP.md gardée : dérive réelle (prévu → livré)
            v["statut"], v["fin"] = "Terminé", d
            livrees.append(v["version"])
    rattache = ""
    if unreleased:  # [Unreleased] = la prochaine version prévue, pas une version à part
        cible = R.prochaine(p["versions"])
        if cible:
            cible["notes"] = cible["notes"] or unreleased["notes"]
            p["versions"] = [v for v in p["versions"] if v["version"].lower() != "unreleased"]  # ancien doublon
            rattache = f", [Unreleased] rattaché à {cible['version']}"
        elif not any(v["version"].lower() == "unreleased" for v in p["versions"]):
            p["versions"].append(unreleased)
    saved = save(p, pid)
    # conformité au standard des dépôts (modeles/GUIDE.md), constatée à l'import : affichée sur la carte du projet
    conf = {"roadmap": bool(roadmap) and roadmap[0].upper() == "ROADMAP.MD", "changelog": bool(changelog),
            "tags": bool(tags), "date": date.today().isoformat()}
    lst = _read_list()
    next(e for e in lst if e["id"] == pid)["conformite"] = saved["conformite"] = conf
    write_atomic(PROJETS, json.dumps(lst, ensure_ascii=False, indent=2) + "\n")
    src = " + ".join(nom for nom, _ in files) or "aucun fichier"
    ajoutees = len({R.vkey(v["version"]) or v["version"] for v in saved["versions"]} - avant)
    msg = f"{origine} : {src} + {len(tags)} tag(s) Git : {ajoutees} version(s) ajoutée(s)"
    return saved, msg + (f", passée(s) à Terminé : {', '.join(livrees)}" if livrees else "") + rattache


def _git(depot, *args):
    try:
        return subprocess.run(["git", "-C", depot, *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise Invalid(f"git impossible : {e}")


def _cible(p, cible):
    """(chemin dans le dépôt, contenu) de ROADMAP.md ou CHANGELOG.md ; refuse d'écraser des modifs non commitées."""
    if p and est_url(p.get("depot")):
        raise Invalid("Dépôt distant (lien Git) : l'écriture et la livraison demandent un dossier local (clone du dépôt)")
    if not p or not p.get("depot") or not os.path.isdir(p["depot"]):
        raise Invalid("Dossier du dépôt non renseigné ou introuvable")
    if cible not in ("ROADMAP.md", "CHANGELOG.md"):
        raise Invalid("Cible inconnue")
    path = _depot_file(p["depot"], [cible]) or os.path.join(p["depot"], cible)
    if os.path.exists(path):  # git sert de sauvegarde : on refuse d'écraser des modifications non commitées
        try:
            dirty = _git(p["depot"], "status", "--porcelain", "--", os.path.basename(path)).stdout.strip()
        except Invalid:
            dirty = ""
        if dirty:
            raise Invalid(f"{os.path.basename(path)} a des modifications non commitées dans le dépôt : commite-les d'abord")
    text = R.fmt(p["nom"], p["versions"]) if cible == "ROADMAP.md" else R.to_changelog(p["nom"], p["versions"])
    return path, text


def export_depot(pid, cible):
    """Écrit ROADMAP.md ou CHANGELOG.md dans le dépôt. Renvoie le chemin écrit."""
    path, text = _cible(get(pid), cible)
    write_atomic(path, text)
    return path


def livrer(pid, version):
    """Livre une version (guide §4) : statut Terminé + fin = aujourd'hui, ROADMAP.md et CHANGELOG.md écrits
    dans le dépôt, commit « Release vX.Y.Z » de ces 2 fichiers seulement, tag annoté. Pas de push."""
    p = get(pid)
    k = R.vkey(version)
    v = next((x for x in (p or {}).get("versions", []) if k and R.vkey(x["version"]) == k), None)
    if not v:
        raise Invalid(f"Version « {version} » introuvable (numéro X.Y.Z attendu)")
    if v["statut"] == "Terminé":
        raise Invalid(f"{v['version']} est déjà livrée")
    for c in ("ROADMAP.md", "CHANGELOG.md"):
        _cible(p, c)  # vérifie tout AVANT d'écrire quoi que ce soit
    depot, tag = p["depot"], "v" + ".".join(map(str, k))
    if _git(depot, "rev-parse", "--git-dir").returncode:
        raise Invalid(f"{depot} n'est pas un dépôt Git")
    if _git(depot, "rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode == 0:
        raise Invalid(f"Le tag {tag} existe déjà dans le dépôt : importe le dépôt pour mettre la version à jour")
    v.update(statut="Terminé", fin=date.today().isoformat(), motif="")
    saved = save(p, pid)
    paths = [export_depot(pid, c) for c in ("ROADMAP.md", "CHANGELOG.md")]
    for args in (["add", "--", *paths], ["commit", "-m", f"Release {tag}", "--", *paths], ["tag", "-a", tag, "-m", tag]):
        r = _git(depot, *args)
        if r.returncode:
            raise Invalid(f"Fichiers écrits mais « git {args[0]} » a échoué : {(r.stderr or r.stdout).strip()}")
    return saved, f"{tag} livrée : commit + tag créés. Reste à publier : git push && git push --tags"
