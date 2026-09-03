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
from flask import Flask, request, jsonify, render_template, send_file
import io
from dzh_export import build_dzh, safe_filename
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

# ─────────────────────────────────────────────
# LISTAS REAIS DE MODELOS (extraídas do manual oficial da M-VAVE MK-300)
# Carregadas de data/mk300_models.json — a "memória" persistente do projeto —
# em vez de ficarem hardcoded aqui. Usadas no prompt da IA (texto), no schema
# do Gemini (enum) e no export de .dzh (para converter o nome do modelo de
# volta em índice binário). Ver também presets/ para os .dzh reais usados
# para descobrir e confirmar o formato binário.
# ─────────────────────────────────────────────

def _load_mk300_data():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mk300_models.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_MK300_DATA = _load_mk300_data()

AMP_TYPES = _MK300_DATA["amp_guitar"] + _MK300_DATA["amp_bass"]
CAB_TYPES = _MK300_DATA["cab"]
DS_TYPES = [item["name"] for item in _MK300_DATA["ds"]]
# DS: confirmado em 2026-09-03 que todos os modelos usam o MESMO layout fixo
# de 8 knobs (Gain/Level/Bass/Middle/Treble/Reso/Pres/Bright) - ver
# data/mk300_models.json -> "ds_params" / "ds_offsets_confirmed".
DS_PARAMS = _MK300_DATA.get("ds_params") or ["Gain", "Level", "Bass", "Middle", "Treble", "Reso", "Pres", "Bright"]
REV_TYPES = [m["name"] for m in _MK300_DATA.get("rev", [])]

# WAH/FX/GATE/MOD/DLY: cada modelo real tem seu PRÓPRIO conjunto de parâmetros
# (ex.: "X-Wah" usa Value/Gain/Level, mas "Wah-Wah" usa Speed/Q/Mix/Width/
# Level/Sync/Sync Bpm). Para caber num schema fixo, usamos slots posicionais
# genéricos param1..paramN (N = maior nº de parâmetros entre os modelos da
# categoria) — o significado de cada slot depende do modelo escolhido, e essa
# tradução (slot -> nome real) é o que os dicionários *_MODELS abaixo guardam,
# usada tanto no prompt da IA quanto no front-end para mostrar o rótulo certo.
# DLY entrou nessa mesma categoria em 2026-09-03: a lista antiga (Analog/
# Digital/Tape/Mod/None) era FICTÍCIA — substituída pela lista real de 27
# modelos lida diretamente do dropdown do M-EFCS (ver data/mk300_models.json
# -> "dly" e presets/README.md).
WAH_MODELS = _MK300_DATA["wah"]
FX_MODELS = _MK300_DATA["fx"]
GATE_MODELS = _MK300_DATA["gate"]
MOD_MODELS = _MK300_DATA["mod"]
DLY_MODELS = _MK300_DATA.get("dly") or []

WAH_TYPES = [m["name"] for m in WAH_MODELS]
FX_TYPES = [m["name"] for m in FX_MODELS]
GATE_TYPES = [m["name"] for m in GATE_MODELS]
MOD_TYPES = [m["name"] for m in MOD_MODELS]
DLY_TYPES = [m["name"] for m in DLY_MODELS]

MAX_PARAMS = {
    "WAH": max(len(m["params"]) if m.get("params") else 0 for m in WAH_MODELS),
    "FX": max(len(m["params"]) if m.get("params") else 0 for m in FX_MODELS),
    "GATE": max(len(m["params"]) if m.get("params") else 0 for m in GATE_MODELS),
    "MOD": max(len(m["params"]) if m.get("params") else 0 for m in MOD_MODELS),
    "DLY": max((len(m["params"]) if m.get("params") else 0 for m in DLY_MODELS), default=6),
}

TYPE_ENUMS = {
    "AMP": AMP_TYPES, "CAB": CAB_TYPES, "DS": DS_TYPES,
    "WAH": WAH_TYPES, "FX": FX_TYPES, "GATE": GATE_TYPES, "MOD": MOD_TYPES,
    "DLY": DLY_TYPES, "REV": REV_TYPES,
}

