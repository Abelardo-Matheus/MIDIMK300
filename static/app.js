/**
 * MK-300 Visual Tone Assistant — Frontend JavaScript
 * Gerencia a cadeia de sinal, modal de parâmetros e busca MIDI
 */

// ─────────────────────────────────────────────
// CONFIGURAÇÃO DOS 11 MÓDULOS DA MK-300
// ─────────────────────────────────────────────

const PEDAL_CONFIG = {
  WAH:  { icon: '🦶', color: '#d97706', label: 'Expressão / Wah',    order: 1 },
  FX:   { icon: '⚡', color: '#7c3aed', label: 'FX / Compressor',    order: 2 },
  GATE: { icon: '🚧', color: '#64748b', label: 'Noise Gate',         order: 3 },
  DS:   { icon: '🔥', color: '#dc2626', label: 'Drive / Distortion', order: 4 },
  AMP:  { icon: '🎚️', color: '#ea580c', label: 'Amplificador',       order: 5 },
  CAB:  { icon: '📦', color: '#78716c', label: 'Gabinete (CAB Sim)', order: 6 },
  EQ:   { icon: '🎛️', color: '#65a30d', label: 'Equalizador',        order: 7 },
  MOD:  { icon: '🌊', color: '#2563eb', label: 'Modulação',          order: 8 },
  DLY:  { icon: '🔁', color: '#0891b2', label: 'Delay / Eco',        order: 9 },
  REV:  { icon: '🌐', color: '#0d9488', label: 'Reverb',             order: 10 },
  VOL:  { icon: '🔊', color: '#6b7280', label: 'Volume Pedal',       order: 11 },
};

const CHAIN_ORDER = ['WAH', 'FX', 'GATE', 'DS', 'AMP', 'CAB', 'EQ', 'MOD', 'DLY', 'REV', 'VOL'];

// Estado global da aplicação
const AppState = {
  currentToneData: null,
  selectedPedal: null,
  llmProvider: null,
};

// ─────────────────────────────────────────────
// UTILITÁRIOS
// ─────────────────────────────────────────────

function showToast(msg, type = 'info') {
  const toast = document.getElementById('toast');
  const icon = type === 'error' ? '❌' : type === 'success' ? '✅' : 'ℹ️';
  toast.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  toast.className = `toast ${type} visible`;
  setTimeout(() => toast.classList.remove('visible'), 4000);
}

function setLoading(visible, text = 'Analisando timbre com IA...') {
  const overlay = document.getElementById('loading-overlay');
  const loadingText = document.getElementById('loading-text');
  loadingText.textContent = text;
  overlay.classList.toggle('visible', visible);
}

function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// ─────────────────────────────────────────────
// INICIALIZAÇÃO E CONFIG
// ─────────────────────────────────────────────

async function loadConfig() {
  try {
    const resp = await fetch('/api/config');
    const data = await resp.json();
    AppState.llmProvider = data.provider;
    const badge = document.getElementById('provider-badge');
    if (badge) {
      badge.textContent = `${data.provider.toUpperCase()} · ${data.model}`;
    }
  } catch (e) {
    console.warn('Não foi possível carregar configurações:', e);
  }
}

// ─────────────────────────────────────────────
// CADEIA DE SINAL — RENDERIZAÇÃO
// ─────────────────────────────────────────────

function renderChain(toneData) {
  const container = document.getElementById('chain-wrapper');
  container.innerHTML = '';

  CHAIN_ORDER.forEach((pedalId, index) => {
    const config = PEDAL_CONFIG[pedalId];
    const moduleData = toneData ? toneData[pedalId] : null;
    const isEnabled = moduleData ? moduleData.enabled : false;

    // Bloco do pedal
    const pedalEl = document.createElement('div');
    pedalEl.className = `pedal-block ${isEnabled ? 'active' : 'inactive'}`;
    pedalEl.id = `pedal-${pedalId}`;
    pedalEl.style.setProperty('--pedal-color', config.color);
    pedalEl.setAttribute('data-pedal', pedalId);
    pedalEl.setAttribute('aria-label', `${pedalId} — ${config.label}`);
    pedalEl.setAttribute('role', 'button');
    pedalEl.setAttribute('tabindex', '0');

    // Nome do tipo (ex: "Tube Screamer")
    const typeName = moduleData?.params?.type && moduleData.params.type !== 'None'
      ? moduleData.params.type
      : config.label;

    pedalEl.innerHTML = `
      <div class="pedal-body">
        <div class="pedal-led"></div>
        <div class="pedal-icon">${config.icon}</div>
        <div class="pedal-name">${pedalId}</div>
      </div>
      <div class="pedal-label">${isEnabled ? typeName : '—'}</div>
    `;

    // Evento de clique
    pedalEl.addEventListener('click', () => openModal(pedalId, moduleData, config));
    pedalEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') openModal(pedalId, moduleData, config);
    });

    container.appendChild(pedalEl);

    // Fio de conexão entre pedais (exceto após o último)
    if (index < CHAIN_ORDER.length - 1) {
      const wire = document.createElement('div');
      wire.className = `chain-wire ${isEnabled ? 'active-wire' : ''}`;
      if (isEnabled) wire.style.setProperty('--wire-color', config.color);
      container.appendChild(wire);
    }
  });
}

