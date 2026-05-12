import asyncio
import json
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse


import torch
from airllm import AutoModel
from transformers import AutoTokenizer

app = FastAPI(title="AirLLM Mock Ollama Server")

MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"
ALIAS_NAME = "mistral"

print("==================================================")
print(f" Inizializzazione AirLLM: {MODEL_NAME}")
print("==================================================")
print("Il caricamento potrebbe richiedere qualche istante...")

# airllm carica i layer uno alla volta nella GPU per risparmiare VRAM
model = AutoModel.from_pretrained(MODEL_NAME)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Modello caricato. Device in uso: {device}")
print("In ascolto sulla porta 11434 (Standard Ollama/Copilot)...")


# =================================================================
#  Mock API di Ollama richieste da Copilot / Strumenti esterni
# =================================================================

@app.get("/api/version")
async def get_version():
    """Risponde con la versione mock di Ollama."""
    return {"version": "0.1.30"}


@app.get("/api/tags")
async def get_tags():
    """Mostra la lista dei modelli disponibili (Copilot lo usa per il dropdown)."""
    return {
        "models": [
            {
                "name": ALIAS_NAME,
                "model": ALIAS_NAME,
                "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "size": 1024 * 1024 * 1024,  # Fake 1GB
                "digest": "fake-digest-12345",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "llama",
                    "families": ["llama"],
                    "parameter_size": "1B",
                    "quantization_level": "Q4_0"
                }
            }
        ]
    }


@app.post("/api/show")
async def show_model(request: Request):
    """Fornisce i dettagli del modello quando richiesto."""
    return {
        "modelfile": f"FROM {ALIAS_NAME}",
        "parameters": "",
        "template": "{{ .Prompt }}",
        "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "llama",
            "families": ["llama"],
            "parameter_size": "1B",
            "quantization_level": "Q4_0"
        }
    }


# =================================================================
#  Endpoint di Inferenza (Chat)
# =================================================================

def generate_text(prompt: str, max_tokens: int = 50) -> str:
    """Funzione sincrona che utilizza airllm per generare il testo."""
    input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(device)
    
    # airllm generation
    generation_output = model.generate(
        input_ids,
        max_new_tokens=max_tokens,
        use_cache=True,
        return_dict_in_generate=True
    )
    
    # Decodifica escludendo l'input
    generated_ids = generation_output.sequences[0][input_ids.shape[1]:]
    output_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
    return output_text.strip()


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """Endpoint in stile OpenAI (spesso usato da Copilot o plugin VSCode)."""
    data = await request.json()
    messages = data.get("messages", [])
    stream = data.get("stream", False)
    max_tokens = data.get("max_tokens", 50)
    
    # Costruiamo il prompt per TinyLlama
    prompt = ""
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        prompt += f"<|{role}|>\n{content}</s>\n"
    prompt += "<|assistant|>\n"
    
    # Eseguiamo l'inferenza (bloccante, per test va bene)
    print("Generazione in corso (OpenAI format)...")
    output_text = generate_text(prompt, max_tokens=max_tokens)
    print(f"Risposta generata: {output_text[:50]}...")
    
    if stream:
        async def stream_generator():
            words = output_text.split(" ")
            for i, word in enumerate(words):
                chunk = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": ALIAS_NAME,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": word + (" " if i < len(words)-1 else "")},
                            "finish_reason": None
                        }
                    ]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.02) # Fake delay per l'effetto stream
                
            final_chunk = {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": ALIAS_NAME,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"
            
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": ALIAS_NAME,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": output_text
                },
                "finish_reason": "stop"
            }
        ]
    }


@app.post("/api/chat")
async def ollama_chat(request: Request):
    """Endpoint in stile Ollama nativo."""
    data = await request.json()
    messages = data.get("messages", [])
    stream = data.get("stream", False)
    
    prompt = ""
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        prompt += f"<|{role}|>\n{content}</s>\n"
    prompt += "<|assistant|>\n"
    
    print("Generazione in corso (Ollama format)...")
    output_text = generate_text(prompt, max_tokens=50)
    print(f"Risposta generata: {output_text[:50]}...")
    
    if stream:
        async def stream_generator():
            words = output_text.split(" ")
            for i, word in enumerate(words):
                chunk = {
                    "model": ALIAS_NAME,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "message": {
                        "role": "assistant", 
                        "content": word + (" " if i < len(words)-1 else "")
                    },
                    "done": False
                }
                yield f"{json.dumps(chunk)}\n"
                await asyncio.sleep(0.02)
                
            final_chunk = {
                "model": ALIAS_NAME,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop"
            }
            yield f"{json.dumps(final_chunk)}\n"
            
        return StreamingResponse(stream_generator(), media_type="application/x-ndjson")
    
    return {
        "model": ALIAS_NAME,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "message": {
            "role": "assistant",
            "content": output_text
        },
        "done": True,
        "done_reason": "stop"
    }


if __name__ == "__main__":
    # Avvia sulla porta 11434, che è la porta di default usata da Ollama
    uvicorn.run(app, host="127.0.0.1", port=11434)
