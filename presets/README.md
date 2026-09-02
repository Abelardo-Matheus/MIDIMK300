# Biblioteca local de presets `.dzh`

Arquivos reais exportados da MK-300, usados para descobrir e confirmar o
formato binário do `.dzh` (veja `dzh_export.py` na raiz do projeto para o
mapeamento de offsets resultante). Guardados aqui como referência e como
material de teste — não são carregados automaticamente pelo app.

| Arquivo | O que mudou em relação ao `base_original_JMDS.dzh` |
|---|---|
| `base_original_JMDS.dzh` | Preset original, ponto de partida de todos os testes. |
| `teste_amp_gain.dzh` | Só o Gain do AMP mudou (39 → 100). |
| `teste_amp_VXO_CL.dzh` | Só o modelo do AMP mudou (J800_DS → VXO_CL). |
| `teste_cab_off.dzh` | Só o módulo CAB foi desligado (bypass). |
| `teste_amp_full.dzh` | Bass=13, Middle=67, Treble=82, Level=24, Presence=91 no AMP. |
| `teste_ds_full.dzh` | DS ligado, com Gain=37, Tone=63, Level=19. |
| `teste_cab_level.dzh` | Só o Level do CAB mudou (→ 71). |
| `teste_vol.dzh` | Só o Volume geral (VOL) mudou (→ 33). |

O template usado pelo gerador de download (`assets/base_preset.dzh`) é uma
cópia do `base_original_JMDS.dzh`.
