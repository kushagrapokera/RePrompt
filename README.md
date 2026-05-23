# RePrompt

RePrompt is an intent-aware prompt enhancement system that improves raw user queries before they are sent to another LLM such as ChatGPT, Claude, Gemini, or Perplexity.

It combines:

- lightweight cleanup for noisy text
- intent classification using a fine-tuned LFM2.5-1.2B classifier
- a fallback fully fine-tuned DistilBERT intent model for low-confidence cases
- intent-aware prompt rewriting using `LiquidAI/LFM2.5-1.2B-Instruct`
- a browser extension that injects a floating enhance button into supported LLM sites

## 1. About The Project

Many user prompts are short, noisy, ambiguous, or poorly structured. RePrompt acts as a middleware layer between the user and the target LLM.

The pipeline:

```text
Raw Query
  -> Regex Cleanup
  -> Intent Classification
  -> Confidence Check + DistilBERT Fallback
  -> Intent-Aware Prompt Enhancement
  -> Better Prompt
```

### Supported intents

- `general_qa`
- `coding`
- `creative_writing`
- `email`
- `summarization`
- `learning`
- `planning`

### What the system does

- cleans obvious formatting noise
- predicts the user intent
- falls back to DistilBERT when the LFM classifier is uncertain
- rewrites the prompt while trying to preserve the original meaning and constraints
- exposes the pipeline through a FastAPI backend and a Chrome/Edge extension

## Project Structure

```text
RePrompt/
  pipeline.py
  run-server.bat
  server/
    main.py
    requirements.txt
  src/
    cleanup.py
    intent_classifier.py
    enhancer.py
  extension/
    manifest.json
    content.js
    styles/content.css
    popup.html
    popup.js
    options.html
    options.js
    icons/
  lfm25_intent_cls_vanilla/      # local LFM classifier weights
  distilbert_intent_model/       # local DistilBERT fallback weights
  intent_cls_lora/               # LoRA/adapters and training artifacts
```

## 2. Fine-Tuning Summary

This project uses two intent-classification tracks:

### A. Full fine-tuning of DistilBERT

DistilBERT is used here as a fallback intent classifier when the primary LFM classifier has confidence below the threshold.

Why DistilBERT was included:

- lightweight and fast
- strong baseline for text classification
- useful as a second opinion when the LFM classifier is uncertain

In this project:

- DistilBERT is loaded from the local folder `distilbert_intent_model/`
- it predicts one of the same 7 intent labels
- it is only used when the LFM classifier confidence is low


Hugging Face link:

- Repo: `https://huggingface.co/KushPokera/reprompt-distilbert-intent`


### B. Fine-tuning of LFM2.5-1.2B

The primary classifier is based on `LiquidAI/LFM2.5-1.2B-Instruct`.

In this project, the LFM model is used in two ways:

- as the main intent classifier
- as the prompt enhancer / rewriter

For classification, the project uses:

- a 4-bit quantized LFM backbone
- a classifier head on top of the backbone
- LoRA-based adaptation during training
- trained weights loaded from `lfm25_intent_cls_vanilla/pytorch_model.bin`

Why LFM2.5-1.2B was used:

- compact enough for local inference compared to larger LLMs
- good instruction-following behavior
- flexible enough to support both classification and enhancement tasks

Hugging Face link:

- Repo: `https://huggingface.co/KushPokera/reprompt-lfm-classifier`


## 3. How To Set Up And Use The Project

### Requirements

- Python 3.10+
- Windows, Linux, or macOS
- CUDA GPU recommended for faster inference
- enough disk space for local model folders

### Install Python dependencies

From the project root:

```bash
pip install torch transformers peft bitsandbytes fastapi "uvicorn[standard]" pydantic
```

If you want to use only the API server dependencies first:

```bash
pip install -r server/requirements.txt
```

### Hugging Face model sources

Use the following Hugging Face repositories as the source for the local model folders:

- LFM classifier: `https://huggingface.co/KushPokera/reprompt-lfm-classifier`
- DistilBERT fallback: `https://huggingface.co/KushPokera/reprompt-distilbert-intent`


### Expected local layout

```text
RePrompt/
  lfm25_intent_cls_vanilla/
    pytorch_model.bin
    config.json
    tokenizer.json
    tokenizer_config.json
    chat_template.jinja

  distilbert_intent_model/
    config.json
    model.safetensors
    tokenizer.json
    tokenizer_config.json
```

### Start the backend

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8787
```

On Windows you can also use:

```bash
run-server.bat
```

### Health check

Open:

```text
http://127.0.0.1:8787/health
```

Expected response:

```json
{"status":"ok","model_loaded":true}
```

## 4. Setup For Using It As An Extension

The extension is located in the `extension/` folder and works on:

- ChatGPT
- Claude
- Gemini
- Perplexity

### Load the extension in Chrome

1. Open `chrome://extensions`
2. Turn on `Developer mode`
3. Click `Load unpacked`
4. Select the `extension/` folder

### Load the extension in Edge

1. Open `edge://extensions`
2. Turn on `Developer mode`
3. Click `Load unpacked`
4. Select the `extension/` folder

### Extension notes

- the floating RePrompt button is draggable
- button position is saved per website
- the extension talks to the backend at `http://127.0.0.1:8787` by default

### Change backend URL

If needed:

1. Open the extension details
2. Open `Options`
3. Change the backend URL
4. Use `Test Connection`

## 5. How To Use It

### Browser extension flow

1. Start the backend server
2. Open ChatGPT, Claude, Gemini, or Perplexity
3. Type a prompt into the input box
4. Click the RePrompt floating button
5. The extension sends the text to the local backend
6. The enhanced prompt is written back into the input field

### API usage

#### `GET /health`

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "model_loaded": true
}
```

#### `POST /enhance`

Request:

```json
{
  "query": "explain black holes in simple language"
}
```

Example response:

```json
{
  "original": "explain black holes in simple language",
  "cleaned": "explain black holes in simple language",
  "intent": "learning",
  "confidence": 0.78,
  "enhanced": "Can you explain black holes in simple terms?"
}
```

### Query logging

Each enhancement request is appended to:

```text
query_log.jsonl
```

The log includes:

- original query
- final predicted intent
- confidence
- LFM classifier output info
- fallback usage info
- DistilBERT fallback info
- enhanced prompt

## How The Current Logic Works

At runtime:

- `pipeline.py` orchestrates the end-to-end flow
- `src/cleanup.py` performs regex-based cleanup
- `src/intent_classifier.py` runs LFM intent classification and optional DistilBERT fallback
- `src/enhancer.py` rewrites the cleaned prompt using the detected intent
- `server/main.py` exposes the pipeline as a FastAPI service
- `extension/content.js` injects the floating button into supported sites