function renderEmptyChain() {
  const container = document.getElementById('chain-wrapper');
  container.innerHTML = '';

  CHAIN_ORDER.forEach((pedalId, index) => {
    const config = PEDAL_CONFIG[pedalId];

    const pedalEl = document.createElement('div');
    pedalEl.className = 'pedal-block inactive';
    pedalEl.style.setProperty('--pedal-color', config.color);
    pedalEl.setAttribute('data-pedal', pedalId);

    pedalEl.innerHTML = `
      <div class="pedal-body">
        <div class="pedal-icon">${config.icon}</div>
        <div class="pedal-name">${pedalId}</div>
      </div>
      <div class="pedal-label">${config.label}</div>
    `;

    container.appendChild(pedalEl);

    if (index < CHAIN_ORDER.length - 1) {
      const wire = document.createElement('div');
      wire.className = 'chain-wire';
      container.appendChild(wire);
    }
  });
}

// ─────────────────────────────────────────────
// MODAL DE PARÂMETROS
// ─────────────────────────────────────────────

function openModal(pedalId, moduleData, config) {
  AppState.selectedPedal = pedalId;

  const overlay = document.getElementById('modal-overlay');
  const panel = document.getElementById('modal-panel');
  const modalIcon = document.getElementById('modal-icon');
  const modalName = document.getElementById('modal-name');
  const modalType = document.getElementById('modal-type');
  const modalStatus = document.getElementById('modal-status');
  const modalContent = document.getElementById('modal-content');

  // Header
  modalIcon.textContent = config.icon;
  modalIcon.style.background = `linear-gradient(135deg, ${config.color}33, ${config.color}22)`;
  modalIcon.style.border = `1px solid ${config.color}44`;

  modalName.textContent = pedalId;
  modalName.style.color = config.color;

  const typeName = moduleData?.params?.type && moduleData.params.type !== 'None'
    ? moduleData.params.type : config.label;
  modalType.textContent = typeName;

  const isEnabled = moduleData?.enabled ?? false;
  modalStatus.textContent = isEnabled ? 'ATIVO' : 'BYPASS';
  modalStatus.className = `modal-status-badge ${isEnabled ? 'on' : 'off'}`;

  // Parâmetros
  modalContent.innerHTML = '';

  if (!moduleData) {
    modalContent.innerHTML = `
      <div style="text-align:center; padding:40px 0; color:var(--text-muted); font-size:13px;">
        Pesquise um timbre para ver<br>os parâmetros deste módulo.
      </div>`;
  } else {
    const params = moduleData.params || {};
    const paramEntries = Object.entries(params);

    if (paramEntries.length === 0) {
      modalContent.innerHTML = `<div style="color:var(--text-muted); font-size:13px;">Sem parâmetros disponíveis.</div>`;
    } else {
      const group = document.createElement('div');
      group.className = 'param-group';

      const label = document.createElement('div');
      label.className = 'param-label';
      label.textContent = 'Parâmetros';
      group.appendChild(label);

      paramEntries.forEach(([key, val]) => {
        const item = document.createElement('div');
        item.className = 'param-item';

        if (key === 'type') {
          // Parâmetro string (tipo de efeito)
          item.innerHTML = `
            <div class="param-row">
              <span class="param-name">Tipo</span>
            </div>
            <div class="param-string" style="border-color: ${config.color}44; color: ${config.color};">
              ${val}
            </div>`;
        } else if (key === 'mic') {
          item.innerHTML = `
            <div class="param-row">
              <span class="param-name">Microfone</span>
            </div>
            <div class="param-string">${val}</div>`;
        } else if (typeof val === 'number') {
          // Parâmetro numérico com barra de progresso
          const displayName = formatParamName(key);
          item.innerHTML = `
            <div class="param-row">
              <span class="param-name">${displayName}</span>
              <span class="param-value" style="color: ${config.color};">${val}</span>
            </div>
            <div class="param-bar">
              <div class="param-fill" 
                   style="width: ${val}%; --pedal-color: ${config.color}; background: ${config.color}; box-shadow: 0 0 6px ${config.color}80;">
              </div>
            </div>`;
        }

        group.appendChild(item);
      });

      modalContent.appendChild(group);

      // Dica de configuração
      const tip = document.createElement('div');
      tip.style.cssText = `
        margin-top: 20px; padding: 14px; background: var(--bg-card);
        border: 1px solid var(--border); border-radius: 8px;
        font-size: 12px; color: var(--text-muted); line-height: 1.6;`;
      tip.innerHTML = `
        <strong style="color: var(--text-secondary);">💡 Dica MK-300</strong><br>
        Acesse o módulo <strong style="color: ${config.color}; font-family: monospace;">${pedalId}</strong>
        na pedaleira e ajuste os parâmetros conforme indicado acima.
        Use os botões ◄ ► para navegar entre os parâmetros.`;
      modalContent.appendChild(tip);
    }
  }

  // Abre o modal
  overlay.classList.add('visible');
  panel.classList.add('visible');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  const overlay = document.getElementById('modal-overlay');
  const panel = document.getElementById('modal-panel');
  overlay.classList.remove('visible');
  panel.classList.remove('visible');
  document.body.style.overflow = '';
  AppState.selectedPedal = null;
}

