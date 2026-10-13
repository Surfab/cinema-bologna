#!/usr/bin/env python3
"""Prepara la mail del giovedi': film nuovi della settimana e, separati, quelli gia' in sala.

Legge data/showtimes.json (e data/meta.json se c'e') e scrive in --out:
  subject.txt   oggetto della mail
  email.html    versione HTML
  email.txt     versione testo
Stampa un riepilogo JSON su stdout.

Solo libreria standard, cosi' gira ovunque senza installare niente.

Uso:
  python scraper/weekly_email.py --data data/showtimes.json --meta data/meta.json --out out
  python scraper/weekly_email.py --today 2026-10-15 ...   # per provare un giovedi' qualsiasi
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
SITE = "https://surfab.github.io/cinema-bologna/"
DAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
DAYS_LONG = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
          "agosto", "settembre", "ottobre", "novembre", "dicembre"]
STALE_HOURS = 30


def d(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


def short_day(day: dt.date) -> str:
    return f"{DAYS[day.weekday()]} {day.day}"


def long_date(day: dt.date) -> str:
    num = "1°" if day.day == 1 else str(day.day)
    return f"{num} {MONTHS[day.month - 1]}"


def dal(day: dt.date) -> str:
    """'dal 13 ottobre', 'dall'8 ottobre', 'dall'11 ottobre'."""
    return ("dall'" if day.day in (8, 11) else "dal ") + long_date(day)


def il(day: dt.date) -> str:
    """'il 15 ottobre', 'l'8 ottobre'."""
    return ("l'" if day.day in (8, 11) else "il ") + long_date(day)


def build(data: dict, meta: Optional[dict], today: dt.date) -> dict:
    """Divide i film della settimana (da oggi a 6 giorni dopo) in nuovi e gia' in sala.

    Nuovo = uscito dopo il giovedi' precedente (today - 6 in poi), comprese le uscite
    o anteprime dei giorni successivi della settimana.
    """
    start, end = today, today + dt.timedelta(days=6)
    new_from = today - dt.timedelta(days=6)

    films = {f["idf"]: f for f in data["films"]}
    cinemas = {c["id"]: c for c in data["cinemas"]}

    # film -> cinema -> giorno -> [(ora, vo)]
    grid: dict[str, dict[int, dict[str, list]]] = {}
    for s in data["shows"]:
        day = d(s["date"])
        if not (start <= day <= end) or s["film"] not in films or s["cinema"] not in cinemas:
            continue
        grid.setdefault(s["film"], {}).setdefault(s["cinema"], {}).setdefault(s["date"], []).append((s["time"], s["vo"]))

    def entry(fid: str) -> dict:
        f = films[fid]
        places = []
        for cid, days in grid[fid].items():
            places.append({
                "cinema": cinemas[cid]["short"],
                "days": [
                    {"label": short_day(d(day)), "times": sorted(set(times))}
                    for day, times in sorted(days.items())
                ],
            })
        places.sort(key=lambda p: (p["days"][0]["label"] != short_day(today), min(t for dd in p["days"] for t, _ in dd["times"]), p["cinema"]))
        n_shows = sum(len(dd["times"]) for p in places for dd in p["days"])
        return {"film": f, "places": places, "shows": n_shows}

    rows = [entry(fid) for fid in grid]
    is_new = lambda r: bool(r["film"].get("release_date")) and d(r["film"]["release_date"]) >= new_from
    # Prima i film gia' usciti (piu' spettacoli = piu' diffusi), poi le uscite dei prossimi giorni
    new = sorted((r for r in rows if is_new(r)), key=lambda r: (r["film"]["release_date"] > today.isoformat(), -r["shows"], r["film"]["title"]))
    old = sorted((r for r in rows if not is_new(r)), key=lambda r: (-r["shows"], r["film"]["title"]))

    stale = None
    if meta and meta.get("updated_at"):
        updated = dt.datetime.fromisoformat(meta["updated_at"])
        hours = (dt.datetime.now(ROME) - updated).total_seconds() / 3600
        if hours > STALE_HOURS:
            stale = updated

    return {"today": today, "end": end, "new": new, "old": old, "meta": meta, "stale": stale}


