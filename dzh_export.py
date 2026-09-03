"""
Gerador de arquivos .dzh (preset binário) para a M-VAVE MK-300.

Formato reverso a partir de comparação byte-a-byte entre um preset real
exportado do equipamento (assets/base_preset.dzh) e variações controladas
(um único parâmetro alterado por vez) fornecidas pelo usuário, usando o
app oficial M-EFCS conectado à pedaleira por USB. Cada offset abaixo foi
CONFIRMADO empiricamente — veja presets/README.md para o histórico
completo das sessões de engenharia reversa.

Estratégia de segurança: nunca escrevemos um arquivo do zero. Sempre partimos
de um preset .dzh real e válido (o "template") e sobrescrevemos apenas os
bytes que temos certeza do significado. Todo o resto do arquivo permanece
IDÊNTICO ao template, portanto sempre um valor válido que a pedaleira aceita.

────────────────────────────────────────────────────────────────────────
DUAS FAMÍLIAS DE MÓDULOS (descoberta importante de 2026-09-03)
────────────────────────────────────────────────────────────────────────
Ao mapear TODOS os módulos (não só AMP/DS/CAB), ficou claro que a MK-300
usa dois esquemas de parâmetro bem diferentes:

1) "FIXOS" (AMP, CAB, DS, VOL, REV, EQ): o layout de knobs é o MESMO
   para qualquer modelo daquele módulo — cada parâmetro tem nome e offset
   fixos, independente de qual modelo está selecionado. Ex.: DS sempre
   tem Gain/Level/Bass/Middle/Treble/Reso/Pres/Bright, seja "TS8" ou
   "BIG-MUFF" (confirmado testando 3 modelos bem diferentes).

2) "POSICIONAIS" (WAH, FX, GATE, MOD, DLY): cada módulo reserva um bloco
   fixo de N slots u16 consecutivos (ex.: FX = 8 slots a partir de 0x5A),
   mas o SIGNIFICADO de cada slot depende do modelo escolhido (ex.: no FX
   "Compress" o slot 0 é "Sustain", mas em outro modelo poderia ser outra
   coisa). Isso bate exatamente com o formato "param1..paramN" que a IA já
   usa para esses módulos (ver app.py) — slot Nº do param = posição na
   lista "params" do modelo em data/mk300_models.json. Time/Fb/Mix do DLY,
   por exemplo, SEMPRE ficam nos slots 0/1/2 (offsets 0x102/0x104/0x106)
   não importa o modelo, e os slots extras variam.

Isso foi confirmado lendo o preset real com cada modelo selecionado no
M-EFCS e comparando o rótulo/posição de cada knob mostrado na tela com os
bytes correspondentes (e, para os casos mais importantes, com diff binário
1-parâmetro-por-vez).
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

# ────────────────────────────────────────────────────────────────────
# Módulos "FIXOS": mesmo layout de parâmetros para qualquer modelo.
# ────────────────────────────────────────────────────────────────────
PARAM_OFFSETS = {
    "AMP": {"gain": 0xA2, "level": 0xA4, "bass": 0xA6, "middle": 0xA8, "treble": 0xAA, "presence": 0xAE},
    # DS: confirmado em 2026-09-03 que TODOS os 40 modelos usam o MESMO
    # layout fixo de 8 knobs (testado em 2TS8, RAT e BIG-MUFF - os 3
    # mostraram exatamente os mesmos 8 rótulos/posições). Os bytes 0x8A-0x98
    # bateram direto com os valores mostrados na tela (30/70/51/50/50/0/88/85),
    # sem precisar de diff. Antes só gain/level/tone (~metade errada: o que
    # existe em 0x92 é "Treble", não um "Tone" genérico) estavam mapeados.
    "DS": {
        "gain": 0x8A, "level": 0x8C, "bass": 0x8E, "middle": 0x90,
        "treble": 0x92, "reso": 0x94, "pres": 0x96, "bright": 0x98,
    },
    # CAB "low_cut"/"high_cut" confirmados em 2026-09-03 via diff binario lendo
    # o preset [003] JM-DS direto do M-EFCS: bytes 0xB6-0xB9 sao sempre zero,
    # 0xBA=Level, 0xBC=Low Cut (inteiro puro), 0xBE=High Cut (inteiro/10 =
    # valor em kHz mostrado na UI, ex.: raw 94 -> "9.4K").
    "CAB": {"level": 0xBA, "low_cut": 0xBC, "high_cut": 0xBE},
    "VOL": {"volume": 0x132},
    # REV: confirmado em 2026-09-03 que Hall, Hall stereo E Room usam o MESMO
    # layout fixo de 5 knobs (Decay/Mix/High Pass/Low Pass/Mod Depth) -
    # assume-se que os outros 15 modelos da lista tambem usam, ja que REV
    # segue o padrao "fixo" (como AMP/CAB/DS), nao o "posicional".
    "REV": {"decay": 0x11A, "mix": 0x11C, "high_pass": 0x11E, "low_pass": 0x120, "mod_depth": 0x122},
    # EQ (modulo de cadeia da aba "Effect", DIFERENTE do "Master EQ" da aba
    # superior - o Master EQ foi confirmado por diff como 100% fora do bloco
    # de 448 bytes do preset). Confirmado so para "Guitar EQ 6" (6 bandas).
    # "Bass EQ 7" e "Normal EQ 10" tem bandas extras nao mapeadas.
    "EQ": {"100hz": 0xD2, "200hz": 0xD4, "400hz": 0xD6, "800hz": 0xD8, "1.6khz": 0xDA, "3.2khz": 0xDC},
}

# Metadados para chaves de PARAM_OFFSETS que NAO seguem o padrao simples
# "u16 sem sinal, valor gravado = valor exibido".
PARAM_META = {
    ("EQ", "100hz"): {"signed": True, "scale": 2},
    ("EQ", "200hz"): {"signed": True, "scale": 2},
    ("EQ", "400hz"): {"signed": True, "scale": 2},
    ("EQ", "800hz"): {"signed": True, "scale": 2},
    ("EQ", "1.6khz"): {"signed": True, "scale": 2},
    ("EQ", "3.2khz"): {"signed": True, "scale": 2},
}

# ────────────────────────────────────────────────────────────────────
# Módulos "POSICIONAIS": bloco fixo de N slots u16 a partir de BASE;
# o significado de cada slot depende do modelo (param1..paramN, na mesma
# ordem da lista "params" do modelo em data/mk300_models.json).
# ────────────────────────────────────────────────────────────────────
POSITIONAL_BASE = {
    "WAH": 0x42,   # confirmado (Cry-Wah: Value/Gain/Level)
    "FX": 0x5A,    # confirmado (Compress: Sustain/Attack/Wet Level/Blend)
    "GATE": 0x72,  # confirmado (Pro Gate: Att/Rel/Thd/Kw/Ratio)
    "MOD": 0xEA,   # confirmado (Phaser: Speed/MidCut/Reso/Fb)
    "DLY": 0x102,  # confirmado (Duck: Time/Fb/Mix/Release/Speed/Depth;
                   # Time/Fb/Mix tambem confirmados nos slots 0/1/2 em
                   # todos os outros modelos DLY testados)
}
POSITIONAL_MAX_SLOTS = {"WAH": 7, "FX": 8, "GATE": 8, "MOD": 6, "DLY": 6}

# Rótulos de parâmetro que exigem tratamento especial (signed e/ou escala),
# aplicados pelo NOME do rótulo (vindo da lista "params" do modelo em
# data/mk300_models.json), não pela posição crua — assim funciona em
# qualquer modelo que tenha um parâmetro com esse nome.
#   - "Thd" (threshold, em dB): confirmado SIGNED no GATE "Pro Gate", e com
#     ESCALA raw = valor/2 (ou seja, valor_exibido = raw*2) — testado em
#     2026-09-03 via import real no M-EFCS: gravamos raw=-15 (sem escala) e
#     a UI mostrou "-30" no knob Thd. Ou seja, pra fazer a UI mostrar o
#     número que a IA pediu (ex.: -30), o valor gravado tem que ser a
#     METADE (scale=0.5) — igual em espírito à escala das bandas de EQ, só
#     que na direção oposta (lá é raw=dB*2, aqui é raw=valor_exibido/2).
#     Assume-se o mesmo para outros modelos com um campo "Thd" (Soft Gate,
#     Hard Gate, Compress Pro, F Compress), já que semanticamente é sempre
#     um limiar em dB.
#   - "Speed" do MOD: confirmado escala raw = valor*10 apenas no "Phaser",
#     pra valores baixos (Speed exibido "4.0" = raw 40). ATENÇÃO: em
#     2026-09-03, testar Speed=40 (raw 400) fez a UI mostrar "1/16"
#     (notação de subdivisão rítmica) em vez de um número — sinal de que em
#     valores altos o campo pode entrar num modo de exibição diferente
#     (sync/tap tempo); a fórmula exata acima de ~raw 100-150 não está
#     clara ainda, usar com cautela nesse range. NÃO aplicamos escala a
#     "Speed" de outros módulos (ex.: DLY) pois não foi testado lá.
POSITIONAL_LABEL_META = {
    ("GATE", "Thd"): {"signed": True, "scale": 0.5},
    ("FX", "Thd"): {"signed": True, "scale": 0.5},
    ("MOD", "Speed"): {"scale": 10},
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


def _clamp_i16(value) -> int:
    """Como _clamp_u16, mas para campos SIGNED (int16 complemento de dois,
    ex.: GATE/FX Thd, bandas de EQ). Satura em -32768..32767 e devolve o
    valor já convertido para o padrão de bits u16 (0..65535), pronto pra
    gravar nos 2 bytes little-endian."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        v = 0
    v = max(-32768, min(32767, v))
    return v & 0xFFFF


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


