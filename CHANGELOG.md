# Changelog

## 2026-10-13, uscite della settimana dopo

- Lo scraper legge il calendario uscite di comingsoon (settimana corrente e successiva) e scrive `data/upcoming.json`; se la pagina non risponde, il giro va avanti con un avviso
- Nuova sezione in fondo alla mail del giovedì: "In uscita dal [giovedì successivo]", divisa per giorno, con genere, regia e i cinema di Bologna che hanno già il film in programma
- Task del giovedì aggiornato per scaricare anche `upcoming.json`
- 5 test in più (30 in tutto), con la pagina reale del calendario come fixture

## 2026-10-13, mail del giovedì

- `scraper/weekly_email.py`: genera oggetto, HTML e testo della mail settimanale, con i film nuovi separati da quelli già in sala
- Task programmato di Claude: ogni giovedì scarica la mail da GitHub e la invia con Gmail a surfab@gmail.com
- V.O. più precisa: se un cinema alterna doppiato e originale nella stessa sala, per i giorni futuri vale l'orario di oggi
- 8 test in più (25 in tutto)

## 2026-10-13, prima versione

- Scraper per i 21 cinema di Bologna città su comingsoon.it: film, sale, orari della settimana, prezzi di oggi, link d'acquisto, versione originale
- Controllo di salute: con meno di 50 spettacoli o meno di metà cinema letti non sovrascrive i dati
- Avviso automatico se comingsoon elenca un cinema nuovo o ne toglie uno
- 17 test sul parser con pagine reali salvate (Odeon, Lumière, The Space, Antoniano)
- Sito statico: vista per film e per cinema, novità della settimana, filtri V.O., fascia oraria, ricerca e "miei cinema"
- Aggiornamento automatico con GitHub Actions verso le 7 e le 16
