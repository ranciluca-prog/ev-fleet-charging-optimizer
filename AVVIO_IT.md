# EV Fleet Charging Optimizer - v3: avvio rapido

## Installazione / aggiornamento in VS Code

1. Estrai il file ZIP in una **nuova cartella**. Non mescolare i file con la versione precedente.
2. Apri VS Code e seleziona **File > Open Folder** sulla nuova cartella.
3. Seleziona **Terminal > New Terminal** (non una cella Jupyter).
4. Su Windows esegui i comandi, uno alla volta:

```powershell
py -m pip install -r requirements.txt
py -m unittest discover -v
py -m streamlit run app.py
```

Se `py` non viene riconosciuto, sostituiscilo con `python`.

Il browser apre di norma http://localhost:8501.

## Cosa provare

1. Carica **Standard fleet** con il pulsante **Load example**.
2. Nella tabella EV modifica **SoC (%)** e verifica la terza colonna **Available energy (kWh)**.
3. Premi **Run optimization** e osserva la matrice viaggio-veicolo e la ricarica di riferimento dalle 18:00.
4. Controlla il grafico della ricarica ottimizzata: ogni segmento colorato include il nome dell'EV in bianco.
5. Nella sezione **Cost versus environmental impact**, confronta il costo minimo e le emissioni minime con i punti aggiuntivi soggetti a limiti CO2.
6. Prova **Carbon-constrained fleet** e le esportazioni CSV/JSON.

## Come vengono calcolati gli scenari aggiuntivi CO2

La regola adottata e' **+4 kg CO2e a ogni passo**, partendo da `ceil(emissioni_minime)`. Con benchmark 13,7 kg e 27,62 kg: 14 + 4 = **18**, poi **22**, poi **26**. **30** e' escluso perche' supera 27,62. I numeri 16 e 24 citati nell'esempio iniziale non rispettano l'incremento +4.

## Come viene calcolata la ricarica dalle 18:00

Usa gli **stessi viaggi assegnati** del piano selezionato per un confronto equo della sola strategia di ricarica. Le colonnine cominciano dalle 18:00, dando priorita' ai veicoli nell'ordine della tabella (EV01, EV02, ...), senza aspettare intenzionalmente ore piu' economiche. Vengono rispettati il numero di colonnine, la potenza per colonnina e il limite del deposito. Ogni EV riceve solo l'energia necessaria per il viaggio con riserva. Se il programma non riesce a terminare, viene segnalato **INCOMPLETE**: i totali parziali non vanno confrontati con una soluzione completa.

## Prima di presentare l'app

Esegui tutti i test nel tuo ambiente Windows, verifica la dashboard nel browser e pubblica i file su GitHub (non lo ZIP), poi collegali a Streamlit Community Cloud. I dati di esempio sono sintetici, non prezzi reali.
