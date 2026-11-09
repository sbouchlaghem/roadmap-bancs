"""Génère la roadmap PPTX à partir de l'onglet « Versions » de Suivi_Projets_KEAS_V4.xlsx.

Usage :  python3 src/ppt/build_roadmap.py [--debut 09/2026] [--fin 01/2027] [fichier.xlsx ou .csv] [sortie.pptx]
  --debut / --fin : période affichée (MM/AAAA ou JJ/MM/AAAA). Sans option : valeurs DEBUT_ROADMAP / FIN_ROADMAP.

Les versions se saisissent dans chaque fiche projet, bloc « Historique des versions » :
  Version | Début | Fin | Description | Statut | Auteur   (on garde les anciennes : c'est l'historique)
  La liste des projets, leur pôle et leur fiche viennent de « Suivi Projets » (colonne « Onglet fiche »).
  - Statut      : Terminé / En cours / Planifié / Bloqué / En retard (vide = déduit des dates)
  - Début, Fin  : dates, ou « 09/2026 » pour tout un mois ; vides si inconnues
  - Commentaire : libre, pas affiché sur la slide
Le classeur est seulement lu, jamais modifié. Python standard uniquement.
"""
import argparse, csv, json, os, re, sys, tempfile, zipfile
from datetime import date, timedelta
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.pptx")
# Source des données : l'onglet « Versions » du fichier de suivi (un .csv marche aussi)
ap = argparse.ArgumentParser(description="Génère la roadmap PPTX depuis l'onglet Versions.")
ap.add_argument("source", nargs="?", default="Suivi_Projets_KEAS_V4.xlsx")  # usage en ligne de commande
ap.add_argument("sortie", nargs="?")
ap.add_argument("--debut", help="début de la période affichée, ex. 09/2026")
ap.add_argument("--fin", help="fin de la période affichée, ex. 01/2027")
ap.add_argument("--jalon", action="append", default=[], help="jalon vertical « 15/12/2026=Salon X » (répétable)")
ap.add_argument("--config", default=os.path.join(HERE, "..", "config.defaut.json"),
                help="configuration JSON (titres, pôles, couleurs, auteur) ; par défaut src/config.defaut.json")
ARGS = ap.parse_args()
with open(ARGS.config, encoding="utf-8") as f:
    CFG = json.load(f)
hexa = lambda c: c.lstrip("#").upper()  # « #da1f3d » -> « DA1F3D » (format PowerPoint)
TITRE = CFG["application"]["titre"]
C_AUJOURDHUI, C_JALON, C_RETARD = (hexa(CFG["couleurs"][k]) for k in ("aujourdhui", "jalon", "retard"))
SOURCE = ARGS.source
TODAY = date.today()
OUT = ARGS.sortie or os.path.join(os.getcwd(), f"{TODAY:%Y%m%d} - {TITRE}.pptx")

# Période affichée sans --debut / --fin : du mois en cours aux 4 mois suivants
DEBUT_ROADMAP = TODAY.replace(day=1)
FIN_ROADMAP = date(TODAY.year + (TODAY.month + 4) // 12, (TODAY.month + 4) % 12 + 1, 1) - timedelta(days=1)

# pôles et couleurs : configuration (pôle -> abréviation sur la slide -> couleur)
POLE_COURT = {p["nom"]: p["court"] for p in CFG["poles"]}
COLORS = {p["court"].upper(): hexa(p["couleur"]) for p in CFG["poles"]}
EXTRA_COLORS = [hexa(c) for c in CFG["couleurs"]["supplementaires"]]  # catégories hors configuration
MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août",
        "Septembre", "Octobre", "Novembre", "Décembre"]
