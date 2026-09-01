"""
MK-300 Visual Tone Assistant - Back-end Flask
Autor: Assistente Full Stack
Descrição: Analisa timbres via LLM e mapeia para os 11 módulos da M-VAVE MK-300
"""

import os
import json
import re
import time
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import dotenv_values
from bs4 import BeautifulSoup

def get_env_config():
    """Lê o .env em tempo real a cada chamada, sem cache."""
    return dotenv_values(".env")

app = Flask(__name__)

def get_llm_provider():
    return get_env_config().get("LLM_PROVIDER", "gemini").lower()

def get_llm_client():
    """Retorna o cliente LLM configurado (somente para openai/groq)."""
    config = get_env_config()
    provider = get_llm_provider()
    
    if provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=config.get("OPENAI_API_KEY"))

    elif provider == "groq":
        from openai import OpenAI
        return OpenAI(
            api_key=config.get("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )

    # gemini usa SDK nativo em analyze_tone_with_llm()
    return None


def get_model_name():
    """Retorna o nome do modelo configurado."""
    config = get_env_config()
    provider = get_llm_provider()
    
    models = {
        "openai": config.get("OPENAI_MODEL", "gpt-4o-mini"),
        "gemini": config.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "groq":   config.get("GROQ_MODEL",   "llama-3.1-8b-instant"),
    }
    return models.get(provider, "gemini-2.5-flash")


# ─────────────────────────────────────────────
# PROMPT DE SISTEMA PARA ANÁLISE DE TIMBRE
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Você é um especialista em timbres de guitarra e pedaleiras de efeitos. 
Sua função é analisar o timbre de músicas/artistas e mapear os parâmetros para a pedaleira M-VAVE MK-300.

A MK-300 possui EXATAMENTE 11 módulos na seguinte ordem de sinal:
WAH → FX → GATE → DS → AMP → CAB → EQ → MOD → DLY → REV → VOL

INSTRUÇÕES OBRIGATÓRIAS:
1. Retorne SOMENTE um JSON válido, sem markdown, sem explicações, sem texto extra.
2. O JSON deve ter EXATAMENTE as 11 chaves: WAH, FX, GATE, DS, AMP, CAB, EQ, MOD, DLY, REV, VOL.
3. Cada módulo tem: "enabled" (boolean) e "params" (objeto com parâmetros específicos).
4. Todos os parâmetros numéricos devem ser inteiros de 0 a 100.
5. Inclua um campo "tone_info" no nível raiz com informações sobre o timbre.
6. Inclua um campo "song_info" no nível raiz com informações sobre a música/artista.

PARÂMETROS ESPERADOS POR MÓDULO:
- WAH: { type: string, sensitivity: int, freq: int, level: int }
- FX: { type: string, rate: int, depth: int, level: int }  
- GATE: { threshold: int, decay: int }
- DS: { type: string, gain: int, tone: int, level: int }
- AMP: { type: string, gain: int, bass: int, middle: int, treble: int, level: int, presence: int }
- CAB: { type: string, mic: string, level: int }
- EQ: { bass: int, low_mid: int, mid: int, high_mid: int, treble: int, level: int }
- MOD: { type: string, rate: int, depth: int, level: int }
- DLY: { type: string, time: int, feedback: int, mix: int }
- REV: { type: string, decay: int, pre_delay: int, mix: int }
- VOL: { volume: int }

TIPOS VÁLIDOS:
- WAH: "Cry Baby", "Volume", "Auto Wah", "None"
- FX: "Compressor", "Chorus", "Phaser", "Flanger", "Tremolo", "None"
- DS: "Tube Screamer", "Big Muff", "RAT", "Boss DS-1", "Fuzz", "Overdrive", "None"
- AMP: "Marshall JCM800", "Fender Twin", "Mesa Boogie", "Vox AC30", "Soldano SLO", "HiWatt", "None"
- CAB: "4x12 Marshall", "2x12 Fender", "4x12 Mesa", "1x12 Vox", "None"
- MOD: "Chorus", "Phaser", "Flanger", "Vibrato", "Tremolo", "None"
- DLY: "Analog", "Digital", "Tape", "Reverb", "None"
- REV: "Hall", "Room", "Plate", "Spring", "Chamber", "None"

EXEMPLO DE SAÍDA (Resumido):
{
  "song_info": {"artist": "Nome", "song": "Música", "era": "Ano", "guitar": "Guitarra", "description": "Curta descrição"},
  "tone_info": {"character": "Clean", "style": "Rock", "key_effects": ["Reverb"]},
  "WAH": { "enabled": false, "params": { "type": "None", "sensitivity": 50, "freq": 50, "level": 50 } },
  "FX": { "enabled": true, "params": { "type": "Compressor", "rate": 40, "depth": 30, "level": 60 } },
  "...": "Siga o mesmo padrão para os 11 módulos (GATE, DS, AMP, CAB, EQ, MOD, DLY, REV, VOL)."
}"""


# ─────────────────────────────────────────────
# BUSCA DE MIDI — WEB SCRAPING
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def search_midi_bitmidi(query: str) -> list:
    """Busca arquivos MIDI no BitMidi."""
    results = []
    try:
        url = f"https://bitmidi.com/search?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "html.parser")

        # Procura por links de MIDI
        for item in soup.select("article, .card, [class*='midi']")[:8]:
            link_tag = item.find("a", href=True)
            title_tag = item.find(["h2", "h3", "h4", "strong", "span"])

            if link_tag:
                href = link_tag.get("href", "")
                title = title_tag.get_text(strip=True) if title_tag else "Arquivo MIDI"

                if href.startswith("/"):
                    href = f"https://bitmidi.com{href}"

                # Link direto para download do MIDI
                midi_url = href.replace("/midi/", "/midi/") 
                if "/midi/" in href or href.endswith(".mid"):
                    results.append({
                        "title": title,
                        "page_url": href,
                        "download_url": href + "/download" if not href.endswith(".mid") else href,
                        "source": "BitMidi"
                    })

        # Fallback: links diretos .mid
        if not results:
            for a in soup.find_all("a", href=True)[:20]:
                href = a.get("href", "")
                if ".mid" in href.lower():
                    full_url = href if href.startswith("http") else f"https://bitmidi.com{href}"
                    results.append({
                        "title": a.get_text(strip=True) or query,
                        "page_url": full_url,
                        "download_url": full_url,
                        "source": "BitMidi"
                    })

    except Exception as e:
        print(f"[MIDI] Erro no BitMidi: {e}")

    return results[:5]


def search_midi_freemidi(query: str) -> list:
    """Busca arquivos MIDI no FreeMidi."""
    results = []
    try:
        url = f"https://freemidi.org/search-midi?search={requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "html.parser")

        for item in soup.select(".song-list-container, .midi-row, [class*='song']")[:8]:
            link_tag = item.find("a", href=True)
            title_tag = item.find(["h3", "h4", "strong", "div", "span"])

            if link_tag:
                href = link_tag.get("href", "")
                title = title_tag.get_text(strip=True) if title_tag else query

                if href.startswith("/"):
                    href = f"https://freemidi.org{href}"

                results.append({
                    "title": title[:60],
                    "page_url": href,
                    "download_url": href,
                    "source": "FreeMidi"
                })

    except Exception as e:
        print(f"[MIDI] Erro no FreeMidi: {e}")

    return results[:5]


def build_midi_results(query: str) -> dict:
    """Combina resultados de múltiplas fontes."""
    all_results = []

    # Busca em paralelo (sequencial por simplicidade)
    bitmidi = search_midi_bitmidi(query)
    all_results.extend(bitmidi)

    if len(all_results) < 3:
        freemidi = search_midi_freemidi(query)
        all_results.extend(freemidi)

    # Remove duplicatas por URL
    seen = set()
    unique = []
    for r in all_results:
        if r["download_url"] not in seen:
            seen.add(r["download_url"])
            unique.append(r)

    return {
        "query": query,
        "count": len(unique),
        "results": unique[:6],
        "search_urls": {
            "bitmidi": f"https://bitmidi.com/search?q={requests.utils.quote(query)}",
            "freemidi": f"https://freemidi.org/search-midi?search={requests.utils.quote(query)}",
            "midiworld": f"https://www.midiworld.com/search/?q={requests.utils.quote(query)}"
        }
    }


# ─────────────────────────────────────────────
# ANÁLISE DE TIMBRE VIA LLM
# ─────────────────────────────────────────────

def analyze_tone_with_llm(query: str) -> dict:
    """Chama a LLM para analisar o timbre e mapear para a MK-300."""
    model = get_model_name()

    user_message = f"""Analise o timbre para: "{query}"

Mapeie os parâmetros para a pedaleira M-VAVE MK-300 com seus 11 módulos.
Pesquise quais equipamentos o artista/música usa (amplificador, pedais de drive, modulação, etc.)
e converta para as opções disponíveis na MK-300.

Retorne SOMENTE o JSON conforme especificado no sistema."""

    # ── Gemini via SDK nativo ──────────────────────────────
    provider = get_llm_provider()
    config = get_env_config()
    
    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={config.get('GEMINI_API_KEY')}"
        pedals = ["WAH", "FX", "GATE", "DS", "AMP", "CAB", "EQ", "MOD", "DLY", "REV", "VOL"]
        schema = {
            "type": "OBJECT",
            "properties": {
                "song_info": {
                    "type": "OBJECT",
                    "properties": {
                        "artist": {"type": "STRING"},
                        "song": {"type": "STRING"},
                        "era": {"type": "STRING"},
                        "guitar": {"type": "STRING"},
                        "description": {"type": "STRING"}
                    },
                    "required": ["artist", "song", "era", "guitar", "description"]
                },
                "tone_info": {
                    "type": "OBJECT",
                    "properties": {
                        "character": {"type": "STRING"},
                        "style": {"type": "STRING"},
                        "key_effects": {"type": "ARRAY", "items": {"type": "STRING"}}
                    },
                    "required": ["character", "style", "key_effects"]
                }
            },
            "required": ["song_info", "tone_info"] + pedals
        }
        
        # Add pedals to schema with specific parameters to prevent 'too many states' schema error
        pedal_params = {
            "WAH": ["type", "sensitivity", "freq", "level"],
            "FX": ["type", "rate", "depth", "level"],
            "GATE": ["threshold", "decay"],
            "DS": ["type", "gain", "tone", "level"],
            "AMP": ["type", "gain", "bass", "middle", "treble", "level", "presence"],
            "CAB": ["type", "mic", "level"],
            "EQ": ["bass", "low_mid", "mid", "high_mid", "treble", "level"],
            "MOD": ["type", "rate", "depth", "level"],
            "DLY": ["type", "time", "feedback", "mix"],
            "REV": ["type", "decay", "pre_delay", "mix"],
            "VOL": ["volume"]
        }
        
        param_types = {
            "type": "STRING", "mic": "STRING",
            "sensitivity": "INTEGER", "freq": "INTEGER", "level": "INTEGER",
            "rate": "INTEGER", "depth": "INTEGER", "threshold": "INTEGER", "decay": "INTEGER",
            "gain": "INTEGER", "tone": "INTEGER", "bass": "INTEGER", "middle": "INTEGER",
            "treble": "INTEGER", "presence": "INTEGER", "low_mid": "INTEGER", "mid": "INTEGER",
            "high_mid": "INTEGER", "time": "INTEGER", "feedback": "INTEGER", "pre_delay": "INTEGER",
            "mix": "INTEGER", "volume": "INTEGER"
        }

        for p, keys in pedal_params.items():
            schema["properties"][p] = {
                "type": "OBJECT",
                "properties": {
                    "enabled": {"type": "BOOLEAN"},
                    "params": {
                        "type": "OBJECT",
                        "properties": {k: {"type": param_types[k]} for k in keys},
                        "required": keys
                    }
                },
                "required": ["enabled", "params"]
            }

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [{
                "parts": [{"text": user_message}]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
                "responseSchema": schema,
                # gemini-2.5-flash é um modelo "thinking": sem isto, os tokens de
                # raciocínio consomem todo o maxOutputTokens e a resposta JSON
                # volta truncada (finishReason=MAX_TOKENS).
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }
        resp = requests.post(url, json=payload)
        if not resp.ok:
            raise Exception(f"Gemini API Error: {resp.text}")
        
        resp_json = resp.json()
        try:
            raw = resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            raise Exception(f"Resposta inesperada da API: {resp_json}")

    # ── OpenAI / Groq via cliente OpenAI-compat ───────────
    else:
        client = get_llm_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        raw = response.choices[0].message.content.strip()

    # Extrai o bloco de JSON da resposta (caso tenha markdown ou texto antes/depois)
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[LLM ERROR] Erro no JSON. Texto retornado pela IA:\n{raw}\n---")
        raise e


# ─────────────────────────────────────────────
# ROTAS FLASK
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """Serve a página principal."""
    return render_template("index.html")


@app.route("/api/search-tone", methods=["POST"])
def search_tone():
    """Analisa timbre via LLM e retorna configuração JSON para a MK-300."""
    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Por favor, insira uma música, artista ou timbre."}), 400

    try:
        tone_data = analyze_tone_with_llm(query)
        return jsonify({"success": True, "data": tone_data})

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Erro ao processar resposta da IA: {str(e)}"}), 500

    except Exception as e:
        err_msg = str(e)
        if "api_key" in err_msg.lower() or "authentication" in err_msg.lower():
            return jsonify({
                "error": "Chave de API inválida ou não configurada. "
                         "Verifique o arquivo .env com sua chave de API."
            }), 401
        return jsonify({"error": f"Erro na análise: {err_msg}"}), 500


@app.route("/api/search-midi", methods=["POST"])
def search_midi():
    """Busca arquivos MIDI relacionados à música pesquisada."""
    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Por favor, insira uma música ou artista."}), 400

    try:
        midi_data = build_midi_results(query)
        return jsonify({"success": True, "data": midi_data})

    except Exception as e:
        return jsonify({"error": f"Erro na busca MIDI: {str(e)}"}), 500


@app.route("/api/config", methods=["GET"])
def api_get_config():
    """Retorna configurações públicas da aplicação."""
    response = jsonify({
        "provider": get_llm_provider(),
        "model": get_model_name(),
        "version": "1.0.0"
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ─────────────────────────────────────────────
# INICIALIZAÇÃO
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    # Compatibilidade com terminal Windows (CP1252 não suporta emojis)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    port = int(get_env_config().get("FLASK_PORT", 5000))
    debug = get_env_config().get("FLASK_DEBUG", "True").lower() == "true"

    print("=======================================================")
    print("  [MK-300] Visual Tone Assistant - M-VAVE")
    print("=======================================================")
    print(f"  Provedor LLM : {get_llm_provider().upper()}")
    print(f"  Modelo       : {get_model_name()}")
    print(f"  Porta        : {port}")
    print(f"  URL          : http://localhost:{port}")
    print("=======================================================")
    print()

    # use_reloader=False evita reinicializações em loop durante instalação de pacotes
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
