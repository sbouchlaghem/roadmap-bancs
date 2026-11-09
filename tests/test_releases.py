import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import releases as R  # noqa: E402

PYJEP = """# Changelog

**Author:** X
---
## [2.3.0]

### Added
 - service A
   - sub

## Fixed
 - bug

## [2.2.0] — 2026-08-28

### Added
  - B
"""


class TestReleases(unittest.TestCase):
    def test_changelog_existant(self):
        v = R.parse(PYJEP)
        self.assertEqual([x["version"] for x in v], ["2.3.0", "2.2.0"])
        self.assertIn("## Fixed", v[0]["notes"])  # « ## Fixed » n'est pas une version
        self.assertEqual((v[1]["statut"], v[1]["fin"]), ("Terminé", "2026-08-28"))
        self.assertEqual(v[0]["statut"], "")

    def test_formats(self):
        v = R.parse("## 1.0.2\n- a\n\n## [Unreleased]\n- b\n## [3.0.0] - Planifié - 01/2027 → 2027-02-15\n")
        self.assertEqual(v[0]["version"], "1.0.2")
        self.assertEqual((v[1]["version"], v[1]["statut"]), ("Unreleased", "En cours"))
        self.assertEqual((v[2]["statut"], v[2]["debut"], v[2]["fin"]), ("Planifié", "2027-01", "2027-02-15"))

    def test_titres_sans_diese(self):
        v = R.parse("# Historique\n\n[2.0.2] - 2026-10-05\n\n- a [1.0] b\n[1.0.0] - 2026-04-2\n[1]: http://x\n")
        self.assertEqual([x["version"] for x in v], ["2.0.2", "1.0.0"])
        self.assertEqual((v[0]["statut"], v[0]["fin"], v[0]["notes"]), ("Terminé", "2026-10-05", "- a [1.0] b"))
        self.assertEqual(v[1]["fin"], "2026-04-02")

    def test_dates(self):
        self.assertEqual(R.norm_date("15/06/2026"), "2026-06-15")
        self.assertEqual(R.norm_date("1/2027"), "2027-01")
        self.assertEqual(R.norm_date("2026-13-40"), "")
        self.assertEqual(R.norm_date("31/02/2026"), "")

    def test_aller_retour(self):
        e = {"prevu": "", "motif": ""}
        vs = [{**e, "version": "v2.1.0", "statut": "En cours", "debut": "2026-09-21", "fin": "2026-11-13",
               "notes": "### Added\n- x\n  - y", "prevu": "2026-10-30"},
              {**e, "version": "v2.0.1", "statut": "Bloqué", "debut": "2026-09", "fin": "2026-12",
               "notes": "", "motif": "attente cartes en cours"},
              {**e, "version": "?", "statut": "", "debut": "", "fin": "", "notes": ""},
              {**e, "version": "v2.0.0", "statut": "Terminé", "debut": "", "fin": "2026-09-24", "notes": "Auteur : VM"}]
        d = date(2026, 11, 5)
        txt = R.fmt("P", vs, d)
        self.assertIn("## [v2.1.0] - 2026-09-21 → 2026-11-13 (prévu 2026-10-30)", txt)  # statut déductible : pas écrit
        self.assertIn("## [v2.0.1] - Bloqué (attente cartes en cours) - 2026-09 → 2026-12", txt)
        self.assertEqual(R.parse(txt, d), vs)

    def test_versions_4_nombres(self):
        self.assertNotEqual(R.vkey("1.2.3.4"), R.vkey("1.2.3.5"))
        self.assertEqual(R.vkey("v2.0"), R.vkey("2.0.0"))

    def test_statut_deduit(self):
        d = date(2026, 11, 5)
        v = R.parse("## [3] - 2027-01 → 2027-02\n## [2] - 2026-11 → 2026-11\n## [1] - 2026-09-01 → 2026-10-31\n"
                    "## [0] - Bloqué - 2026-09-01 → 2026-10-31\n## [9] - Planifié - 2026-09-01 → 2026-12-31\n", d)
        self.assertEqual([x["statut"] for x in v], ["Planifié", "En cours", "En retard", "Bloqué", "En cours"])

    def test_merge_et_tri(self):
        a = [{"version": "v2.0", "statut": "Terminé", "debut": "", "fin": "", "notes": ""}]
        b = [{"version": "2.0.0", "statut": "", "debut": "", "fin": "2026-01-01", "notes": "n"},
             {"version": "2.1.0", "statut": "", "debut": "", "fin": "", "notes": ""}]
        m = R.merge(a, b)
        self.assertEqual([x["version"] for x in m], ["2.1.0", "v2.0"])
        self.assertEqual((m[1]["statut"], m[1]["fin"], m[1]["notes"]), ("Terminé", "2026-01-01", "n"))

    def test_changelog_export(self):
        vs = [{"version": "v1.1.0", "statut": "Planifié", "debut": "", "fin": "", "notes": "- futur"},
              {"version": "v1.0.0", "statut": "Terminé", "debut": "", "fin": "2026-06-15", "notes": "- a"}]
        out = R.to_changelog("P", vs)
        self.assertIn("## [1.0.0] - 2026-06-15", out)
        self.assertNotIn("futur", out)  # les versions seulement planifiées ne vont pas dans le changelog


if __name__ == "__main__":
    unittest.main()
