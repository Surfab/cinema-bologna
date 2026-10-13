#!/usr/bin/env python3
"""Raccoglie film, sale e orari dei cinema di Bologna da comingsoon.it.

Per ogni cinema legge:
  1. la pagina del cinema  -> film in programmazione, sale, orari e prezzi di oggi
  2. la pagina "tutte le date" di ogni film -> orari dei giorni successivi + link d'acquisto

Scrive due file:
  data/showtimes.json  -> cinema, film e spettacoli (cambia solo se cambia la programmazione)
  data/meta.json       -> quando e com'e' andato l'ultimo aggiornamento

Uso:
  python scraper/scrape.py --out data
  python scraper/scrape.py --out /tmp/test --only odeon   # un solo cinema, per debug
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://www.comingsoon.it"
ROME = ZoneInfo("Europe/Rome")
USER_AGENT = (
    "Mozilla/5.0 (compatible; cinema-bologna/1.0; "
    "+https://github.com/Surfab/cinema-bologna)"
)
MONTHS = {
    "GEN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAG": 5, "GIU": 6,
    "LUG": 7, "AGO": 8, "SET": 9, "OTT": 10, "NOV": 11, "DIC": 12,
}
VO_PATTERN = re.compile(r"v\.?\s?o\.?|orig|sottotit|subtitle", re.I)
TIME_PRICE = re.compile(r"(\d{1,2})[.:](\d{2})(?:\s*/\s*(\d+(?:,\d{1,2})?)\s*€)?")

log = logging.getLogger("cinema-bologna")


# --------------------------------------------------------------------------- utils

def clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def to_hhmm(hours: str, minutes: str) -> str:
    return f"{int(hours):02d}:{int(minutes):02d}"


def parse_price(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def parse_date_it(raw: str) -> Optional[str]:
    """'08/10/2026' -> '2026-10-08'."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw or "")
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def infer_year(today: dt.date, month: int, day: int) -> dt.date:
    """Le pagine 'tutte le date' non riportano l'anno: lo deduciamo.

    Una data piu' vecchia di 60 giorni e' dell'anno prossimo (es. 2 GEN visto a dicembre),
    una data oltre 300 giorni nel futuro e' dell'anno scorso.
    """
    candidate = dt.date(today.year, month, day)
    if (today - candidate).days > 60:
        candidate = dt.date(today.year + 1, month, day)
    elif (candidate - today).days > 300:
        candidate = dt.date(today.year - 1, month, day)
    return candidate


def sala_key(name: str) -> str:
    """Chiave per confrontare la stessa sala scritta in modi diversi.

    'Odeon A' ~ 'Sala A', 'Sala Off. / Mastroianni' ~ 'Mastroianni', 'Sala 6' ~ 'Sala 6'.
    """
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    return tokens[-1] if tokens else ""


def is_vo(tags: list[str]) -> bool:
    return any(VO_PATTERN.search(t) for t in tags)


# --------------------------------------------------------------------------- parser