# --------------------------------------------------------------------------- testo

def film_meta(f: dict, today: dt.date) -> str:
    bits = []
    if f.get("genres"):
        bits.append(", ".join(f["genres"]).capitalize())
    if f.get("duration"):
        bits.append(f"{f['duration']} min")
    if f.get("release_date"):
        rel = d(f["release_date"])
        bits.append(f"Esce {il(rel)}" if rel > today else f"Al cinema {dal(rel)}")
    return ". ".join(bits)


def times_text(times: list) -> str:
    return ", ".join(f"{t} V.O." if vo else t for t, vo in times)


def subject(w: dict) -> str:
    n, start = len(w["new"]), w["today"]
    if n == 0:
        return f"🎬 Cinema a Bologna {dal(start)}: nessuna uscita nuova, {len(w['old'])} film in sala"
    return f"🎬 Cinema a Bologna {dal(start)}: {n} {'film nuovo' if n == 1 else 'film nuovi'}"


def updated_line(w: dict) -> str:
    meta = w["meta"] or {}
    if not meta.get("updated_at"):
        return ""
    up = dt.datetime.fromisoformat(meta["updated_at"]).astimezone(ROME)
    return f"Orari aggiornati {DAYS_LONG[up.weekday()]} {long_date(up.date())} alle {up:%H:%M}."


def render_text(w: dict) -> str:
    out = [f"Cinema a Bologna, da {DAYS_LONG[w['today'].weekday()]} {long_date(w['today'])} a {DAYS_LONG[w['end'].weekday()]} {long_date(w['end'])}"]
    if w["stale"]:
        out.append(f"ATTENZIONE: gli orari non si aggiornano da {w['stale']:%d/%m alle %H:%M}. Controlla Actions su GitHub.")
    out.append(updated_line(w))

    def section(title: str, rows: list, empty: str) -> None:
        out.append("")
        out.append(f"== {title} ({len(rows)}) ==")
        if not rows:
            out.append(empty)
        for r in rows:
            f = r["film"]
            out.append("")
            out.append(f["title"] + (f" ({f['original_title']})" if f.get("original_title") else ""))
            meta = film_meta(f, w["today"])
            if meta:
                out.append(meta)
            for p in r["places"]:
                out.append(f"  {p['cinema']}")
                for day in p["days"]:
                    out.append(f"    {day['label']}: {times_text(day['times'])}")

    section("Nuovi questa settimana", w["new"], "Nessun film nuovo in programmazione a Bologna questa settimana.")
    section("Ancora in sala", w["old"], "Nessun altro film in programmazione.")
    out += [
        "",
        "Molti cinema pubblicano gli orari pochi giorni alla volta: per il weekend ricontrolla sul sito.",
        f"Tutti gli orari, con i link per i biglietti: {SITE}",
        "Dati da ComingSoon.it.",
    ]
    return "\n".join(line for line in out if line is not None) + "\n"


# --------------------------------------------------------------------------- html

