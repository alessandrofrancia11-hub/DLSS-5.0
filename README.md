# DLSS 5 Dashboard

Launcher locale per Windows: trova i giochi installati, installa DLSS 5 (community) gioco per gioco,
regola tutti i parametri modificabili e avvia il gioco con DLSS 5 **acceso o spento**.

Solo libreria standard di Python: niente da installare oltre a Python 3.10+.

## Avvio

1. Installa Python da <https://www.python.org/downloads/> (spunta "Add python.exe to PATH").
2. Scarica questo repository (Code → Download ZIP) ed estrailo.
3. Doppio clic su `avvia_dashboard.bat`: si apre il browser su `http://127.0.0.1:8765`.

Comandi utili (da terminale nella cartella del progetto):

```
py -m dlss5_dashboard sysinfo      # info di sistema (GPU, driver, CPU, RAM) e cosa puoi fare con DLSS 5
py -m dlss5_dashboard games        # giochi trovati
py -m dlss5_dashboard serve --port 8765
```

## Cosa fa

| Sezione | Dettagli |
|---|---|
| **Sistema** | GPU, driver, VRAM (via `nvidia-smi`), CPU, RAM, Windows. Dice cosa supporta la tua scheda. |
| **Giochi** | Scansione delle librerie Steam e **Xbox / PC Game Pass** (cartelle `XboxGames`) + aggiunta manuale di qualsiasi `.exe`. Rileva architettura, API grafica, DLSS nativo e anti-cheat. |
| **Installa** | Route **DLSS5-Feeder** per i giochi senza DLSS (es. Euro Truck Simulator 2) oppure **OptiScaler DLSS-NR** per i giochi con DLSS. Backup automatico prima di toccare qualunque file. |
| **Parametri** | Feeder (`dlss5-feed.cfg`): on/off, modalità, preset, risoluzione di lavoro neurale, HDR, depth, motion vector. OptiScaler (`OptiScaler.ini`): preset DLSS, rapporti di scala, output scaling, nitidezza, tutti i controlli DLSS 5 Neural Rendering, sblocco Multi Frame Generation RTX 40. |
| **Avvio** | Interruttore DLSS 5 ON/OFF + parametri di avvio. OFF rinomina le DLL iniettate in `*.dlss5off`, quindi il gioco parte originale. |
| **Verifica DLSS 5** | Legge `ReShade.log` dopo una partita: stato del modello neurale (ENGAGED o no), costo in ms, FPS con/senza. |
| **Tasto confronto** | Un tasto in gioco (es. Bloc Scorr) che spegne e riaccende all'istante DLSS 5 per confrontare l'immagine. |
| **Ripristina** | Toglie tutto ciò che l'installazione ha aggiunto e rimette i file originali. |

Tutti i componenti vengono scaricati **dai rispettivi autori** al momento dell'installazione: nulla è incluso qui.

- DLSS5-Feeder: <https://github.com/jlrouzies-fr/DLSS5-Feeder> (installer PowerShell ufficiale, si apre in una finestra dove rispondi alle domande)
- OptiScaler DLSS-NR: <https://github.com/wilsjo2/OptiScaler-DLSSNR-PreSR-Multipass>, OptiScaler: <https://github.com/optiscaler/OptiScaler>

## RTX 4070: cosa aspettarsi (onestamente)

- **DLSS 5 ufficiale = solo RTX 50.** NVIDIA ha confermato le RTX 40 senza data.
- Sulle RTX 40 il passaggio neurale dipende dalla combinazione di DLL, add-on e driver della community.
  Testato: **RTX 4070 SUPER, driver 617.14, ETS2 a 1440p → neurale ENGAGED, ~11,5 ms per frame, 60 fps**.
  In 4K costa circa 2,25 volte tanto: abbassa la "Risoluzione di lavoro neurale" o la risoluzione.
- Usa **Verifica DLSS 5** dopo una partita per sapere se il modello ha lavorato davvero.
- Anche senza quella DLL hai benefici reali: **DLAA** nei giochi senza DLSS (Feeder), preset transformer e
  **Frame Generation 3x/4x** sui giochi con DLSS-FG (build `+ sblocco MFG RTX 40`).

## Giochi Xbox / PC Game Pass

- La dashboard trova i giochi nelle cartelle `XboxGames` di ogni disco (quella scelta nell'app Xbox).
- Usa l'eseguibile vero del gioco, non `gamelaunchhelper.exe`, e lo avvia tramite Windows come fa l'app Xbox.
- I giochi rimasti in `C:\Program Files\WindowsApps` sono protetti e non si possono modificare: spostali
  dall'app Xbox (Gestisci → File) in una cartella `XboxGames`.
- Attenzione ai giochi Game Pass con anti-cheat (es. Forza Horizon, titoli online): rischio ban.

## Euro Truck Simulator 2

- Niente DLSS nativo → route **DLSS5-Feeder** (ReShade + motion vector stimati + DLAA + add-on neurale).
- Renderer DirectX 11 (quello predefinito).
- **Non usarlo con TruckersMP** (multiplayer).
- In gioco: `HOME` apre ReShade. Le impostazioni della dashboard valgono dal prossimo avvio.
- Se qualcosa non va: nella cartella `bin\win_x64` trovi `ReShade.log` e `dlss5-feed.log`, ed esegui lo script
  `Verify-DLSS5Feeder.ps1` del Feeder.

## Sicurezza

- Il server ascolta solo su `127.0.0.1` e richiede un token per ogni chiamata: altri siti aperti nel browser non possono pilotarlo.
- Esistono **copie malevole** di questi progetti (siti fake, ".exe 1-click"). La dashboard scarica solo dagli URL ufficiali qui sopra.
- Non usare iniezioni di DLL in giochi con anti-cheat: rischi il ban. La dashboard li segnala.

## Dati

Stato, backup e download stanno in `%APPDATA%\DLSS5-Dashboard`.

## Sviluppo

```
python -m unittest discover -s tests
```
