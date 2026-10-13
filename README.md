# Cinema a Bologna

Film, cinema e orari di Bologna in una pagina sola, aggiornata da sola due volte al giorno (verso le 7 e le 16).

**Sito:** https://surfab.github.io/cinema-bologna/

Ogni giovedì controllavo a mano cosa usciva e dove. Ora uno script legge la programmazione dei 21 cinema della città, GitHub Actions lo fa girare ogni giorno e GitHub Pages pubblica il risultato. Zero server, zero costi.

## Cosa fa

- Mostra i film del giorno con cinema e orari, per i prossimi giorni disponibili
- Mette in alto i film usciti negli ultimi 7 giorni
- Vista per film o per cinema
- Filtri: versione originale, fascia oraria, ricerca per titolo, attore o cinema, scelta dei "miei cinema" (salvata nel browser)
- Ogni orario porta alla pagina d'acquisto del cinema, quando esiste
- Orari già passati barrati, tema chiaro e scuro automatico

## Come funziona

```
comingsoon.it ──► scraper/scrape.py ──► data/showtimes.json ──► index.html
                  (GitHub Actions,                              (GitHub Pages)
                   2 volte al giorno)
```

1. Per ognuno dei 21 cinema in `scraper/cinemas.json` lo script legge la pagina del cinema (film, sale, orari e prezzi di oggi).
2. Per ogni film apre la pagina "tutte le date" (orari dei giorni successivi e link d'acquisto).
3. Unisce le due fonti, deduce la versione originale dalle sale, scrive `data/showtimes.json` e `data/meta.json`.
   Legge anche il calendario uscite di comingsoon (questa settimana e la prossima) e scrive `data/upcoming.json`.
4. Se trova meno di 50 spettacoli o legge meno di metà dei cinema **non sovrascrive i dati** ed esce con errore: GitHub manda una mail e il sito continua a mostrare l'ultima versione buona.
5. La pagina è HTML, CSS e JavaScript senza framework: legge il JSON e fa tutto nel browser.

Lo script aspetta 1,5 secondi tra una richiesta e l'altra (circa 150 pagine per giro, più 2 del calendario uscite) e si presenta con uno user agent che rimanda a questo repository.

## Mail del giovedì

Ogni giovedì mattina arriva una mail con i film della settimana (da giovedì a mercoledì):

- **Nuovi questa settimana**: tutto ciò che è uscito dopo il giovedì precedente, più le uscite dei giorni successivi
- **Ancora in sala**: gli altri film, in una sezione separata
- **In uscita dal giovedì successivo**: le uscite italiane della settimana dopo, con genere e regia, e i cinema di Bologna che le hanno già in programma
- Per ogni film in sala: cinema, giorni e orari, con la V.O. evidenziata

La mail la prepara `scraper/weekly_email.py` (solo libreria standard, testato in CI). Un task programmato di Claude la scarica da questo repo e la spedisce con Gmail. Per provarla in locale:

```bash
python scraper/weekly_email.py --data data/showtimes.json --meta data/meta.json \
  --upcoming data/upcoming.json --out /tmp/mail --today 2026-10-15
open /tmp/mail/email.html
```

## Struttura

| Percorso | Contenuto |
|---|---|
| `index.html`, `assets/` | Il sito |
| `data/showtimes.json` | Cinema, film e spettacoli (generato) |
| `data/meta.json` | Ora e stato dell'ultimo aggiornamento (generato) |
| `data/upcoming.json` | Uscite italiane di questa settimana e della prossima (generato) |
| `scraper/scrape.py` | Lo scraper |
| `scraper/cinemas.json` | I 21 cinema seguiti, con nome breve e indirizzo |
| `scraper/weekly_email.py` | Genera la mail del giovedì (oggetto, HTML, testo) |
| `tests/` | Test del parser su pagine reali salvate |
| `.github/workflows/update.yml` | Aggiornamento automatico |

## Usarlo in locale

```bash
pip install -r scraper/requirements.txt
python -m unittest discover -s tests -v       # test
python scraper/scrape.py --out data           # aggiornamento completo (~4 minuti)
python scraper/scrape.py --out /tmp/prova --only odeon   # un solo cinema
python -m http.server 8000                    # poi apri http://localhost:8000
```

Per aggiornare a mano da GitHub: scheda **Actions**, workflow **Aggiorna programmazione**, **Run workflow**.

## Formato dei dati

`data/showtimes.json`:

```json
{
  "today": "2026-10-13",
  "cinemas": [{ "id": 174, "name": "Odeon", "short": "Odeon", "address": "Via Mascarella, 3", "url": "...", "active": true }],
  "films":   [{ "idf": "22259", "title": "L'Estranea", "genres": ["Drammatico", "Thriller"], "duration": 115,
                "release_date": "2026-10-08", "poster": "...", "scheda_url": "...", "trailer_url": "..." }],
  "shows":   [{ "film": "22259", "cinema": 174, "date": "2026-10-13", "time": "16:15", "sala": "Odeon A",
                "vo": false, "tags": [], "price": 8.0, "url": "https://..." }]
}
```

`price` c'è solo per gli spettacoli di oggi. `vo` è dedotto dalla sala e, se un cinema alterna doppiato e originale, dall'orario di oggi: per i giorni futuri resta una stima.

## Limiti noti

- Dipende dall'HTML di comingsoon.it: se cambia il layout, lo scraper si ferma e i test lo segnalano. I dati vecchi restano online.
- I cinema pubblicano spesso solo 2-3 giorni alla volta: il resto della settimana compare quando lo caricano loro, di solito il mercoledì.
- Locandine e orari sono di ComingSoon.it e dei cinema. Progetto personale, non commerciale.
