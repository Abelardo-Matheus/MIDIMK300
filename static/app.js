/* ============================================================
   MK-300 Tone Assistant — front-end
   Cadeia de 11 módulos clicável, painel de parâmetros com
   sliders ao vivo, MIDI, toasts e navegação por teclado.
   Dados reais via /api/search-tone, /api/search-midi, /api/config.
   ============================================================ */

(function () {
  'use strict';

  const MODULES = [
    { id: 'WAH', name: 'WAH', sub: 'Wah / Expressão',
      hint: 'O bloco WAH simula pedal de expressão. Ajuste Sensitivity conforme a dinâmica da palhetada.',
      params: [
        { key: 'sensitivity', label: 'Sensitivity' },
        { key: 'freq', label: 'Freq' },
        { key: 'level', label: 'Level' },
      ] },
    { id: 'FX', name: 'FX', sub: 'Compressor / FX',
      hint: 'O bloco FX cobre compressão e modulação de entrada. Use com moderação antes da distorção.',
      params: [
        { key: 'rate', label: 'Rate' },
        { key: 'depth', label: 'Depth' },
        { key: 'level', label: 'Level' },
      ] },
    { id: 'GATE', name: 'GATE', sub: 'Noise Gate',
      hint: 'O bloco GATE corta ruído entre notas. Suba o Threshold aos poucos até o ruído sumir.',
      params: [
        { key: 'threshold', label: 'Threshold' },
        { key: 'decay', label: 'Decay' },
      ] },
    { id: 'DS', name: 'DS', sub: 'Drive / Distortion',
      hint: 'O bloco DS define a saturação. Ajuste Tone para equilibrar brilho e corpo.',
      params: [
        { key: 'gain', label: 'Gain' },
        { key: 'tone', label: 'Tone' },
        { key: 'level', label: 'Level' },
      ] },
    { id: 'AMP', name: 'AMP', sub: 'Amplificador',
      hint: 'O bloco AMP define o caráter. Ajuste Presence por último, com o volume real.',
      params: [
        { key: 'gain', label: 'Gain' },
        { key: 'bass', label: 'Bass' },
        { key: 'middle', label: 'Middle' },
        { key: 'treble', label: 'Treble' },
        { key: 'presence', label: 'Presence' },
      ] },
    { id: 'CAB', name: 'CAB', sub: 'Gabinete (CAB)',
      hint: 'O bloco CAB simula o gabinete e o microfone. Pequenos ajustes de Level já mudam bastante o timbre.',
      params: [
        { key: 'level', label: 'Level' },
      ] },
    { id: 'EQ', name: 'EQ', sub: 'Equalizador',
      hint: 'O bloco EQ refina o que sobrou depois do amp. Corte antes de aumentar.',
      params: [
        { key: 'bass', label: 'Bass' },
        { key: 'low_mid', label: 'Low-Mid' },
        { key: 'mid', label: 'Mid' },
        { key: 'high_mid', label: 'High-Mid' },
        { key: 'treble', label: 'Treble' },
        { key: 'level', label: 'Level' },
      ] },
    { id: 'MOD', name: 'MOD', sub: 'Modulação',
      hint: 'O bloco MOD adiciona movimento ao sinal. Rates mais baixos soam mais sutis.',
      params: [
        { key: 'rate', label: 'Rate' },
        { key: 'depth', label: 'Depth' },
        { key: 'level', label: 'Level' },
      ] },
    { id: 'DLY', name: 'DLY', sub: 'Delay',
      hint: 'O bloco DLY repete o sinal no tempo. Sincronize Feedback e Mix com a música.',
      params: [
        { key: 'time', label: 'Time' },
        { key: 'feedback', label: 'Feedback' },
        { key: 'mix', label: 'Mix' },
      ] },
    { id: 'REV', name: 'REV', sub: 'Reverb',
      hint: 'O bloco REV adiciona espaço. Pre-Delay maior separa o sinal seco da cauda.',
      params: [
        { key: 'decay', label: 'Decay' },
        { key: 'pre_delay', label: 'Pre-Delay' },
        { key: 'mix', label: 'Mix' },
      ] },
    { id: 'VOL', name: 'VOL', sub: 'Volume',
      hint: 'O bloco VOL é o volume final da cadeia, após todos os efeitos.',
      params: [
        { key: 'volume', label: 'Volume' },
      ] },
  ];

  const DEFAULT_ENABLED = {
    WAH: false, FX: true, GATE: true, DS: true, AMP: true,
    CAB: true, EQ: false, MOD: false, DLY: true, REV: true, VOL: true,
  };

  const els = {};
  let moduleState = {};
  let baselineState = {};
  let selectedId = 'AMP';
  let busy = false;

  function clone(obj) { return JSON.parse(JSON.stringify(obj)); }

  function clampNum(v) {
    const n = Number(v);
    if (Number.isNaN(n)) return 50;
    return Math.max(0, Math.min(100, Math.round(n)));
  }

  function escapeHtml(str) {
    return String(str == null ? '' : str).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function buildDefaultState() {
    const state = {};
    MODULES.forEach((m) => {
      const params = {};
      m.params.forEach((p) => { params[p.key] = 50; });
      if (m.id === 'AMP') {
        Object.assign(params, { gain: 50, bass: 55, middle: 50, treble: 58, presence: 50 });
      }
      state[m.id] = { enabled: DEFAULT_ENABLED[m.id], params };
    });
    return state;
  }

  function moduleByIndex(index) { return MODULES[index]; }
  function indexOfModule(id) { return MODULES.findIndex((m) => m.id === id); }

  /* ─── Toasts ─── */

  function toast(message, type) {
    const el = document.createElement('div');
    el.className = 'toast' + (type === 'error' ? ' toast-error' : '');
    el.textContent = message;
    els.toastContainer.appendChild(el);
    setTimeout(() => {
      el.classList.add('toast-out');
      setTimeout(() => el.remove(), 200);
    }, 3500);
  }

  /* ─── Status pill ─── */

  function setStatus(state) {
    const labels = { idle: 'PRONTO', busy: 'ANALISANDO...', error: 'ERRO' };
    els.statusPill.dataset.state = state;
    els.statusPill.textContent = labels[state] || 'PRONTO';
  }

  function setBusy(next) {
    busy = next;
    els.searchBtn.disabled = busy;
    els.searchBtn.querySelector('.btn-label').textContent = busy ? 'Analisando...' : 'Analisar timbre';
    setStatus(busy ? 'busy' : 'idle');
  }

  /* ─── Chain rendering ─── */

  function updateChainSummary() {
    const total = MODULES.length;
    const on = MODULES.filter((m) => moduleState[m.id].enabled).length;
    els.chainSummary.textContent = `${on} ativos · ${total - on} bypass`;
  }

  function renderChain() {
    els.chainTrack.innerHTML = '';
    MODULES.forEach((m) => {
      const st = moduleState[m.id];
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'module-card' + (m.id === selectedId ? ' is-selected' : '');
      card.dataset.enabled = String(st.enabled);
      card.setAttribute('role', 'listitem');
      card.setAttribute('aria-pressed', m.id === selectedId ? 'true' : 'false');
      card.setAttribute('aria-label', `${m.name} - ${st.enabled ? 'ativo' : 'desligado'}`);
      card.innerHTML = `
        <div class="module-card-top">
          <span class="module-dot" aria-hidden="true"></span>
          <span class="module-state">${st.enabled ? 'ON' : 'OFF'}</span>
        </div>
        <div class="module-name">${m.name}</div>
        <div class="module-sub">${m.sub}</div>
      `;
      card.addEventListener('click', () => selectModule(m.id));
      els.chainTrack.appendChild(card);
    });
    updateChainSummary();
  }

  function selectModule(id) {
    selectedId = id;
    renderChain();
    renderModulePanel();
    const idx = indexOfModule(id);
    const card = els.chainTrack.children[idx];
    if (card) {
      card.focus({ preventScroll: true });
      card.scrollIntoView({ inline: 'center', behavior: 'smooth', block: 'nearest' });
    }
  }

  /* ─── Module detail panel ─── */

  function renderModulePanel() {
    const m = MODULES.find((x) => x.id === selectedId);
    const st = moduleState[selectedId];
    const panel = els.modulePanel;
    panel.dataset.enabled = String(st.enabled);

    const paramsHtml = m.params.map((p) => `
      <div class="param-row">
        <div class="param-label-row">
          <span class="param-name">${p.label}</span>
          <span class="param-value mono" data-key="${p.key}">${st.params[p.key]}</span>
        </div>
        <input type="range" min="0" max="100" value="${st.params[p.key]}" data-key="${p.key}" aria-label="${p.label}">
      </div>
    `).join('');

    panel.innerHTML = `
      <div class="module-panel-header">
        <div>
          <div class="module-panel-title" data-enabled="${st.enabled}">${m.name}</div>
          <div class="module-panel-sub">${m.sub}</div>
        </div>
        <div class="module-panel-actions">
          <span class="status-pill status-pill-sm" data-state="${st.enabled ? 'idle' : 'error'}">${st.enabled ? 'ATIVO' : 'DESLIGADO'}</span>
          <button type="button" class="btn btn-outline" id="toggle-module-btn">${st.enabled ? 'DESLIGAR' : 'LIGAR'}</button>
        </div>
      </div>
      <div id="param-list">${paramsHtml}</div>
      <div class="param-actions">
        <button type="button" class="btn-outline" id="copy-module-btn">Copiar ajustes do m&oacute;dulo</button>
        <button type="button" class="btn-outline" id="restore-module-btn">Restaurar</button>
      </div>
      <p class="module-hint">${m.hint}</p>
    `;

    panel.querySelector('#toggle-module-btn').addEventListener('click', () => {
      st.enabled = !st.enabled;
      renderChain();
      renderModulePanel();
    });

    panel.querySelectorAll('input[type="range"]').forEach((input) => {
      input.addEventListener('input', () => {
        const key = input.dataset.key;
        st.params[key] = clampNum(input.value);
        panel.querySelector(`.param-value[data-key="${key}"]`).textContent = st.params[key];
      });
    });

    panel.querySelector('#copy-module-btn').addEventListener('click', copyModuleSettings);
    panel.querySelector('#restore-module-btn').addEventListener('click', restoreModule);
  }

  function copyModuleSettings() {
    const payload = JSON.stringify({ module: selectedId, ...moduleState[selectedId] }, null, 2);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(payload)
        .then(() => toast(`Ajustes de ${selectedId} copiados.`))
        .catch(() => toast('Não foi possível copiar os ajustes.', 'error'));
    } else {
      toast('Copiar não é suportado neste navegador.', 'error');
    }
  }

  function restoreModule() {
    moduleState[selectedId] = clone(baselineState[selectedId]);
    renderChain();
    renderModulePanel();
    toast(`${selectedId} restaurado.`);
  }

  /* ─── Song / tone info ─── */

  function renderSongInfo(data) {
    if (!data) {
      els.songInfo.hidden = true;
      els.songInfo.innerHTML = '';
      return;
    }
    const song = data.song_info || {};
    const tone = data.tone_info || {};
    const metaBits = [song.era, song.guitar].filter(Boolean).map(escapeHtml).join(' · ');
    const tags = [tone.character, tone.style, ...(tone.key_effects || [])]
      .filter(Boolean)
      .map((t) => `<span class="tag">${escapeHtml(t)}</span>`)
      .join('');

    els.songInfo.innerHTML = `
      <div>
        <h3>${escapeHtml(song.artist || '')}${song.song ? ' — ' + escapeHtml(song.song) : ''}</h3>
        <p>${escapeHtml(song.description || '')}${metaBits ? ' · ' + metaBits : ''}</p>
      </div>
      <div class="tone-tags">${tags}</div>
    `;
    els.songInfo.hidden = false;
  }

  /* ─── MIDI panel ─── */

  function renderMidiResults(data) {
    if (!data || !data.results || data.results.length === 0) {
      els.midiResults.innerHTML = '<p class="midi-empty">Nenhum arquivo MIDI encontrado para essa busca.</p>';
      els.midiStatus.textContent = 'VAZIO';
      els.midiStatus.dataset.state = 'idle';
      return;
    }
    els.midiStatus.textContent = `${data.results.length} ENCONTRADOS`;
    els.midiStatus.dataset.state = 'idle';
    const items = data.results.map((r) => `
      <li class="midi-item">
        <div>
          <div class="midi-item-title">${escapeHtml(r.title || 'Arquivo MIDI')}</div>
          <div class="midi-item-source mono">${escapeHtml(r.source || '')}</div>
        </div>
        <a href="${escapeHtml(r.download_url || r.page_url || '#')}" target="_blank" rel="noopener noreferrer">ABRIR</a>
      </li>
    `).join('');
    els.midiResults.innerHTML = `<ul class="midi-list">${items}</ul>`;
  }

  function resetMidiPanel() {
    els.midiResults.innerHTML = '<p class="midi-empty">Pesquise um timbre para listar arquivos MIDI relacionados.</p>';
    els.midiStatus.textContent = 'AGUARDANDO';
    els.midiStatus.dataset.state = 'idle';
  }

  /* ─── Aplicar resultado da análise ─── */

  function applyToneData(data) {
    const next = buildDefaultState();
    MODULES.forEach((m) => {
      const incoming = data && data[m.id];
      if (!incoming) return;
      const params = { ...next[m.id].params };
      Object.keys(params).forEach((key) => {
        if (incoming.params && incoming.params[key] !== undefined) {
          params[key] = clampNum(incoming.params[key]);
        }
      });
      next[m.id] = { enabled: !!incoming.enabled, params };
    });
    moduleState = next;
    baselineState = clone(next);
    if (!moduleState[selectedId]) selectedId = 'AMP';
    renderSongInfo(data);
    renderChain();
    renderModulePanel();
  }

  /* ─── Busca / análise ─── */

  async function runAnalysis(query) {
    const q = (query || '').trim();
    if (!q || busy) return;

    setBusy(true);
    const [toneRes, midiRes] = await Promise.allSettled([
      fetch('/api/search-tone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
      }),
      fetch('/api/search-midi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
      }),
    ]);

    if (toneRes.status === 'fulfilled') {
      try {
        const payload = await toneRes.value.json();
        if (toneRes.value.ok && payload.success) {
          applyToneData(payload.data);
          setStatus('idle');
          const song = (payload.data && payload.data.song_info) || {};
          const label = [song.artist, song.song].filter(Boolean).join(' — ');
          toast(label ? `Timbre analisado: ${label}` : 'Timbre analisado.');
        } else {
          setStatus('error');
          toast(payload.error || 'Erro ao analisar timbre.', 'error');
        }
      } catch (e) {
        setStatus('error');
        toast('Resposta inválida ao analisar timbre.', 'error');
      }
    } else {
      setStatus('error');
      toast('Falha de conexão ao analisar timbre.', 'error');
    }

    if (midiRes.status === 'fulfilled') {
      try {
        const payload = await midiRes.value.json();
        renderMidiResults(midiRes.value.ok && payload.success ? payload.data : null);
      } catch (e) {
        renderMidiResults(null);
      }
    } else {
      renderMidiResults(null);
    }

    setBusy(false);
  }

  /* ─── Config (provedor / modelo) ─── */

  function loadConfig() {
    fetch('/api/config')
      .then((r) => r.json())
      .then((cfg) => {
        if (cfg && cfg.provider) {
          els.providerInfo.textContent = `${cfg.provider.toUpperCase()} · ${cfg.model}`;
        }
      })
      .catch(() => {});
  }

  /* ─── Reset geral ─── */

  function resetAll() {
    moduleState = buildDefaultState();
    baselineState = clone(moduleState);
    selectedId = 'AMP';
    els.searchInput.value = '';
    renderSongInfo(null);
    resetMidiPanel();
    renderChain();
    renderModulePanel();
    setStatus('idle');
    toast('Configuração restaurada.');
  }

  /* ─── Navegação por teclado (← / →) ─── */

  function handleKeydown(e) {
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const idx = indexOfModule(selectedId);
    const nextIdx = e.key === 'ArrowRight' ? Math.min(idx + 1, MODULES.length - 1) : Math.max(idx - 1, 0);
    if (nextIdx !== idx) {
      e.preventDefault();
      selectModule(moduleByIndex(nextIdx).id);
    }
  }

  /* ─── Init ─── */

  function bindEvents() {
    els.searchForm.addEventListener('submit', (e) => {
      e.preventDefault();
      runAnalysis(els.searchInput.value);
    });

    document.querySelectorAll('.chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        els.searchInput.value = chip.dataset.query;
        runAnalysis(chip.dataset.query);
      });
    });

    els.resetBtn.addEventListener('click', resetAll);
    document.addEventListener('keydown', handleKeydown);
  }

  function cacheEls() {
    els.searchForm = document.getElementById('search-form');
    els.searchInput = document.getElementById('search-input');
    els.searchBtn = document.getElementById('search-btn');
    els.statusPill = document.getElementById('status-pill');
    els.resetBtn = document.getElementById('reset-btn');
    els.providerInfo = document.getElementById('provider-info');
    els.chainTrack = document.getElementById('chain-track');
    els.chainSummary = document.getElementById('chain-summary');
    els.modulePanel = document.getElementById('module-panel');
    els.midiResults = document.getElementById('midi-results');
    els.midiStatus = document.getElementById('midi-status');
    els.songInfo = document.getElementById('song-info');
    els.toastContainer = document.getElementById('toast-container');
  }

  function init() {
    cacheEls();
    moduleState = buildDefaultState();
    baselineState = clone(moduleState);
    renderChain();
    renderModulePanel();
    bindEvents();
    loadConfig();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