def parse_cinema_page(html: str) -> tuple[list[dict], list[dict]]:
    """Ritorna (film_in_programmazione, cinema_di_bologna_elencati_nella_sidebar)."""
    soup = BeautifulSoup(html, "html.parser")
    films: list[dict] = []

    for block in soup.select("div.header-scheda"):
        title_a = block.select_one("a.tit_olo")
        if not title_a:
            continue
        idf_match = re.search(r"idf=(\d+)", title_a.get("href", ""))
        if not idf_match:
            continue

        meta: dict[str, str] = {}
        for p in block.select(".meta .p"):
            label, value = p.find("b"), p.find("span")
            if label and value:
                meta[clean(label.get_text()).rstrip(":").lower()] = clean(value.get_text())

        scheda = block.select_one('a[href*="/scheda/"]')
        trailer = block.select_one('a[href*="/video/"]')
        ticket = block.select_one('a[href*="/ticket/"]')
        poster = block.select_one(".immagine img")
        rating_el = block.select_one("[data-rating]")
        original = block.select_one(".sottotitolo")

        cs_id = None
        if scheda:
            m = re.search(r"/film/[^/]+/(\d+)/scheda", scheda["href"])
            cs_id = int(m.group(1)) if m else None

        duration = None
        m = re.search(r"(\d+)", meta.get("durata", ""))
        if m:
            duration = int(m.group(1))

        rating = None
        if rating_el:
            try:
                rating = round(float(rating_el["data-rating"].replace(",", ".")), 1)
            except ValueError:
                rating = None

        salas = []
        for sb in block.select("div.sala"):
            spans = sb.select(".row-between > span")
            if len(spans) < 2:
                continue
            parts = [clean(x) for x in clean(spans[0].get_text()).split("|")]
            seats, tags = None, []
            for part in parts[1:]:
                pm = re.match(r"Posti\s+(\d+)", part, re.I)
                if pm:
                    seats = int(pm.group(1))
                elif part:
                    tags.append(part)
            times = [
                {"time": to_hhmm(h, mi), "price": parse_price(pr)}
                for h, mi, pr in TIME_PRICE.findall(clean(spans[1].get_text()))
            ]
            salas.append({
                "sala": parts[0],
                "seats": seats,
                "tags": tags,
                "vo": is_vo(tags),
                "times": times,
            })

        original_title = clean(original.get_text()).strip("() ").strip() if original else ""
        title = clean(title_a.get_text())
        films.append({
            "idf": idf_match.group(1),
            "cs_id": cs_id,
            "title": title,
            "original_title": original_title if original_title.lower() != title.lower() else "",
            "genres": [g.strip() for g in meta.get("genere", "").split(",") if g.strip()],
            "duration": duration,
            "release_date": parse_date_it(meta.get("uscita al cinema", "")),
            "cast": [c.strip() for c in meta.get("cast", "").split(",") if c.strip()][:4],
            "rating": rating,
            "poster": poster.get("src") if poster else None,
            "scheda_url": BASE + scheda["href"] if scheda else None,
            "trailer_url": BASE + trailer["href"] if trailer else None,
            "ticket_path": ticket["href"] if ticket else None,
            "salas": salas,
        })

    return films, parse_city_sidebar(soup)


def parse_city_sidebar(soup: BeautifulSoup) -> list[dict]:
    """La sidebar di ogni pagina cinema elenca i cinema della citta': ci serve per
    accorgerci se ne apre uno nuovo o ne chiude uno."""
    for head in soup.select("div.h3"):
        link = head.find("a", href="/cinema/bologna/")
        if not link:
            continue
        ul = head.find_next_sibling("ul")
        found = []
        for a in ul.select("a.cs-box") if ul else []:
            m = re.match(r"/cinema/bologna/([^/]+)/(\d+)/", a.get("href", ""))
            if m:
                title = a.select_one(".titolo")
                found.append({
                    "slug": m.group(1),
                    "id": int(m.group(2)),
                    "name": clean(title.get_text() if title else a.get("title")),
                })
        return found
    return []


def parse_ticket_page(html: str, today: dt.date) -> Optional[list[dict]]:
    """Pagina 'Acquista biglietto e vedi tutte le date'. None se non ha il calendario."""
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one("#salaFilmList")
    if not box:
        return None
    shows = []
    for media in box.select("div.media"):
        day_el, month_el = media.select_one(".day"), media.select_one(".month")
        if not day_el or not month_el:
            continue
        month = MONTHS.get(clean(month_el.get_text()).upper()[:3])
        if not month:
            continue
        try:
            date = infer_year(today, month, int(clean(day_el.get_text())))
        except ValueError:
            continue
        for btn in media.select("button.btn-fab"):
            m = re.search(r"(\d{1,2})[.:](\d{2})", btn.get_text())
            if not m:
                continue
            shows.append({
                "date": date.isoformat(),
                "time": to_hhmm(*m.groups()),
                "sala": clean(btn.get("title")),
                "url": btn.get("data-url") or None,
            })
    return shows


