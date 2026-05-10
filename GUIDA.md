# TunneLLM — Guida Passo per Passo

Questa guida ti spiega come usare un modello LLM (es. Qwen, Llama, ecc.) su un **server remoto con GPU** direttamente da **VS Code Copilot** sul tuo PC Windows, anche se il server **non ha accesso a internet** e puoi raggiungerlo **solo via SSH**.

---

## Cosa fa TunneLLM

```
Il tuo PC (Windows)                         Server remoto (Linux + GPU)
┌─────────────────────┐                     ┌──────────────────────┐
│  VS Code + Copilot   │                     │  Ollama + Modello    │
│         │            │                     │    (porta 11434)     │
│         ▼            │     SSH tunnel      │         ▲            │
│  Proxy locale  ──────┼─────────────────────┼─────────┘            │
│  (porta 11434)       │                     │                      │
└─────────────────────┘                     └──────────────────────┘
```

VS Code Copilot parla con il proxy locale sulla porta 11434 (la stessa porta di Ollama). Il proxy inoltra tutto al server remoto attraverso un tunnel SSH. Per Copilot, è come se Ollama girasse sul tuo PC.

---

## Prerequisiti

- **Windows 10/11** con PowerShell
- **Python 3.10+** installato sul tuo PC ([python.org](https://python.org))
- **Accesso SSH** al server remoto (devi poter fare `ssh user@server`)
- **VS Code** con l'estensione **GitHub Copilot**
- Il server remoto deve avere **Linux** e una **GPU** (NVIDIA o AMD)

---

## Passo 1: Clona il progetto

Apri un terminale PowerShell e clona il repository:

```powershell
git clone https://github.com/GiuseppeBellamacina/TunneLLM.git
cd TunneLLM
```

---

## Passo 2: Installa Ollama sul tuo PC (Windows)

Ti serve Ollama locale per scaricare i modelli prima di trasferirli al server.

1. Vai su [ollama.com/download](https://ollama.com/download) e scarica la versione Windows
2. Installa normalmente
3. Verifica che funzioni aprendo un terminale:

```powershell
ollama --version
```

Dovresti vedere qualcosa tipo `ollama version 0.x.x`.

---

## Passo 3: Scarica il modello sul tuo PC

Scarica il modello che vuoi usare. Esempio con Qwen 2.5 14B:

```powershell
ollama pull qwen2.5:14b
```

> **Nota:** Il download può richiedere tempo (il modello pesa diversi GB).
> Puoi scegliere qualsiasi modello supportato da Ollama. Vedi la lista su [ollama.com/library](https://ollama.com/library).
> Modelli più piccoli (es. `qwen2.5:7b`, `llama3:8b`) sono più veloci da trasferire e richiedono meno VRAM.

---

## Passo 4: Installa Ollama sul server remoto

Il server non ha internet, quindi scarichiamo tutto dal nostro PC e lo trasferiamo via SSH.

### 4a. Verifica che riesci a connetterti al server

```powershell
ssh user@server
```

Sostituisci `user` col tuo username e `server` con l'hostname o IP del server. Se ti chiede la password e riesci ad entrare, sei a posto. Esci con `exit`.

### 4b. Lancia lo script di deploy

Lo script `download_and_deploy.ps1` fa tutto automaticamente:

- Scarica il binario di Ollama per Linux
- Lo trasferisce al server via SCP
- Lo installa sul server

```powershell
cd local
.\download_and_deploy.ps1 -SshTarget "user@server"
```

> **Se il server usa una porta SSH diversa da 22:**
>
> ```powershell
> .\download_and_deploy.ps1 -SshTarget "user@server" -SshPort 2222
> ```

> **Se il server ha una GPU AMD (invece di NVIDIA):**
>
> ```powershell
> .\download_and_deploy.ps1 -SshTarget "user@server" -IncludeROCm
> ```

> **Se il server ha architettura ARM (es. Raspberry Pi, Jetson):**
>
> ```powershell
> .\download_and_deploy.ps1 -SshTarget "user@server" -Arch arm64
> ```

Aspetta che finisca. Dovresti vedere `Installation complete!` alla fine.

### 4c. Se preferisci fare tutto manualmente

Se lo script non funziona o preferisci fare a mano:

```powershell
# 1. Scarica l'archivio di Ollama per Linux
Invoke-WebRequest -Uri "https://ollama.com/download/ollama-linux-amd64.tgz" -OutFile "ollama-linux-amd64.tgz"

# 2. Crea la cartella sul server
ssh user@server "mkdir -p ~/ollama-server"

# 3. Trasferisci l'archivio
scp ollama-linux-amd64.tgz user@server:~/ollama-server/

# 4. Trasferisci gli script di setup
scp -r ..\remote\* user@server:~/ollama-server/

# 5. Connettiti al server e installa
ssh user@server
cd ~/ollama-server
OLLAMA_ARCHIVE=~/ollama-server/ollama-linux-amd64.tgz bash setup.sh
exit
```

---

## Passo 5: Trasferisci il modello al server

Il modello che hai scaricato al Passo 3 va copiato sul server. Usa Git Bash o WSL per eseguire lo script bash (PowerShell non esegue script bash nativamente):

```powershell
cd C:\Users\TUO_UTENTE\Codici\TunneLLM\local
.\transfer_model.ps1 -SshTarget "user@server"
```

> Se il server usa una porta SSH diversa:
>
> ```powershell
> .\transfer_model.ps1 -SshTarget "user@server" -SshPort 2222
> ```

> **Nota:** Questo trasferimento può richiedere molto tempo per modelli grandi (10+ GB). Assicurati di avere una connessione SSH stabile.

### Alternativa: Scaricare un modello GGUF da HuggingFace

Se il server **ha accesso a internet** (es. può raggiungere huggingface.co), puoi scaricare un modello GGUF direttamente sul server senza trasferirlo dal tuo PC.

1. **Trova il modello su HuggingFace** — cerca un file `.gguf` (es. [Qwen3-Coder-30B-A3B](https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF))

2. **Scaricalo direttamente sul server:**

```bash
ssh user@server
cd ~/ollama-server

# Usa il link "resolve" (non "blob") per il download diretto
wget https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/resolve/main/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf
```

> **Se il server non ha accesso a internet**, scarica dal tuo PC e trasferisci via SCP:
>
> ```powershell
> # Dal tuo PC Windows
> Invoke-WebRequest -Uri "https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/resolve/main/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf" -OutFile "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
> scp Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf user@server:~/ollama-server/
> ```

3. **Crea un Modelfile** che dice a Ollama di usare quel GGUF:

```bash
cat > Modelfile <<'EOF'
FROM ./Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf
EOF
```

4. **Importa il modello in Ollama** (serve il server attivo):

```bash
# Avvia Ollama temporaneamente
ollama serve &
sleep 2

# Importa con il nome che vuoi
ollama create qwen3-coder:30b -f Modelfile

# Verifica
ollama list

# Ferma il server
kill %1
```

> Per importare con il Modelfile personalizzato (con template e tool calling), usa quello dalla cartella `remote/` del progetto (già presente in `~/ollama-server/` dopo l'`scp`):
>
> ```bash
> ollama create qwen3-coder:30b -f ~/ollama-server/Modelfile
> ```

5. **Pulizia** — dopo il `create`, Ollama copia il GGUF nei suoi blob. Puoi eliminare il file originale:

```bash
rm Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf Modelfile
```

> **Nota:** Il nome che dai al `create` (es. `qwen3-coder:30b`) è quello che userai in `MODEL_NAME` nel `.env`.

---

## Passo 6: Avvia Ollama sul server

### Caso A: Server standalone (senza SLURM)

Se il server ti dà accesso diretto alla GPU:

```powershell
ssh user@server
cd ~/ollama-server
bash start_server.sh
```

> **Importante:** Lascia questo terminale aperto! Se lo chiudi, Ollama si ferma.
> Per farlo girare in background puoi usare `screen` o `tmux`:
>
> ```bash
> screen -S ollama
> bash start_server.sh
> # Premi Ctrl+A poi D per staccarti dalla sessione
> # Per riattaccarti: screen -r ollama
> ```

### Caso B: Cluster con SLURM

Su un cluster SLURM le GPU sono disponibili **solo dentro un job**. Non puoi avviare Ollama direttamente sul login node.

#### 6b.0. Trasferisci gli script sul cluster

Dal tuo PC, copia la cartella `remote/` sul cluster (contiene `setup.sh`, `start_server.sh`, `ollama_job.sh`):

```powershell
# Crea la cartella sul cluster
ssh user@server "mkdir -p ~/ollama-server"

# Copia tutti gli script
scp -r remote\* user@server:~/ollama-server/
```

> Se il server usa una porta SSH diversa:
>
> ```powershell
> ssh -p 2222 user@server "mkdir -p ~/ollama-server"
> scp -P 2222 -r remote\* user@server:~/ollama-server/
> ```

Dopo questo comando, sul cluster avrai:

```
~/ollama-server/
├── setup.sh            # installazione Ollama
├── start_server.sh     # avvio standalone
└── ollama_job.sh       # avvio via SLURM
```

#### 6b.1. Modifica le direttive SLURM

Prima di lanciare il job, apri `ollama_job.sh` e decommenta/adatta le righe con il tuo account:

```bash
#SBATCH --account=dl-course-q2        # ← il tuo account
#SBATCH --partition=dl-course-q2      # ← la tua partizione
#SBATCH --qos=gpu-xlarge              # ← QoS con abbastanza VRAM
```

> **Come trovo il mio account/partizione/QoS?**
>
> ```bash
> ssh user@server
> sacctmgr show associations user=$USER format=Account,Partition,QOS -P
> ```

> **Quale QoS scegliere?**
>
> | QoS        | VRAM   | Tempo max | Per quale modello      |
> | ---------- | ------ | --------- | ---------------------- |
> | gpu-medium | 5.5 GB | 6h        | Modelli piccoli (1-3B) |
> | gpu-large  | 11 GB  | 12h       | Modelli medi (7-8B)    |
> | gpu-xlarge | 22 GB  | 12h       | Modelli grandi (14B+)  |

#### 6b.2. Lancia il job

```bash
ssh user@server
cd ~/ollama-server
sbatch ollama_job.sh
```

Oppure con un modello specifico:

```bash
sbatch ollama_job.sh qwen2.5:7b
```

#### 6b.3. Trova il nodo assegnato

Dopo che il job parte, controlla su quale nodo è finito:

```bash
# Opzione 1: dal file generato automaticamente
cat ~/ollama-server/node_info.txt

# Opzione 2: da squeue
squeue --me
```

Il file `node_info.txt` contiene qualcosa tipo:

```
NODE=gnode10
PORT=11434
MODEL=qwen2.5:14b
JOB_ID=12345
```

**Prendi nota del valore di `NODE`** (es. `gnode10`) — ti serve al passo successivo.

#### 6b.4. Configura REMOTE_HOST

Nel file `.env` sul tuo PC locale, imposta `REMOTE_HOST` con il nome del nodo:

```env
REMOTE_HOST=gnode10
```

> **Nota:** Ogni volta che lanci un nuovo job SLURM, il nodo potrebbe cambiare. Dovrai aggiornare `REMOTE_HOST` nel `.env` e riavviare il proxy locale.

#### 6b.5. Monitora e gestisci il job

```bash
# Vedi i log
tail -f ollama-<JOB_ID>.log

# Controlla stato
squeue --me

# Ferma il job
scancel <JOB_ID>
```

> **Se vuoi usare un modello diverso:**
>
> ```bash
> sbatch ollama_job.sh llama3:8b
> ```

---

## Passo 7: Configura il proxy locale

### 7a. Installa le dipendenze Python

Apri un **nuovo terminale PowerShell** sul tuo PC:

```powershell
cd C:\Users\TUO_UTENTE\Codici\TunneLLM\local
pip install -r requirements.txt
```

### 7b. Crea il file di configurazione

```powershell
copy ..\.env.example .env
```

### 7c. Modifica il file `.env`

Apri il file `local/.env` con un editor di testo (o VS Code) e modifica i valori SSH:

```env
# Metti l'hostname o IP del tuo server
SSH_HOST=server-hostname-o-ip

# Porta SSH (di solito 22)
SSH_PORT=22

# Il tuo username SSH
SSH_USER=tuo-username

# Path alla tua chiave SSH privata (di solito questa)
SSH_KEY_PATH=~/.ssh/id_rsa

# Se la chiave è protetta da password, decommentare:
# SSH_PASSWORD=la-tua-password

# Queste di solito non vanno cambiate
# Per cluster SLURM: imposta REMOTE_HOST al nodo GPU (es. gnode10)
#   → lo trovi in ~/ollama-server/node_info.txt dopo sbatch
REMOTE_HOST=127.0.0.1
REMOTE_PORT=11434
LOCAL_HOST=127.0.0.1
LOCAL_PORT=11434
TUNNEL_PORT=11435

# Il modello che hai installato sul server
MODEL_NAME=qwen2.5:14b
```

### 7d. Ferma Ollama locale (se attivo)

Se hai Ollama in esecuzione sul tuo PC Windows, **fermalo** perché usa la stessa porta (11434):

```powershell
# Controlla se è in esecuzione
Get-Process ollama -ErrorAction SilentlyContinue

# Se lo è, fermalo
ollama stop
# oppure chiudi l'app Ollama dalla system tray (icona in basso a destra)
```

### 7e. Avvia il proxy

```powershell
cd C:\Users\TUO_UTENTE\Codici\TunneLLM\local
python main.py
```

Dovresti vedere:

```
Starting TunneLLM proxy on 127.0.0.1:11434
  SSH tunnel port: 11435 → 127.0.0.1:11434
  SSH target: tuo-username@server-hostname:22
  Model: qwen2.5:14b
  VS Code Copilot → http://127.0.0.1:11434
```

> **Lascia questo terminale aperto!** Il proxy deve restare in esecuzione.

### 7f. Verifica che funzioni

Apri un **altro terminale** e testa:

```powershell
# Controlla lo stato
curl http://localhost:11434/health

# Dovresti vedere qualcosa tipo:
# {"tunnel":"up","ollama":"up","model":"qwen2.5:14b"}
```

Se vedi `"tunnel":"up"` e `"ollama":"up"`, tutto funziona!

---

## Passo 8: Configura VS Code Copilot

### 8a. Apri le impostazioni di VS Code

1. Apri **VS Code**
2. Premi `Ctrl + Shift + P`
3. Digita `Preferences: Open User Settings (JSON)` e premi Invio

### 8b. Aggiungi il modello

Aggiungi questo blocco nel JSON delle impostazioni:

```json
{
  "github.copilot.chat.models": [
    {
      "family": "gpt-4o",
      "id": "qwen2.5:14b",
      "name": "Qwen2.5-14B (TunneLLM)",
      "url": "http://localhost:11434",
      "isDefault": false
    }
  ]
}
```

> **Nota:** Cambia `id` e `name` se usi un modello diverso.
> Il campo `family` serve a Copilot per sapere come formattare le richieste — `gpt-4o` funziona come formato generico.

### 8c. Usa il modello

1. Apri la **chat di Copilot** (`Ctrl + Shift + I` o dal pannello laterale)
2. In alto nella chat, clicca sul nome del modello (es. "GPT-4o")
3. Dovresti vedere **"Qwen2.5-14B (TunneLLM)"** nella lista
4. Selezionalo e inizia a chattare!

---

## Riepilogo: Cosa deve essere in esecuzione

Per usare il tutto, devono essere attivi **contemporaneamente**:

### Server standalone (senza SLURM)

| Dove              | Cosa           | Comando                                                        |
| ----------------- | -------------- | -------------------------------------------------------------- |
| **Server remoto** | Ollama         | `ssh user@server "cd ~/ollama-server && bash start_server.sh"` |
| **PC locale**     | Proxy TunneLLM | `cd local && python main.py`                                   |
| **VS Code**       | Copilot Chat   | Seleziona il modello TunneLLM                                  |

### Cluster SLURM

| Dove          | Cosa              | Comando                                                        |
| ------------- | ----------------- | -------------------------------------------------------------- |
| **Cluster**   | Job SLURM         | `ssh user@server "cd ~/ollama-server && sbatch ollama_job.sh"` |
| **PC locale** | `.env` aggiornato | `REMOTE_HOST=gnode10` (il nodo dal job)                        |
| **PC locale** | Proxy TunneLLM    | `cd local && python main.py`                                   |
| **VS Code**   | Copilot Chat      | Seleziona il modello TunneLLM                                  |

---

## Troubleshooting

### "tunnel: down" nel health check

- Verifica che i dati SSH nel file `.env` siano corretti
- Verifica che riesci a fare `ssh user@server` dal tuo PC
- Controlla che la chiave SSH (`SSH_KEY_PATH`) esista e sia corretta

### "ollama: down" nel health check

- Ollama non è in esecuzione sul server
- **Server standalone:** connettiti e avvia `bash start_server.sh`
- **Cluster SLURM:** controlla che il job sia attivo (`squeue --me`) e che `REMOTE_HOST` nel `.env` punti al nodo giusto
- Controlla se Ollama è crashato: `ssh user@server "ps aux | grep ollama"`

### Copilot non mostra il modello

- Verifica che il JSON in `settings.json` sia valido (niente virgole in eccesso)
- Riavvia VS Code dopo aver modificato le impostazioni
- Controlla che il proxy locale sia in esecuzione (`curl http://localhost:11434/health`)

### Errore "Address already in use" avviando il proxy

- Hai Ollama locale in esecuzione sulla porta 11434 → fermalo (vedi Passo 7d)
- Oppure cambia `LOCAL_PORT` nel `.env` (es. `LOCAL_PORT=11435`) e aggiorna l'URL in VS Code di conseguenza

### Timeout o risposte lente

- La prima richiesta dopo l'avvio è lenta perché il modello viene caricato in memoria GPU (~30 secondi)
- Le richieste successive saranno molto più veloci

### Il modello non è trovato sul server

```powershell
ssh user@server "ollama list"
```

Se il modello non appare, devi trasferirlo di nuovo (Passo 5).

---

## Comandi rapidi di riferimento

### Server standalone

```powershell
# === SETUP (una tantum) ===
# Installa Ollama sul server
cd local
.\download_and_deploy.ps1 -SshTarget "user@server"

# Scarica e trasferisci un modello
ollama pull qwen2.5:14b
.\transfer_model.ps1 -SshTarget "user@server"

# === USO QUOTIDIANO ===
# 1. Avvia Ollama sul server (in un terminale)
ssh user@server "cd ~/ollama-server && bash start_server.sh"

# 2. Avvia il proxy locale (in un altro terminale)
cd C:\Users\TUO_UTENTE\Codici\TunneLLM\local
python main.py

# 3. Apri VS Code e usa Copilot con il modello TunneLLM
```

### Cluster SLURM

```powershell
# === SETUP (una tantum) ===
cd local
.\download_and_deploy.ps1 -SshTarget "user@server"
ollama pull qwen2.5:14b
.\transfer_model.ps1 -SshTarget "user@server"

# === USO QUOTIDIANO ===
# 1. Lancia il job SLURM
ssh user@server "cd ~/ollama-server && sbatch ollama_job.sh"

# 2. Trova il nodo assegnato
ssh user@server "cat ~/ollama-server/node_info.txt"
#    → prendi il valore di NODE (es. gnode10)

# 3. Aggiorna REMOTE_HOST nel .env con il nodo
#    REMOTE_HOST=gnode10

# 4. Avvia il proxy locale
cd C:\Users\TUO_UTENTE\Codici\TunneLLM\local
python main.py

# 5. Apri VS Code e usa Copilot

# === FERMARE IL JOB ===
ssh user@server "scancel <JOB_ID>"
```