MOIS_COURT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def parse_date(s, line, fin=False):
    s = (s or "").strip().split(" ")[0]  # « 04/09/2026 00:00 » exporté par Excel
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        s = f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", s) or re.fullmatch(r"()(\d{1,2})/(\d{4})", s)
    if not m:
        sys.exit(f"{line} : date invalide « {s} » (exemples : 04/09/2026, 09/2026)")
    j, mo, a = (int(v) if v else 1 for v in m.groups())
    try:
        d = date(a + 2000 if a < 100 else a, mo, j)
        if fin and not m.group(1):  # MM/AAAA en date de fin = dernier jour du mois
            d = date(d.year + d.month // 12, d.month % 12 + 1, 1) - timedelta(days=1)
        return d
    except ValueError:
        sys.exit(f"{line} : date inexistante « {s} »")


def norm(h):  # en-tête sans accents/majuscules/espaces : « Catégorie » -> « categorie »
    h = (h or "").strip().lower()
    for a, b in [("é", "e"), ("è", "e"), ("ê", "e"), ("ô", "o")]:
        h = h.replace(a, b)
    return h.replace(" ", "")


COLS = {"categorie": "cat", "pole": "cat", "projet": "nom", "nom": "nom", "version": "ver",
        "statut": "st", "debut": "debut", "fin": "fin", "prevu": "prevu"}
DERIVE = {}  # (nom, version) -> jours de retard sur la fin prévue initialement (colonne « prevu » du CSV)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:  # utf-8-sig : CSV enregistré par Excel
        text = f.read()
    numbered = [(n, l) for n, l in enumerate(text.splitlines(), start=1)
                if l.strip(" ;,\t") and not l.lstrip().startswith("#")]  # garde les vrais n° de ligne
    if not numbered:
        return []
    sep = max(";,\t", key=numbered[0][1].count)
    return [(n, next(csv.reader([l], delimiter=sep))) for n, l in numbered]


def read_xlsx(path, sheet):
    """Lit un onglet .xlsx (lecture seule, bibliothèque standard). Renvoie [(n° de ligne, [cellules])]."""
    import xml.etree.ElementTree as ET  # lecture seule : on ne réécrit jamais le classeur
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        sys.exit(f"Impossible d'ouvrir {path} : {e}")
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sh = next((s for s in wb.iterfind("m:sheets/m:sheet", ns) if s.get("name") == sheet), None)
    if sh is None:
        sys.exit(f"Onglet « {sheet} » introuvable dans {os.path.basename(path)}")
    rid = sh.get(f"{{{ns['r']}}}id")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(r.get("Target") for r in rels if r.get("Id") == rid)
    part = target.lstrip("/") if target.startswith("/") else "xl/" + target
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iterfind("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
    out = []
    for row in ET.fromstring(z.read(part)).iterfind("m:sheetData/m:row", ns):
        cells = {}
        for c in row.iterfind("m:c", ns):
            col = 0
            for ch in re.match(r"[A-Z]+", c.get("r")).group(0):
                col = col * 26 + ord(ch) - 64
            t, v = c.get("t"), c.find("m:v", ns)
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
            elif v is None:
                val = ""
            elif t == "s":
                val = shared[int(v.text)]
            elif t in ("str", "b", "e"):
                val = v.text or ""
            else:  # nombre : on garde la valeur brute, les dates sont converties plus bas
                val = ("N", float(v.text))
            cells[col] = val
        if cells:
            out.append((int(row.get("r")), [cells.get(k, "") for k in range(1, max(cells) + 1)]))
    return out


def as_text(v, is_date):
    if isinstance(v, tuple):  # nombre Excel
        if is_date:
            return f"{date(1899, 12, 30) + timedelta(days=int(v[1])):%d/%m/%Y}"
        return f"{v[1]:g}"
    return v


def read_suivi(path):
    """« Suivi Projets » : nom du projet -> (pôle, statut du projet). C'est la liste de référence des projets."""
    table = read_xlsx(path, "Suivi Projets")
    head = [norm(as_text(h, False)) for h in table[0][1]]
    ip, inom, ist, ifi = head.index("pole"), head.index("projet/banc"), head.index("statut"), head.index("ongletfiche")
    out = {}
    for _, row in table[1:]:
        row = row + [""] * (max(ip, inom, ist, ifi) + 1 - len(row))
        nom = " ".join(as_text(row[inom], False).split())
        if nom:
            out[nom] = (as_text(row[ip], False).strip(), as_text(row[ist], False).strip(),
                        as_text(row[ifi], False).strip())
    return out


def read_fiches(path, suivi):
    """Bloc « Historique des versions » de chaque fiche -> même format qu'un tableau de versions."""
    table = [("", ["Projet", "Version", "Statut", "Début", "Fin"])]
    for nom, (_, _, fiche) in suivi.items():
        if not fiche:
            print(f"⚠ Suivi Projets : {nom} n'a pas d'« Onglet fiche » — pas de versions lues")
            continue
        rows = read_xlsx(path, fiche)
        txt = lambda row, i: as_text(row[i], False).strip() if i < len(row) else ""
        h = next((k for k, (_, row) in enumerate(rows) if txt(row, 1) == "Historique des versions"), None)
        if h is None or h + 1 >= len(rows):
            print(f"⚠ Fiche « {fiche} » : bloc « Historique des versions » introuvable")
            continue
        head = {norm(txt(rows[h + 1][1], i)): i for i in range(len(rows[h + 1][1]))}
        col = {k: head.get(k) for k in ("version", "statut", "debut", "fin")}
        if col["version"] is None:
            print(f"⚠ Fiche « {fiche} » : colonne « Version » introuvable")
            continue
        for n, row in rows[h + 2:]:
            if txt(row, 1).startswith("Plan d"):
                break
            get = lambda k: row[col[k]] if col[k] is not None and col[k] < len(row) else ""
            if not as_text(get("version"), False).strip():
                continue  # ligne vide du bloc
            table.append((f"Fiche « {fiche} » ligne {n}", [nom, get("version"), get("statut"), get("debut"), get("fin")]))
    return table


def load(path):
    is_csv = path.lower().endswith(".csv")
    suivi = {} if is_csv else read_suivi(path)
    table = read_csv(path) if is_csv else read_fiches(path, suivi)
    if not table:
        sys.exit("Aucune donnée")
    header = [COLS.get(norm(as_text(h, False))) for h in table[0][1]]
    if {"nom", "ver"} - set(header) or (is_csv and "cat" not in header):
        sys.exit("En-tête attendu : Projet | Version | Statut | Début | Fin | Commentaire")
    items, en_cours = [], set()
    for n, row in table[1:]:
        lieu = n if isinstance(n, str) else f"Ligne {n}"
        r = {k: as_text(v, k in ("debut", "fin")).strip() for k, v in zip(header, row) if k}
        nom_complet, ver = " ".join(r.get("nom", "").split()), r.get("ver", "")
        if not nom_complet:
            continue
        if is_csv:
            cat = POLE_COURT.get(r.get("cat", ""), r.get("cat", ""))
        elif nom_complet in suivi:
            cat = POLE_COURT.get(suivi[nom_complet][0], suivi[nom_complet][0])
        else:
            print(f"⚠ {lieu} : « {nom_complet} » n'existe pas dans « Suivi Projets » — ligne ignorée")
            continue
        nom = nom_complet.split("]", 1)[1].strip() if nom_complet.startswith("[") and "]" in nom_complet else nom_complet
        a, b = parse_date(r.get("debut"), lieu), parse_date(r.get("fin"), lieu, fin=True)
        if a and b and b < a:
            sys.exit(f"{lieu} ({nom} {ver}) : la fin {b:%d/%m/%Y} est avant le début {a:%d/%m/%Y}")
        st = statut_of(r.get("st", ""), a, b, lieu)
        prevu = parse_date(r.get("prevu"), lieu, fin=True)
        if prevu and b and b != prevu:
            DERIVE[(nom, ver)] = (b - prevu).days
        # alertes de cohérence : n'arrêtent pas la génération
        if st == "Prévue" and a and a < TODAY:
            print(f"⚠ {lieu} {nom} {ver} : « Planifié » mais début passé ({a:%d/%m}) — en cours ou en retard ?")
        if st == "En cours" and b and b < TODAY:
            print(f"⚠ {lieu} {nom} {ver} : « En cours » mais fin passée ({b:%d/%m}) — terminée ou en retard ?")
        if st == "En cours":
            en_cours.add(nom_complet)
        items.append((cat, nom, ver, a, b, st))
    for nom_complet, (pole, st_projet, _) in suivi.items():
        if nom_complet in en_cours and st_projet in ("Non démarré", "Planifié", "Terminé"):
            print(f"⚠ Suivi Projets : {nom_complet} est « {st_projet} » mais a une version « En cours »")
        if st_projet == "En cours" and nom_complet not in en_cours:
            print(f"⚠ Suivi Projets : {nom_complet} est « En cours » mais aucune de ses versions n'est « En cours »")
    if not items:
        sys.exit("Aucune version")
    return items


def statut_of(s, a, b, n):
    s = s.strip().lower()
    for key, val in [("livr", "Livrée"), ("termin", "Livrée"), ("cours", "En cours"), ("prév", "Prévue"),
                     ("prev", "Prévue"), ("plan", "Prévue"), ("démarr", "Prévue"), ("bloq", "Bloquée"),
                     ("retard", "En retard")]:
        if key in s:
            return val
    if s:
        sys.exit(f"{n} : statut inconnu « {s} » (Livrée / En cours / Prévue / Bloquée)")
    if b and b < TODAY:
        return "Livrée"
    return "En cours" if a and a <= TODAY else "Prévue"


if ARGS.debut:
    DEBUT_ROADMAP = parse_date(ARGS.debut, "Option --debut")
if ARGS.fin:
    FIN_ROADMAP = parse_date(ARGS.fin, "Option --fin", fin=True)
if FIN_ROADMAP < DEBUT_ROADMAP:
    sys.exit(f"Période invalide : fin {FIN_ROADMAP:%d/%m/%Y} avant début {DEBUT_ROADMAP:%d/%m/%Y}")
ALL = load(SOURCE)
# Gantt : versions datées et pas terminées avant le début de la roadmap (l'historique reste dans le CSV)
ITEMS = [i for i in ALL if i[3] and i[4] and i[4] >= DEBUT_ROADMAP and i[3] <= FIN_ROADMAP]
undated = sorted({f"{i[1]} {i[2]}" for i in ALL if not (i[3] and i[4]) and i[5] != "Livrée"})
if undated:
    print("Pas sur la slide (dates manquantes) : " + ", ".join(undated))
if not ITEMS:
    sys.exit("Aucune version datée dans la période de la roadmap")
CATS = [c for c in dict.fromkeys(i[0] for i in ALL) if any(i[0] == c for i in ITEMS)]  # ordre de l'onglet
# versions d'un même projet regroupées, projets triés par leur 1re date dans la période
proj_start = {}
for i in ITEMS:
    proj_start[(i[0], i[1])] = min(proj_start.get((i[0], i[1]), i[3]), i[3])
ITEMS.sort(key=lambda i: (CATS.index(i[0]), proj_start[(i[0], i[1])], i[1], i[3]))
color_of = {}
for c in CATS:
    color_of[c] = COLORS.get(c.upper()) or EXTRA_COLORS[len([k for k in color_of if k.upper() not in COLORS]) % len(EXTRA_COLORS)]

# fenêtre : du lundi précédant le 1er du mois de début au lundi suivant la fin du dernier mois
first = max(DEBUT_ROADMAP, min(i[3] for i in ITEMS)).replace(day=1)
last = min(FIN_ROADMAP, max(i[4] for i in ITEMS))
after = date(last.year + last.month // 12, last.month % 12 + 1, 1)
T0 = first - timedelta(days=first.weekday())
T1 = after + timedelta(days=(7 - after.weekday()) % 7)
DAYS = (T1 - T0).days

EMU = 914400
CAT_X, CAT_W = int(0.55 * EMU), int(0.34 * EMU)
NAME_X, NAME_W = CAT_X + CAT_W + int(0.05 * EMU), int(2.35 * EMU)
GX0, GX1 = NAME_X + NAME_W + int(0.05 * EMU), int(12.75 * EMU)
MONTH_Y, MONTH_H = int(1.42 * EMU), int(0.26 * EMU)
WEEK_Y, WEEK_H = MONTH_Y + MONTH_H, int(0.22 * EMU)
ROW_Y0 = WEEK_Y + WEEK_H + int(0.06 * EMU)
CAT_GAP = int(0.07 * EMU)
AREA_BOTTOM = int(6.45 * EMU)
xd = lambda dt: GX0 + (GX1 - GX0) * (dt - T0).days // DAYS


def geo(it):
    """Position de la barre et de son étiquette de dates (x en EMU)."""
    cat, nom, ver, a, b, st = it
    x0, x1 = xd(max(a, T0)), xd(min(b + timedelta(days=1), T1))
    tag = ("⚠ " if st in ("Bloquée", "En retard") else "") + ver
    fits = x1 - x0 >= int((0.12 + 0.065 * len(tag)) * EMU)  # sinon la version passe à côté de la barre
    lw, gap = int(((0.95 if fits else 1.45) + (0.35 if (nom, ver) in DERIVE else 0)) * EMU), int(0.04 * EMU)
    right = x1 + gap + lw <= GX1 or x0 - gap - lw < GX0
    lx = x1 + gap if right else x0 - gap - lw
    return dict(x0=x0, x1=x1, tag=tag, fits=fits, lw=lw, right=right, lx=lx,
                left_edge=min(x0, lx), right_edge=max(x1, lx + lw))


# une ligne par projet ; une version qui chevauche (barre + dates) la précédente passe sur une sous-ligne
LANES = []  # (cat, nom, [items], 1re sous-ligne du projet ?)
for key in dict.fromkeys((i[0], i[1]) for i in ITEMS):
    lanes = []
    for it in sorted((i for i in ITEMS if (i[0], i[1]) == key), key=lambda i: i[3]):
        g = geo(it)
        lane = next((l for l in lanes if geo(l[-1])["right_edge"] + int(0.05 * EMU) <= g["left_edge"]), None)
        if lane is None:
            lanes.append([it])
        else:
            lane.append(it)
    LANES += [(key[0], key[1], l, k == 0) for k, l in enumerate(lanes)]
ROW_H = min(int(0.305 * EMU), (AREA_BOTTOM - ROW_Y0 - CAT_GAP * (len(CATS) - 1)) // len(LANES))

nid = [100]


def sp(x, y, w, h, text="", fill=None, line=None, sz=900, bold=False, color="000000",
       algn="ctr", geom="rect", rot=0, name="Shape", lw=6350):
    nid[0] += 1
    fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    line_xml = (f'<a:ln w="{lw}"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>'
                if line else "<a:ln><a:noFill/></a:ln>")
    rot_xml = f' rot="{rot}"' if rot else ""
    av = '<a:gd name="adj" fmla="val 30000"/>' if geom == "roundRect" else ""
    run = (f'<a:r><a:rPr lang="fr-FR" sz="{sz}" b="{int(bold)}" dirty="0">'
           f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
           f'<a:latin typeface="Tahoma"/><a:cs typeface="Tahoma"/></a:rPr>'
           f'<a:t>{escape(text)}</a:t></a:r>') if text else ""
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{nid[0]}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm{rot_xml}><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
            f'<a:prstGeom prst="{geom}"><a:avLst>{av}</a:avLst></a:prstGeom>{fill_xml}{line_xml}</p:spPr>'
            f'<p:txBody><a:bodyPr wrap="none" lIns="18288" tIns="0" rIns="18288" bIns="0" anchor="ctr" rtlCol="0">'
            f'<a:noAutofit/></a:bodyPr><a:lstStyle/><a:p><a:pPr algn="{algn}"/>{run}'
            f'<a:endParaRPr lang="fr-FR" sz="{sz}" dirty="0"/></a:p></p:txBody></p:sp>')


def vline(x, y0, y1, color, w=6350, dash=None, name="Ligne"):
    nid[0] += 1
    dash_xml = f'<a:prstDash val="{dash}"/>' if dash else ""
    return (f'<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="{nid[0]}" name="{name}"/><p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y0}"/><a:ext cx="0" cy="{y1 - y0}"/></a:xfrm>'
            f'<a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:ln w="{w}"><a:solidFill><a:srgbClr val="{color}"/>'
            f'</a:solidFill>{dash_xml}</a:ln></p:spPr></p:cxnSp>')


shapes, rows, y = [], [], ROW_Y0
for i, ln in enumerate(LANES):
    if i and ln[0] != LANES[i - 1][0]:
        y += CAT_GAP
    rows.append((ln, y)); y += ROW_H
Y_END = y

# en-tête mois
m, k = date(T0.year, T0.month, 1), 0
while m < T1:
    nxt = date(m.year + m.month // 12, m.month % 12 + 1, 1)
    a, b = xd(max(m, T0)), xd(min(nxt, T1))
    label = MOIS[m.month - 1] if b - a > int(0.9 * EMU) else MOIS_COURT[m.month - 1].capitalize()
    if b - a < int(0.4 * EMU):
        label = ""  # bout de mois de quelques jours en bordure
    shapes.append(sp(a, MONTH_Y, b - a, MONTH_H, label, fill="595959" if k % 2 else "7F7F7F",
                     line="FFFFFF", sz=1000, bold=True, color="FFFFFF", name=f"Mois {m:%m/%Y}"))
    if m > T0:
        shapes.append(vline(a, MONTH_Y, Y_END, "A6A6A6", w=9525, name="Limite mois"))
    m, k = nxt, k + 1

# en-tête semaines + grille
wk_sz = 700 if (GX1 - GX0) * 7 // DAYS > int(0.4 * EMU) else 550
wk = T0
while wk < T1:
    a, b = xd(wk), xd(wk + timedelta(days=7))
    n = wk.isocalendar()[1]
    shapes.append(sp(a, WEEK_Y, b - a, WEEK_H, f"S{n}", fill="F2F2F2", line="FFFFFF",
                     sz=wk_sz, color="595959", name=f"Semaine {n}"))
    shapes.append(vline(a, ROW_Y0, Y_END, "E0E0E0", name="Grille"))
    wk += timedelta(days=7)
shapes.append(vline(GX1, ROW_Y0, Y_END, "E0E0E0", name="Grille"))

# bandeaux catégories (texte vertical comme le deck d'origine)
for cat in CATS:
    ys = [yy for (c, *_), yy in rows if c == cat]
    top, h = ys[0], ys[-1] + ROW_H - ys[0]
    cx, cy = CAT_X + CAT_W // 2, top + h // 2
    lbl = cat.upper() if len(cat) <= 5 else cat.upper()[:5] + "."
    shapes.append(sp(cx - h // 2, cy - CAT_W // 2, h, CAT_W, lbl if h > int(0.45 * EMU) else lbl[:3],
                     fill="D9D9D9", sz=1000, bold=True, rot=16200000, name=f"Catégorie {cat}"))

def tint(hexc, f=0.55):  # couleur éclaircie vers le blanc
    return "".join(f"{int(int(hexc[k:k + 2], 16) + (255 - int(hexc[k:k + 2], 16)) * f):02X}" for k in (0, 2, 4))


def bar_style(cat, st):
    c = color_of[cat]
    return {"Livrée": dict(fill=tint(c), color="404040"),
            "En cours": dict(fill=c, color="FFFFFF"),
            "Prévue": dict(fill="FFFFFF", line=c, lw=15875, color=c),
            "Bloquée": dict(fill=c, line="000000", lw=28575, color="FFFFFF"),
            "En retard": dict(fill=c, line=C_RETARD, lw=28575, color="FFFFFF")}[st]


# lignes : bande par projet, nom sur la 1re sous-ligne, barres avec version, dates
grp = -1
for (cat, nom, lane, first_lane), yy in rows:
    grp += first_lane
    if grp % 2 == 0:
        shapes.append(sp(NAME_X, yy, GX1 - NAME_X, ROW_H, fill="F7F7F7", name="Bande"))
    if first_lane:
        shapes.append(sp(NAME_X, yy, NAME_W, ROW_H, nom, sz=950, algn="l", name=f"Nom {nom}"))
    bh = int(ROW_H * 0.62)
    for it in lane:
        _, _, ver, a, b, st = it
        g = geo(it)
        shapes.append(sp(g["x0"], yy + (ROW_H - bh) // 2, g["x1"] - g["x0"], bh, g["tag"] if g["fits"] else "",
                         geom="roundRect", sz=850, bold=True, name=f"Barre {nom} {ver}", **bar_style(cat, st)))
        dv = DERIVE.get((nom, ver))
        shapes.append(sp(g["lx"], yy, g["lw"], ROW_H, ("" if g["fits"] else g["tag"] + "  ") + f"{a:%d/%m} → {b:%d/%m}"
                         + (f"  ({dv:+d} j)" if dv else ""),
                         sz=750, color="595959", algn="l" if g["right"] else "r", name=f"Dates {nom} {ver}"))

# repère aujourd'hui
if T0 <= TODAY < T1:
    tx = xd(TODAY)
    shapes.append(vline(tx, WEEK_Y, Y_END, C_AUJOURDHUI, w=19050, dash="dash", name="Aujourd'hui"))
    shapes.append(sp(tx - int(0.55 * EMU), Y_END + int(0.02 * EMU), int(1.1 * EMU), int(0.2 * EMU),
                     f"Aujourd'hui ({TODAY:%d/%m})", sz=750, bold=True, color=C_AUJOURDHUI, name="Aujourd'hui label"))

# jalons communs (salon, audit…) : trait vertical + libellé sous le Gantt
for arg in ARGS.jalon:
    jd, _, label = arg.partition("=")
    jd = parse_date(jd, "Option --jalon")
    if T0 <= jd < T1:
        jx = xd(jd)
        shapes.append(vline(jx, WEEK_Y, Y_END, C_JALON, w=12700, dash="sysDash", name=f"Jalon {label}"))
        jw, left = int(1.6 * EMU), jx + int(1.65 * EMU) > GX1  # libellé à droite du trait, à gauche près du bord
        shapes.append(sp(jx - jw - int(0.03 * EMU) if left else jx + int(0.03 * EMU), Y_END + int(0.02 * EMU), jw,
                         int(0.2 * EMU), f"{label} ({jd:%d/%m})", sz=750, bold=True, color=C_JALON,
                         algn="r" if left else "l", name=f"Jalon label {label}"))

# légende
lx, ly = NAME_X, Y_END + int(0.28 * EMU)
legend = [(cat, dict(fill=color_of[cat])) for cat in CATS]
legend += [("|", None)] + [(st, bar_style(CATS[0], st) if st != "Livrée" else dict(fill=tint("7F7F7F")))
                           for st in ("Livrée", "En cours", "Prévue", "Bloquée", "En retard")]
step = min(int(1.15 * EMU), (GX1 - NAME_X) // (len(legend) - 1))  # 6 pôles + 5 statuts tiennent sur la largeur
for label, style in legend:
    if style is None:  # séparateur catégories / statuts
        shapes.append(vline(lx - int(0.15 * EMU), ly + int(0.02 * EMU), ly + int(0.22 * EMU), "A6A6A6"))
        continue
    if label in ("En cours", "Prévue", "Bloquée", "En retard"):
        style = {**style, "fill": style["fill"] if label == "Prévue" else "7F7F7F",
                 "line": style.get("line") and {"Prévue": "7F7F7F", "En retard": C_RETARD}.get(label, "000000")}
    style = {k: v for k, v in style.items() if k != "color"}
    shapes.append(sp(lx, ly + int(0.05 * EMU), int(0.3 * EMU), int(0.14 * EMU), geom="roundRect",
                     name=f"Légende {label}", **style))
    shapes.append(sp(lx + int(0.33 * EMU), ly, int(0.85 * EMU), int(0.24 * EMU),
                     {"Livrée": "Terminé", "Prévue": "Planifié", "Bloquée": "Bloqué"}.get(label, label), sz=900, algn="l",
                     name=f"Légende txt {label}"))
    lx += step

periode = f"{MOIS_COURT[first.month - 1]} {first.year} – {MOIS_COURT[last.month - 1]} {last.year}"

# ---------- assemblage à partir du modèle (slides 1, 15, 18 conservées) ----------
zin = zipfile.ZipFile(TEMPLATE)
files = {n: zin.read(n) for n in zin.namelist()}
txt = lambda n: files[n].decode("utf-8")

s15 = txt("ppt/slides/slide15.xml")
start, end = s15.index("<p:spTree>"), s15.index("</p:spTree>")
tree = s15[start:end]
keep = [tree[:tree.index("</p:grpSpPr>") + len("</p:grpSpPr>")]]
mo = re.search(r"<mc:AlternateContent.*?</mc:AlternateContent>", tree, re.S)  # objet OLE du modèle
if mo:
    keep.append(mo.group(0))
for nm in ["Titel 5", "Text Placeholder 6", "Footer Placeholder 6"]:
    i = tree.index(f'name="{nm}"'); s = tree.rfind("<p:sp>", 0, i); e = tree.index("</p:sp>", i) + 7
    keep.append(tree[s:e])
s15 = s15[:start] + "".join(keep) + "".join(shapes) + s15[end:]
for old, new in [("<a:t>Envisaged D&amp;N Roadmap </a:t>", f"<a:t>{escape(TITRE)} </a:t>"),
                 ("<a:t>(indicative and early stage approximation)</a:t>", f"<a:t>({escape(periode)})</a:t>"),
                 ("<a:t>DIRAC Roadmap </a:t>", f"<a:t>{escape(CFG['application']['titre_court'])} </a:t>"),
                 ("<a:t>| 24/11/2022</a:t>", f"<a:t>| {TODAY:%d/%m/%Y}</a:t>")]:
    assert old in s15, old
    s15 = s15.replace(old, new)
files["ppt/slides/slide15.xml"] = s15.encode("utf-8")

s1 = txt("ppt/slides/slide1.xml")
for old, new in [("Indicative DIRAC Development Plan &amp; Roadmap", escape(TITRE)),
                 ("Challenges, considerations and risk", f"Planning {escape(periode)}"),
                 ("For internal discussion", escape(CFG["ppt"]["mention"])),
                 ("25.11.2022 | Oliver Bosshard", f"{TODAY:%d.%m.%Y}" + (f" | {escape(CFG['ppt']['auteur'])}" if CFG["ppt"]["auteur"] else ""))]:
    assert old in s1, old
    s1 = s1.replace(old, new)
files["ppt/slides/slide1.xml"] = s1.encode("utf-8")

# ne garder que les slides 1, 15 et 18 dans la présentation
rels = txt("ppt/_rels/presentation.xml.rels")
rid = {}
for t in re.findall(r"<Relationship [^>]*slides/slide\d+\.xml[^>]*>", rels):
    rid[re.search(r"slides/slide(\d+)\.xml", t).group(1)] = re.search(r'Id="(rId\d+)"', t).group(1)
want = {rid["1"], rid["15"], rid["18"]}
pres = re.sub(r'<p:sldId id="\d+" r:id="(rId\d+)"/>', lambda m: m.group(0) if m.group(1) in want else "",
              txt("ppt/presentation.xml"))
files["ppt/presentation.xml"] = pres.encode("utf-8")
# shortcut: les autres slides restent dans le zip (invisibles, ~6 Mo) ; nettoyer si la taille gêne

fd, tmp = tempfile.mkstemp(suffix=".pptx", dir=os.path.dirname(os.path.abspath(OUT)))
os.close(fd)
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
    for info in zin.infolist():
        z.writestr(info, files[info.filename])
os.replace(tmp, OUT)  # écriture atomique : pas de fichier à moitié écrit si le PPT est ouvert ailleurs
print(f"OK : {len(ITEMS)} versions affichées ({len(ALL)} dans l'historique), {periode} -> {OUT}")