function formatParamName(key) {
  const names = {
    gain: 'Gain', tone: 'Tom', level: 'Level', bass: 'Baixo',
    middle: 'Middle', treble: 'Agudo', presence: 'Presence',
    low_mid: 'Low-Mid', high_mid: 'High-Mid', rate: 'Rate',
    depth: 'Depth', feedback: 'Feedback', mix: 'Mix', time: 'Tempo',
    decay: 'Decay', pre_delay: 'Pre-Delay', threshold: 'Threshold',
    sensitivity: 'Sensibilidade', freq: 'Frequência', volume: 'Volume',
  };
  return names[key] || capitalize(key.replace(/_/g, ' '));
}

// ─────────────────────────────────────────────
// SONG INFO CARD
// ─────────────────────────────────────────────

function renderSongInfo(data) {
  const card = document.getElementById('song-info-card');
  const info = data.song_info || {};
  const toneInfo = data.tone_info || {};

  document.getElementById('song-avatar').textContent =
    info.song ? '🎸' : '🎵';
  document.getElementById('song-name').textContent =
    info.song || info.artist || 'Timbre Personalizado';
  document.getElementById('song-artist').textContent =
    [info.artist, info.era, info.guitar].filter(Boolean).join(' · ');
  document.getElementById('song-desc').textContent =
    info.description || toneInfo.character || '';

  const tagsEl = document.getElementById('song-tags');
  tagsEl.innerHTML = '';
  const tags = [toneInfo.style, ...(toneInfo.key_effects || [])].filter(Boolean).slice(0, 3);
  tags.forEach(tag => {
    const el = document.createElement('span');
    el.className = 'tag';
    el.textContent = tag;
    tagsEl.appendChild(el);
  });

  card.classList.add('visible');
}

// ─────────────────────────────────────────────
// BUSCA PRINCIPAL DE TIMBRE
// ─────────────────────────────────────────────

