"""Test del parser su pagine reali di comingsoon.it salvate in tests/fixtures.

Eseguire con:  python -m unittest discover -s tests -v
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

import scrape  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
TODAY = dt.date(2026, 10, 13)


def fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


class ParseCinemaPage(unittest.TestCase):
    def test_film_metadata(self):
        films, _ = scrape.parse_cinema_page(fixture("odeon_cinema.html"))
        self.assertEqual([f["title"] for f in films], ["L'Estranea", "Coyote vs. Acme"])
        f = films[0]
        self.assertEqual(f["idf"], "22259")
        self.assertEqual(f["cs_id"], 68142)
        self.assertEqual(f["duration"], 115)
        self.assertEqual(f["release_date"], "2026-10-08")
        self.assertEqual(f["genres"], ["Drammatico", "Thriller"])
        self.assertEqual(f["rating"], 3.9)
        self.assertEqual(len(f["cast"]), 4)
        self.assertEqual(f["original_title"], "")  # uguale al titolo italiano
        self.assertTrue(f["poster"].endswith("/68142.jpg"))
        self.assertEqual(f["ticket_path"], "/cinema/bologna/odeon/174/ticket/?idf=22259")

    def test_sala_times_prices_and_vo(self):
        films, _ = scrape.parse_cinema_page(fixture("odeon_cinema.html"))
        sala = films[0]["salas"][0]
        self.assertEqual(sala["sala"], "Sala A")
        self.assertEqual(sala["seats"], 322)
        self.assertFalse(sala["vo"])
        self.assertEqual(sala["times"], [
            {"time": "16:15", "price": 8.0},
            {"time": "18:45", "price": 10.0},
            {"time": "21:15", "price": 10.0},
        ])
        coyote = films[1]["salas"][0]
        self.assertTrue(coyote["vo"])
        self.assertEqual(coyote["tags"], ["V.O."])

    def test_sala_without_seats(self):
        films, _ = scrape.parse_cinema_page(fixture("lumiere_cinema.html"))
        sala = films[0]["salas"][0]
        self.assertEqual(sala["sala"], "Sala Off. / Mastroianni")
        self.assertIsNone(sala["seats"])
        self.assertTrue(sala["vo"])
        self.assertIsNone(films[1]["trailer_url"])
        self.assertIsNone(films[1]["ticket_path"])

    def test_original_title(self):
        films, _ = scrape.parse_cinema_page(fixture("space_cinema.html"))
        self.assertEqual(films[0]["original_title"], "Other Mommy")
        self.assertEqual(len(films[0]["salas"]), 5)

    def test_empty_cinema(self):
        films, sidebar = scrape.parse_cinema_page(fixture("antoniano_cinema.html"))
        self.assertEqual(films, [])
        self.assertEqual(sidebar, [])

    def test_city_sidebar_only_bologna(self):
        _, sidebar = scrape.parse_cinema_page(fixture("odeon_cinema.html"))
        self.assertEqual([c["id"] for c in sidebar], [147, 5075, 9999, 174, 171])
        self.assertNotIn(2512, [c["id"] for c in sidebar])  # Casalecchio esclusa


class ParseTicketPage(unittest.TestCase):
    def test_days_and_buttons(self):
        shows = scrape.parse_ticket_page(fixture("odeon_ticket_22259.html"), TODAY)
        self.assertEqual(len(shows), 7)
        self.assertEqual(shows[0], {
            "date": "2026-10-13", "time": "16:15", "sala": "Odeon A",
            "url": "http://odeon.ccb.18tickets.it/film/l-estranea_2026-f394b759-becd-4d99-8167-127384813f1a/840869#sala",
        })
        self.assertEqual(shows[-1]["date"], "2026-10-18")
        self.assertEqual(shows[-1]["time"], "18:15")

    def test_missing_calendar(self):
        self.assertIsNone(scrape.parse_ticket_page(fixture("antoniano_cinema.html"), TODAY))


class InferYear(unittest.TestCase):
    def test_same_year(self):
        self.assertEqual(scrape.infer_year(TODAY, 10, 18), dt.date(2026, 10, 18))

    def test_new_year_rollover(self):
        self.assertEqual(scrape.infer_year(dt.date(2026, 12, 30), 1, 2), dt.date(2027, 1, 2))

    def test_recent_past_stays_this_year(self):
        self.assertEqual(scrape.infer_year(TODAY, 10, 12), dt.date(2026, 10, 12))


class BuildShows(unittest.TestCase):
    def test_week_from_ticket_page_with_prices_today(self):
        films, _ = scrape.parse_cinema_page(fixture("odeon_cinema.html"))
        ticket = scrape.parse_ticket_page(fixture("odeon_ticket_22259.html"), TODAY)
        shows = scrape.build_shows(films[0], ticket, TODAY)
        self.assertEqual(len(shows), 7)
        today = [s for s in shows if s["date"] == "2026-10-13"]
        self.assertEqual([s["price"] for s in today], [8.0, 10.0, 10.0])
        self.assertTrue(all(s["url"] for s in shows))
        self.assertFalse(any(s["vo"] for s in shows))

    def test_vo_propagates_to_other_days(self):
        films, _ = scrape.parse_cinema_page(fixture("lumiere_cinema.html"))
        ticket = scrape.parse_ticket_page(fixture("lumiere_ticket_22430.html"), TODAY)
        shows = scrape.build_shows(films[0], ticket, TODAY)
        self.assertEqual(len(shows), 6)
        self.assertTrue(all(s["vo"] for s in shows))

    def test_union_keeps_today_shows_missing_from_ticket_page(self):
        films, _ = scrape.parse_cinema_page(fixture("space_cinema.html"))
        ticket = scrape.parse_ticket_page(fixture("space_ticket_21315.html"), TODAY)
        shows = scrape.build_shows(films[0], ticket, TODAY)
        today_times = [s["time"] for s in shows if s["date"] == "2026-10-13"]
        # 18:15 in Sala 1 c'e' solo sulla pagina del cinema
        self.assertEqual(today_times, ["16:45", "18:15", "18:40", "20:30", "21:15", "22:00"])
        extra = next(s for s in shows if s["time"] == "18:15")
        self.assertIsNone(extra["url"])
        self.assertEqual(extra["sala"], "Sala 1")
        self.assertEqual(len([s for s in shows if s["date"] == "2026-10-14"]), 6)

    def test_mixed_vo_same_sala_uses_time_of_day(self):
        film = {"salas": [
            {"sala": "Sala 1", "seats": None, "tags": [], "vo": False, "times": [{"time": "16:30", "price": 7.0}]},
            {"sala": "Sala 1", "seats": None, "tags": ["V.O."], "vo": True, "times": [{"time": "20:45", "price": 7.0}]},
        ]}
        ticket = [
            {"date": "2026-10-14", "time": "16:30", "sala": "Roma", "url": "u1"},
            {"date": "2026-10-14", "time": "20:45", "sala": "Roma", "url": "u2"},
        ]
        shows = scrape.build_shows(film, ticket, TODAY)
        tomorrow = {s["time"]: s["vo"] for s in shows if s["date"] == "2026-10-14"}
        self.assertEqual(tomorrow, {"16:30": False, "20:45": True})

    def test_fallback_without_ticket_page(self):
        films, _ = scrape.parse_cinema_page(fixture("lumiere_cinema.html"))
        shows = scrape.build_shows(films[1], None, TODAY)
        self.assertEqual([s["time"] for s in shows], ["18:00", "20:00", "22:15"])
        self.assertTrue(all(s["date"] == "2026-10-13" and s["vo"] for s in shows))

    def test_drops_past_days(self):
        # Pagina date letta il 13, ma "oggi" e' il 15: i giorni 13 e 14 vanno scartati.
        # (salas vuote: la pagina cinema del 15 non avrebbe orari del 13)
        films, _ = scrape.parse_cinema_page(fixture("odeon_cinema.html"))
        ticket = scrape.parse_ticket_page(fixture("odeon_ticket_22259.html"), TODAY)
        film = {**films[0], "salas": []}
        shows = scrape.build_shows(film, ticket, dt.date(2026, 10, 15))
        self.assertEqual([s["date"] for s in shows], ["2026-10-18"])


class ScrapeEndToEnd(unittest.TestCase):
    CINEMAS = [
        {"id": 147, "slug": "antoniano", "name": "Antoniano", "short": "Antoniano", "address": "Via Guinizelli, 3"},
        {"id": 5075, "slug": "lumiere", "name": "Lumière", "short": "Lumière", "address": "Via Azzo Gardino, 65"},
        {"id": 174, "slug": "odeon", "name": "Odeon", "short": "Odeon", "address": "Via Mascarella, 3"},
        {"id": 171, "slug": "the-space-cinema-bologna", "name": "The Space", "short": "The Space", "address": "Viale Europa"},
        {"id": 176, "slug": "orione", "name": "Orione", "short": "Orione", "address": "Via Cimabue, 14"},
    ]
    PAGES = {
        "/cinema/bologna/antoniano/147/": "antoniano_cinema.html",
        "/cinema/bologna/lumiere/5075/": "lumiere_cinema.html",
        "/cinema/bologna/lumiere/5075/ticket/?idf=22430": "lumiere_ticket_22430.html",
        "/cinema/bologna/odeon/174/": "odeon_cinema.html",
        "/cinema/bologna/odeon/174/ticket/?idf=22259": "odeon_ticket_22259.html",
        "/cinema/bologna/the-space-cinema-bologna/171/": "space_cinema.html",
        "/cinema/bologna/the-space-cinema-bologna/171/ticket/?idf=21315": "space_ticket_21315.html",
    }

    def fake_fetch(self, path):
        if path not in self.PAGES:
            raise ConnectionError(path)
        return fixture(self.PAGES[path])

    def test_full_run(self):
        result = scrape.scrape(self.CINEMAS, self.fake_fetch, TODAY)
        data, stats, warnings = result["showtimes"], result["stats"], result["warnings"]

        self.assertEqual(stats["cinemas_ok"], 4)
        self.assertEqual(stats["cinemas_failed"], 1)  # Orione non c'e' nei fixture
        self.assertEqual(stats["cinemas_with_shows"], 3)
        # L'Estranea e' sia all'Odeon sia a The Space: un solo film, due cinema
        idfs = [f["idf"] for f in data["films"]]
        self.assertEqual(len(idfs), len(set(idfs)))
        self.assertIn("22259", idfs)
        estranea_cinemas = {s["cinema"] for s in data["shows"] if s["film"] == "22259"}
        self.assertEqual(estranea_cinemas, {174, 171})

        # Coyote all'Odeon: pagina date non disponibile -> warning + orari di oggi
        self.assertTrue(any("Coyote" in w for w in warnings))
        coyote = [s for s in data["shows"] if s["film"] == "22160"]
        self.assertEqual([(s["date"], s["time"], s["vo"]) for s in coyote], [("2026-10-13", "17:20", True)])

        # Sidebar: segnala il cinema nuovo
        self.assertTrue(any("Nuovo Cinema Test" in w for w in warnings))

        # Campi pronti per il frontend
        cinema = next(c for c in data["cinemas"] if c["id"] == 147)
        self.assertFalse(cinema["active"])
        self.assertTrue(cinema["url"].endswith("/antoniano/147/"))
        self.assertNotIn("salas", data["films"][0])
        self.assertNotIn("ticket_path", data["films"][0])
        dates = [s["date"] for s in data["shows"]]
        self.assertEqual(dates, sorted(dates))


if __name__ == "__main__":
    unittest.main()
