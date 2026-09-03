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


## Sessao de engenharia reversa - 2026-09-03 (via M-EFCS conectado por USB)

O app oficial da pedaleira (**M-EFCS**, `M-efcs.exe`, instalado em
`Desktop\M-EFCS\`) tem, no menu "More" da aba Effect, duas opcoes que nao
estavam documentadas aqui antes:

- **Share all presets**: exporta os 160 slots da pedaleira (80 presets de
  fabrica/nomeados + 80 slots "USER PRESET" vazios) de uma vez, num unico
  arquivo `.adzh`. Formato: 160 blocos de 448 bytes concatenados (o mesmo
  tamanho e layout de um `.dzh` avulso) + marcador `PATCHEND` (8 bytes) no
  final. `MK300_AllPresets.adzh` (exportado nesta sessao) foi separado nos
  160 arquivos individuais em `presets/factory_export/`.
- **Import all presets** / **Import current preset** / **Swap preset** /
  **Export Snapshot** / **Factory Restore**: dao pra importar de volta pra
  pedaleira direto pelo app (nao testado nesta sessao, so o export).

### Truque para confirmar o indice de qualquer modelo (novo)

O combobox de modelo do M-EFCS mostra o indice (1-based) colado no nome,
sem espaco - ex.: AMP mostrando `24J800_DS` = indice 24 (1-based) = indice
23 (0-based, o que o `.dzh` guarda) = `"J800_DS"` em `amp_guitar[23]`;
CAB mostrando `18FD_TW1971` = indice 17 (0-based) = `"FD_TW1971"` em
`cab[17]`. Isso CONFIRMA que o esquema `TYPE_OFFSET + byte = indice da
lista em data/mk300_models.json` vale nao so pra AMP/CAB/DS (ja usado por
`dzh_export.py`) como, em principio, pra WAH/FX/GATE/MOD/EQ tambem - so
falta ler o combobox de cada modulo pra confirmar cada lista uma por uma.

### Novos offsets confirmados por diff binario (1 parametro por vez)

Preset usado como base: `[003] JM-DS` (o mesmo carregado no M-EFCS durante
a sessao). Metodologia identica a que gerou os offsets de AMP/DS/CAB/VOL
originais: mudar 1 parametro no app, exportar ("Share current preset"),
comparar byte a byte com o export anterior.

- **CAB** tinha mais 2 parametros alem de "Level" que nao estavam
  documentados: `Low Cut` (offset `0xBC`, inteiro puro) e `High Cut`
  (offset `0xBE`, inteiro/10 = valor em kHz mostrado na UI - ex. raw 94 =
  "9.4K"). Confirmado por leitura direta do preset real (nao precisou nem
  editar - os 3 valores (57, 87, 9.4K) bateram exatamente com os bytes
  0xBA/0xBC/0xBE = 57/87/94).
- **WAH** (modelo Cry-Wah): `Value`=`0x42`, `Gain`=`0x44`, `Level`=`0x46`
  (u16 LE). O bloco reservado pro WAH parece ir de `0x42` a `0x4E` (7 slots
  u16 = espaco pro modelo com mais parametros, "Sense-Wah"/"Wah-Wah", que
  tem 7 cada) mas so os 3 primeiros foram de fato testados.
  **Cuidado**: o valor "Value" exibido na carga do preset original era 100
  mas o byte cru era 50 (parece ter escala x2 na leitura do dispositivo);
  depois de editar via scroll do app pra "98", o byte cru virou 98 direto
  (sem escala). Ou seja, o app pode ter uma inconsistencia entre o valor
  que ele LE de um preset carregado e o valor que ele ESCREVE quando voce
  edita - nao testamos o round-trip completo (salvar e recarregar) pra
  confirmar se isso da problema.
- **DLY** (modelo Duck): `Time`=`0x102`, `Fb`=`0x104`, `Mix`=`0x106`,
  `Release`=`0x108`, `Speed`=`0x10a`, `Depth`=`0x10c` (todos u16 LE). Todos
  os 6 parametros do modulo confirmados. `Time` tem uma escala/offset ainda
  nao resolvido (raw 244 -> UI "0.500", raw 245 -> UI "0.501" - nao e um
  `raw * 0.001` simples, precisa de mais pontos pra achar a formula).

Os offsets novos ja foram adicionados em `dzh_export.py` -> `PARAM_OFFSETS`
(WAH e DLY sao novos; CAB ganhou `low_cut`/`high_cut`). `build_dzh()` ja
usa esse dict genericamente, entao esses modulos passam a ser gravados
automaticamente quando o JSON de entrada tiver as chaves certas - so
`high_cut` do CAB ainda precisa de tratamento manual da escala /10 antes de
virar isso confiavel (hoje `_clamp_u16` grava o valor bruto sem converter).

### O que ainda falta (nao confirmado)

FX, GATE, MOD, EQ e REV continuam sem offset numerico confirmado - so tem
nome de modelo e lista de parametros (extraidos do manual oficial, ja em
`data/mk300_models.json`). O metodo pra confirmar cada um e o mesmo: abrir
o M-EFCS, mudar 1 parametro de cada vez, exportar ("Share current preset")
e comparar com o export anterior. Os 160 presets de fabrica em
`presets/factory_export/` tambem dao pra usar como material de diff em
massa (por ex., comparar dois presets que usam o mesmo modelo de efeito
com parametros bem diferentes), mas sem o valor real mostrado na tela do
app pra cada um, um diff cego arrisca achar coincidencia em vez do offset
certo.


## Continuacao (mesma sessao, 2026-09-03) - FX, GATE, MOD, REV e EQ confirmados

Seguindo o pedido de fechar tudo que faltava: os 5 modulos listados acima
como "nao confirmado" foram testados um por um, mesma metodologia (mudar 1
parametro no M-EFCS, "Share current preset", diff binario contra o export
anterior). Nada foi salvo na pedaleira fisica em nenhum momento - so
"Share current preset" (exporta pra arquivo) foi usado, nunca "Save"/"Save
to". Ao final de cada modulo testado, o preset foi restaurado ao estado
original trocando o seletor de preset pra outro e voltando pro "JM-DS" (o
app recarrega os valores reais gravados, descartando qualquer edicao nao
salva na tela - jeito rapido de "resetar" sem precisar reverter campo por
campo).

### Descoberta importante: as listas de modelo do manual estavam erradas pra FX/GATE/MOD, e a de REV nem existia

Comparando a ORDEM real do dropdown do app com `data/mk300_models.json`
(que veio do PDF do manual oficial), a ordem e o conteudo batiam certo so
pra WAH. Pra FX, GATE e MOD a lista do manual estava incompleta e/ou fora
de ordem; pra REV nao existia lista nenhuma ainda. As listas foram
reconstruidas lendo o dropdown do app diretamente (com o truque do indice
colado no nome, ex. "9Compress" = indice 9 (1-based) = indice 8 (0-based))
e ja atualizadas em `data/mk300_models.json`:

- **FX**: 16 modelos (era uma lista menor/errada) - Wah-Wah, Lofi,
  Sense-Wah, Boost, A Boost, E Boost, B Boost, Boost ED, Compress, Compress
  Pro, F Compress, Pitch, Octave, Ring, Pitch shifter, Whammy.
- **GATE**: 8 modelos (a lista antiga tinha um "AI Ms Gate Gen2" que nao
  existe no app - removido) - AI Gate, Soft Gate, Hard Gate, Pro Gate,
  Compress, Compress Pro, F Compress, AI Ms Gate.
- **MOD**: 20 modelos (a lista antiga so tinha 9) - os 9 originais (Chorus,
  Flanger, Phaser, Tremolo, Auto Wah, Rotary, Vibrato + mais 2) mais 11
  descobertos agora: Tri Vibrato, Opto Vibrato, Univibe, Tri Univibe,
  Autofilter, Phaser Stereo, Flanger Stereo, Vibe Stereo, Chorus Stereo,
  Tremolo Stereo, Vibrato Stereo.
- **REV**: lista nova, nao existia - 18 modelos: Room, Hall, Plate, Spring,
  Shimmer, Bloom, Cloud, Lofi, Swell, e as 9 versoes "stereo" de cada um.

**IMPORTANTE pra quem for gerar `.dzh` programaticamente**: se algum codigo
tivesse usado as listas antigas do manual pra escolher o indice de um
modelo de FX/GATE/MOD, o indice gravado no byte `TYPE_OFFSET` estaria
ERRADO (apontando pro modelo errado na ordem real do firmware). As listas
em `data/mk300_models.json` sao agora a fonte de verdade, nao o manual.

### Offsets numericos confirmados (1 modelo representativo por modulo)

Todos os offsets sao dentro do bloco de 448 bytes do preset, mesma regra
dos offsets antigos (AMP/DS/CAB/VOL/WAH/DLY). Ja adicionados em
`dzh_export.py` -> `PARAM_OFFSETS`, com um novo dict `PARAM_META` pra
marcar os campos que fogem do padrao "u16 sem sinal, valor bruto = valor
exibido":

- **FX** (modelo "Compress"): `Sustain`=`0x5A`, `Attack`=`0x5C`,
  `Level`=`0x5E`, `Blend`=`0x60`. So testado nesse modelo - Compress
  Pro/F Compress (nomes parecidos) nao foram testados individualmente.
- **GATE** (modelo "Pro Gate"): `Att`=`0x72`, `Rel`=`0x74`, `Thd`=`0x76`,
  `Kw`=`0x78`, `Ratio`=`0x7A`. **`Thd` (threshold) e SIGNED** - guarda
  valores negativos de dB como int16 complemento de dois (ex.: -50dB nao e
  o mesmo bit pattern que +50). Os outros 4 campos sao u16 normal.
- **MOD** (modelo "Phaser"): `Speed`=`0xEA`, `MidCut`=`0xEC`, `Reso`=`0xEE`,
  `Fb`=`0xF0`. **`Speed` usa ESCALA `raw = valor_exibido * 10`** (ex.: UI
  "4.0" -> raw 40).
- **REV** (modelos "Hall" e "Hall stereo" - os dois bateram no mesmo
  offset, so muda o byte de `TYPE_OFFSET`): `Decay`=`0x11A`, `Mix`=`0x11C`,
  `High Pass`=`0x11E`, `Low Pass`=`0x120`, `Mod Depth`=`0x122`.
- **EQ** (modulo de cadeia da aba Effect - NAO e o Master EQ, ver proxima
  secao; modelo "Guitar EQ 6"): `100Hz`=`0xD2`, `200Hz`=`0xD4`,
  `400Hz`=`0xD6`, `800Hz`=`0xD8`, `1.6kHz`=`0xDA`, `3.2kHz`=`0xDC`.
  **Todas as 6 bandas sao SIGNED e usam ESCALA `raw = dB * 2`** (ex.:
  -0.5dB -> raw `0xFFFF`, que e -1 em int16). Esse diff precisou de um
  baseline "limpo" exportado na hora (edicoes acumuladas de FX/GATE/MOD/REV
  na sessao estavam sujando o diff contra o baseline antigo). "Bass EQ 7" e
  "Normal EQ 10" tem bandas extras (mais graves/agudos) que nao foram
  mapeadas - presume-se mesmo padrao sequencial de offset, nao testado.

### Master EQ (aba superior) NAO faz parte do preset .dzh

O app tem uma aba "EQ" separada da aba "Effect" - um EQ parametrico global
de 4 bandas (Freq/Q/Gain x4, P1-P4) mais Low Cut/High Cut, com botoes
proprios "Share EQ"/"Import EQ". Testado por diff: mudar um valor la e
re-exportar o preset ("Share current preset") deu **0 bytes de diferenca**
no `.dzh` de 448 bytes. Ou seja, o Master EQ e um dado completamente
separado (nao fica dentro do preset individual) - nao faz sentido procurar
por ele nos offsets do `.dzh`, e ele nao e exportado/importado junto com
presets individuais.

### DS pode ter ate 8 parametros, nao so 3

O modulo DS (Drive/Distortion) mapeado hoje em `PARAM_OFFSETS["DS"]` so
tem `gain`/`level`/`tone` (3 campos). Ao navegar pelos modelos de DS no
app, varios modelos mostram ate 8 knobs na tela (nao so os 3 mapeados) -
esse modulo provavelmente tem o mesmo padrao de "bloco reservado maior que
o modelo mais simples usa" que o WAH ja mostrou (bloco de 7 slots pro WAH,
so 3 usados pelo Cry-Wah). Os offsets dos parametros extras do DS NAO foram
mapeados nesta sessao - fica como proximo passo se for preciso editar
esses modelos com mais parametros.

## Continuacao (nova sessao, 2026-09-03) - Por que DLY/MOD/DS nao mudavam de tipo ao importar, e correcao completa

Pedido do usuario: DLY, MOD e DS continuavam sem mudar para o modelo
correto quando o `.dzh` gerado pela aplicacao era importado no M-EFCS.
Investigacao encontrou **duas causas-raiz distintas**, ambas corrigidas:

1. **`build_dzh()` nunca escrevia o byte `TYPE_OFFSET` de WAH, FX, GATE,
   MOD e DLY** - so AMP, CAB e DS tinham essa escrita implementada. Ou
   seja, mesmo que a lista de modelos estivesse certa, o app nunca
   gravava qual modelo usar nesses 5 modulos; o pedal ficava com o que
   já estava la antes (por isso "nao mudava o tipo").
2. **As listas de modelo de DLY e REV enviadas pra IA eram ficticias** -
   nao correspondiam a nenhum modelo real do firmware (a lista de DLY
   antiga nao tinha nenhuma correspondencia com o dropdown real do app).
   Mesmo corrigindo (1), gravar o indice de um nome ficticio ou nao
   gravar nada (quando `_match_type` nao achava correspondencia).

### Arquitetura descoberta: modulos "fixos" x "posicionais"

Testando cada modulo trocando de modelo e comparando os knobs exibidos,
ficou claro que os 11 modulos do MK-300 se dividem em duas familias:

- **Fixos** (AMP, CAB, DS, VOL, REV, EQ): o layout de parametros por nome
  e o MESMO nao importa qual modelo esteja selecionado (ex.: DS sempre
  tem Gain/Level/Bass/Middle/Treble/Reso/Pres/Bright, os offsets desses 8
  campos nao mudam quando voce troca de "RAT" pra "Big Muff").
- **Posicionais** (WAH, FX, GATE, MOD, DLY): existe um bloco reservado de
  N slots de 16 bits sequenciais a partir de `POSITIONAL_BASE[modulo]`
  (WAH=0x42 c/ 7 slots, FX=0x5A c/ 8, GATE=0x72 c/ 8, MOD=0xEA c/ 6,
  DLY=0x102 c/ 6), e o SIGNIFICADO de cada slot depende de qual modelo
  esta selecionado - slot `i` = posicao `i` na lista `params` daquele
  modelo especifico em `data/mk300_models.json`. Isso bate exatamente com
  a convencao ja usada pela IA (`param1`, `param2`, ... `paramN`).

`dzh_export.py` foi reescrito em cima dessa divisao: `PARAM_OFFSETS` cobre
so a familia fixa (com `PARAM_META` pra excecoes signed/escala, hoje so
o EQ), e um novo loop generico sobre `positional_models` cobre os 5
modulos posicionais - casa o nome do modelo (`_match_type`), escreve o
indice em `TYPE_OFFSET`, e ai escreve `param1..paramN` nos slots na ordem
real dos `params` daquele modelo, aplicando `POSITIONAL_LABEL_META` quando
o rotulo do slot precisa de tratamento especial (signed/escala).

### DS: confirmado 8 parametros uniformes em TODOS os 40 modelos reais

O que a secao anterior deste README deixava como "proximo passo" foi
resolvido: navegando pelos 40 modelos de DS no app, todos mostram os
MESMOS 8 knobs, sempre nos mesmos offsets (familia fixa, nao posicional):
`Gain=0x8A`, `Level=0x8C`, `Bass=0x8E`, `Middle=0x90`, `Treble=0x92`,
`Reso=0x94`, `Pres=0x96`, `Bright=0x98`. O mapeamento antigo (so
gain/tone/level, 3 campos) sub-utilizava o modulo - "tone" na verdade
gravava no offset do "Treble", nao era um controle generico.

### DLY: lista real de 27 modelos reconstruida (a antiga era ficticia)

Lida diretamente do dropdown do app (o dropdown de DLY mostra nomes puros,
sem indice colado ao nome como AMP/CAB/DS/FX/GATE/MOD/REV/WAH - entao a
confirmacao de ordem foi por leitura visual sequencial + diff binario nos
5 primeiros). Ordem real: Clean, Modern, Echo, Analog, Duck, Dtype,
Tremolo, Filter, Dual, Lofi, Pattern, Ice, Reverse, PingPong Stereo, e
depois os 13 modelos mono de novo cada um com sufixo " Stereo". `Time`,
`Fb` (feedback) e `Mix` ocupam sempre os 3 primeiros slots posicionais
independente do modelo; modelos com mais controles (5 ou 6 slots) usam os
slots extras para parametros especificos daquele algoritmo (ex.: Dtype,
Ratio). So "Duck" foi confirmado por diff byte-a-byte direto; os demais
15 modelos mono foram confirmados por leitura de tela (numero de knobs e
nomes batendo exatamente com os valores gravados apos exportar/importar);
as 13 variantes " Stereo" foram assumidas com os mesmos `params` do
equivalente mono (padrao ja visto em MOD/REV) e nao foram testadas uma a
uma.

### REV: lista real de 18 modelos agora usada pela aplicacao

A lista real (Room, Hall, Plate, Spring, Shimmer, Bloom, Cloud, Lofi,
Swell + as 9 versoes stereo) ja tinha sido descoberta na sessao anterior
e estava em `data/mk300_models.json`, mas `app.py` ainda usava a lista
ficticia antiga ("Hall","Room","Plate","Spring","Chamber","None") no
prompt da IA e no schema, e REV nem entrava em `TYPE_ENUMS` - ou seja,
mesmo corrigindo a escrita do byte de tipo, a IA nunca pediria um nome
que desse match. Corrigido: REV agora usa os 18 nomes reais e o schema
passou a expor `decay/mix/high_pass/low_pass/mod_depth` (nomeado, familia
fixa) em vez do "pre_delay" que nao existe no pedal.

### Bug de escala encontrado e corrigido: GATE/FX "Thd" (threshold)

A sessao anterior tinha mapeado `Thd` como int16 signed sem escala
(`raw = valor_exibido`). Testando o ciclo completo (gerar `.dzh` -> import
no M-EFCS -> conferir na tela, exatamente como o usuario pediu), um
`Thd` gravado como -15 apareceu na tela do M-EFCS como **-30** (o dobro).
Ou seja, a formula de exibicao do proprio app MULTIPLICA o raw por 2, o
que so foi descoberto fazendo o teste ponta-a-ponta (nao aparecia num
diff binario isolado, porque o diff so mostra o que muda no arquivo, nao
como o app interpreta esse valor). Correcao em `POSITIONAL_LABEL_META`:
`("GATE","Thd")` e `("FX","Thd")` agora usam `scale=0.5` na escrita (ou
seja, se a IA pede Thd=-30, o app grava raw=-15, e o M-EFCS mostra -30 na
tela). Reconfirmado por reimportacao: `Thd` pedido = -30 -> tela mostra
exatamente "-30".

### MOD "Speed": ressalva de exibicao em valores altos (nao totalmente resolvido)

Confirmado (so no modelo Phaser) que `Speed` usa `raw = valor_exibido *
10` para valores baixos (bate com a nota da sessao anterior). Em valores
de raw mais altos (~400), a tela do M-EFCS passa a mostrar uma FRACAO de
sincronismo de tempo (tipo "1/16") em vez de um numero direto - ou seja,
existe algum ponto de corte onde o campo muda de modo de exibicao
(numero livre -> divisao rítmica sincronizada ao BPM). Isso NAO afeta a
escrita (o valor gravado no arquivo continua correto pela formula linear),
mas o numero que a IA pede pode nao corresponder ao que aparece na tela
se cair nessa faixa alta. Fica como ressalva conhecida, nao como bug
corrigido - nao foi mapeado exatamente onde comeca esse corte nem se ele
se aplica aos outros modelos de MOD (Chorus, Flanger etc).

### Testes ponta-a-ponta realizados (gerar .dzh -> importar no M-EFCS -> conferir na tela)

Todos via "Import current preset" (nunca "Save"/"Save to" - nenhum teste
grava no pedal fisico):

- **DS**: RAT, 8 parametros + tipo -> todos batendo.
- **REV**: Plate, 5 parametros + tipo -> todos batendo.
- **DLY**: Duck, tipo + 5 de 6 parametros batendo (Time tem uma ressalva
  de escala nao-linear ja conhecida de antes, nao mexida nesta sessao).
- **MOD**: Phaser, tipo + 2 de 3 parametros batendo (Speed com a ressalva
  de modo de exibicao acima).
- **GATE**: Pro Gate, tipo + 5 parametros -> todos batendo, incluindo o
  Thd corrigido (-30 pedido = -30 na tela).

WAH e FX nao foram reimportados individualmente nesta sessao (o caminho
de codigo e o mesmo generico usado por GATE/MOD/DLY, que foram testados),
mas continuam validos como proximo passo se algo especifico deles for
reportado.

### Arquivos alterados nesta sessao

- `data/mk300_models.json`: nova chave `dly` (27 modelos), `ds_params`
  (8 nomes) + `ds_offsets_confirmed`.
- `dzh_export.py`: reescrito - familia fixa (`PARAM_OFFSETS`) separada da
  familia posicional (`POSITIONAL_BASE`/`POSITIONAL_MAX_SLOTS`/
  `POSITIONAL_LABEL_META`), `build_dzh()` agora recebe `rev_types` e
  `positional_models` e escreve `TYPE_OFFSET` + parametros de TODOS os 11
  modulos, nao so 3.
- `app.py`: `DS_PARAMS`, `REV_TYPES`, `DLY_MODELS`/`DLY_TYPES`,
  `POSITIONAL_MODELS`, schema da IA e `SYSTEM_PROMPT` atualizados pra
  DS (8 params), DLY (27 modelos reais + posicional) e REV (18 modelos
  reais + 5 params fixos); rota `/api/effects` passou a expor `dly`,
  `rev` e `ds_params` tambem.