CSS = """
body{margin:0;padding:0;background:#F2F3EF;color:#1C2238;font-family:Helvetica,Arial,sans-serif;font-size:15px;line-height:1.45}
.w{max-width:640px;margin:0 auto;padding:22px 16px 30px}
h1{font-size:24px;line-height:1.15;margin:0 0 6px}
.up{color:#585E73;font-size:13px;margin:0}
.al{background:#fff;border-left:3px solid #C42B3A;padding:8px 10px;margin:12px 0 0;font-size:14px}
h2{font-size:19px;margin:30px 0 4px;padding-top:12px;border-top:2px solid #1C2238}
h2 span{color:#585E73;font-weight:normal;font-size:14px}
.f{padding:12px 0;border-bottom:1px solid #D8DAD2}
.t{font-size:17px;font-weight:bold;margin:0}
.t a{color:#1C2238;text-decoration:none}
.o{color:#585E73;font-weight:normal;font-size:14px}
.m{color:#585E73;font-size:13px;margin:2px 0 6px}
.c{margin:6px 0 0;font-size:14px}
.c b{display:block}
.g{color:#585E73;display:inline-block;min-width:46px}
.h{background:#F4D3D8;color:#7B1F2D;border-radius:3px;padding:1px 5px;white-space:nowrap;font-weight:bold}
.v{background:#CDEADB;color:#1C5A3B}
.old .t{font-size:16px}
.e{color:#585E73}
.ft{color:#585E73;font-size:13px;margin-top:26px}
.ft a{color:#1C2238}
"""


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def render_html(w: dict) -> str:
    def times_html(times: list) -> str:
        return " ".join(
            f'<span class="h v">{t} V.O.</span>' if vo else f'<span class="h">{t}</span>'
            for t, vo in times
        )

    def film_html(r: dict) -> str:
        f = r["film"]
        title = esc(f["title"])
        if f.get("scheda_url"):
            title = f'<a href="{esc(f["scheda_url"])}">{title}</a>'
        orig = f' <span class="o">({esc(f["original_title"])})</span>' if f.get("original_title") else ""
        meta = film_meta(f, w["today"])
        places = "".join(
            f'<p class="c"><b>{esc(p["cinema"])}</b>'
            + "<br>".join(f'<span class="g">{esc(day["label"])}</span> {times_html(day["times"])}' for day in p["days"])
            + "</p>"
            for p in r["places"]
        )
        return f'<div class="f"><p class="t">{title}{orig}</p>{f"<p class=m>{esc(meta)}</p>" if meta else ""}{places}</div>'

    def section(title: str, rows: list, empty: str, cls: str = "") -> str:
        body = "".join(film_html(r) for r in rows) or f'<p class="e">{esc(empty)}</p>'
        return f'<div class="{cls}"><h2>{esc(title)} <span>{len(rows)}</span></h2>{body}</div>'

    head = f"Da {DAYS_LONG[w['today'].weekday()]} {long_date(w['today'])} a {DAYS_LONG[w['end'].weekday()]} {long_date(w['end'])}"
    alert = ""
    if w["stale"]:
        alert = f'<p class="al">Gli orari non si aggiornano da {w["stale"]:%d/%m alle %H:%M}: l\'aggiornamento automatico potrebbe essersi fermato. Controlla la scheda Actions su GitHub.</p>'

    return (
        '<!doctype html><html lang="it"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{CSS.strip()}</style></head><body><div class=\"w\">"
        f"<h1>Cinema a Bologna</h1><p class=\"up\">{esc(head)}. {esc(updated_line(w))}</p>{alert}"
        + section("Nuovi questa settimana", w["new"], "Nessun film nuovo in programmazione a Bologna questa settimana.")
        + section("Ancora in sala", w["old"], "Nessun altro film in programmazione.", "old")
        + '<p class="ft">Molti cinema pubblicano gli orari pochi giorni alla volta: per il weekend ricontrolla sul sito.<br>'
        f'Tutti gli orari, con i link per i biglietti: <a href="{SITE}">{SITE.replace("https://", "").rstrip("/")}</a><br>'
        "Dati da ComingSoon.it.</p>"
        "</div></body></html>\n"
    )


# --------------------------------------------------------------------------- main

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/showtimes.json")
    ap.add_argument("--meta", default="data/meta.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--today", help="YYYY-MM-DD, default: oggi a Bologna")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    meta_path = Path(args.meta)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(ROME).date()

    w = build(data, meta, today)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    subj = subject(w)
    (out / "subject.txt").write_text(subj + "\n", encoding="utf-8")
    (out / "email.html").write_text(render_html(w), encoding="utf-8")
    (out / "email.txt").write_text(render_text(w), encoding="utf-8")

    print(json.dumps({
        "subject": subj,
        "week": [w["today"].isoformat(), w["end"].isoformat()],
        "new_films": [r["film"]["title"] for r in w["new"]],
        "old_films": len(w["old"]),
        "stale": bool(w["stale"]),
        "html_bytes": (out / "email.html").stat().st_size,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