async function searchTone(query) {
  setLoading(true, 'Analisando timbre com IA...');
  document.getElementById('search-btn').disabled = true;

  try {
    const resp = await fetch('/api/search-tone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });

    const result = await resp.json();

    if (!resp.ok || !result.success) {
      throw new Error(result.error || 'Erro desconhecido');
    }

    AppState.currentToneData = result.data;
    renderChain(result.data);
    renderSongInfo(result.data);
    showToast('Timbre analisado com sucesso!', 'success');

  } catch (err) {
    showToast(err.message, 'error');
    console.error('[ToneSearch]', err);
  } finally {
    setLoading(false);
    document.getElementById('search-btn').disabled = false;
  }
}

// ─────────────────────────────────────────────
// BUSCA DE MIDI
// ─────────────────────────────────────────────

async function searchMidi(query) {
  const midiStatus = document.getElementById('midi-status');
  const midiResults = document.getElementById('midi-results');

  midiStatus.textContent = 'Buscando...';
  midiResults.innerHTML = `
    <div class="midi-empty">
      <div style="font-size: 24px; margin-bottom: 8px;">⏳</div>
      Buscando arquivos MIDI...
    </div>`;

  try {
    const resp = await fetch('/api/search-midi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });

    const result = await resp.json();

    if (!resp.ok || !result.success) {
      throw new Error(result.error || 'Erro na busca MIDI');
    }

    renderMidiResults(result.data);

  } catch (err) {
    midiResults.innerHTML = `
      <div class="midi-empty">
        <div style="font-size: 24px; margin-bottom: 8px;">⚠️</div>
        ${err.message}
      </div>`;
    midiStatus.textContent = 'Erro';
  }
}

function renderMidiResults(data) {
  const midiStatus = document.getElementById('midi-status');
  const midiResults = document.getElementById('midi-results');
  const midiLinks = document.getElementById('midi-external-links');

  midiStatus.textContent = `${data.count} resultado(s)`;

  if (data.results.length === 0) {
    midiResults.innerHTML = `
      <div class="midi-empty">
        <div style="font-size: 24px; margin-bottom: 8px;">🔍</div>
        Nenhum arquivo encontrado automaticamente.<br>
        Use os links abaixo para buscar manualmente.
      </div>`;
  } else {
    midiResults.innerHTML = '';
    data.results.forEach(item => {
      const el = document.createElement('div');
      el.className = 'midi-result-item';
      el.innerHTML = `
        <div class="midi-result-icon">🎹</div>
        <div class="midi-result-info">
          <div class="midi-result-title" title="${item.title}">${item.title}</div>
          <div class="midi-result-source">📡 ${item.source}</div>
        </div>
        <a href="${item.download_url}" target="_blank" rel="noopener" class="midi-download-btn">
          ⬇ Download
        </a>`;
      midiResults.appendChild(el);
    });
  }

  // Links externos para busca manual
  if (data.search_urls) {
    midiLinks.innerHTML = `
      <span style="font-size:11px; color:var(--text-muted)">Buscar manualmente:</span>
      ${Object.entries(data.search_urls).map(([name, url]) =>
        `<a href="${url}" target="_blank" rel="noopener" class="midi-ext-link">
          🔗 ${capitalize(name)}
        </a>`
      ).join('')}`;
  }
}

// ─────────────────────────────────────────────
// FORMULÁRIO E EVENTOS
// ─────────────────────────────────────────────

function handleSearch() {
  const input = document.getElementById('search-input');
  const query = input.value.trim();

  if (!query) {
    showToast('Digite uma música, artista ou estilo de timbre.', 'error');
    input.focus();
    return;
  }

  // Roda ambas as buscas
  searchTone(query);
  searchMidi(query);
}

// ─────────────────────────────────────────────
// CONFIGURAÇÃO DE CHAVE API (modal inline)
// ─────────────────────────────────────────────

function showApiKeyModal() {
  const key = prompt(
    'Cole sua chave de API aqui.\n\n' +
    'Para uso permanente, edite o arquivo .env na pasta do projeto.\n\n' +
    'Chave temporária (válida até fechar o servidor):'
  );
  if (key) {
    fetch('/api/set-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key })
    }).then(r => r.json()).then(d => {
      if (d.success) showToast('Chave configurada com sucesso!', 'success');
      else showToast('Erro ao configurar chave.', 'error');
    });
  }
}

// ─────────────────────────────────────────────
// DOMContentLoaded — Bootstrap
// ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {

  // Carrega configurações
  loadConfig();

  // Renderiza cadeia vazia inicial
  renderEmptyChain();

  // Formulário de busca
  const form = document.getElementById('search-form');
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    handleSearch();
  });

  // Botão de busca
  document.getElementById('search-btn').addEventListener('click', handleSearch);

  // Enter no input
  document.getElementById('search-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSearch();
  });

  // Exemplos de busca
  document.querySelectorAll('.search-example').forEach(el => {
    el.addEventListener('click', () => {
      document.getElementById('search-input').value = el.dataset.query;
      handleSearch();
    });
  });

  // Fechar modal
  document.getElementById('modal-overlay').addEventListener('click', closeModal);
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  // Botão de API Key
  const apiKeyBtn = document.getElementById('api-key-btn');
  if (apiKeyBtn) apiKeyBtn.addEventListener('click', showApiKeyModal);
});
