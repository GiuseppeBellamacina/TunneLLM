# TunneLLM

Usa un modello LLM hostato su un server remoto (Ollama) come se fosse il tuo Ollama locale. Pensato per server raggiungibili **solo via SSH** (senza rete tradizionale). VS Code Copilot si connette al proxy locale che inoltra tutto al server remoto tramite tunnel SSH.

## Architettura

```
[VS Code Copilot / qualsiasi client Ollama]
        │  http://localhost:11434 (Ollama API)
        ▼
[Local: FastAPI Proxy (porta 11434)]
        │  httpx → localhost:11435
        ▼
[SSH Tunnel (porta 11435 → remote:11434)]
        │  sshtunnel / paramiko
        ▼
[Remote: Ollama (porta 11434)]
        │  GPU
        ▼
[Modello: qwen2.5:14b (o qualsiasi altro)]
```

## Setup

### 1. Server remoto (GPU) — Installazione Ollama

#### Con internet sul server

```bash
scp -r remote/ user@server:~/ollama-server/
ssh user@server
cd ~/ollama-server
bash setup.sh
ollama pull qwen2.5:14b
```

#### Senza internet (solo SSH)

Dal tuo PC locale:

```bash
# 1. Scarica il binario di Ollama
curl -fsSL https://ollama.com/download/ollama-linux-amd64.tgz -o ollama.tgz

# 2. Trasferisci via SCP
scp ollama.tgz user@server:~/
scp -r remote/ user@server:~/ollama-server/

# 3. Installa sul server
ssh user@server
cd ~/ollama-server
OLLAMA_TGZ=~/ollama.tgz bash setup.sh
```

#### Trasferire un modello offline

Dal tuo PC locale (con Ollama installato):

```bash
# Scarica il modello localmente
ollama pull qwen2.5:14b

# Trasferisci al server
cd local
.\transfer_model.ps1 -SshTarget "user@server"
```

### 2. Avviare Ollama sul server

```bash
ssh user@server
cd ~/ollama-server
bash start_server.sh
# oppure con un modello diverso:
MODEL=llama3:8b bash start_server.sh
```

### 3. Macchina locale

```bash
cd local/
pip install -r requirements.txt
cp ../.env.example .env   # se presente
# Edita .env con i dati SSH del tuo server
```

Verifica che il tunnel SSH funzioni:

```bash
ssh -N -L 11435:127.0.0.1:11434 user@server
# In un altro terminale:
curl http://localhost:11435/api/tags
```

Se funziona, avvia il proxy:

```bash
cd local/
python main.py
```

> **Nota:** Se hai Ollama locale in esecuzione sulla porta 11434, fermalo prima (`ollama stop` o `systemctl stop ollama`) oppure cambia `LOCAL_PORT` nel `.env`.

### 4. VS Code — Copilot

In VS Code `settings.json`:

```json
{
  "github.copilot.chat.models": [
    {
      "family": "gpt-4o",
      "id": "qwen2.5:14b",
      "name": "Qwen2.5-14B (remote via TunneLLM)",
      "url": "http://localhost:11434",
      "isDefault": false
    }
  ]
}
```

Oppure, se Copilot supporta provider Ollama:

```json
{
  "github.copilot.chat.models.ollama.url": "http://localhost:11434"
}
```

## Endpoints

Il proxy inoltra tutte le richieste Ollama al server remoto:

| Endpoint               | Metodo | Descrizione                     |
| ---------------------- | ------ | ------------------------------- |
| `/`                    | GET    | "Ollama is running"             |
| `/health`              | GET    | Stato tunnel SSH + Ollama       |
| `/api/tags`            | GET    | Lista modelli (= `ollama list`) |
| `/api/chat`            | POST   | Chat completions                |
| `/api/generate`        | POST   | Text generation                 |
| `/api/embeddings`      | POST   | Embeddings                      |
| `/api/show`            | POST   | Info modello                    |
| `/api/ps`              | GET    | Modelli in esecuzione           |
| `/v1/chat/completions` | POST   | OpenAI-compatible chat          |
| `/v1/models`           | GET    | OpenAI-compatible model list    |

## Configurazione

Tutte le variabili sono in `.env`. Override via environment variables.

| Variabile      | Default         | Descrizione                      |
| -------------- | --------------- | -------------------------------- |
| `SSH_HOST`     | `localhost`     | Hostname del server GPU          |
| `SSH_PORT`     | `22`            | Porta SSH                        |
| `SSH_USER`     | `root`          | Username SSH                     |
| `SSH_KEY_PATH` | `~/.ssh/id_rsa` | Path alla chiave privata SSH     |
| `LOCAL_PORT`   | `11434`         | Porta del proxy (= porta Ollama) |
| `TUNNEL_PORT`  | `11435`         | Porta interna del tunnel SSH     |
| `REMOTE_PORT`  | `11434`         | Porta Ollama sul server remoto   |
| `MODEL_NAME`   | `qwen2.5:14b`   | Nome modello                     |

## Troubleshooting

- **`/health` dice `tunnel: down`:** Verifica SSH credentials in `.env` e che il server sia raggiungibile via SSH
- **`/health` dice `ollama: down`:** Ollama non è avviato sul server. SSH nel server e controlla `bash start_server.sh`
- **Conflitto porta 11434:** Se hai Ollama locale, fermalo o cambia `LOCAL_PORT`
- **Timeout sulle risposte:** Il modello potrebbe essere in fase di caricamento (prima richiesta). Aspetta ~30s
- **Modello non trovato:** Assicurati che il modello sia stato pullato/trasferito sul server: `ssh user@server "ollama list"`
