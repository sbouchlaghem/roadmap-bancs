"""Lecture / écriture des ROADMAP.md (historique + versions à venir) et export CHANGELOG.md.

Format d'un ROADMAP.md (ancien nom : RELEASE.md) (versions de la plus récente à la plus ancienne) :

    # Release — GBR3W Testbench

    ## [2.2.0] - Planifié - 2027-01-04 → 2027-02-12
    - Fonctionnalité prévue

    ## [2.1.0] - Bloqué (attente cartes) - 2026-09-21 → 2026-11-13 (prévu 2026-10-30)
    ### Added
    - ...

Dates en AAAA-MM-JJ (ou AAAA-MM pour un mois), « ? » si inconnue.
« (prévu …) » : fin prévue initialement, ajoutée par l'outil quand la fin change (sert à mesurer la dérive).
La lecture accepte aussi les changelogs existants : « ## 1.0.2 », « ## [2.2.0] — 2026-08-28 », « ## [Unreleased] »,
« [2.0.2] - 2026-10-05 » (sans ##).
"""
import re
from datetime import date

STATUTS = ["Terminé", "En cours", "Planifié", "Bloqué", "En retard"]
MANUELS = ("Terminé", "Bloqué")  # les seuls statuts qui ne se déduisent pas des dates
_VERSION = r"v?\d+(?:\.\d+)*|unreleased|\?"
# « ## 1.0.2 », « ## [1.0.2] … » ou, sans ##, « [1.0.2] - 2026-10-05 » (crochets obligatoires)
_HEAD = re.compile(rf"^(?:##\s+\[?({_VERSION})\]?|\[({_VERSION})\])(?=\s|$)(.*)$", re.I)
_MOTIF = re.compile(r"Bloqué\s*\(([^)]*)\)", re.I)
_PREVU = re.compile(r"\(prévu\s+([^)]*)\)", re.I)
_DATE = re.compile(r"\d{4}-\d{1,2}(?:-\d{1,2})?|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{4}")


def norm_date(s):
    """« 15/06/2026 » -> « 2026-06-15 », « 01/2027 » -> « 2027-01 », sinon AAAA-MM(-JJ) normalisé."""
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        s = f"{m[3]}-{m[2]}-{m[1]}"
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        s = f"{m[2]}-{m[1]}"
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", s)
    if not m:
        return ""
    try:  # refuse 2026-13-40
        date(int(m[1]), int(m[2]), int(m[3] or 1))
    except ValueError:
        return ""
    return f"{m[1]}-{int(m[2]):02d}" + (f"-{int(m[3]):02d}" if m[3] else "")


def _first_date(s):
    m = _DATE.search(s)
    return norm_date(m.group(0)) if m else ""


def deduce(debut, fin, today=None):
    """Statut déduit des dates (« Terminé » vient du tag Git à l'import, « Bloqué » s'écrit à la main)."""
    t = (today or date.today()).isoformat()
    if fin and (fin + "-31")[:10] < t:  # fin « 2026-11 » = fin du mois
        return "En retard"
    if debut:
        return "En cours" if debut <= t else "Planifié"
    return ""


def parse(text, today=None):
    """Texte markdown -> liste de versions {version, statut, debut, fin, notes} dans l'ordre du fichier."""
    out, cur = [], None
    for line in text.splitlines():
        m = _HEAD.match(line.strip())
        if m:
            ver, rest = m.group(1) or m.group(2), m.group(3)
            motif = prevu = ""
            b = _MOTIF.search(rest)  # avant le statut : le motif peut contenir « en cours »
            if b:
                motif, rest = b[1].strip(), rest[:b.start()] + "Bloqué" + rest[b.end():]
            b = _PREVU.search(rest)
            if b:
                prevu, rest = norm_date(b[1].strip()), rest[:b.start()] + rest[b.end():]
            statut = next((s for s in STATUTS if s.lower() in rest.lower()), "")
            if "→" in rest:
                left, right = rest.split("→", 1)
                debut, fin = _first_date(left), _first_date(right)
            else:
                debut, fin = "", _first_date(rest)  # « ## [1.2.2] - 2026-06-15 » = date de livraison
            if ver.lower() == "unreleased":
                ver, statut = "Unreleased", statut or "En cours"
            elif not statut and fin and "→" not in rest:
                statut = "Terminé"
            elif statut not in MANUELS and "→" in rest:  # Planifié / En cours / En retard : les dates font foi
                statut = deduce(debut, fin, today) or statut
            cur = {"version": ver, "statut": statut, "debut": debut, "fin": fin, "notes": [],
                   "prevu": prevu, "motif": motif if statut == "Bloqué" else ""}
            out.append(cur)
        elif cur is not None:
            cur["notes"].append(line.rstrip())
    for v in out:
        v["notes"] = "\n".join(v["notes"]).strip("\n")
    return out


