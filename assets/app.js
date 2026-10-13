/* Cinema a Bologna: legge data/showtimes.json e mostra film, cinema e orari. */
(() => {
  "use strict";

  const TZ = "Europe/Rome";
  const EVENING = "19:00";
  const STALE_HOURS = 36;
  const STORE_KEY = "cb.cinemas";

  const $ = (sel) => document.querySelector(sel);
  const els = {
    title: $("#day-title"), days: $("#days"), list: $("#lista"), q: $("#q"),
    vo: $("#f-vo"), pom: $("#f-pom"), sera: $("#f-sera"),
    pick: $("#pick"), pickLabel: $("#pick-label"), pickList: $("#pick-list"),
    pickAll: $("#pick-all"), pickNone: $("#pick-none"),
    notice: $("#notice"), updated: $("#updated"),
    views: document.querySelectorAll("[data-view]"),
  };

  const state = {
    data: null, meta: null,
    view: "film", day: null, q: "", vo: false, slot: null,
    cinemas: null,            // null = tutti
    open: new Set(),          // film con dettagli aperti
  };
  let idx = null;

  // ------------------------------------------------------------------ date

  const fmtDate = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
  const fmtTime = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false });
  const romeNow = () => { const d = new Date(); return { date: fmtDate.format(d), time: fmtTime.format(d) }; };

  const fromIso = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)); };
  const addDays = (iso, n) => { const d = fromIso(iso); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  const it = (opts) => new Intl.DateTimeFormat("it-IT", { timeZone: "UTC", ...opts });
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  function dayShort(iso, today) {
    if (iso === today) return "Oggi";
    if (iso === addDays(today, 1)) return "Domani";
    return cap(it({ weekday: "short" }).format(fromIso(iso)).replace(".", ""));
  }
  const dayNum = (iso) => it({ day: "numeric", month: "short" }).format(fromIso(iso)).replace(".", "");
  const dayLong = (iso) => cap(it({ weekday: "long", day: "numeric", month: "long" }).format(fromIso(iso)));
  const dayFrom = (iso) => it({ day: "numeric", month: "long" }).format(fromIso(iso));

  // ------------------------------------------------------------------ utils

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const euro = (p) => (p == null ? "" : `${p.toFixed(2).replace(".", ",")} euro`);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  function load(key) { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } }
  function save(key, v) { try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* storage non disponibile */ } }

  // ------------------------------------------------------------------ index

  function buildIndex(data, today) {
    const films = new Map(data.films.map((f) => [f.idf, f]));
    const cinemas = new Map(data.cinemas.map((c) => [c.id, c]));
    const byDay = new Map();
    for (const s of data.shows) {
      if (s.date < today || !films.has(s.film) || !cinemas.has(s.cinema)) continue;
      if (!byDay.has(s.date)) byDay.set(s.date, []);
      byDay.get(s.date).push(s);
    }
    const days = [...byDay.keys()].sort();
    const searchText = new Map(data.films.map((f) => [f.idf, norm([f.title, f.original_title, ...(f.cast || []), ...(f.genres || [])].join(" "))]));
    return { films, cinemas, byDay, days, searchText };
  }

  // ------------------------------------------------------------------ filtri

  function cinemaAllowed(id) { return !state.cinemas || state.cinemas.has(id); }

  function filteredShows(day, { ignoreSlot = false, ignoreQuery = false } = {}) {
    const q = norm(state.q.trim());
    return (idx.byDay.get(day) || []).filter((s) => {
      if (!cinemaAllowed(s.cinema)) return false;
      if (state.vo && !s.vo) return false;
      if (!ignoreSlot && state.slot === "pom" && s.time >= EVENING) return false;
      if (!ignoreSlot && state.slot === "sera" && s.time < EVENING) return false;
      if (!ignoreQuery && q) {
        const c = idx.cinemas.get(s.cinema);
        if (!idx.searchText.get(s.film).includes(q) && !norm(`${c.name} ${c.short}`).includes(q)) return false;
      }
      return true;
    });
  }

  // ------------------------------------------------------------------ pezzi

  function ticket(s, now) {
    const c = idx.cinemas.get(s.cinema);
    const past = s.date === now.date && s.time < now.time;
    const label = [s.time, s.sala, s.vo ? "versione originale" : "", euro(s.price)].filter(Boolean).join(", ");
    const inner = `<span>${esc(s.time)}</span>${s.vo ? '<span class="tk__vo" aria-hidden="true">V.O.</span>' : ""}`;
    const cls = `tk${s.vo ? " is-vo" : ""}${past ? " is-past" : ""}`;
    if (past) return `<span class="${cls}" title="${esc(label)}, gia' iniziato">${inner}</span>`;
    const href = s.url || c.url;
    const action = s.url ? "acquista il biglietto" : "vai alla pagina del cinema";
    return `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener" title="${esc(label)}" aria-label="${esc(`${label}: ${action}`)}">${inner}</a>`;
  }

  function filmMeta(f) {
    const bits = [];
    if (f.genres?.length) bits.push(cap(f.genres.join(", ").toLowerCase()));
    if (f.duration) bits.push(`${f.duration} min`);
    return bits.join(". ");
  }

  function badgeFor(f, day) {
    if (!f.release_date) return "";
    if (f.release_date > day) return '<span class="badge">Anteprima</span>';
    if (f.release_date >= addDays(day, -6)) return '<span class="badge">Nuovo</span>';
    return "";
  }

  // ------------------------------------------------------------------ vista film

  function renderFilms(day, now) {
    const shows = filteredShows(day);
    const byFilm = new Map();
    for (const s of shows) {
      if (!byFilm.has(s.film)) byFilm.set(s.film, []);
      byFilm.get(s.film).push(s);
    }
    if (!byFilm.size) return emptyFilters();

    const isToday = day === now.date;
    const rows = [...byFilm.entries()].map(([id, list]) => {
      const f = idx.films.get(id);
      const upcoming = list.filter((s) => !(isToday && s.time < now.time)).length;
      return { f, list, upcoming };
    });

    const weekAgo = addDays(day, -6);
    const isNew = (r) => r.f.release_date && r.f.release_date >= weekAgo;
    const byRank = (a, b) => (b.upcoming > 0) - (a.upcoming > 0) || b.list.length - a.list.length || a.f.title.localeCompare(b.f.title, "it");
    const fresh = rows.filter(isNew).sort((a, b) => (b.f.release_date || "").localeCompare(a.f.release_date || "") || byRank(a, b));
    const rest = rows.filter((r) => !isNew(r)).sort(byRank);

    let html = "";
    if (fresh.length) {
      html += `<section class="group" aria-labelledby="g-new"><h2 id="g-new">Usciti questa settimana <span class="n">${fresh.length}</span></h2>${fresh.map((r) => filmRow(r, day, now)).join("")}</section>`;
    }
    if (rest.length) {
      html += `<section class="group" aria-labelledby="g-all"><h2 id="g-all">${fresh.length ? "Ancora in sala" : "In programmazione"} <span class="n">${rest.length}</span></h2>${rest.map((r) => filmRow(r, day, now)).join("")}</section>`;
    }
    return html;
  }

  function filmRow({ f, list }, day, now) {
    const byCinema = new Map();
    for (const s of list) {
      if (!byCinema.has(s.cinema)) byCinema.set(s.cinema, []);
      byCinema.get(s.cinema).push(s);
    }
    const where = [...byCinema.entries()]
      .sort((a, b) => a[1][0].time.localeCompare(b[1][0].time))
      .map(([cid, ss]) => {
        const c = idx.cinemas.get(cid);
        return `<div class="where__row"><div class="where__name">${esc(c.short)}</div><div class="times">${ss.map((s) => ticket(s, now)).join("")}</div></div>`;
      }).join("");

    // Altri giorni in cui il film passa (rispettando cinema e V.O.)
    const others = idx.days.filter((d) => d !== day && filteredShows(d, { ignoreSlot: true, ignoreQuery: true }).some((s) => s.film === f.idf)).slice(0, 5);
    const also = others.length
      ? `<p class="also">Anche ${others.map((d) => `<button type="button" data-day="${d}">${esc(dayShort(d, now.date).toLowerCase())} ${esc(dayNum(d).split(" ")[0])}</button>`).join(", ")}.</p>`
      : "";

    const open = state.open.has(f.idf);
    const detailsId = `d-${f.idf}`;
    const more = open ? `<div class="more" id="${detailsId}">
        ${f.original_title ? `<p>Titolo originale: ${esc(f.original_title)}</p>` : ""}
        ${f.cast?.length ? `<p>Con ${esc(f.cast.join(", "))}</p>` : ""}
        ${f.release_date ? `<p>Al cinema dal ${esc(dayFrom(f.release_date))}${f.rating ? `. Voto del pubblico ${String(f.rating).replace(".", ",")} su 5` : ""}</p>` : ""}
        <p>${f.scheda_url ? `<a href="${esc(f.scheda_url)}" target="_blank" rel="noopener">Scheda</a>` : ""}${f.trailer_url ? `<a href="${esc(f.trailer_url)}" target="_blank" rel="noopener">Trailer</a>` : ""}</p>
      </div>` : "";

    return `<article class="film">
      <div class="poster">${f.poster ? `<img src="${esc(f.poster)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</div>
      <div>
        <h3 class="film__title"><button type="button" data-film="${esc(f.idf)}" aria-expanded="${open}" aria-controls="${detailsId}">${esc(f.title)}</button>${badgeFor(f, day)}</h3>
        <p class="film__meta">${esc(filmMeta(f))}</p>
        ${more}
        <div class="where">${where}</div>
        ${also}
      </div>
    </article>`;
  }

  // ------------------------------------------------------------------ vista cinema

  function renderCinemas(day, now) {
    const shows = filteredShows(day);
    const byCinema = new Map();
    for (const s of shows) {
      if (!byCinema.has(s.cinema)) byCinema.set(s.cinema, new Map());
      const films = byCinema.get(s.cinema);
      if (!films.has(s.film)) films.set(s.film, []);
      films.get(s.film).push(s);
    }
    if (!byCinema.size) return emptyFilters();

    const sorted = [...byCinema.entries()].sort((a, b) => idx.cinemas.get(a[0]).short.localeCompare(idx.cinemas.get(b[0]).short, "it"));
    let html = '<section class="group" aria-label="Cinema">';
    for (const [cid, films] of sorted) {
      const c = idx.cinemas.get(cid);
      const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${c.name}, ${c.address}, Bologna`)}`;
      const rows = [...films.entries()]
        .sort((a, b) => a[1][0].time.localeCompare(b[1][0].time))
        .map(([fid, ss]) => {
          const f = idx.films.get(fid);
          return `<div class="where__row"><div class="where__name"><button type="button" data-goto-film="${esc(f.title)}">${esc(f.title)}</button>${badgeFor(f, day)}</div><div class="times">${ss.map((s) => ticket(s, now)).join("")}</div></div>`;
        }).join("");
      html += `<article class="cin">
        <div class="cin__head"><h3 class="cin__name">${esc(c.name)}</h3><a class="cin__addr" href="${maps}" target="_blank" rel="noopener">${esc(c.address)}</a></div>
        <div class="where">${rows}</div>
      </article>`;
    }
    html += "</section>";

    const quiet = idx.data.cinemas.filter((c) => cinemaAllowed(c.id) && !byCinema.has(c.id)).map((c) => c.short);
    if (quiet.length && !state.q && !state.vo && !state.slot) {
      html += `<p class="off">Nessuno spettacolo in elenco: ${esc(quiet.join(", "))}.</p>`;
    }
    return html;
  }

  function emptyFilters() {
    return `<div class="empty"><b>Nessuno spettacolo con questi filtri.</b>Prova un altro giorno o <button type="button" class="chip" data-reset>azzera i filtri</button></div>`;
  }

  // ------------------------------------------------------------------ chrome

  function renderDays(now) {
    els.days.innerHTML = idx.days.map((d) => {
      const n = new Set(filteredShows(d, { ignoreSlot: true, ignoreQuery: true }).map((s) => s.film)).size;
      return `<button type="button" class="day" data-day="${d}" ${d === state.day ? 'aria-current="date"' : ""} aria-label="${esc(`${dayLong(d)}, ${plural(n, "film", "film")}`)}"><b>${esc(dayShort(d, now.date))}</b><span>${esc(dayNum(d))}</span></button>`;
    }).join("");
    // Porta in vista il giorno scelto solo in orizzontale, senza far saltare la pagina
    const current = els.days.querySelector('[aria-current="date"]');
    if (current) {
      const left = current.offsetLeft;
      const right = left + current.offsetWidth;
      if (left < els.days.scrollLeft) els.days.scrollLeft = left - 16;
      else if (right > els.days.scrollLeft + els.days.clientWidth) els.days.scrollLeft = right - els.days.clientWidth + 16;
    }
  }

  function renderTitle() {
    const shows = filteredShows(state.day);
    const films = new Set(shows.map((s) => s.film)).size;
    const cinemas = new Set(shows.map((s) => s.cinema)).size;
    els.title.innerHTML = `${esc(dayLong(state.day))}<small>${films ? `${plural(films, "film", "film")} in ${plural(cinemas, "cinema", "cinema")}` : "Nessun film con questi filtri"}</small>`;
  }

  function renderPicker() {
    const counts = new Map();
    for (const s of idx.byDay.get(state.day) || []) counts.set(s.cinema, (counts.get(s.cinema) || 0) + 1);
    const list = [...idx.data.cinemas].sort((a, b) => a.short.localeCompare(b.short, "it"));
    els.pickList.innerHTML = list.map((c) => `<label><input type="checkbox" value="${c.id}" ${cinemaAllowed(c.id) ? "checked" : ""}> ${esc(c.short)} <span class="n">${counts.get(c.id) ? plural(counts.get(c.id), "orario", "orari") : "nessun orario"}</span></label>`).join("");
    const total = idx.data.cinemas.length;
    const chosen = state.cinemas ? state.cinemas.size : total;
    els.pickLabel.textContent = chosen === total ? "Tutti i cinema" : chosen === 0 ? "Nessun cinema" : `${plural(chosen, "cinema", "cinema")} su ${total}`;
    els.pickLabel.setAttribute("aria-pressed", String(chosen !== total));
  }

  function renderUpdated() {
    const m = state.meta;
    if (!m?.updated_at) { els.updated.textContent = ""; return; }
    const at = new Date(m.updated_at);
    const now = romeNow();
    const atDay = fmtDate.format(at);
    const when = atDay === now.date ? "oggi" : atDay === addDays(now.date, -1) ? "ieri" : `il ${dayFrom(atDay)}`;
    els.updated.textContent = `Aggiornato ${when} alle ${fmtTime.format(at)}.`;
    const hours = (Date.now() - at.getTime()) / 36e5;
    if (hours > STALE_HOURS) {
      els.notice.hidden = false;
      els.notice.textContent = `Gli orari risalgono a ${Math.round(hours / 24)} giorni fa: l'aggiornamento automatico potrebbe essersi fermato. Controlla la scheda Actions su GitHub.`;
    }
  }

  function syncControls() {
    els.views.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === state.view)));
    els.vo.setAttribute("aria-pressed", String(state.vo));
    els.pom.setAttribute("aria-pressed", String(state.slot === "pom"));
    els.sera.setAttribute("aria-pressed", String(state.slot === "sera"));
    const url = new URL(location.href);
    url.searchParams.set("giorno", state.day);
    if (state.view === "cinema") url.searchParams.set("vista", "cinema"); else url.searchParams.delete("vista");
    history.replaceState(null, "", url);
  }

  function render({ animate = false } = {}) {
    const now = romeNow();
    if (!idx.days.includes(state.day)) state.day = idx.days[0];
    syncControls();
    renderDays(now);
    renderTitle();
    renderPicker();
    els.list.innerHTML = state.view === "film" ? renderFilms(state.day, now) : renderCinemas(state.day, now);
    if (animate) {
      els.list.classList.remove("is-swapping");
      void els.list.offsetWidth;
      els.list.classList.add("is-swapping");
    }
  }

  // ------------------------------------------------------------------ eventi

  function bind() {
    document.addEventListener("click", (e) => {
      const t = e.target.closest("button, [data-reset]");
      if (!t) return;
      if (t.dataset.day) { state.day = t.dataset.day; render({ animate: true }); window.scrollTo({ top: 0 }); return; }
      if (t.dataset.view) { state.view = t.dataset.view; render({ animate: true }); return; }
      if (t.dataset.film) {
        const id = t.dataset.film;
        state.open.has(id) ? state.open.delete(id) : state.open.add(id);
        render();
        document.querySelector(`[data-film="${CSS.escape(id)}"]`)?.focus();
        return;
      }
      if (t.dataset.gotoFilm) { state.view = "film"; state.q = t.dataset.gotoFilm; els.q.value = state.q; render({ animate: true }); return; }
      if (t.hasAttribute("data-reset")) {
        Object.assign(state, { q: "", vo: false, slot: null, cinemas: null });
        els.q.value = ""; save(STORE_KEY, null); render({ animate: true }); return;
      }
    });

    els.vo.addEventListener("click", () => { state.vo = !state.vo; render(); });
    els.pom.addEventListener("click", () => { state.slot = state.slot === "pom" ? null : "pom"; render(); });
    els.sera.addEventListener("click", () => { state.slot = state.slot === "sera" ? null : "sera"; render(); });

    let timer;
    els.q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.q = els.q.value; render(); }, 120); });

    els.pickList.addEventListener("change", () => {
      const ids = [...els.pickList.querySelectorAll("input:checked")].map((i) => Number(i.value));
      state.cinemas = ids.length === idx.data.cinemas.length ? null : new Set(ids);
      save(STORE_KEY, state.cinemas ? [...state.cinemas] : null);
      render();
    });
    els.pickAll.addEventListener("click", () => { state.cinemas = null; save(STORE_KEY, null); render(); });
    els.pickNone.addEventListener("click", () => { state.cinemas = new Set(); save(STORE_KEY, []); render(); });
    document.addEventListener("click", (e) => { if (els.pick.open && !els.pick.contains(e.target)) els.pick.open = false; });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && els.pick.open) { els.pick.open = false; els.pickLabel.focus(); } });

    // Se la pagina resta aperta a lungo o torna in primo piano, gli orari passati si aggiornano
    setInterval(() => { if (!document.hidden) render(); }, 5 * 60_000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) render(); });
  }

  // ------------------------------------------------------------------ avvio

  async function getJson(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return res.json();
  }

  async function start() {
    try {
      const [data, meta] = await Promise.all([getJson("data/showtimes.json"), getJson("data/meta.json").catch(() => null)]);
      state.data = data;
      state.meta = meta;
    } catch {
      els.list.innerHTML = `<div class="empty"><b>Ancora nessun orario.</b>Il primo aggiornamento automatico parte su GitHub Actions dopo la pubblicazione e richiede qualche minuto. Ricarica la pagina tra poco.</div>`;
      els.title.textContent = "Cinema a Bologna";
      return;
    }

    const now = romeNow();
    idx = buildIndex(state.data, now.date);
    idx.data = state.data;
    renderUpdated();

    if (!idx.days.length) {
      els.title.textContent = "Cinema a Bologna";
      els.list.innerHTML = `<div class="empty"><b>Nessun orario da oggi in poi.</b>I dati salvati sono vecchi. L'aggiornamento automatico potrebbe essersi fermato: controlla la scheda Actions del repository.</div>`;
      return;
    }

    const params = new URLSearchParams(location.search);
    state.day = idx.days.includes(params.get("giorno")) ? params.get("giorno") : idx.days[0];
    state.view = params.get("vista") === "cinema" ? "cinema" : "film";
    const saved = load(STORE_KEY);
    if (Array.isArray(saved)) {
      const valid = saved.filter((id) => idx.cinemas.has(id));
      state.cinemas = valid.length === state.data.cinemas.length ? null : new Set(valid);
    }

    bind();
    render();
  }

  start();
})();