# Passado para dzh_export.build_dzh() para os módulos "posicionais" (ver
# comentário no topo de dzh_export.py) — cada entrada é a lista de dicts
# {"name", "params"} de data/mk300_models.json, usada tanto pra achar o
# índice do modelo quanto pra saber o rótulo de cada slot param1..paramN.
POSITIONAL_MODELS = {
    "WAH": WAH_MODELS, "FX": FX_MODELS, "GATE": GATE_MODELS,
    "MOD": MOD_MODELS, "DLY": DLY_MODELS,
}


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
- WAH: { type: string, param1..param7: int }  (significado de cada slot depende do modelo — ver TIPOS VÁLIDOS)
- FX: { type: string, param1..param8: int }  (significado de cada slot depende do modelo — ver TIPOS VÁLIDOS)
- GATE: { type: string, param1..param8: int }  (significado de cada slot depende do modelo — ver TIPOS VÁLIDOS)
- DS: { type: string, gain: int, level: int, bass: int, middle: int, treble: int, reso: int, pres: int, bright: int }  (os 8 knobs são os MESMOS pra qualquer modelo de DS)
- AMP: { type: string, gain: int, bass: int, middle: int, treble: int, level: int, presence: int }
- CAB: { type: string, level: int }  (mic já está embutido no nome do gabinete)
- EQ: { bass: int, low_mid: int, mid: int, high_mid: int, treble: int, level: int }
- MOD: { type: string, param1..param6: int }  (significado de cada slot depende do modelo — ver TIPOS VÁLIDOS)
- DLY: { type: string, param1..param6: int }  (significado de cada slot depende do modelo — ver TIPOS VÁLIDOS; param1/param2/param3 são SEMPRE Time/Fb/Mix em todos os modelos)
- REV: { type: string, decay: int, mix: int, high_pass: int, low_pass: int, mod_depth: int }  (os 5 knobs são os MESMOS pra qualquer modelo de REV)
- VOL: { volume: int }

TIPOS VÁLIDOS (extraídos do manual oficial da M-VAVE MK-300 — use SOMENTE estes valores,
pois são os nomes REAIS gravados na pedaleira física; qualquer outro nome não existirá no
equipamento do usuário):

- WAH (6 modelos reais, cada um com seus PRÓPRIOS parâmetros — envie sempre os
  7 slots param1..param7, preenchendo somente os que o modelo usa e os demais com 0):
    * "X-Wah": param1=Value, param2=Gain, param3=Level
    * "Funk-Wah": param1=Value, param2=Gain, param3=Level
    * "Slide-Wah": param1=Value, param2=Gain, param3=Level
    * "Cry-Wah": param1=Value, param2=Gain, param3=Level
    * "Wah-Wah": param1=Speed, param2=Q, param3=Mix, param4=Width, param5=Level, param6=Sync (0=desligado, 1=ligado), param7=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Sense-Wah": param1=Sense, param2=Attack, param3=Q, param4=fPeak, param5=Mix, param6=Width, param7=Level

