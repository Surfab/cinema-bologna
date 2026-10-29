#!/usr/bin/env python3
"""Prepara la mail del giovedi': film nuovi della settimana e, separati, quelli gia' in sala.

Legge data/showtimes.json (e, se ci sono, data/meta.json e data/upcoming.json) e scrive in --out:
  subject.txt   oggetto della mail
  email.html    versione HTML
  email.txt     versione testo
Stampa un riepilogo JSON su stdout.

Solo libreria standard, cosi' gira ovunque senza installare niente.

Uso:
  python scraper/weekly_email.py --data data/showtimes.json --meta data/meta.json --upcoming data/upcoming.json --out out
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


def build(data: dict, meta: Optional[dict], today: dt.date, upcoming: Optional[dict] = None) -> dict:
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
                    {"date": day, "label": short_day(d(day)), "times": sorted(set(times))}
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

    return {"today": today, "end": end, "new": new, "old": old, "meta": meta, "stale": stale,
            "upcoming": pick_upcoming(upcoming, data, today)}


def pick_upcoming(upcoming: Optional[dict], data: dict, today: dt.date) -> Optional[dict]:
    """La prima settimana del calendario che parte dopo oggi, solo con i film non ancora usciti.

    Per ogni film segna i cinema di Bologna che lo hanno gia' in programma (anteprime, prevendite).
    """
    if not upcoming or not upcoming.get("weeks"):
        return None
    weeks = sorted((w for w in upcoming["weeks"] if w.get("from") and d(w["from"]) > today), key=lambda w: w["from"])
    if not weeks:
        return None
    week = weeks[0]

    cinemas = {c["id"]: c["short"] for c in data["cinemas"]}
    by_cs: dict[int, set] = {}
    films = {f["idf"]: f for f in data["films"]}
    for s in data["shows"]:
        f = films.get(s["film"])
        if f and f.get("cs_id") and d(s["date"]) >= today and s["cinema"] in cinemas:
            by_cs.setdefault(f["cs_id"], set()).add(cinemas[s["cinema"]])

    items = []
    for f in week["films"]:
        if not f.get("release_date") or d(f["release_date"]) <= today:
            continue
        items.append({**f, "in_bologna": sorted(by_cs.get(f.get("cs_id"), set()))})
    if not items:
        return None
    return {"from": d(week["from"]), "films": items}


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


def day_runs(days: list) -> list:
    """Unisce i giorni di calendario consecutivi con gli stessi orari: 'gio 29–mer 4'.

    Un giorno senza spettacoli interrompe il gruppo, cosi' non sembra che il film ci sia.
    """
    runs: list = []
    for day in days:
        last = runs[-1] if runs else None
        if last and last["times"] == day["times"] and d(day["date"]) - d(last["to"]) == dt.timedelta(days=1):
            last["to"], last["to_label"] = day["date"], day["label"]
        else:
            runs.append({"from_label": day["label"], "to": day["date"], "to_label": day["label"], "times": day["times"]})
    return [{"label": r["from_label"] if r["from_label"] == r["to_label"] else f"{r['from_label']}–{r['to_label']}",
             "times": r["times"]} for r in runs]


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
                for day in day_runs(p["days"]):
                    out.append(f"    {day['label']}: {times_text(day['times'])}")

    section("Nuovi questa settimana", w["new"], "Nessun film nuovo in programmazione a Bologna questa settimana.")
    section("Ancora in sala", w["old"], "Nessun altro film in programmazione.")

    up = w.get("upcoming")
    if up:
        out.append("")
        out.append(f"== In uscita {dal(up['from'])} ({len(up['films'])}) ==")
        out.append("Uscite in tutta Italia: non tutti i film arrivano nei cinema di Bologna.")
        for day, group in group_by_day(up["films"]):
            out.append("")
            out.append(f"{DAYS_LONG[day.weekday()].capitalize()} {long_date(day)}")
            for f in group:
                line = f"  {f['title']}" + (f" ({f['original_title']})" if f.get("original_title") else "")
                extra = upcoming_meta(f)
                out.append(line + (f". {extra}" if extra else ""))
                if f["in_bologna"]:
                    out.append(f"    Già in programma a Bologna: {', '.join(f['in_bologna'])}")
    out += [
        "",
        "Molti cinema pubblicano gli orari pochi giorni alla volta: per il weekend ricontrolla sul sito.",
        f"Tutti gli orari, con i link per i biglietti: {SITE}",
        "Dati da ComingSoon.it.",
    ]
    return "\n".join(line for line in out if line is not None) + "\n"


def group_by_day(films: list) -> list:
    groups: dict[dt.date, list] = {}
    for f in films:
        groups.setdefault(d(f["release_date"]), []).append(f)
    return sorted(groups.items())


def upcoming_meta(f: dict) -> str:
    bits = []
    if f.get("genres"):
        bits.append(", ".join(f["genres"]).capitalize())
    if f.get("director"):
        bits.append(f"Regia di {f['director']}")
    return ". ".join(bits)


# --------------------------------------------------------------------------- html

# Il connettore Gmail toglie <style> e gli attributi class, e la forma abbreviata
# "background:". Per questo ogni stile sta direttamente sul tag (style="..."),
# i colori di sfondo usano background-color/bgcolor e l'impaginazione usa tabelle.
INK, MUTED, LINE, PAPER = "#1C2238", "#585E73", "#D8DAD2", "#F2F3EF"
FONT = "font-family:Helvetica,Arial,sans-serif"
S = {
    "wrap": f"max-width:640px;margin:0 auto;padding:22px 16px 30px;color:{INK};{FONT};font-size:15px;line-height:1.45",
    "h1": f"font-size:24px;line-height:1.15;margin:0 0 6px;color:{INK}",
    "up": f"color:{MUTED};font-size:13px;margin:0",
    "al": "background-color:#FFFFFF;border-left:3px solid #C42B3A;padding:8px 10px;margin:12px 0 0;font-size:14px",
    "h2": f"font-size:19px;margin:30px 0 4px;padding-top:12px;border-top:2px solid {INK};color:{INK}",
    "h2n": f"color:{MUTED};font-weight:normal;font-size:14px",
    "f": f"padding:12px 0;border-bottom:1px solid {LINE}",
    "t": f"font-size:17px;font-weight:bold;margin:0;color:{INK}",
    "t_old": f"font-size:16px;font-weight:bold;margin:0;color:{INK}",
    "ta": f"color:{INK};text-decoration:none",
    "o": f"color:{MUTED};font-weight:normal;font-size:14px",
    "m": f"color:{MUTED};font-size:13px;margin:2px 0 6px",
    "cin": f"font-size:14px;font-weight:bold;margin:8px 0 2px;color:{INK}",
    # Le righe degli orari si ripetono centinaia di volte: stili corti, o Gmail
    # taglia la mail oltre i 102 KB. Colore e grassetto degli orari stanno sulla
    # tabella e le celle li ereditano; la cella del giorno li riporta al normale.
    "grid": "border-collapse:collapse;font-size:14px;color:#7B1F2D;font-weight:bold",
    "day": f"color:{MUTED};font-weight:normal;padding-right:10px;white-space:nowrap",
    "v": "background-color:#CDEADB;color:#1C5A3B",
    "e": f"color:{MUTED}",
    "h3": f"font-size:15px;margin:14px 0 4px;color:{INK}",
    "u": "margin:0 0 8px;font-size:14px",
    "ua": f"color:{INK}",
    "um": f"color:{MUTED};font-size:13px",
    "b": "font-size:13px;color:#1C5A3B",
    "ft": f"color:{MUTED};font-size:13px;margin-top:26px",
    "fta": f"color:{INK}",
}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def render_html(w: dict) -> str:
    def link(url: Optional[str], text: str, style: str) -> str:
        return f'<a href="{esc(url)}" style="{style}">{text}</a>' if url else text

    def times_html(times: list) -> str:
        return " &nbsp;".join(f'<span style="{S["v"]}">{t}&nbsp;V.O.</span>' if vo else t for t, vo in times)

    def film_html(r: dict, old: bool) -> str:
        f = r["film"]
        title = link(f.get("scheda_url"), esc(f["title"]), S["ta"])
        orig = f' <span style="{S["o"]}">({esc(f["original_title"])})</span>' if f.get("original_title") else ""
        meta = film_meta(f, w["today"])
        places = "".join(
            f'<p style="{S["cin"]}">{esc(p["cinema"])}</p>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="{S["grid"]}">'
            + "".join(
                f'<tr valign="top"><td style="{S["day"]}">{esc(day["label"])}</td><td>{times_html(day["times"])}</td></tr>'
                for day in day_runs(p["days"])
            )
            + "</table>"
            for p in r["places"]
        )
        meta_html = f'<p style="{S["m"]}">{esc(meta)}</p>' if meta else ""
        return f'<div style="{S["f"]}"><p style="{S["t_old"] if old else S["t"]}">{title}{orig}</p>{meta_html}{places}</div>'

    def section(title: str, rows: list, empty: str, old: bool = False) -> str:
        body = "".join(film_html(r, old) for r in rows) or f'<p style="{S["e"]}">{esc(empty)}</p>'
        return f'<h2 style="{S["h2"]}">{esc(title)} <span style="{S["h2n"]}">{len(rows)}</span></h2>{body}'

    def upcoming_html(up: Optional[dict]) -> str:
        if not up:
            return ""
        parts = [f'<h2 style="{S["h2"]}">In uscita {esc(dal(up["from"]))} <span style="{S["h2n"]}">{len(up["films"])}</span></h2>',
                 f'<p style="{S["m"]}">Uscite in tutta Italia: non tutti i film arrivano nei cinema di Bologna.</p>']
        for day, group in group_by_day(up["films"]):
            parts.append(f'<h3 style="{S["h3"]}">{esc(DAYS_LONG[day.weekday()].capitalize())} {esc(long_date(day))}</h3>')
            for f in group:
                title = link(f.get("scheda_url"), esc(f["title"]), S["ua"])
                orig = f' <span style="{S["o"]}">({esc(f["original_title"])})</span>' if f.get("original_title") else ""
                extra = upcoming_meta(f)
                extra_html = f'<br><span style="{S["um"]}">{esc(extra)}</span>' if extra else ""
                here = f'<br><span style="{S["b"]}">Già in programma a Bologna: {esc(", ".join(f["in_bologna"]))}</span>' if f["in_bologna"] else ""
                parts.append(f'<p style="{S["u"]}"><b>{title}</b>{orig}{extra_html}{here}</p>')
        return "".join(parts)

    head = f"Da {DAYS_LONG[w['today'].weekday()]} {long_date(w['today'])} a {DAYS_LONG[w['end'].weekday()]} {long_date(w['end'])}"
    alert = ""
    if w["stale"]:
        alert = f'<p style="{S["al"]}">Gli orari non si aggiornano da {w["stale"]:%d/%m alle %H:%M}: l\'aggiornamento automatico potrebbe essersi fermato. Controlla la scheda Actions su GitHub.</p>'

    site = SITE.replace("https://", "").rstrip("/")
    return (
        '<!doctype html><html lang="it"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;padding:0;background-color:{PAPER}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{PAPER}" style="background-color:{PAPER}"><tr><td>'
        f'<div style="{S["wrap"]}">'
        f'<h1 style="{S["h1"]}">Cinema a Bologna</h1><p style="{S["up"]}">{esc(head)}. {esc(updated_line(w))}</p>{alert}'
        + section("Nuovi questa settimana", w["new"], "Nessun film nuovo in programmazione a Bologna questa settimana.")
        + section("Ancora in sala", w["old"], "Nessun altro film in programmazione.", old=True)
        + upcoming_html(w.get("upcoming"))
        + f'<p style="{S["ft"]}">Molti cinema pubblicano gli orari pochi giorni alla volta: per il weekend ricontrolla sul sito.<br>'
        f'Tutti gli orari, con i link per i biglietti: <a href="{SITE}" style="{S["fta"]}">{site}</a><br>'
        "Dati da ComingSoon.it.</p>"
        "</div></td></tr></table></body></html>\n"
    )


# --------------------------------------------------------------------------- main

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/showtimes.json")
    ap.add_argument("--meta", default="data/meta.json")
    ap.add_argument("--upcoming", default="data/upcoming.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--today", help="YYYY-MM-DD, default: oggi a Bologna")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    meta_path = Path(args.meta)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(ROME).date()

    up_path = Path(args.upcoming)
    upcoming = json.loads(up_path.read_text(encoding="utf-8")) if up_path.exists() else None
    w = build(data, meta, today, upcoming)
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
        "upcoming_films": len(w["upcoming"]["films"]) if w["upcoming"] else 0,
        "stale": bool(w["stale"]),
        "html_bytes": (out / "email.html").stat().st_size,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
