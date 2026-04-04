# Abusive-LLM

Self-hosted LLM API via SSH tunnel. Serve un modello LLM su un server GPU remoto (vLLM) e lo espone localmente come API OpenAI-compatible per VS Code (Continue / Copilot).

## Architettura

```
[VS Code: Continue / Copilot]
        │  http://localhost:11434/v1
        ▼
[Local: FastAPI Proxy (porta 11434)]
        │  httpx → localhost:11435
        ▼
[SSH Tunnel (porta 11435 → remote:8000)]
        │  sshtunnel / paramiko
        ▼
[Remote: vLLM Server (porta 8000)]
        │  GPU 22GB VRAM
        ▼
[Qwen2.5-14B-Instruct-AWQ (~9GB 4-bit)]
```

## Setup

### 1. Server remoto (GPU)

Copia la cartella `remote/` sul server:

```bash
scp -r remote/ user@server:~/abusive-llm/
```

Sul server:

```bash
cd ~/abusive-llm
bash setup.sh          # installa vLLM + scarica modello
bash start_server.sh   # avvia vLLM su 127.0.0.1:8000
```

> Se il server non ha accesso a HuggingFace, scarica il modello localmente e trasferiscilo via SCP:
>
> ```bash
> # locale
> huggingface-cli download Qwen/Qwen2.5-14B-Instruct-AWQ --local-dir ./model
> scp -r ./model user@server:~/.cache/huggingface/hub/models--Qwen--Qwen2.5-14B-Instruct-AWQ/
> ```

### 2. Macchina locale

```bash
cd local/
pip install -r requirements.txt
cp ../.env.example ../.env
# Edita .env con i dati SSH del tuo server
```

Verifica che il tunnel SSH funzioni:

```bash
ssh -N -L 11435:127.0.0.1:8000 user@server
# In un altro terminale:
curl http://localhost:11435/v1/models
```

Se funziona, avvia il proxy:

```bash
cd local/
python main.py
```

### 3. VS Code — Continue Extension

Installa [Continue](https://marketplace.visualstudio.com/items?itemName=Continue.continue) e configura `.continue/config.yaml`:

```yaml
name: Abusive-LLM
version: 0.0.1
schema: v1
models:
  - name: Qwen2.5-14B
    provider: openai
    model: Qwen/Qwen2.5-14B-Instruct-AWQ
    apiBase: http://localhost:11434/v1
    apiKey: dummy
```

### 4. VS Code — Copilot Custom Models (sperimentale)

In `settings.json`:

```json
{
  "github.copilot.chat.models": [
    {
      "family": "gpt-4o",
      "id": "Qwen/Qwen2.5-14B-Instruct-AWQ",
      "name": "Qwen2.5-14B (self-hosted)",
      "url": "http://localhost:11434",
      "isDefault": false
    }
  ]
}
```

## Endpoints

| Endpoint               | Metodo | Descrizione                             |
| ---------------------- | ------ | --------------------------------------- |
| `/health`              | GET    | Stato tunnel SSH + vLLM                 |
| `/v1/models`           | GET    | Lista modelli disponibili               |
| `/v1/chat/completions` | POST   | Chat completions (streaming supportato) |
| `/v1/completions`      | POST   | Text completions                        |

## Configurazione

Tutte le variabili sono in `.env` (vedi `.env.example`). Override via environment variables.

| Variabile      | Default                         | Descrizione                            |
| -------------- | ------------------------------- | -------------------------------------- |
| `SSH_HOST`     | `localhost`                     | Hostname del server GPU                |
| `SSH_PORT`     | `22`                            | Porta SSH                              |
| `SSH_USER`     | `root`                          | Username SSH                           |
| `SSH_KEY_PATH` | `~/.ssh/id_rsa`                 | Path alla chiave privata SSH           |
| `LOCAL_PORT`   | `11434`                         | Porta pubblica del proxy (per VS Code) |
| `TUNNEL_PORT`  | `11435`                         | Porta interna del tunnel SSH           |
| `REMOTE_PORT`  | `8000`                          | Porta vLLM sul server remoto           |
| `MODEL_NAME`   | `Qwen/Qwen2.5-14B-Instruct-AWQ` | Nome modello                           |

## Troubleshooting

- **`/health` dice tunnel: down`:** Verifica SSH credentials in `.env` e che il server sia raggiungibile
- **`/health` dice vllm: down`:** vLLM non è avviato sul server. SSH nel server e controlla `bash start_server.sh`
- **Timeout sulle risposte:** Il modello potrebbe essere in fase di caricamento (prima richiesta dopo l'avvio). Aspetta ~30s
- **Out of memory sul server:** Riduci `MAX_MODEL_LEN` o `GPU_MEMORY_UTILIZATION` in `start_server.sh`
