# TunneLLM

Usa un modello LLM hostato su un server remoto (Ollama) come se fosse il tuo Ollama locale. Pensato per server raggiungibili **solo via SSH** (senza rete tradizionale). VS Code Copilot si connette al proxy locale che inoltra tutto al server remoto tramite tunnel SSH.

## Features

- **OpenAI-compatible API completa** — `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/models` con formato OpenAI nativo
- **True SSE streaming** — Token-by-token streaming via `text/event-stream`, nessun buffering
- **Auto-reconnect SSH** — Il tunnel si riconnette automaticamente con exponential backoff
- **Retry robusti** — Le richieste fallite vengono riprovate con backoff esponenziale
- **Request queue** — Semaforo per limitare le inferenze concorrenti e proteggere la GPU
- **Metriche real-time** — Tokens/sec, latency, TTFT (first-token latency), token usage via `/metrics`
- **Multi-model** — Nomi modello con `:` (es. `llama3:8b`) vengono passati direttamente a Ollama
- **CORS abilitato** — Funziona con client browser-based (OpenWebUI, Continue, ecc.)
- **Proxy Ollama nativo** — Tutti gli endpoint `/api/*` passano direttamente a Ollama

### Compatibilità client

Grazie all'API OpenAI-compatible, TunneLLM funziona con:

- VS Code Copilot / GitHub Copilot
- Continue (VS Code extension)
- OpenWebUI
- aider
- Cline / Roo Code
- LangChain / LlamaIndex
- Qualsiasi client OpenAI-compatible

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

### OpenAI-compatible (nativi, con SSE streaming e metriche)

| Endpoint               | Metodo | Descrizione                      |
| ---------------------- | ------ | -------------------------------- |
| `/v1/chat/completions` | POST   | Chat completions (SSE streaming) |
| `/v1/completions`      | POST   | Text completions (SSE streaming) |
| `/v1/embeddings`       | POST   | Embeddings                       |
| `/v1/models`           | GET    | Lista modelli (formato OpenAI)   |

### Ollama API (proxy passthrough)

| Endpoint          | Metodo | Descrizione                      |
| ----------------- | ------ | -------------------------------- |
| `/`               | GET    | "Ollama is running"              |
| `/api/tags`       | GET    | Lista modelli (= `ollama list`)  |
| `/api/chat`       | POST   | Chat (formato Ollama)            |
| `/api/generate`   | POST   | Text generation (formato Ollama) |
| `/api/embeddings` | POST   | Embeddings (formato Ollama)      |
| `/api/show`       | POST   | Info modello                     |
| `/api/ps`         | GET    | Modelli in esecuzione            |

### Monitoring

| Endpoint   | Metodo | Descrizione                      |
| ---------- | ------ | -------------------------------- |
| `/health`  | GET    | Stato tunnel + Ollama + metriche |
| `/metrics` | GET    | Metriche dettagliate             |

## Configurazione

Tutte le variabili sono in `.env`. Override via environment variables.

| Variabile                    | Default         | Descrizione                          |
| ---------------------------- | --------------- | ------------------------------------ |
| `SSH_HOST`                   | `localhost`     | Hostname del server GPU              |
| `SSH_PORT`                   | `22`            | Porta SSH                            |
| `SSH_USER`                   | `root`          | Username SSH                         |
| `SSH_KEY_PATH`               | `~/.ssh/id_rsa` | Path alla chiave privata SSH         |
| `SSH_PASSWORD`               | —               | Password SSH (se chiave protetta)    |
| `SSH_KEEPALIVE`              | `10.0`          | Intervallo keepalive SSH (sec)       |
| `LOCAL_PORT`                 | `11434`         | Porta del proxy                      |
| `TUNNEL_PORT`                | `11435`         | Porta interna del tunnel SSH         |
| `REMOTE_HOST`                | `127.0.0.1`     | Host remoto (per SLURM: nodo GPU)    |
| `REMOTE_PORT`                | `11434`         | Porta Ollama sul server remoto       |
| `MODEL_NAME`                 | `qwen3.6:35b`   | Nome modello di default              |
| `MAX_RETRIES`                | `3`             | Tentativi di retry per richiesta     |
| `RETRY_BASE_DELAY`           | `1.0`           | Delay base per backoff (sec)         |
| `MAX_CONCURRENT_INFERENCES`  | `4`             | Max richieste di inferenza in volo   |
| `CONNECT_TIMEOUT`            | `10.0`          | Timeout connessione HTTP (sec)       |
| `READ_TIMEOUT`               | `600.0`         | Timeout lettura HTTP (sec)           |
| `WRITE_TIMEOUT`              | `10.0`          | Timeout scrittura HTTP (sec)         |
| `TUNNEL_CHECK_INTERVAL`      | `5.0`           | Intervallo health check tunnel (sec) |
| `TUNNEL_MAX_RECONNECT_DELAY` | `30.0`          | Cap backoff per riconnessione (sec)  |

