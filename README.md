# MK-300 Visual Tone Assistant

Aplicação web (Flask) que roda **localmente** e usa a API de um provedor de
LLM na nuvem (Gemini, OpenAI ou Groq) para analisar o timbre de uma música
ou artista e sugerir os parâmetros dos 11 módulos da pedaleira **M-VAVE
MK-300** (WAH → FX → GATE → DS → AMP → CAB → EQ → MOD → DLY → REV → VOL).

Também inclui uma busca auxiliar de arquivos MIDI relacionados (via
BitMidi/FreeMidi).

## Pré-requisitos

- Python 3.9 ou superior
- Uma chave de API de um dos provedores suportados: Gemini, OpenAI ou Groq

## Instalação

1. Crie e ative um ambiente virtual (recomendado):

   ```
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # Linux/Mac
   ```

2. Instale as dependências:

   ```
   pip install -r requirements.txt
   ```

3. Copie o arquivo de exemplo de configuração e edite com sua chave de API:

   ```
   copy .env.example .env        # Windows
   cp .env.example .env          # Linux/Mac
   ```

   No arquivo `.env`, defina `LLM_PROVIDER` como `gemini`, `openai` ou
   `groq`, e preencha a chave correspondente (`GEMINI_API_KEY`,
   `OPENAI_API_KEY` ou `GROQ_API_KEY`).

## Executando

```
python app.py
```

Acesse **http://localhost:5000** no navegador. A porta pode ser alterada
via `FLASK_PORT` no `.env`.

## Testando a conexão com a API

Se algo der errado (chave inválida, modelo incorreto, etc.), rode o script
de diagnóstico para isolar o problema antes de abrir o app:

```
python diagnostico_api.py
```

Ele lê a configuração do `.env` e faz uma chamada simples de teste ao
provedor configurado, mostrando o status da resposta e mensagens de erro
detalhadas.

## Segurança

- **Nunca** coloque chaves de API diretamente no código-fonte — use sempre
  o arquivo `.env` (que não deve ser compartilhado nem versionado; veja
  `.gitignore`).
- Se você desconfiar que alguma chave já foi exposta publicamente, gere uma
  nova chave no painel do provedor e revogue a antiga.

## Estrutura do projeto

```
app.py                 # Servidor Flask + integração com a LLM
diagnostico_api.py      # Script de diagnóstico da conexão com a API
requirements.txt        # Dependências Python
.env.example             # Modelo de configuração (copie para .env)
templates/index.html     # Página principal
static/app.js             # Lógica do front-end
static/style.css         # Estilos
```