def fmt(nom, versions, today=None):
    """Versions -> ROADMAP.md (statut écrit seulement s'il ne se déduit pas des dates)."""
    lines = [f"# Roadmap — {nom}", "",
             "<!-- ## [version] - début → fin   (statut déduit des dates ; écrire « Terminé » ou « Bloqué (motif) » si besoin ;"
             " dates AAAA-MM-JJ, AAAA-MM ou ? ; « (prévu …) » = fin prévue initialement, gérée par l'outil) -->", ""]
    for v in versions:
        head = f"## [{v['version']}]"
        if v.get("statut") and (v["statut"] in MANUELS or not deduce(v.get("debut"), v.get("fin"), today)):
            head += f" - {v['statut']}" + (f" ({v['motif']})" if v["statut"] == "Bloqué" and v.get("motif") else "")
        head += f" - {v.get('debut') or '?'} → {v.get('fin') or '?'}"
        if v.get("prevu") and v["prevu"] != v.get("fin"):
            head += f" (prévu {v['prevu']})"
        lines.append(head)
        if v.get("notes", "").strip():
            lines.append(v["notes"].strip("\n"))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def to_changelog(nom, versions):
    """Versions -> CHANGELOG.md (format Keep a Changelog : versions livrées + Unreleased pour l'en-cours)."""
    lines = ["# Changelog", "", f"Historique des versions de {nom}.", ""]
    pending = [v for v in versions if v.get("statut") in ("En cours", "Bloqué", "En retard") and v.get("notes")]
    if pending:
        lines += ["## [Unreleased]", ""]
        for v in pending:
            lines += [f"<!-- {v['version']} -->", v["notes"].strip("\n"), ""]
    for v in versions:
        if v.get("statut") == "Terminé":
            lines.append(f"## [{v['version'].lstrip('vV')}]" + (f" - {v['fin']}" if v.get("fin") else ""))
            if v.get("notes", "").strip():
                lines += ["", v["notes"].strip("\n")]
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def vkey(version):
    """Clé de tri/fusion : « v2.0 » == « 2.0.0 ». None si pas un numéro."""
    s = str(version).strip().lstrip("vV")
    if not re.fullmatch(r"\d+(?:\.\d+)*", s):
        return None
    p = [int(x) for x in s.split(".")]
    return tuple(p + [0] * (3 - len(p)))  # 1.2.3.4 garde ses 4 nombres


def sort_versions(versions):
    """Plus récente en premier ; « Unreleased » et « ? » en tête."""
    return sorted(versions, key=lambda v: (vkey(v["version"]) is not None, vkey(v["version"]) or ()), reverse=True)


def prochaine(versions):
    """Prochaine version à livrer : la plus petite version numérotée non terminée au-dessus de la dernière livrée."""
    derniere = max((vkey(v["version"]) for v in versions if v.get("statut") == "Terminé" and vkey(v["version"])), default=())
    candidates = [v for v in versions if v.get("statut") != "Terminé" and vkey(v["version"]) and vkey(v["version"]) > derniere]
    return min(candidates, key=lambda v: vkey(v["version"]), default=None)


def merge(existing, imported):
    """Ajoute les versions importées ; une version déjà connue garde ses valeurs, on ne complète que les vides."""
    by = {vkey(v["version"]) or v["version"]: dict(v) for v in existing}
    for v in imported:
        k = vkey(v["version"]) or v["version"]
        if k in by:
            for f in ("statut", "debut", "fin", "notes", "prevu", "motif"):
                if not by[k].get(f) and v.get(f):
                    by[k][f] = v[f]
        else:
            by[k] = dict(v)
    return sort_versions(list(by.values()))
