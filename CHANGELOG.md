# Changelog

## 2026-10-29, niente orari di ieri nel giro notturno

- La pagina del cinema su comingsoon non scrive la data e, di notte, mostra ancora la programmazione del giorno prima. Il giro del 29/10 alle 03:24 aveva registrato come giovedì 62 spettacoli di mercoledì (su 116), finiti anche nella mail
- Prima delle 6 (ora di Roma) lo scraper usa solo le pagine con le date: niente orari presi solo dalla pagina del cinema, niente prezzi di "oggi". La pagina del cinema serve ancora a capire se uno spettacolo è in V.O.
- Effetto collaterale voluto: nella mail del giovedì mancano gli spettacoli di oggi senza vendita online (per esempio Jolly, Galliera, Modernissimo, Bellinzona). Il giro delle 6:17 li rimette sul sito
- 6 test in più (37 in tutto), con il caso reale del Rialto

## 2026-10-15, mail leggibile in Gmail

- Il connettore Gmail toglie `<style>`, gli attributi `class` e la forma abbreviata `background:`: la mail arrivava senza grafica
- `weekly_email.py` ora scrive gli stili direttamente sui tag e impagina giorni e orari in tabelle
- Orari in grassetto colorato, V.O. con sfondo verde; HTML da 135 a 75 KB per restare sotto il taglio di Gmail (102 KB)
- 1 test in più (31 in tutto)

## 2026-10-15, mail generata da GitHub Actions

- Il giovedì (e a ogni lancio manuale) il workflow genera la mail dopo lo scraping e la salva in `data/email/` con un `summary.json`
- Il task di Claude non esegue più lo script: scarica i file pronti e li spedisce. L'ambiente cloud bloccava l'esecuzione di codice scaricato
- Se la generazione fallisce, gli orari vengono salvati lo stesso

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