- FX (14 modelos reais, cada um com seus PRÓPRIOS parâmetros — envie sempre os
  8 slots param1..param8, preenchendo somente os que o modelo usa e os demais com 0):
    * "Lofi": param1=Bit, param2=Level, param3=Filter
    * "Pitch shifter": param1=Semi (faixa -24 a 24 semitons)
    * "Boost": param1=Gain, param2=Level
    * "A Boost": param1=Gain, param2=Bass, param3=Mid, param4=Treble, param5=Level
    * "E Boost": param1=Gain, param2=Bass, param3=Mid, param4=Treble, param5=Level
    * "B Boost": param1=Gain, param2=Bass, param3=Mid, param4=Treble, param5=Level
    * "Boost ED": param1=Gain, param2=Grit, param3=Level
    * "Compress": param1=Sustain, param2=Attack, param3=Wet Level, param4=Blend
    * "Compress Pro": param1=Ratio, param2=Gain, param3=Knee, param4=Thd, param5=Attack, param6=Wet Level, param7=Blend
    * "F Compress": param1=Ratio, param2=Gain, param3=Knee, param4=Thd, param5=Attack, param6=Tone, param7=Wet Level, param8=Blend
    * "Pitch": param1=High Pitch, param2=Low Pitch, param3=High Level, param4=Low Level, param5=Dry Level
    * "Octave": param1=High Level, param2=Low Level, param3=Dry Level
    * "Ring": param1=Freq, param2=Mix
    * "Whammy": SEM PARÂMETROS CONFIRMADOS — envie todos os slots como 0 (modelo novo, use com cautela)

- GATE (9 modelos reais, cada um com seus PRÓPRIOS parâmetros — envie sempre os
  8 slots param1..param8, preenchendo somente os que o modelo usa e os demais com 0):
    * "AI Gate": param1=Gate, param2=Bias
    * "AI Ms Gate Gen2": param1=Gate, param2=Bias
    * "AI Ms Gate": param1=Gate, param2=Bias
    * "Soft Gate": param1=Thd
    * "Hard Gate": param1=Thd
    * "Pro Gate": param1=Att, param2=Rel, param3=Thd, param4=Kw, param5=Ratio
    * "Compress": param1=Sustain, param2=Attack, param3=Wet Level, param4=Blend
    * "Compress Pro": param1=Ratio, param2=Gain, param3=Knee, param4=Thd, param5=Attack, param6=Wet Level, param7=Blend
    * "F Compress": param1=Ratio, param2=Gain, param3=Knee, param4=Thd, param5=Attack, param6=Tone, param7=Wet Level, param8=Blend