def build_dzh(tone_data: dict, preset_name: str, amp_types: list, cab_types: list,
              ds_types: list, rev_types: list = None, positional_models: dict = None):
    """Recebe o JSON retornado pela análise de timbre (mesmo formato usado no
    front-end: uma chave por módulo com {enabled, params}) e devolve
    (bytes_do_dzh, lista_de_avisos), baseado no preset-template real.

    amp_types / cab_types / ds_types / rev_types: listas simples de nomes
    reais de modelo (na ordem exata do firmware), para os módulos "fixos".

    positional_models: dict {"WAH": [...], "FX": [...], "GATE": [...],
    "MOD": [...], "DLY": [...]}, cada um uma lista de dicts
    {"name": str, "params": [str, ...] ou None} — vem de data/mk300_models.json
    (WAH_MODELS/FX_MODELS/GATE_MODELS/MOD_MODELS/DLY_MODELS em app.py).
    Usado tanto para escolher o índice do modelo (TYPE_OFFSET) quanto para
    saber quantos slots posicionais escrever e com qual rótulo (pra aplicar
    POSITIONAL_LABEL_META corretamente).

    Avisos são gerados quando um "type" não bate com nenhum modelo real
    conhecido (mantém o valor do template) ou quando bateu por aproximação.
    """
    rev_types = rev_types or []
    positional_models = positional_models or {}

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

    # ── Modelo (type) dos módulos "fixos": AMP / CAB / DS / REV ──────
    type_lists = {"AMP": amp_types, "CAB": cab_types, "DS": ds_types, "REV": rev_types}
    for mod, names in type_lists.items():
        if not names:
            continue
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

    # ── Parâmetros numéricos dos módulos "fixos" ─────────────────────
    for mod, param_map in PARAM_OFFSETS.items():
        info = tone_data.get(mod) or {}
        values = info.get("params") or {}
        for key, offset in param_map.items():
            if key in values:
                meta = PARAM_META.get((mod, key), {})
                scaled = values[key] * meta.get("scale", 1)
                v = _clamp_i16(scaled) if meta.get("signed") else _clamp_u16(scaled)
                buf[offset] = v & 0xFF
                buf[offset + 1] = (v >> 8) & 0xFF

    # ── Modelo (type) + parâmetros posicionais: WAH / FX / GATE / MOD / DLY ──
    for mod, models in positional_models.items():
        if not models or mod not in POSITIONAL_BASE:
            continue
        names = [m["name"] for m in models]
        info = tone_data.get(mod) or {}
        params = info.get("params") or {}
        type_name = params.get("type")
        matched, idx = _match_type(type_name, names)
        if matched is None:
            if type_name:
                warnings.append(f'{mod}: modelo "{type_name}" não reconhecido — mantido o modelo que já estava no preset-modelo.')
            continue

        buf[TYPE_OFFSET + MODULE_CANONICAL_ID[mod]] = idx & 0xFF
        if matched != type_name:
            warnings.append(f'{mod}: "{type_name}" interpretado como "{matched}" (correspondência aproximada).')

        model_entry = models[idx]
        labels = model_entry.get("params") or []
        base = POSITIONAL_BASE[mod]
        max_slots = min(len(labels), POSITIONAL_MAX_SLOTS.get(mod, len(labels)))
        for pos in range(max_slots):
            slot_key = f"param{pos + 1}"
            if slot_key not in params:
                continue
            label = labels[pos]
            meta = POSITIONAL_LABEL_META.get((mod, label), {})
            scaled = params[slot_key] * meta.get("scale", 1)
            v = _clamp_i16(scaled) if meta.get("signed") else _clamp_u16(scaled)
            offset = base + pos * 2
            buf[offset] = v & 0xFF
            buf[offset + 1] = (v >> 8) & 0xFF

    return bytes(buf), warnings


def safe_filename(preset_name: str) -> str:
    safe = "".join(c for c in (preset_name or "") if c.isalnum() or c in " -_").strip()
    return (safe or "preset").replace(" ", "_")
