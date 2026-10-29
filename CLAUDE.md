# Cinema a Bologna

Sito statico con film, cinema e orari dei 21 cinema di Bologna città.
Uno scraper Python legge comingsoon.it, GitHub Actions lo lancia due volte al giorno, GitHub Pages pubblica.
Sito: https://surfab.github.io/cinema-bologna/ · Progetto personale di Fabri, non commerciale.

## Comandi

```bash
pip install -r scraper/requirements.txt
python -m unittest discover -s tests -v                  # 31 test, ~1 secondo, niente rete
python scraper/scrape.py --out /tmp/prova --only odeon   # un cinema solo, per provare
python scraper/scrape.py --out data                      # giro completo, ~150 richieste, 2-4 minuti
python scraper/weekly_email.py --data data/showtimes.json --meta data/meta.json \
  --upcoming data/upcoming.json --out /tmp/mail --today 2026-10-15
python -m http.server 8000                               # sito su http://localhost:8000
```

## Dove sta cosa

- `scraper/scrape.py`: parser di comingsoon (pagina cinema, pagina "tutte le date", calendario uscite) e scrittura dei JSON
- `scraper/cinemas.json`: i 21 cinema (id comingsoon, slug, nome breve, indirizzo)
- `scraper/weekly_email.py`: mail del giovedì (oggetto, HTML, testo, `summary.json`)
- `index.html`, `assets/app.js`, `assets/style.css`: il sito, JavaScript senza framework né build
- `data/`: tutto generato dal workflow
- `tests/fixtures/`: pagine reali di comingsoon salvate, base dei test del parser
- `.github/workflows/update.yml`: cron, test, scraping, mail del giovedì, commit dei dati

## Regole del progetto

- **Non modificare a mano i file in `data/`.** Li scrive il bot. Se servono dati di prova, usa una cartella in `/tmp`.
- Il bot committa su `main` due volte al giorno: fai sempre `git pull --rebase` prima di lavorare e prima di pushare.
- Un push su `main` che tocca `scraper/`, `tests/` o il workflow fa partire uno scraping completo e un commit dei dati.
- Il controllo di salute (minimo 50 spettacoli e metà dei cinema letti) evita di pubblicare dati vuoti. Non abbassarlo e non aggirarlo.
- Rispetta comingsoon: lascia il ritardo di 1,5 secondi tra le richieste e lo user agent che rimanda al repo.
- Se comingsoon cambia l'HTML: salva la nuova pagina in `tests/fixtures/`, scrivi prima il test che fallisce, poi correggi il parser.
- `weekly_email.py` usa solo la libreria standard.
- La mail passa dal connettore Gmail, che toglie `<style>`, gli attributi `class` e la forma breve `background:`. Quindi solo stili inline sui tag, `background-color` esplicito, layout a tabelle, HTML sotto i 102 KB (la settimana del 29 ottobre 2026 era già a 88 KB: margine stretto).
- Un task programmato di Claude, il giovedì alle 10:45, scarica `data/email/` e spedisce la mail controllando `summary.json`. Non rinominare quei file né cambiare le chiavi di `summary.json` senza dirlo a Fabri: il task si romperebbe.
- I cron del workflow sono in UTC. Gli orari di Bologna cambiano con l'ora legale.
- Sito: niente framework, niente dipendenze npm. Colori come token in `:root` con la variante scura, `localStorage` solo tramite `load()`/`save()` che hanno già il try/catch.

## Convenzioni

- Tutto in italiano: commenti, testi del sito, messaggi di commit, CHANGELOG.
- Commit brevi e descrittivi, sullo stile di quelli esistenti (es. "Aggiunge licenza MIT", "Mail del giovedi': sezione con le uscite della settimana dopo"). Il prefisso `dati:` è riservato al bot.
- Ogni modifica che cambia il comportamento aggiorna `CHANGELOG.md` (sezione `## AAAA-MM-GG, titolo` con punti elenco, conteggio dei test aggiornato) e, se serve, il README.
- Lancia i test prima di ogni commit.

## Come lavorare con Fabri

- Rispondi in italiano, frasi brevi, niente giri di parole.
- Prima di toccare più di due file, spiega il piano in poche righe e aspetta l'ok.
- Chiedi conferma prima di: pushare su `main`, cambiare i cron, cambiare il formato di `data/` o di `data/email/`.
- Non cancellare file: spostali e dillo.
- Quando chiudi un lavoro, spiega in due righe cosa è cambiato e come verificarlo dal sito.
