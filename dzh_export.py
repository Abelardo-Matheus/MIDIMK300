"""
Gerador de arquivos .dzh (preset binário) para a M-VAVE MK-300.

Formato reverso a partir de comparação byte-a-byte entre um preset real
exportado do equipamento (assets/base_preset.dzh) e variações controladas
(um único parâmetro alterado por vez) fornecidas pelo usuário. Cada offset
abaixo foi CONFIRMADO empiricamente (não é uma suposição) — veja o histórico
da conversa para o diff completo que embasou cada um.

Estratégia de segurança: nunca escrevemos um arquivo do zero. Sempre partimos
de um preset .dzh real e válido (o "template") e sobrescrevemos apenas os
bytes que temos certeza do significado. Todo o resto do arquivo (WAH, FX,
GATE, EQ, MOD, DLY, REV — que não têm lista de modelos oficial documentada,
e cujos offsets de parâmetro numérico não foram mapeados) permanece
IDÊNTICO ao template, portanto sempre um valor válido que a pedaleira aceita.
"""

import os
import re
import difflib

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "base_preset.dzh")

# IDs canônicos dos 11 módulos, na ordem usada internamente pelo arquivo .dzh
# (confirmado via o array de "chain order" no offset 0x20 e o array de
# enabled/bypass no offset 0x2B, ambos indexados por este ID).
MODULE_CANONICAL_ID = {
    "WAH": 0, "FX": 1, "GATE": 2, "DS": 3, "AMP": 4, "CAB": 5,
    "EQ": 6, "MOD": 7, "DLY": 8, "REV": 9, "VOL": 10,
}

NAME_OFFSET = 0x00
NAME_FIELD_LEN = 20          # campo observado no template: ASCII + zero-padding
NAME_MAX_CHARS = 19          # deixa ao menos 1 byte de terminador zero

FLAGS_OFFSET = 0x2B          # 11 bytes, um por módulo (indexado por MODULE_CANONICAL_ID)
TYPE_OFFSET = 0x36           # 11 bytes, um por módulo (índice do modelo, quando aplicável)

# Offsets confirmados por diff binário (valores uint16 little-endian).
# Somente AMP, DS, CAB e VOL foram mapeados com confiança alta — os demais
# módulos não têm parâmetros numéricos gravados por esta versão do exportador.
PARAM_OFFSETS = {
    "AMP": {"gain": 0xA2, "level": 0xA4, "bass": 0xA6, "middle": 0xA8, "treble": 0xAA, "presence": 0xAE},
    "DS":  {"gain": 0x8A, "level": 0x8C, "tone": 0x92},
    "CAB": {"level": 0xBA},
    "VOL": {"volume": 0x132},
}

TYPE_NAME_LISTS = {
    "AMP": None,  # injetado por build_dzh (vem de app.py: AMP_TYPES combinando guitarra+baixo)
    "CAB": None,
    "DS": None,
}


def _sanitize_name(name: str) -> bytes:
    """ASCII simples, sem acentos/símbolos, truncado ao tamanho do campo."""
    safe = "".join(c for c in (name or "") if c.isalnum() or c in " -_").strip()
    if not safe:
        safe = "PRESET"
    safe = safe[:NAME_MAX_CHARS]
    return safe.encode("ascii", errors="ignore")


def _clamp_u16(value) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        v = 0
    return max(0, min(65535, v))


def _normalize_name(s: str) -> str:
    """Remove espaços/hífens/underscores e baixa a caixa, para comparar nomes
    de modelo de forma tolerante a pequenas diferenças de formatação."""
    return re.sub(r"[\s_\-]+", "", (s or "").strip().lower())


def _match_type(type_name: str, names: list):
    """Encontra o nome real (e seu índice) mais próximo de type_name numa
    lista de modelos reais. Provedores sem enforcement de schema (Groq/OpenAI)
    não são obrigados a copiar o nome EXATAMENTE como está na lista — sem essa
    tolerância, uma diferença mínima de maiúscula/espaço/hífen fazia o tipo
    nunca ser gravado no .dzh (ficava sempre com o valor do preset-modelo).
    Retorna (nome_real_encontrado, índice) ou (None, None) se nada bater."""
    if not type_name or not names:
        return None, None
    if type_name in names:
        return type_name, names.index(type_name)

    norm_target = _normalize_name(type_name)
    norm_map = {}
    for n in names:
        norm_map.setdefault(_normalize_name(n), n)
    if norm_target in norm_map:
        matched = norm_map[norm_target]
        return matched, names.index(matched)

    close = difflib.get_close_matches(type_name, names, n=1, cutoff=0.72)
    if close:
        matched = close[0]
        return matched, names.index(matched)

    return None, None


def build_dzh(tone_data: dict, preset_name: str, amp_types: list, cab_types: list, ds_types: list):
    """Recebe o JSON retornado pela análise de timbre (mesmo formato usado no
    front-end: uma chave por módulo com {enabled, params}) e devolve
    (bytes_do_dzh, lista_de_avisos), baseado no preset-template real. Avisos
    são gerados quando um "type" não bate com nenhum modelo real conhecido
    (mantém o valor do template) ou quando bateu por aproximação."""

    with open(TEMPLATE_PATH, "rb") as f:
        buf = bytearray(f.read())

    warnings = []

    # ── Nome do preset ──────────────────────────────────────────────
    name_bytes = _sanitize_name(preset_name)
    for i in range(NAME_FIELD_LEN):
        buf[NAME_OFFSET + i] = name_bytes[i] if i < len(name_bytes) else 0

    # ── Liga/desliga (bypass) de todos os 11 módulos ────────────────
    for mod, cid in MODULE_CANONICAL_ID.items():
        info = tone_data.get(mod) or {}
        buf[FLAGS_OFFSET + cid] = 1 if info.get("enabled") else 0

    # ── Modelo (type) de AMP / CAB / DS ──────────────────────────────
    type_lists = {"AMP": amp_types, "CAB": cab_types, "DS": ds_types}
    for mod, names in type_lists.items():
        info = tone_data.get(mod) or {}
        params = info.get("params") or {}
        type_name = params.get("type")
        matched, idx = _match_type(type_name, names)
        if matched is not None:
            buf[TYPE_OFFSET + MODULE_CANONICAL_ID[mod]] = idx & 0xFF
            if matched != type_name:
                warnings.append(f'{mod}: "{type_name}" interpretado como "{matched}" (correspondência aproximada).')
        elif type_name:
            warnings.append(f'{mod}: modelo "{type_name}" não reconhecido — mantido o modelo que já estava no preset-modelo.')

    # ── Parâmetros numéricos confirmados (AMP, DS, CAB, VOL) ─────────
    for mod, param_map in PARAM_OFFSETS.items():
        info = tone_data.get(mod) or {}
        values = info.get("params") or {}
        for key, offset in param_map.items():
            if key in values:
                v = _clamp_u16(values[key])
                buf[offset] = v & 0xFF
                buf[offset + 1] = (v >> 8) & 0xFF

    return bytes(buf), warnings


def safe_filename(preset_name: str) -> str:
    safe = "".join(c for c in (preset_name or "") if c.isalnum() or c in " -_").strip()
    return (safe or "preset").replace(" ", "_")