# --------------------------------------------------------------------------- merge

def build_shows(film: dict, ticket_shows: Optional[list[dict]], today: dt.date) -> list[dict]:
    """Unisce gli orari di oggi (pagina cinema) con quelli della settimana (pagina date)."""
    today_iso = today.isoformat()
    salas = film["salas"]

    by_today_time: dict[str, dict] = {}
    for s in salas:
        for t in s["times"]:
            by_today_time.setdefault(t["time"], {**s, "price": t["price"]})

    vo_values = {s["vo"] for s in salas}
    common_tags = sorted(set.intersection(*(set(s["tags"]) for s in salas))) if salas else []

    def describe(date: str, time_: str, sala_name: str) -> tuple[bool, list[str], Optional[float]]:
        if date == today_iso and time_ in by_today_time:
            hit = by_today_time[time_]
            return hit["vo"], hit["tags"], hit["price"]
        if len(vo_values) == 1:
            return next(iter(vo_values)), common_tags, None
        # Doppiato e V.O. alternati: i cinema ripetono gli stessi orari, quindi
        # lo stesso orario di oggi indica la stessa versione.
        if time_ in by_today_time:
            hit = by_today_time[time_]
            return hit["vo"], hit["tags"], None
        key = sala_key(sala_name)
        for s in salas:
            if key and sala_key(s["sala"]) == key:
                return s["vo"], s["tags"], None
        return False, common_tags, None

    out: dict[tuple, dict] = {}

    for t in ticket_shows or []:
        if t["date"] < today_iso:
            continue
        vo, tags, price = describe(t["date"], t["time"], t["sala"])
        key = (t["date"], t["time"], sala_key(t["sala"]))
        out[key] = {
            "date": t["date"], "time": t["time"], "sala": t["sala"],
            "vo": vo, "tags": tags, "price": price, "url": t["url"],
        }

    # Orari di oggi presenti solo sulla pagina del cinema (es. vendita online chiusa)
    have_today = {(d, tm) for (d, tm, _) in out if d == today_iso}
    for s in salas:
        for t in s["times"]:
            if (today_iso, t["time"]) in have_today:
                continue
            key = (today_iso, t["time"], sala_key(s["sala"]))
            out.setdefault(key, {
                "date": today_iso, "time": t["time"], "sala": s["sala"],
                "vo": s["vo"], "tags": s["tags"], "price": t["price"], "url": None,
            })

    return sorted(out.values(), key=lambda x: (x["date"], x["time"], x["sala"]))


# --------------------------------------------------------------------------- fetch

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "it-IT,it;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    })
    retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def make_fetcher(delay: float) -> Callable[[str], str]:
    session = make_session()
    last = [0.0]

    def fetch(path: str) -> str:
        wait = delay - (time.monotonic() - last[0])
        if wait > 0:
            time.sleep(wait)
        url = path if path.startswith("http") else BASE + path
        resp = session.get(url, timeout=25)
        last[0] = time.monotonic()
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        return resp.text

    return fetch


# --------------------------------------------------------------------------- scrape

