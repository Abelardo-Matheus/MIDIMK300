/* ============================================================
   MK-300 Tone Assistant — front-end
   Cadeia de 11 módulos clicável, painel de parâmetros com
   sliders ao vivo, MIDI, toasts e navegação por teclado.
   Dados reais via /api/search-tone, /api/search-midi, /api/config.
   ============================================================ */

(function () {
  'use strict';

  // WAH/FX/GATE/MOD: cada modelo real tem seu PRÓPRIO conjunto de parâmetros
  // (ex.: "X-Wah" usa Value/Gain/Level, "Wah-Wah" usa Speed/Q/Mix/Width/Level/
  // Sync/Sync Bpm). Por isso esses 4 módulos não têm uma lista fixa de
  // parâmetros aqui — os rótulos e a quantidade de sliders são resolvidos em
  // tempo real a partir do catálogo buscado em /api/effects (ver
  // paramLabelsFor() e renderModulePanel()), usando slots genéricos
  // param1..paramN armazenados no estado. DYNAMIC_MAX_PARAMS abaixo precisa
  // bater com MAX_PARAMS do app.py.
  const DYNAMIC_MAX_PARAMS = { WAH: 7, FX: 8, GATE: 8, MOD: 6 };
  const PARAM_RANGE_OVERRIDES = { 'Sync': [0, 1], 'Sync Bpm': [40, 240], 'Semi': [-24, 24] };
  let effectsCatalog = { wah: [], fx: [], gate: [], mod: [] };

  const MODULES = [
    { id: 'WAH', name: 'WAH', sub: 'Wah / Expressão',
      hint: 'O bloco WAH tem vários modelos reais (X-Wah, Wah-Wah, Sense-Wah...), cada um com seus próprios controles.',
      dynamic: true, params: [] },
    { id: 'FX', name: 'FX', sub: 'Compressor / FX',
      hint: 'O bloco FX cobre compressores, boosts, pitch e outros efeitos de entrada — os controles mudam conforme o modelo.',
      dynamic: true, params: [] },
    { id: 'GATE', name: 'GATE', sub: 'Noise Gate / Compressor',
      hint: 'O bloco GATE tem modelos de noise gate e também de compressor — os controles mudam conforme o modelo.',
      dynamic: true, params: [] },
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
      hint: 'O bloco MOD tem vários modelos reais (Chorus, Flanger, Tremolo, Phaser...), cada um com seus próprios controles.',
      dynamic: true, params: [] },
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
  let lastToneData = null;
  let lastQuery = '';

  const PRESETS_KEY = 'mk300_saved_presets';

  function clone(obj) { return JSON.parse(JSON.stringify(obj)); }

  function clampNum(v, min, max) {
    const lo = min === undefined ? 0 : min;
    const hi = max === undefined ? 100 : max;
    const n = Number(v);
    if (Number.isNaN(n)) return Math.round((lo + hi) / 2);
    return Math.max(lo, Math.min(hi, Math.round(n)));
  }

  function escapeHtml(str) {
    return String(str == null ? '' : str).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  /* ─── Presets salvos (localStorage) ─── */

  function normalizeQuery(q) {
    return String(q || '').trim().toLowerCase().replace(/\s+/g, ' ');
  }

  function loadPresetsStore() {
    try {
      const raw = localStorage.getItem(PRESETS_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }

  function savePresetsStore(store) {
    try {
      localStorage.setItem(PRESETS_KEY, JSON.stringify(store));
    } catch (e) {
      /* localStorage indisponível (modo privado, quota, etc.) — ignora silenciosamente */
    }
  }

  function getPreset(query) {
    const store = loadPresetsStore();
    return store[normalizeQuery(query)] || null;
  }

  function upsertPreset(query, toneData, midiData) {
    const store = loadPresetsStore();
    const key = normalizeQuery(query);
    store[key] = {
      query: String(query).trim(),
      toneData,
      midiData,
      savedAt: Date.now(),
    };
    savePresetsStore(store);
    renderPresetsList();
  }

  function removePreset(key) {
    const store = loadPresetsStore();
    delete store[key];
    savePresetsStore(store);
    renderPresetsList();
  }

  function clearAllPresets() {
    savePresetsStore({});
    renderPresetsList();
    toast('Presets salvos removidos.');
  }

  function formatRelativeTime(ts) {
    const diff = Math.max(0, Date.now() - ts);
    const min = Math.floor(diff / 60000);
    if (min < 1) return 'agora';
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h} h`;
    const d = Math.floor(h / 24);
    return `${d} d`;
  }

  function renderPresetsList() {
    if (!els.presetsList) return;
    const store = loadPresetsStore();
    const entries = Object.entries(store).sort((a, b) => b[1].savedAt - a[1].savedAt);
    if (els.presetsCount) els.presetsCount.textContent = String(entries.length);

    if (entries.length === 0) {
      els.presetsList.innerHTML = '<li class="presets-empty">Nenhum preset salvo ainda. Suas buscas s&atilde;o salvas automaticamente.</li>';
      return;
    }

    els.presetsList.innerHTML = entries.map(([key, entry]) => `
      <li class="preset-item" data-key="${escapeHtml(key)}">
        <button type="button" class="preset-item-main" data-key="${escapeHtml(key)}">
          <span class="preset-item-title">${escapeHtml(entry.query)}</span>
          <span class="preset-item-time mono">${formatRelativeTime(entry.savedAt)}</span>
        </button>
        <button type="button" class="preset-item-remove" data-key="${escapeHtml(key)}" aria-label="Remover preset">&times;</button>
      </li>
    `).join('');
  }

  function positionPresetsPanel() {
    const rect = els.presetsBtn.getBoundingClientRect();
    const panelWidth = Math.min(300, window.innerWidth - 24);
    let left = rect.right - panelWidth;
    left = Math.max(12, Math.min(left, window.innerWidth - panelWidth - 12));
    let top = rect.bottom + 8;
    top = Math.min(top, window.innerHeight - 60);
    els.presetsPanel.style.left = `${left}px`;
    els.presetsPanel.style.top = `${top}px`;
  }

  function togglePresetsPanel(force) {
    const open = typeof force === 'boolean' ? force : els.presetsPanel.hidden;
    els.presetsPanel.hidden = !open;
    els.presetsBtn.setAttribute('aria-expanded', String(open));
    if (open) {
      renderPresetsList();
      positionPresetsPanel();
    }
  }

  function buildDefaultState() {
    const state = {};
    MODULES.forEach((m) => {
      const params = {};
      if (m.dynamic) {
        const n = DYNAMIC_MAX_PARAMS[m.id] || 0;
        for (let i = 1; i <= n; i++) params[`param${i}`] = 0;
      } else {
        m.params.forEach((p) => { params[p.key] = 50; });
        if (m.id === 'AMP') {
          Object.assign(params, { gain: 50, bass: 55, middle: 50, treble: 58, presence: 50 });
        }
      }
      state[m.id] = { enabled: DEFAULT_ENABLED[m.id], params, type: null };
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
        <div class="module-sub">${st.type ? escapeHtml(st.type) : m.sub}</div>
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

  function normalizeModelName(s) {
    return String(s || '').trim().toLowerCase().replace(/[\s_-]+/g, '');
  }

  function findDynamicModel(moduleId, typeName) {
    const list = effectsCatalog[moduleId.toLowerCase()];
    if (!list || !typeName) return null;
    const target = normalizeModelName(typeName);
    return list.find((mo) => normalizeModelName(mo.name) === target) || null;
  }

  function renderModulePanel() {
    const m = MODULES.find((x) => x.id === selectedId);
    const st = moduleState[selectedId];
    const panel = els.modulePanel;
    panel.dataset.enabled = String(st.enabled);

    let paramsHtml = '';
    let unconfirmedNote = '';

    if (m.dynamic) {
      const model = findDynamicModel(m.id, st.type);
      if (model && model.params && model.params.length) {
        paramsHtml = model.params.map((label, i) => {
          const key = `param${i + 1}`;
          const range = PARAM_RANGE_OVERRIDES[label] || [0, 100];
          const value = st.params[key] !== undefined ? st.params[key] : range[0];
          return `
            <div class="param-row">
              <div class="param-label-row">
                <span class="param-name">${escapeHtml(label)}</span>
                <span class="param-value mono" data-key="${key}">${value}</span>
              </div>
              <input type="range" min="${range[0]}" max="${range[1]}" value="${value}" data-key="${key}" aria-label="${escapeHtml(label)}">
            </div>
          `;
        }).join('');
        if (model.unconfirmed) {
          unconfirmedNote = `<p class="module-hint module-hint-warn">⚠ Parâmetros deste modelo (${escapeHtml(model.name)}) ainda não foram confirmados oficialmente — valores aproximados por padrão com modelos parecidos.</p>`;
        }
      } else if (st.type) {
        paramsHtml = `<p class="midi-empty">Modelo "${escapeHtml(st.type)}" não reconhecido no catálogo — pesquise novamente ou ajuste direto na pedaleira.</p>`;
      } else {
        paramsHtml = `<p class="midi-empty">Pesquise um timbre para ver os parâmetros reais deste módulo.</p>`;
      }
    } else {
      paramsHtml = m.params.map((p) => `
        <div class="param-row">
          <div class="param-label-row">
            <span class="param-name">${p.label}</span>
            <span class="param-value mono" data-key="${p.key}">${st.params[p.key]}</span>
          </div>
          <input type="range" min="0" max="100" value="${st.params[p.key]}" data-key="${p.key}" aria-label="${p.label}">
        </div>
      `).join('');
    }

    const modelRowHtml = st.type ? `
      <div class="module-model-row">
        <span class="module-model-label">Modelo na pedaleira</span>
        <span class="module-model-value mono">${escapeHtml(st.type)}</span>
      </div>
    ` : '';

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
      ${modelRowHtml}
      <div id="param-list">${paramsHtml}</div>
      <div class="param-actions">
        <button type="button" class="btn-outline" id="copy-module-btn">Copiar ajustes do m&oacute;dulo</button>
        <button type="button" class="btn-outline" id="restore-module-btn">Restaurar</button>
      </div>
      ${unconfirmedNote}
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
        const min = Number(input.min) || 0;
        const max = Number(input.max) || 100;
        st.params[key] = clampNum(input.value, min, max);
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
      <div class="song-info-main">
        <div>
          <h3>${escapeHtml(song.artist || '')}${song.song ? ' — ' + escapeHtml(song.song) : ''}</h3>
          <p>${escapeHtml(song.description || '')}${metaBits ? ' · ' + metaBits : ''}</p>
        </div>
        <button type="button" id="export-dzh-btn" class="btn btn-outline" title="Baixa um arquivo .dzh para carregar direto na MK-300 (beta)">
          BAIXAR PRESET (.dzh)
        </button>
      </div>
      <div class="tone-tags">${tags}</div>
    `;
    els.songInfo.hidden = false;

    const exportBtn = document.getElementById('export-dzh-btn');
    if (exportBtn) exportBtn.addEventListener('click', downloadDzhPreset);
  }

  /* ─── Export .dzh (preset binário para a MK-300) ─── */

  async function downloadDzhPreset() {
    if (!lastToneData) {
      toast('Pesquise um timbre antes de baixar o preset.', 'error');
      return;
    }
    const btn = document.getElementById('export-dzh-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'GERANDO...'; }
    try {
      const presetName = (lastToneData.song_info && lastToneData.song_info.song)
        ? `${lastToneData.song_info.artist || ''} - ${lastToneData.song_info.song}`.trim()
        : (lastQuery || 'MK300_PRESET');

      const resp = await fetch('/api/export-dzh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tone_data: lastToneData, preset_name: presetName }),
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || `Erro HTTP ${resp.status}`);
      }

      const blob = await resp.blob();
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = /filename="?([^";]+)"?/.exec(disposition);
      const filename = match ? match[1] : `${presetName.replace(/\s+/g, '_')}.dzh`;
      const warningsHeader = resp.headers.get('X-Dzh-Warnings');

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      toast(`Preset .dzh baixado: ${filename} (beta — confira AMP/CAB/DS/VOL na pedaleira)`);

      if (warningsHeader) {
        try {
          const warnings = JSON.parse(warningsHeader);
          warnings.forEach((w) => toast(w, 'error'));
        } catch (e) { /* ignore malformed header */ }
      }
    } catch (err) {
      toast(`Não foi possível gerar o .dzh: ${err.message}`, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'BAIXAR PRESET (.dzh)'; }
    }
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
    lastToneData = data || null;
    const next = buildDefaultState();
    MODULES.forEach((m) => {
      const incoming = data && data[m.id];
      if (!incoming) return;
      const type = incoming.params && incoming.params.type ? String(incoming.params.type) : null;
      const params = { ...next[m.id].params };

      // Para módulos dinâmicos (WAH/FX/GATE/MOD), cada slot paramN tem uma
      // faixa diferente dependendo do rótulo real do modelo selecionado
      // (ex.: "Sync" é 0/1, "Sync Bpm" é 40-240) — resolve isso antes de
      // aplicar o clamp, senão um valor válido como Sync Bpm=120 seria
      // cortado para 100 pelo clamp genérico 0-100.
      const model = m.dynamic ? findDynamicModel(m.id, type) : null;

      Object.keys(params).forEach((key) => {
        if (incoming.params && incoming.params[key] !== undefined) {
          let min = 0, max = 100;
          if (model && model.params) {
            const idx = Number(key.replace('param', '')) - 1;
            const label = model.params[idx];
            const range = label && PARAM_RANGE_OVERRIDES[label];
            if (range) { min = range[0]; max = range[1]; }
          }
          params[key] = clampNum(incoming.params[key], min, max);
        }
      });
      next[m.id] = { enabled: !!incoming.enabled, params, type };
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
    lastQuery = q;

    // ─ Preset já salvo com esse nome: usa o cache local, sem requisição extra ─
    const cached = getPreset(q);
    if (cached) {
      applyToneData(cached.toneData);
      renderMidiResults(cached.midiData);
      els.searchInput.value = cached.query;
      setStatus('idle');
      togglePresetsPanel(false);
      toast(`Preset salvo carregado: ${cached.query} (sem nova requisição)`);
      return;
    }

    setBusy(true);
    let toneDataOk = null;
    let midiDataOk = null;
    let toneSucceeded = false;

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
          toneDataOk = payload.data;
          toneSucceeded = true;
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
        midiDataOk = midiRes.value.ok && payload.success ? payload.data : null;
        renderMidiResults(midiDataOk);
      } catch (e) {
        renderMidiResults(null);
      }
    } else {
      renderMidiResults(null);
    }

    // ─ Só salva como preset quando a análise de timbre teve sucesso ─
    if (toneSucceeded) {
      upsertPreset(q, toneDataOk, midiDataOk);
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

  function loadEffectsCatalog() {
    fetch('/api/effects')
      .then((r) => r.json())
      .then((data) => {
        if (data && data.wah) {
          effectsCatalog = { wah: data.wah, fx: data.fx, gate: data.gate, mod: data.mod };
          // re-renderiza caso o módulo selecionado seja dinâmico e já tenha
          // um tipo aplicado antes do catálogo terminar de carregar
          if (MODULES.find((m) => m.id === selectedId && m.dynamic)) {
            renderModulePanel();
          }
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
    lastToneData = null;
    lastQuery = '';
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
    window.addEventListener('resize', () => {
      if (!els.presetsPanel.hidden) positionPresetsPanel();
    });

    // ─ Presets salvos ─
    els.presetsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      togglePresetsPanel();
    });

    els.presetsList.addEventListener('click', (e) => {
      const removeBtn = e.target.closest('.preset-item-remove');
      if (removeBtn) {
        removePreset(removeBtn.dataset.key);
        return;
      }
      const mainBtn = e.target.closest('.preset-item-main');
      if (mainBtn) {
        const store = loadPresetsStore();
        const entry = store[mainBtn.dataset.key];
        if (entry) {
          els.searchInput.value = entry.query;
          runAnalysis(entry.query);
        }
      }
    });

    els.presetsClearBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      clearAllPresets();
    });

    els.presetsPanel.addEventListener('click', (e) => e.stopPropagation());

    document.addEventListener('click', () => togglePresetsPanel(false));
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
    els.presetsBtn = document.getElementById('presets-btn');
    els.presetsPanel = document.getElementById('presets-panel');
    els.presetsList = document.getElementById('presets-list');
    els.presetsCount = document.getElementById('presets-count');
    els.presetsClearBtn = document.getElementById('presets-clear-btn');
  }

  function init() {
    cacheEls();
    moduleState = buildDefaultState();
    baselineState = clone(moduleState);
    renderChain();
    renderModulePanel();
    renderPresetsList();
    bindEvents();
    loadConfig();
    loadEffectsCatalog();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