- DS (Drive/Distortion, 40 modelos reais, use EXATAMENTE o nome do modelo escolhido como "type".
  TODO modelo de DS usa os MESMOS 8 knobs — gain/level/bass/middle/treble/reso/pres/bright
  (confirmado testando 3 modelos bem diferentes no equipamento real):
    * Overdrive: "BLUES_OD", "TS8", "M-VAVE_OD", "M-VAVE_TS1", "M-VAVE_TS2", "JHS_1", "TS-9", "BD", "SuperOD", "BLUES_DR", "Black-BOX"
    * Distortion: "DS1", "DS2", "M-VAVE_DS", "RAT", "RAT_BT", "JHS_2", "MT_1", "MT_2", "TDS", "XC_DS", "QC_DS", "HIGAIN", "BIG-DR", "M90S", "M2000", "DS800", "DS900", "MAR-DS", "BOG_DS", "SONDO", "RED_DS", "MODEN_DS", "PLX"
    * Boost: "SUPA_1", "SUPA_2", "M-BOOSTER", "CL_BOOST", "MID-BOST", "BIG-MUFF"
- AMP (Guitarra — 100 modelos reais; use estes quando o timbre for de guitarra):
    "J120_CL", "J900_OD", "J900_DS", "J900_HV", "M_BLUES", "HORIZON", "M-VAVE_DS", "ROOM40",
    "FD1_BR", "JOY_OD", "M-VAVE_TS3", "MT100 LEAD", "RAT_CL", "RAT_CR", "RAT_DS", "MES_RED",
    "FD_CH1", "FD_CH1_HOT", "MT80 CL", "M_SUPER OD", "J800_CL_1960", "J800_CL_AMP", "J800_OD",
    "J800_DS", "JOHNS_CH1", "DARK_OD", "DARK_OD2", "DARK_DS", "VXO_CL", "VXO_OD", "VXO_OD2",
    "VXO_OD3", "OR_CL", "OR_CRUNCH", "HIGIAN", "HIGIAN_RED", "COOL_CL", "JVMcrunch", "JV410_BOOST",
    "AXE", "MES_CH1", "M-VAVE_DS3", "M-VAVE_DS4", "M-VAVE LEAD", "LANY_CH1", "LANY_CH1_BR",
    "LANY_CH2_OD", "LANY_CH3_DS", "ROLANS_CL", "ROLANS_DS", "ROLANS_TDS", "BOOSS_METEL",
    "J900_CH1", "J900_CH2", "JVM_OD_FG", "JVM_DS_FG", "RADAL_CL_FG", "RADAL_DS", "RADAL_TDS",
    "RADAL_HDS", "DUMBLE_FG", "JAZZ_OD", "M-VAVE_TS1", "M-VAVE_TS2", "EHV5150_CH1", "EHV5150_CH2",
    "EHV5150_DS", "EHV5150_MT", "XC_CL", "XC_OD", "XC_DS", "XC_HV", "J2000_CL_FG", "J2000_CR_FG",
    "J2000_TR_FG", "J2000_DS_FG", "J900_CL_57", "J900_DS_57", "MAR_METEL", "MAR_HV", "WS_JZCL_57",
    "OR_CL_ECM", "OR_CRUNCH", "OR_SWEET", "BOG_LEAD", "BOG_LEAD2", "BOG_LEAD3", "BOG_SOLO",
    "MATTER_DS", "UK_DS", "JHS_DS", "JHS_TDS", "M-VAVE_HOT", "M-VAVE_RED", "M-VAVE_MT",
    "M-VAVE_BST", "MES_CH2_57", "MES_CH2_AMP", "MES_CH3_57", "MES_CH3_AMP"
- AMP (Baixo — 20 modelos reais; use estes quando o timbre for de baixo elétrico):
    "AgDb750_BS", "ApSVT_BS", "DgM900_BS", "FenRum_BS", "GkF550_BS", "HkeHd50_BS", "MarkLm_BS",
    "OrgAd_BS", "PjBuddy_BS", "RolDb_BS", "Mb400C1_BS", "Mb400C2_BS", "DgXu_BS", "ApSp_BS",
    "Mar50_BS", "Mark500_BS", "PjbCub_BS", "Tc21Vt_BS", "WatMod_BS", "GKL800_BS"
- CAB (100 gabinetes/IRs reais — o microfone já está embutido em cada nome, não existe
  parâmetro separado de "mic"):
    "AC-SeVin", "JVM_1960_57", "JVM_G12_ECM", "DELUXE REV", "BOG_57", "FD120_7B", "HESS_212DM",
    "HESS_212VTY", "HIW412SWF", "MAR1960_412", "MESA_412_57", "MESA_412_ECM", "WANGS112_ECM",
    "WANGS212_ECM", "V30_MC834", "V30_MD421", "VOX_AC30", "FD_TW1971", "FD_TW1980", "FD_TW1988",
    "FD_TW2000", "M160_Center", "MD421_Center", "Chug_L", "Chug_R", "EV_MIX_B", "G12-EVH",
    "G12-EVH_CT", "G12-EVH_i5", "G12-EVH_m160", "Marshall_Box", "BGN412V30", "MESA_LS", "MESA_CS",
    "MESA_HS", "Recto_112", "FRMAN112", "OR_112", "HIFI_OK", "Ranll_412", "OR_V30_212",
    "OR_G75_212", "RE_SUPER_412", "EGNL01_412", "EGNL02_412", "EGNL03_412", "MeOSick-II",
    "MeOSick-III", "MesaOSick-I", "SoldHor", "SoldSC412", "AC-SeTV20", "Pey5150", "MRSH03",
    "VA5153", "AC-EmG212", "AC-Se210", "CeleAt", "AC-SeGol", "AC-CateEx", "AC-CateFw", "DieV30",
    "EAGLProV30s", "Sperimental", "Peavey115", "Peavey112", "VxAc15", "FimanVt", "FenDeluX",
    "FenProJ", "Alton212", "OgP412", "OgV30", "HaBtonV", "MarMfour", "Elctrovoice", "J120Rolnd",
    "MessOS", "Mar60AV", "WS212_57", "Agula410", "AmpgSVT410", "AmpgSVT810", "AshB115",
    "Bareface110", "Bstert 115", "DavEendD410", "DgD210C", "DgDG212N", "FdBman410", "FdBmanSf210",
    "GKRB410A", "GKRB410B", "Hark410", "MbSubway210", "OgOBC212", "Pey115", "RanRB100", "SR115",
    "Tace412"
- MOD (20 modelos reais, cada um com seus PRÓPRIOS parâmetros — envie sempre os
  6 slots param1..param6, preenchendo somente os que o modelo usa e os demais com 0):
    * "Chorus": param1=Speed, param2=Depth, param3=Mix, param4=Sync (0=desligado, 1=ligado), param5=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Tri Chorus": param1=Speed, param2=Depth, param3=Mix, param4=Sync (0=desligado, 1=ligado), param5=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Flanger": param1=Speed, param2=Depth, param3=Fb, param4=Mix, param5=Sync (0=desligado, 1=ligado), param6=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Tri Flanger": param1=Speed, param2=Depth, param3=Fb, param4=Mix, param5=Sync (0=desligado, 1=ligado), param6=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Tremolo": param1=Speed, param2=Depth, param3=Level, param4=Sync (0=desligado, 1=ligado), param5=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Tri Tremolo": param1=Speed, param2=Depth, param3=Level, param4=Sync (0=desligado, 1=ligado), param5=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Opto Tremolo": param1=Speed, param2=Depth, param3=Level, param4=Sync (0=desligado, 1=ligado), param5=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Phaser": param1=Speed, param2=MidCut, param3=Reso, param4=Fb, param5=Sync (0=desligado, 1=ligado), param6=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Vibrato": param1=Speed, param2=Depth, param3=Mix, param4=Sync (0=desligado, 1=ligado), param5=Sync Bpm (faixa 40-240, só relevante se Sync=1)
    * "Autofilter": param1=Speed, param2=Min, param3=Max, param4=Mix, param5=Fb
    * "Univibe": param1=Speed, param2=Depth, param3=Mix
    * "Tri Vibrato", "Opto Vibrato", "Tri Univibe": use a MESMA lista de parâmetros do modelo base sem "Tri"/"Opto" (ex.: Tri Vibrato = Vibrato)
    * "Phaser Stereo", "Flanger Stereo", "Vibe Stereo", "Chorus Stereo", "Tremolo Stereo", "Vibrato Stereo": use a MESMA lista de parâmetros do modelo mono correspondente (ex.: Chorus Stereo = Chorus; Vibe Stereo = Univibe)

- DLY (27 modelos reais, cada um com seus PRÓPRIOS parâmetros — envie sempre os
  6 slots param1..param6, preenchendo somente os que o modelo usa e os demais com 0.
  param1=Time, param2=Fb, param3=Mix SEMPRE, em TODOS os modelos):
    * "Clean", "Echo", "Analog", "PingPong Stereo": só param1=Time, param2=Fb, param3=Mix
    * "Modern", "Reverse": param1=Time, param2=Fb, param3=Mix, param4=Phaser, param5=Mod
    * "Duck": param1=Time, param2=Fb, param3=Mix, param4=Release, param5=Speed, param6=Depth
    * "Dtype", "Lofi": param1=Time, param2=Fb, param3=Mix, param4=Grit, param5=Speed, param6=Depth
    * "Tremolo", "Pattern": param1=Time, param2=Fb, param3=Mix, param4=Pattern, param5=Speed, param6=Depth
    * "Filter": param1=Time, param2=Fb, param3=Mix, param4=Filter, param5=Speed, param6=Depth
    * "Dual": param1=Time, param2=Fb, param3=Mix, param4=T-Mode, param5=Speed, param6=Depth
    * "Ice": param1=Time, param2=Fb, param3=Mix, param4=Pitch, param5=Mod
    * Qualquer modelo "X Stereo" (Clean Stereo, Modern Stereo, Echo Stereo, Analog Stereo, Duck Stereo,
      Dtype Stereo, Tremolo Stereo, Filter Stereo, Dual Stereo, Lofi Stereo, Pattern Stereo, Ice Stereo,
      Reverse Stereo): use a MESMA lista de parâmetros do modelo mono "X" correspondente (confirmado
      que Duck Stereo == Duck; os demais seguem o mesmo padrão)

- REV (18 modelos reais — TODO modelo usa os MESMOS 5 knobs: decay, mix, high_pass, low_pass, mod_depth,
  não use param1..paramN aqui, os nomes já são fixos):
    "Room", "Hall", "Plate", "Spring", "Shimmer", "Bloom", "Cloud", "Lofi", "Swell",
    "Room stereo", "Hall stereo", "Plate stereo", "Spring stereo", "Shimmer stereo",
    "Bloom stereo", "Cloud stereo", "Lofi stereo", "Swell stereo"

OBSERVAÇÃO IMPORTANTE: DS, AMP, CAB, WAH, FX, GATE, MOD, DLY e REV agora têm listas oficiais e
completas de modelos reais (lidas diretamente do equipamento físico via app oficial, não do
manual — o manual estava incompleto/errado para vários desses módulos) — use EXATAMENTE os
nomes e o mapa de parâmetros mostrados acima para cada um, copiando o nome do modelo caractere
por caractere (sem mudar maiúsculas/minúsculas, espaços ou hífens). Só o EQ (bandas de graves/
agudos) não tem "type" — é sempre o mesmo conjunto fixo de parâmetros.

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
        # WAH/FX/GATE/MOD/DLY usam slots posicionais genéricos (param1..paramN)
        # porque cada modelo real tem seu próprio conjunto de parâmetros — ver
        # MAX_PARAMS e TIPOS VÁLIDOS no SYSTEM_PROMPT para o mapa slot -> nome
        # real por modelo. AMP/CAB/DS/REV têm layout FIXO (mesmos parâmetros
        # não importa o modelo) — ver dzh_export.py para a explicação completa
        # das duas famílias de módulo.
        pedal_params = {
            "WAH": ["type"] + [f"param{i}" for i in range(1, MAX_PARAMS["WAH"] + 1)],
            "FX": ["type"] + [f"param{i}" for i in range(1, MAX_PARAMS["FX"] + 1)],
            "GATE": ["type"] + [f"param{i}" for i in range(1, MAX_PARAMS["GATE"] + 1)],
            # DS: confirmado em 2026-09-03 que todo modelo usa os MESMOS 8 knobs.
            "DS": ["type", "gain", "level", "bass", "middle", "treble", "reso", "pres", "bright"],
            "AMP": ["type", "gain", "bass", "middle", "treble", "level", "presence"],
            "CAB": ["type", "level"],
            "EQ": ["bass", "low_mid", "mid", "high_mid", "treble", "level"],
            "MOD": ["type"] + [f"param{i}" for i in range(1, MAX_PARAMS["MOD"] + 1)],
            "DLY": ["type"] + [f"param{i}" for i in range(1, MAX_PARAMS["DLY"] + 1)],
            # REV: confirmado em 2026-09-03 que Hall/Hall stereo/Room usam os
            # MESMOS 5 knobs — nomes reais da UI (não "pre_delay", que não existe).
            "REV": ["type", "decay", "mix", "high_pass", "low_pass", "mod_depth"],
            "VOL": ["volume"]
        }

        param_types = {
            "type": "STRING",
            "gain": "INTEGER", "bass": "INTEGER", "middle": "INTEGER",
            "treble": "INTEGER", "presence": "INTEGER", "low_mid": "INTEGER", "mid": "INTEGER",
            "high_mid": "INTEGER", "level": "INTEGER", "mix": "INTEGER", "decay": "INTEGER",
            "volume": "INTEGER", "reso": "INTEGER", "pres": "INTEGER", "bright": "INTEGER",
            "high_pass": "INTEGER", "low_pass": "INTEGER", "mod_depth": "INTEGER",
        }
        for i in range(1, max(MAX_PARAMS.values()) + 1):
            param_types[f"param{i}"] = "INTEGER"

        # Listas REAIS de modelos definidas no topo do arquivo (AMP_TYPES/CAB_TYPES/DS_TYPES/TYPE_ENUMS)

        for p, keys in pedal_params.items():
            param_props = {}
            for k in keys:
                prop = {"type": param_types[k]}
                if k == "type" and p in TYPE_ENUMS:
                    prop["enum"] = TYPE_ENUMS[p]
                param_props[k] = prop
            schema["properties"][p] = {
                "type": "OBJECT",
                "properties": {
                    "enabled": {"type": "BOOLEAN"},
                    "params": {
                        "type": "OBJECT",
                        "properties": param_props,
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


@app.route("/api/export-dzh", methods=["POST"])
def export_dzh():
    """Gera um arquivo .dzh pronto para carregar na MK-300, a partir do
    resultado de uma análise de timbre (mesmo JSON usado no front-end).

    Desde 2026-09-03, TODOS os 11 módulos têm seu modelo (type) e seus
    parâmetros numéricos gravados no binário — AMP/CAB/DS/REV/VOL/EQ usam
    layout fixo (mesmos parâmetros pra qualquer modelo), e WAH/FX/GATE/MOD/
    DLY usam layout posicional (param1..paramN, onde o significado de cada
    slot depende do modelo escolhido — ver dzh_export.py). O liga/desliga
    (bypass) é gravado para os 11 módulos. Um parâmetro que a IA não enviar
    (ou um nome de modelo não reconhecido) mantém o valor do preset-modelo,
    então o arquivo gerado é sempre um preset válido.
    """
    data = request.get_json(silent=True) or {}
    tone_data = data.get("tone_data")
    preset_name = data.get("preset_name") or "MK300_PRESET"

    if not tone_data or not isinstance(tone_data, dict):
        return jsonify({"error": "Dados do preset ausentes ou inválidos."}), 400

    try:
        dzh_bytes, warnings = build_dzh(
            tone_data, preset_name, AMP_TYPES, CAB_TYPES, DS_TYPES,
            rev_types=REV_TYPES, positional_models=POSITIONAL_MODELS,
        )
    except FileNotFoundError:
        return jsonify({"error": "Arquivo-modelo do preset (assets/base_preset.dzh) não encontrado no servidor."}), 500
    except Exception as e:
        return jsonify({"error": f"Erro ao gerar o arquivo .dzh: {str(e)}"}), 500

    filename = f"{safe_filename(preset_name)}.dzh"
    response = send_file(
        io.BytesIO(dzh_bytes),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=filename,
    )
    if warnings:
        # Cabeçalho custom (não são dados sensíveis) para o front-end avisar o
        # usuário sem precisar de uma segunda requisição — ex.: quando o
        # provedor de IA (Groq/OpenAI, sem enum) devolveu um nome de modelo
        # que não bateu exatamente com a lista real do fabricante.
        response.headers["X-Dzh-Warnings"] = json.dumps(warnings, ensure_ascii=True)
    return response


@app.route("/api/effects", methods=["GET"])
def api_get_effects():
    """Catálogo de efeitos reais da MK-300, para o front-end mostrar o nome
    certo de cada parâmetro conforme o modelo selecionado (WAH/FX/GATE/MOD/DLY
    têm parâmetros diferentes por modelo — ver data/mk300_models.json)."""
    response = jsonify({
        "wah": WAH_MODELS,
        "fx": FX_MODELS,
        "gate": GATE_MODELS,
        "mod": MOD_MODELS,
        "dly": DLY_MODELS,
        "rev": REV_TYPES,
        "ds_params": DS_PARAMS,
        "max_params": MAX_PARAMS,
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


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
