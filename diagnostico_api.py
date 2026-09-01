"""
MK-300 Visual Tone Assistant - Diagnostico de API
Script unico para testar a conexao com o provedor de LLM configurado no .env
(substitui os antigos test_gemini.py, test2.py e test3.py).

Uso:
    python diagnostico_api.py

IMPORTANTE: nunca coloque chaves de API diretamente no codigo. Este script
le tudo do arquivo .env.
"""

import json
import re
import sys

import requests
from dotenv import dotenv_values

config = dotenv_values(".env")

PROVIDER = config.get("LLM_PROVIDER", "gemini").lower()

MODELS = {
    "openai": config.get("OPENAI_MODEL", "gpt-4o-mini"),
    "gemini": config.get("GEMINI_MODEL", "gemini-2.5-flash"),
    "groq": config.get("GROQ_MODEL", "llama-3.1-8b-instant"),
}
MODEL = MODELS.get(PROVIDER, "gemini-2.5-flash")

KEYS = {
    "openai": config.get("OPENAI_API_KEY", ""),
    "gemini": config.get("GEMINI_API_KEY", ""),
    "groq": config.get("GROQ_API_KEY", ""),
}
API_KEY = KEYS.get(PROVIDER, "")


def mask(key: str) -> str:
    if not key or len(key) < 10:
        return "(vazia ou muito curta)"
    return f"{key[:6]}...{key[-4:]}"


def check_prefix(provider: str, key: str) -> bool:
    prefixes = {"openai": "sk-", "gemini": "AIza", "groq": "gsk_"}
    expected = prefixes.get(provider, "")
    return key.startswith(expected) if expected else True


def test_gemini(api_key: str, model: str) -> None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": "Diga apenas: OK"}]}]}
    resp = requests.post(url, json=payload, timeout=15)
    print(f"Status HTTP: {resp.status_code}")
    if not resp.ok:
        print(f"Resposta de erro: {resp.text[:500]}")
        return
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    print(f"SUCESSO! Resposta do modelo: {text}")


def test_openai_compat(api_key: str, model: str, base_url: str) -> None:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Diga apenas: OK"}],
        max_tokens=10,
    )
    print(f"SUCESSO! Resposta do modelo: {resp.choices[0].message.content}")


def main() -> int:
    print("=" * 55)
    print("  Diagnostico de API - MK-300 Tone Assistant")
    print("=" * 55)
    print(f"Provedor configurado : {PROVIDER}")
    print(f"Modelo configurado   : {MODEL}")
    print(f"Chave (mascarada)    : {mask(API_KEY)}")
    print(f"Prefixo esperado OK? : {check_prefix(PROVIDER, API_KEY)}")
    print()

    if not API_KEY:
        print(f"ERRO: nenhuma chave encontrada para o provedor '{PROVIDER}' no .env.")
        return 1

    try:
        if PROVIDER == "gemini":
            test_gemini(API_KEY, MODEL)
        elif PROVIDER == "openai":
            test_openai_compat(API_KEY, MODEL, base_url=None)
        elif PROVIDER == "groq":
            test_openai_compat(API_KEY, MODEL, base_url="https://api.groq.com/openai/v1")
        else:
            print(f"ERRO: provedor desconhecido '{PROVIDER}'. Use openai, gemini ou groq.")
            return 1
    except Exception as exc:
        print(f"ERRO: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
