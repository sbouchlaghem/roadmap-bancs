import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date

TMP = tempfile.mkdtemp()
os.environ["ROADMAP_DATA"] = os.path.join(TMP, "data")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import server  # noqa: E402
import store  # noqa: E402


def snapshot(path):
    """Données publiées (window.SNAPSHOT) d'une page générée par server.publier."""
    import json, re
    html = open(path, encoding="utf-8").read()
    return json.loads(re.search(r"window\.SNAPSHOT = (.*?);</script>", html, re.S).group(1).replace("<\\/", "</"))


def gantt_versions(path):
    return {v["version"] for p in snapshot(path)["projets"] for v in p["versions"]}


def git(depot, *a):
    return subprocess.run(["git", "-C", depot, *a], capture_output=True, text=True, check=True).stdout


class TestStore(unittest.TestCase):
    def test_fin_prevue_gardee(self):
        p = store.save({"nom": "Derive", "versions": [{"version": "1.0.0", "debut": "2026-01-01", "fin": "2026-02-01"}]})
        v = store.save({**p, "versions": [{**p["versions"][0], "fin": "2026-03-01"}]}, p["id"])["versions"][0]
        self.assertEqual((v["fin"], v["prevu"]), ("2026-03-01", "2026-02-01"))
        v = store.save({**p, "versions": [{**v, "prevu": "", "fin": "2026-04-01"}]}, p["id"])["versions"][0]
        self.assertEqual(v["prevu"], "2026-02-01")  # la 1re date prévue reste la référence

    def test_motif_seulement_si_bloque(self):
        p = store.save({"nom": "Motif", "versions": [{"version": "1.0.0", "statut": "Bloqué", "motif": "cartes"},
                                                      {"version": "0.9.0", "statut": "Terminé", "motif": "x"}]})
        self.assertEqual([v["motif"] for v in p["versions"]], ["cartes", ""])
        with self.assertRaises(store.Invalid):
            store.save({"nom": "Motif", "versions": [{"version": "1", "statut": "Bloqué", "motif": "a (b)"}]}, p["id"])

    def test_jalons(self):
        self.assertEqual(store.save_jalons([{"date": "2026-12-15", "label": " Audit  client "}, {"date": "2026-11-01", "label": "A"}]),
                         [{"date": "2026-11-01", "label": "A"}, {"date": "2026-12-15", "label": "Audit client"}])
        self.assertEqual(len(store.load_jalons()), 2)
        with self.assertRaises(store.Invalid):
            store.save_jalons([{"date": "2026-12", "label": "mois seul"}])

    def test_livrer(self):
        depot = tempfile.mkdtemp(dir=TMP)
        git(depot, "init", "-q")
        git(depot, "config", "user.name", "Test")
        git(depot, "config", "user.email", "test@example.com")
        open(os.path.join(depot, "a.txt"), "w").write("x")
        git(depot, "add", "a.txt")
        git(depot, "commit", "-qm", "init")
        p = store.save({"nom": "Livre", "depot": depot,
                        "versions": [{"version": "2.2.0", "debut": "2026-01-01", "fin": "2026-02-01", "notes": "- A"}]})
        open(os.path.join(depot, "a.txt"), "w").write("modif non commitée")  # ne doit pas partir dans le commit
        saved, msg = store.livrer(p["id"], "2.2.0")
        v = saved["versions"][0]
        self.assertEqual((v["statut"], v["fin"], v["prevu"]), ("Terminé", date.today().isoformat(), "2026-02-01"))
        self.assertIn("v2.2.0", git(depot, "tag"))
        self.assertEqual(git(depot, "show", "--name-only", "--format=%s", "HEAD").split(),
                         ["Release", "v2.2.0", "CHANGELOG.md", "ROADMAP.md"])
        self.assertIn("## [2.2.0] - " + date.today().isoformat(), open(os.path.join(depot, "CHANGELOG.md")).read())
        with self.assertRaises(store.Invalid):
            store.livrer(p["id"], "2.2.0")  # déjà livrée

    def test_publier(self):
        store.save({"nom": "Piège </script><b>", "depot": TMP, "versions": [
            {"version": "8.8.8", "debut": "2026-01-01", "fin": "2099-01-01"},
            {"version": "7.7.7", "statut": "Terminé", "fin": "2025-01-01"}]})
        with self.assertRaises(store.Invalid):
            server.publier("2026", "x")
        html = open(server.publier("2026-09", "2027-01"), encoding="utf-8").read()
        self.assertIn('"8.8.8"', html)
        vs = gantt_versions(server.publier("2026-09", "2027-01"))
        self.assertNotIn("7.7.7", vs)        # livrée avant la période : pas sur le Gantt publié
        self.assertIn("7.7.7", {v["version"] for p in snapshot(server.publier("2026-09", "2027-01"))["parc"] for v in p["versions"]})
        p = store.get(store.slug("Piège </script><b>"))
        store.save({**p, "versions": p["versions"] + [{"version": "7.8.0", "statut": "Terminé", "debut": "2026-09-01", "fin": "2026-10-01"}]}, p["id"])
        self.assertIn("7.8.0", gantt_versions(server.publier("2026-09", "2027-01")))  # livrée dans la période
        store.save_config({"publication": {"terminees": False}})
        try:
            self.assertNotIn("7.8.0", gantt_versions(server.publier("2026-09", "2027-01")))
        finally:
            os.remove(store.CONFIG)
        self.assertIn('"periode": ["2026-09", "2027-01"]', html)
        self.assertIn("window.SNAPSHOT", html)
        self.assertNotIn('src="/app.js"', html)
        self.assertNotIn("</script><b>", html)  # le nom est échappé
        self.assertNotIn(TMP, html)             # pas de chemins locaux publiés

    def test_envoyer_publication(self):
        with self.assertRaises(store.Invalid):
            server.envoyer_publication("2026-09", "2027-01")  # pas configuré : message clair
        dest = os.path.join(TMP, "pi-index.html")  # scp sait copier en local : remplace la Raspberry
        store.write_atomic(store.CONFIG, '{"publier_vers": "%s", "publier_url": "http://pi/"}' % dest)  # ancien format lu
        try:
            self.assertEqual(server.envoyer_publication("2026-09", "2027-01"),
                             "Publié : http://pi/ — équipe production : http://pi/production.html")
            self.assertEqual(snapshot(dest)["vue"], "")  # page complète
            self.assertEqual(snapshot(os.path.join(TMP, "production.html"))["vue"], "prod")  # page de l'équipe production
            store.write_atomic(store.CONFIG, '{"publication": {"serveur": "-oProxyCommand=x"}}')
            with self.assertRaises(store.Invalid):
                server.envoyer_publication("2026-09", "2027-01")  # pas d'option déguisée en cible
        finally:
            os.remove(store.CONFIG)

    def test_config(self):
        try:
            c = store.config()  # valeurs par défaut livrées
            self.assertEqual((c["application"]["theme"], len(store.poles())), ("sombre", 6))
            self.assertFalse(c["application"]["qui_travaille"])  # bloc « qui travaille sur quoi » masqué par défaut
            c = store.save_config({"application": {"titre": "Ma roadmap", "theme": "clair"},
                                   "publication": {"serveur": "roadmap@10.0.0.2:/var/www/roadmap/index.html", "lien": "http://x/"},
                                   "ppt": {"auteur": "Moi"}})
            self.assertEqual((c["application"]["titre"], c["application"]["theme"], c["ppt"]["auteur"]), ("Ma roadmap", "clair", "Moi"))
            self.assertEqual(c["application"]["port"], 8765)  # non fourni : valeur par défaut gardée
            c = store.save_config({"equipe": [" A. Dupont ", "B. Durand", "a. dupont", ""]})
            self.assertEqual(c["equipe"], ["A. Dupont", "B. Durand"])  # annuaire nettoyé
            self.assertEqual(c["ppt"]["auteur"], "Moi")  # le reste de la configuration est gardé
            for bad in ({"application": {"theme": "rose"}}, {"application": {"port": 80}},
                        {"publication": {"serveur": "-oProxyCommand=x"}}, {"publication": {"lien": "javascript:x"}},
                        {"poles": []}, {"poles": [{"nom": "A", "court": "A", "couleur": "rouge"}]},
                        {"poles": [{"nom": "A", "court": "A", "couleur": "#000000"}] * 2},
                        {"equipe": [f"P{i}" for i in range(201)]}, {"equipe": "pas une liste ?"} and {"equipe": 3}):
                with self.assertRaises(store.Invalid, msg=bad):
                    store.save_config(bad)
            store.save({"nom": "Utilise SAV", "pole": "Bancs SAV"})
            with self.assertRaises(store.Invalid):  # pôle encore utilisé : on ne peut pas le retirer
                store.save_config({"poles": [{"nom": "Library", "court": "LIB", "couleur": "#00a4c8"}]})
        finally:
            if os.path.exists(store.CONFIG):
                os.remove(store.CONFIG)

    def test_depot_distant(self):
        src = tempfile.mkdtemp(dir=TMP)  # dépôt « distant » (lien file://) : main + develop + tag
        git(src, "init", "-q", "-b", "main")
        git(src, "config", "user.name", "Test")
        git(src, "config", "user.email", "test@example.com")
        open(os.path.join(src, "CHANGELOG.md"), "w").write("## [1.0.0] - 2026-01-10\n- première\n")
        git(src, "add", ".")
        git(src, "commit", "-qm", "v1")
        git(src, "tag", "v1.0.0")
        git(src, "checkout", "-qb", "develop")
        open(os.path.join(src, "Roadmap.md"), "w").write("## [1.1.0] - 2026-02-01 → 2026-03-01\n- en préparation\n")
        git(src, "add", ".")
        git(src, "commit", "-qm", "roadmap")
        url = "file://" + src
        self.assertEqual(store.branches(url), {"branches": ["develop", "main"], "defaut": "develop"})
        p = store.save({"nom": "Distant", "depot": url, "branche": "main"})
        p, msg = store.import_depot(p["id"])
        self.assertEqual([v["version"] for v in p["versions"]], ["v1.0.0"])  # main : pas de Roadmap.md
        self.assertIn("(main)", msg)
        p = store.save({**p, "branche": "develop"}, p["id"])
        p, _ = store.import_depot(p["id"])  # copie locale mise à jour, autre branche
        self.assertEqual([(v["version"], v["notes"]) for v in p["versions"]],
                         [("v1.1.0", "- en préparation"), ("v1.0.0", "- première")])
        self.assertEqual(p["versions"][1]["statut"], "Terminé")  # tag v1.0.0 lu dans la copie
        with self.assertRaises(store.Invalid):
            store.export_depot(p["id"], "ROADMAP.md")  # écriture : dossier local seulement
        with self.assertRaises(store.Invalid):
            store.save({**p, "branche": "inconnue"}, p["id"]) and store.import_depot(p["id"])
        for bad in ("--upload-pack=touch /tmp/x", "ext::sh -c touch% /tmp/x", "https://x/a b"):
            with self.assertRaises(store.Invalid, msg=bad):
                store.save({"nom": "Piège", "depot": bad})

    def test_identifiants_refuses_avant_git(self):  # aucune commande Git lancée : rien n'est écrit
        for args in (("git@host:x.git", "u", "p"), ("https://h/x.git", "u", "a\nurl=https://piege"),
                     ("https://h/x.git", "", "p"), ("--upload-pack=x", "u", "p")):
            with self.assertRaises(store.Invalid, msg=args):
                store.git_identifiants(*args)

    def test_equipe(self):
        p = store.save({"nom": "Equipe", "ressources": " A. Dupont ,B. Durand, a. dupont,, "})
        self.assertEqual(p["ressources"], ["A. Dupont", "B. Durand"])  # texte « A, B », doublons et vides retirés
        p = store.save({**p, "ressources": ["Équipe A"], "versions": [{"version": "9.9.9", "debut": "2026-10-01", "fin": "2099-01-01"}]}, p["id"])
        self.assertEqual(p["ressources"], ["Équipe A"])
        with self.assertRaises(store.Invalid):
            store.save({"nom": "Equipe", "ressources": ["x" * 61]}, p["id"])
        self.assertIn('"Équipe A"', open(server.publier("2026-09", "2027-01"), encoding="utf-8").read())  # visible sur la page publiée

    def test_equipe_par_version(self):
        depot = tempfile.mkdtemp(dir=TMP)
        open(os.path.join(depot, "ROADMAP.md"), "w").write("## [2.2.0] - 2026-12 → 2027-01\n- nouvelle\n")
        p = store.save({"nom": "EqV", "depot": depot, "ressources": ["Projet A"], "versions": [
            {"version": "v2.1", "debut": "2026-10-01", "fin": "2026-11-30", "ressources": "Alice, Bob"},
            {"version": "2.0.0", "statut": "Terminé", "fin": "2026-09-01"}]})
        self.assertEqual([v["ressources"] for v in p["versions"]], [["Alice", "Bob"], []])  # vide = équipe du projet
        p, _ = store.import_depot(p["id"])  # import : 2.2.0 ajoutée, l'équipe de 2.1 est gardée
        self.assertEqual({v["version"]: v["ressources"] for v in p["versions"]},
                         {"v2.2.0": [], "v2.1": ["Alice", "Bob"], "2.0.0": []})
        self.assertNotIn("Alice", open(store.release_path(p["id"]), encoding="utf-8").read())  # pas dans le ROADMAP.md
        self.assertNotIn("equipes", p)

    def test_decalage_ou_erreur_de_saisie(self):
        p = store.save({"nom": "Saisie", "versions": [{"version": "1.0.0", "debut": "2026-01-01", "fin": "2026-02-01"}]})
        v0 = p["versions"][0]
        v = store.save({**p, "versions": [{**v0, "fin": "2026-02-10", "decalage": False}]}, p["id"])["versions"][0]
        self.assertEqual((v["fin"], v["prevu"]), ("2026-02-10", ""))  # erreur de saisie corrigée : pas de dérive
        v = store.save({**p, "versions": [{**v, "fin": "2026-03-01", "decalage": True}]}, p["id"])["versions"][0]
        self.assertEqual(v["prevu"], "2026-02-10")  # vrai décalage : dérive
        self.assertNotIn("decalage", v)  # le choix n'est pas stocké
        v = store.save({**p, "versions": [{**v, "prevu": "", "prevu_efface": True}]}, p["id"])["versions"][0]
        self.assertEqual(v["prevu"], "")  # date prévue saisie à tort : effacée
        v = store.save({**p, "versions": [{**v, "fin": "2026-04-01"}]}, p["id"])["versions"][0]
        self.assertEqual(v["prevu"], "2026-03-01")  # sans réponse (import, livraison) : décalage

    def test_import_roadmap_et_changelog(self):
        depot = tempfile.mkdtemp(dir=TMP)
        open(os.path.join(depot, "ROADMAP.md"), "w").write(
            "## [2.2.0] - 2026-11-01 → 2099-12-15\n\n## [2.1.0] - 2026-09-01 → 2026-10-01\n- Mesure voie 3\n")
        open(os.path.join(depot, "CHANGELOG.md"), "w").write(
            "## [Unreleased]\n### Added\n- Début cyclage\n\n## [2.1.0] - 2026-10-08\n### Added\n- Mesure voie 3\n")
        p = store.save({"nom": "RoadmapChangelog", "depot": depot,
                        "versions": [{"version": "Unreleased", "statut": "En cours"}]})  # doublon d'un ancien import
        p, msg = store.import_depot(p["id"])
        v = {x["version"]: x for x in p["versions"]}
        self.assertEqual(sorted(v), ["v2.1.0", "v2.2.0"])  # [Unreleased] n'est pas une version à part
        self.assertEqual(v["v2.2.0"]["notes"], "### Added\n- Début cyclage")  # son contenu va à la prochaine version
        self.assertEqual((v["v2.1.0"]["statut"], v["v2.1.0"]["fin"], v["v2.1.0"]["prevu"]),
                         ("Terminé", "2026-10-08", "2026-10-01"))  # livrée d'après le CHANGELOG, même sans tag
        self.assertIn("rattaché à v2.2.0", msg)
        p, msg = store.import_depot(p["id"])
        self.assertEqual((len(p["versions"]), " 0 version(s) ajoutée(s)" in msg), (2, True))  # réimport : rien ne bouge
        os.remove(os.path.join(depot, "ROADMAP.md"))
        q = store.save({"nom": "SansRoadmap", "depot": depot})
        q, _ = store.import_depot(q["id"])
        self.assertIn("Unreleased", [x["version"] for x in q["versions"]])  # pas de version prévue : gardé tel quel

    def test_mise_en_production(self):
        depot = tempfile.mkdtemp(dir=TMP)
        open(os.path.join(depot, "CHANGELOG.md"), "w").write("## [1.1.0] - 2026-10-08\n- b\n\n## [1.0.0] - 2026-01-10\n- a\n")
        p = store.save({"nom": "Prod", "depot": depot})
        p, _ = store.import_depot(p["id"])
        vs = [{**v, "prod": "2026-02-01" if v["version"] == "v1.0.0" else ""} for v in p["versions"]]
        p = store.save({**p, "versions": vs}, p["id"])
        self.assertEqual({v["version"]: v["prod"] for v in p["versions"]}, {"v1.1.0": "", "v1.0.0": "2026-02-01"})
        p, _ = store.import_depot(p["id"])  # réimport : la date de mise en prod est gardée
        self.assertEqual([v["prod"] for v in p["versions"] if v["version"] == "v1.0.0"], ["2026-02-01"])
        self.assertNotIn("2026-02-01", open(store.release_path(p["id"]), encoding="utf-8").read())  # pas dans le ROADMAP.md
        with self.assertRaises(store.Invalid):  # en production = déjà livrée
            store.save({"nom": "Prod2", "versions": [{"version": "3.0.0", "debut": "2026-01-01", "fin": "2099-01-01", "prod": "2026-02-01"}]})
        html = open(server.publier("2026-09", "2027-01"), encoding="utf-8").read()
        self.assertIn('"prod": "2026-02-01"', html)  # onglet En production : même si la version est hors période

    def test_etat_et_selection_production(self):
        p = store.save({"nom": "Banc état", "etat": "panne", "etat_note": "  carte voie 3   HS "})
        self.assertEqual((p["etat"], p["etat_note"], p["etat_date"], p["prod_publie"]),
                         ("panne", "carte voie 3 HS", date.today().isoformat(), True))
        store.write_atomic(store.PROJETS, open(store.PROJETS, encoding="utf-8").read().replace(
            date.today().isoformat(), "2026-01-01"))  # simule un état posé plus tôt
        p = store.save({**store.get(p["id"]), "etat_note": "pièce commandée"}, p["id"])
        self.assertEqual(p["etat_date"], "2026-01-01")  # même état : la date ne bouge pas
        p = store.save({**p, "etat": "ok", "etat_date": ""}, p["id"])
        self.assertEqual(p["etat_date"], date.today().isoformat())  # changement d'état sans date : date du jour
        p = store.save({**p, "etat": "ok", "etat_date": "2026-10-02"}, p["id"])
        self.assertEqual(p["etat_date"], "2026-10-02")  # « opérationnel depuis le » choisi à l'écran
        self.assertEqual(store.save({**p, "etat": "maj", "etat_date": ""}, p["id"])["etat"], "maj")  # en mise à jour
        p = store.save({**p, "etat": "ok", "etat_date": "2026-10-02"}, p["id"])
        for bad in ({"etat": "cassé"}, {"etat": "ok", "etat_date": "02/13/2026"}, {"etat": "", "etat_date": "2026-10-02"}):
            with self.assertRaises(store.Invalid, msg=bad):
                store.save({**p, **bad}, p["id"])
        store.save({"nom": "Banc masqué", "prod_publie": False})
        parc = {x["nom"]: x for x in snapshot(server.publier("2026-09", "2027-01"))["parc"]}
        self.assertNotIn("Banc masqué", parc)  # décoché : absent de « En production » publié
        self.assertEqual(parc["Banc état"]["etat"], "ok")

    def test_postes(self):
        p = store.save({"nom": "Banc 2 postes", "postes": ["Poste A", {"nom": " Poste  B ", "etat": "panne", "etat_note": "alim HS"}]})
        self.assertEqual([(x["nom"], x["etat"], x["etat_date"]) for x in p["postes"]],
                         [("Poste A", "", ""), ("Poste B", "panne", date.today().isoformat())])
        p = store.save({**p, "postes": [{"nom": "poste b", "etat": "panne"}]}, p["id"])
        self.assertEqual(p["postes"][0]["etat_note"], "")  # retrouvé par nom (casse ignorée), même état : date gardée
        self.assertEqual(p["postes"][0]["etat_date"], date.today().isoformat())
        self.assertEqual(store.save({"nom": "Banc seul"})["postes"], [])  # sans poste : comme avant
        for bad in (["A", "a"], [{"nom": "A", "etat": "cassé"}], "A, B", ["x" * 41]):
            with self.assertRaises(store.Invalid, msg=bad):
                store.save({**p, "postes": bad}, p["id"])
        parc = {x["nom"]: x for x in snapshot(server.publier("2026-09", "2027-01"))["parc"]}
        self.assertEqual(parc["Banc 2 postes"]["postes"][0]["etat"], "panne")  # publié

class TestFiltres(unittest.TestCase):
    def test_garde(self):
        p = {"pole": "Library"}
        bloque, cours = {"statut": "Bloqué"}, {"statut": "En cours"}
        self.assertTrue(server.garde(p, cours))
        self.assertFalse(server.garde(p, cours, pole="Validation"))
        self.assertTrue(server.garde(p, bloque, "Library", "alerte"))
        self.assertFalse(server.garde(p, cours, statut="alerte"))
        self.assertTrue(server.garde(p, cours, statut="En cours"))

if __name__ == "__main__":
    unittest.main()