### Multi-model

Per usare più modelli, basta che siano caricati su Ollama remoto. Nelle richieste, usa il nome Ollama completo (con `:`):

```json
{"model": "llama3:8b", "messages": [...]}
```

Nomi senza `:` (es. `gpt-4o`) vengono mappati automaticamente a `MODEL_NAME`.

## Troubleshooting

- **`/health` dice `tunnel: down`:** Verifica SSH credentials in `.env` e che il server sia raggiungibile via SSH
- **`/health` dice `ollama: down`:** Ollama non è avviato sul server. SSH nel server e controlla `bash start_server.sh`
- **Conflitto porta 11434:** Se hai Ollama locale, fermalo o cambia `LOCAL_PORT`
- **Timeout sulle risposte:** Il modello potrebbe essere in fase di caricamento (prima richiesta). Aspetta ~30s
- **Modello non trovato:** Assicurati che il modello sia stato pullato/trasferito sul server: `ssh user@server "ollama list"`

## Metriche e Benchmark

TunneLLM traccia automaticamente le prestazioni di ogni richiesta di inferenza. Accedi alle metriche via:

```bash
curl http://localhost:11435/metrics
```

Risposta di esempio:

```json
{
  "total_requests": 42,
  "completed": 40,
  "failed": 2,
  "in_progress": 0,
  "avg_latency_s": 3.456,
  "avg_first_token_s": 0.284,
  "avg_tokens_per_sec": 28.3,
  "total_prompt_tokens": 12500,
  "total_completion_tokens": 8400,
  "recent": [
    {
      "model": "qwen3.6:35b",
      "endpoint": "/v1/chat/completions",
      "latency_s": 2.84,
      "first_token_s": 0.31,
      "tokens_per_sec": 32.1,
      "prompt_tokens": 256,
      "completion_tokens": 91
    }
  ]
}
```

### Metriche tracciate

| Metrica                   | Descrizione                                          |
| ------------------------- | ---------------------------------------------------- |
| `avg_latency_s`           | Latenza media totale (richiesta → risposta completa) |
| `avg_first_token_s`       | TTFT — Time To First Token (latency hiding)          |
| `avg_tokens_per_sec`      | Velocità media di generazione                        |
| `total_prompt_tokens`     | Token di prompt totali consumati                     |
| `total_completion_tokens` | Token di completamento totali generati               |

> **Nota:** Le metriche includono solo le richieste tramite endpoint OpenAI nativi (`/v1/*`). Le richieste proxy (`/api/*`) non vengono tracciate.

### Benchmark di riferimento

Valori indicativi con Qwen3.6:35B (Q4_K_S) su diverse GPU:

| GPU       | VRAM  | tokens/sec | TTFT  |
| --------- | ----- | ---------- | ----- |
| A100 80GB | 80 GB | ~45 t/s    | ~0.2s |
| A40 48GB  | 48 GB | ~35 t/s    | ~0.3s |
| RTX 4090  | 24 GB | ~30 t/s    | ~0.3s |
| RTX 3090  | 24 GB | ~22 t/s    | ~0.4s |

> I valori dipendono dalla lunghezza del prompt, quantizzazione, e carico SSH. Usa `/metrics` per misurare le tue prestazioni reali.
