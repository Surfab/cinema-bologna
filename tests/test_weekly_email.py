"""Test della mail del giovedi'. Eseguire con: python -m unittest discover -s tests -v"""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(ROOT / "tests"))

import scrape  # noqa: E402
import weekly_email  # noqa: E402
import test_scrape  # noqa: E402

TODAY = test_scrape.TODAY


def fixture_data():
    case = test_scrape.ScrapeEndToEnd()
    return scrape.scrape(case.CINEMAS, case.fake_fetch, TODAY)["showtimes"]


class WeeklyEmail(unittest.TestCase):
    def setUp(self):
        self.data = fixture_data()

    def test_new_and_old_are_separated(self):
        w = weekly_email.build(self.data, None, TODAY)
        new = [r["film"]["title"] for r in w["new"]]
        old = [r["film"]["title"] for r in w["old"]]
        self.assertEqual(set(new), {"L'Estranea", "Mammina"})            # usciti l'8 ottobre
        self.assertEqual(set(old), {"Digger", "The Invite - Il Piacere è tutto nostro", "Coyote vs. Acme"})
        self.assertFalse(set(new) & set(old))

    def test_last_thursday_release_is_old_next_week(self):
        w = weekly_email.build(self.data, None, dt.date(2026, 10, 15))
        self.assertEqual([r["film"]["title"] for r in w["new"]], [])  # l'8 ottobre e' la settimana prima
        self.assertIn("L'Estranea", [r["film"]["title"] for r in w["old"]])

    def test_places_and_days(self):
        w = weekly_email.build(self.data, None, TODAY)
        estranea = next(r for r in w["new"] if r["film"]["title"] == "L'Estranea")
        odeon = next(p for p in estranea["places"] if p["cinema"] == "Odeon")
        self.assertEqual([d["label"] for d in odeon["days"]], ["mar 13", "mer 14", "dom 18"])
        self.assertEqual(odeon["days"][0]["times"], [("16:15", False), ("18:45", False), ("21:15", False)])

    def test_rendering(self):
        w = weekly_email.build(self.data, {"updated_at": "2026-10-13T07:17+02:00"}, TODAY)
        text = weekly_email.render_text(w)
        html = weekly_email.render_html(w)
        self.assertLess(text.index("Nuovi questa settimana"), text.index("Ancora in sala"))
        self.assertIn("Al cinema dall'8 ottobre", text)
        self.assertIn("17:20 V.O.", text)                                   # Coyote all'Odeon
        self.assertIn("L&#x27;Estranea", html)
        self.assertNotIn("None", html + text)
        self.assertEqual(weekly_email.subject(w), "🎬 Cinema a Bologna dal 13 ottobre: 2 film nuovi")

    def test_no_new_films_subject(self):
        w = weekly_email.build(self.data, None, dt.date(2026, 10, 15))
        self.assertIn("nessuna uscita nuova", weekly_email.subject(w))

    def test_italian_dates(self):
        self.assertEqual(weekly_email.dal(dt.date(2026, 10, 8)), "dall'8 ottobre")
        self.assertEqual(weekly_email.dal(dt.date(2026, 10, 1)), "dal 1° ottobre")
        self.assertEqual(weekly_email.il(dt.date(2026, 10, 11)), "l'11 ottobre")

    def test_cli_writes_files(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "showtimes.json"
            data_path.write_text(json.dumps(self.data), encoding="utf-8")
            rc = weekly_email.main(["--data", str(data_path), "--meta", str(Path(tmp) / "nope.json"),
                                    "--out", str(Path(tmp) / "out"), "--today", "2026-10-13"])
            self.assertEqual(rc, 0)
            for name in ("subject.txt", "email.html", "email.txt"):
                self.assertTrue((Path(tmp) / "out" / name).read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