def scrape(cinemas: list[dict], fetch: Callable[[str], str], today: dt.date) -> dict:
    films: dict[str, dict] = {}
    shows: list[dict] = []
    warnings: list[str] = []
    ok, failed = [], []
    sidebar_checked = False

    for cinema in cinemas:
        path = f"/cinema/bologna/{cinema['slug']}/{cinema['id']}/"
        try:
            page_films, sidebar = parse_cinema_page(fetch(path))
        except Exception as exc:  # noqa: BLE001 - un cinema rotto non deve fermare gli altri
            log.warning("%s: pagina non letta (%s)", cinema["name"], exc)
            failed.append(cinema["id"])
            warnings.append(f"{cinema['name']}: pagina non letta ({type(exc).__name__})")
            continue
        ok.append(cinema["id"])

        if sidebar and not sidebar_checked:
            sidebar_checked = True
            known = {c["id"] for c in cinemas}
            listed = {c["id"]: c for c in sidebar}
            for cid in listed.keys() - known:
                warnings.append(f"Nuovo cinema su comingsoon: {listed[cid]['name']} ({listed[cid]['slug']}/{cid})")
            for cid in known - listed.keys():
                name = next(c["name"] for c in cinemas if c["id"] == cid)
                warnings.append(f"Cinema non piu' elencato su comingsoon: {name}")

        log.info("%s: %d film", cinema["name"], len(page_films))
        for film in page_films:
            ticket_shows = None
            if film["ticket_path"]:
                try:
                    ticket_shows = parse_ticket_page(fetch(film["ticket_path"]), today)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{cinema['name']} / {film['title']}: date non lette ({type(exc).__name__})")

            film_shows = build_shows(film, ticket_shows, today)
            if not film_shows:
                continue

            record = {k: v for k, v in film.items() if k not in ("salas", "ticket_path")}
            existing = films.get(film["idf"])
            if existing:
                for k, v in record.items():
                    if not existing.get(k) and v:
                        existing[k] = v
            else:
                films[film["idf"]] = record

            for s in film_shows:
                shows.append({"film": film["idf"], "cinema": cinema["id"], **s})

    shows.sort(key=lambda s: (s["date"], s["time"], s["cinema"], s["film"]))
    active_cinemas = {s["cinema"] for s in shows}
    film_list = sorted(films.values(), key=lambda f: (f["release_date"] or "", f["title"]), reverse=True)

    return {
        "showtimes": {
            "version": 1,
            "today": today.isoformat(),
            "source": "https://www.comingsoon.it/cinema/bologna/",
            "cinemas": [
                {**{k: c[k] for k in ("id", "name", "short", "address")},
                 "url": f"{BASE}/cinema/bologna/{c['slug']}/{c['id']}/",
                 "active": c["id"] in active_cinemas}
                for c in cinemas
            ],
            "films": film_list,
            "shows": shows,
        },
        "stats": {
            "cinemas_ok": len(ok),
            "cinemas_failed": len(failed),
            "cinemas_with_shows": len(active_cinemas),
            "films": len(film_list),
            "shows": len(shows),
        },
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- main

def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data", help="cartella di output (default: data)")
    parser.add_argument("--delay", type=float, default=1.5, help="secondi tra una richiesta e l'altra")
    parser.add_argument("--only", help="slug di un solo cinema, per test")
    parser.add_argument("--min-shows", type=int, default=50,
                        help="sotto questa soglia non sovrascrive i dati ed esce con errore")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    here = Path(__file__).resolve().parent
    cinemas = json.loads((here / "cinemas.json").read_text(encoding="utf-8"))
    if args.only:
        cinemas = [c for c in cinemas if c["slug"] == args.only]
        args.min_shows = 1

    now = dt.datetime.now(ROME)
    started = time.monotonic()
    result = scrape(cinemas, make_fetcher(args.delay), now.date())
    stats = result["stats"]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    healthy = stats["shows"] >= args.min_shows and stats["cinemas_ok"] >= len(cinemas) // 2

    meta = {
        "updated_at": now.isoformat(timespec="minutes"),
        "duration_s": round(time.monotonic() - started),
        "healthy": healthy,
        **stats,
        "warnings": result["warnings"],
    }

    if healthy:
        write_json(out / "showtimes.json", result["showtimes"])
        write_json(out / "meta.json", meta)
        log.info("OK: %d film, %d spettacoli, %d/%d cinema letti",
                 stats["films"], stats["shows"], stats["cinemas_ok"], len(cinemas))
        for w in result["warnings"]:
            log.warning(w)
        return 0

    # Dati sospetti: teniamo quelli vecchi e falliamo, cosi' GitHub manda una mail.
    log.error("Dati insufficienti (%s). Non sovrascrivo showtimes.json.", stats)
    for w in result["warnings"]:
        log.error(w)
    return 1


if __name__ == "__main__":
    sys.exit(main())
