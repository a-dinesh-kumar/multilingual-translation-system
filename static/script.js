(() => {
  const $ = (id) => document.getElementById(id);
  const sourceLanguage = $('sourceLanguage');
  const targetLanguage = $('targetLanguage');
  const sourceText = $('sourceText');
  const translatedText = $('translatedText');
  const translateBtn = $('translateBtn');
  const errorMessage = $('errorMessage');
  const outputState = $('outputState');
  const copyBtn = $('copyTranslation');
  const resultMeta = $('resultMeta');
  const detectionNote = $('detectionNote');
  const protectTerms = $('protectTerms');
  const charCount = $('charCount');
  const singleModeBtn = $('singleModeBtn');
  const batchModeBtn = $('batchModeBtn');
  const batchNote = $('batchNote');
  let mode = 'single';
  let lastTranslation = '';
  let toastTimer;

  const languageNames = { en: 'English', fr: 'French', es: 'Spanish', hi: 'Hindi', ta: 'Tamil' };

  function showToast(message) {
    const toast = $('toast');
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 2200);
  }

  function setState(state, label) {
    outputState.className = `output-state ${state || ''}`.trim();
    outputState.innerHTML = `<span class="state-dot"></span> ${label}`;
  }

  function updateCount() {
    if (mode === 'single') {
      charCount.textContent = `${sourceText.value.length.toLocaleString()} / 10,000`;
    } else {
      const count = sourceText.value.split('\n').filter(line => line.trim()).length;
      charCount.textContent = `${count} message${count === 1 ? '' : 's'} · ${sourceText.value.length.toLocaleString()} characters`;
    }
  }

  function setMode(nextMode) {
    mode = nextMode;
    const single = mode === 'single';
    singleModeBtn.classList.toggle('active', single);
    batchModeBtn.classList.toggle('active', !single);
    singleModeBtn.setAttribute('aria-selected', String(single));
    batchModeBtn.setAttribute('aria-selected', String(!single));
    $('sourcePanelLabel').textContent = single ? 'Your message' : 'Your messages';
    $('inputHint').textContent = single ? 'Enter text to translate' : 'One message per line · up to 32';
    sourceText.placeholder = single ? 'Type or paste a customer message here…' : 'Enter one customer message per line…';
    translateBtn.querySelector('.btn-label').textContent = single ? 'Translate message' : 'Translate messages';
    batchNote.hidden = single;
    translatedText.textContent = 'Your translation will appear here.';
    translatedText.classList.add('empty-state');
    lastTranslation = '';
    copyBtn.disabled = true;
    resultMeta.hidden = true;
    detectionNote.hidden = true;
    errorMessage.hidden = true;
    setState('', 'Ready');
    updateCount();
  }

  async function translate() {
    const text = sourceText.value.trim();
    errorMessage.hidden = true;
    if (!text) {
      showError(mode === 'single' ? 'Enter a message before translating.' : 'Enter at least one message before translating.');
      sourceText.focus();
      return;
    }
    const messages = text.split('\n').map(line => line.trim()).filter(Boolean);
    if (mode === 'batch' && messages.length > 32) {
      showError('Batch translation supports up to 32 non-empty messages at a time.');
      return;
    }
    if (mode === 'single' && text.length > 10000) {
      showError('Your message must be 10,000 characters or fewer.');
      return;
    }
    if (sourceLanguage.value && sourceLanguage.value === targetLanguage.value) {
      showError('Choose different source and target languages, or use Auto-detect as the source.');
      return;
    }

    translateBtn.disabled = true;
    translateBtn.classList.add('loading');
    translateBtn.querySelector('.btn-label').textContent = 'Translating';
    setState('busy', 'Working');
    translatedText.classList.remove('empty-state');
    translatedText.textContent = mode === 'single' ? 'Translating your message…' : `Translating ${messages.length} messages…`;
    copyBtn.disabled = true;
    resultMeta.hidden = true;
    detectionNote.hidden = true;
    lastTranslation = '';

    // An empty source-language value means Auto-detect. Omit source_language
    // entirely so the backend's notebook-based detector resolves it per message.
    const payload = {
      target_language: targetLanguage.value,
      protect_terms: protectTerms.checked
    };
    if (sourceLanguage.value) {
      payload.source_language = sourceLanguage.value;
    }
    let endpoint;
    if (mode === 'single') {
      endpoint = '/api/translate';
      payload.text = text;
    } else {
      endpoint = '/api/translate/batch';
      payload.messages = messages;
    }

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        let detail = data.detail;
        if (Array.isArray(detail)) detail = detail.map(item => item.msg || JSON.stringify(item)).join('; ');
        throw new Error(detail || `Request failed with status ${response.status}.`);
      }
      if (mode === 'single') renderSingle(data);
      else renderBatch(data);
    } catch (error) {
      const message = error instanceof TypeError
        ? 'Could not reach the API. Open this UI at http://127.0.0.1:8000/ (not by double-clicking index.html), and confirm the FastAPI server is running. The first translation can take several seconds while the model warms up.'
        : (error.message || 'Translation request failed. Check the FastAPI terminal for details.');
      showError(message);
      translatedText.textContent = 'Your translation will appear here.';
      translatedText.classList.add('empty-state');
      setState('', 'Ready');
    } finally {
      translateBtn.disabled = false;
      translateBtn.classList.remove('loading');
      translateBtn.querySelector('.btn-label').textContent = mode === 'single' ? 'Translate message' : 'Translate messages';
    }
  }

  function renderSingle(data) {
    lastTranslation = data.translated_text || '';
    translatedText.textContent = lastTranslation || 'No translation was returned.';
    translatedText.classList.toggle('empty-state', !lastTranslation);
    copyBtn.disabled = !lastTranslation;
    $('resultLanguage').textContent = data.target_language_name || languageNames[data.target_language] || 'Translation';
    const sourceName = data.source_language_name || languageNames[data.source_language] || 'Unknown';
    const confidence = Number(data.detected_confidence);
    $('metaSource').textContent = sourceLanguage.value
      ? `${sourceName} (selected)`
      : `${sourceName} · auto${Number.isFinite(confidence) ? ` ${Math.round(confidence * 100)}%` : ''}`;
    $('metaTokens').textContent = data.input_token_count ?? '—';
    $('metaLatency').textContent = Number.isFinite(Number(data.latency_ms)) ? `${Number(data.latency_ms).toLocaleString(undefined, { maximumFractionDigits: 0 })} ms` : '—';
    $('metaProtection').textContent = protectTerms.checked ? 'Enabled' : 'Disabled';
    resultMeta.hidden = false;
    if (data.detection_note) {
      detectionNote.textContent = data.detection_note;
      detectionNote.hidden = false;
    }
    setState('done', 'Translated');
  }

  function renderBatch(data) {
    const results = Array.isArray(data.results) ? data.results : [];
    lastTranslation = results.map((item, index) => `${index + 1}. ${item.translated_text || ''}`).join('\n\n');
    translatedText.textContent = lastTranslation || 'No translations were returned.';
    translatedText.classList.toggle('empty-state', !lastTranslation);
    copyBtn.disabled = !lastTranslation;
    $('resultLanguage').textContent = `${results.length} result${results.length === 1 ? '' : 's'}`;
    $('metaSource').textContent = sourceLanguage.value
      ? `${languageNames[sourceLanguage.value]} (selected)`
      : 'Auto-detected per message';
    $('metaTokens').textContent = results.reduce((sum, item) => sum + (Number(item.input_token_count) || 0), 0).toLocaleString();
    const totalMs = results.reduce((sum, item) => sum + (Number(item.latency_ms) || 0), 0);
    $('metaLatency').textContent = `${Math.round(totalMs).toLocaleString()} ms total`;
    $('metaProtection').textContent = protectTerms.checked ? 'Enabled' : 'Disabled';
    resultMeta.hidden = false;
    const notes = [...new Set(results.map(item => item.detection_note).filter(Boolean))];
    if (notes.length) {
      detectionNote.textContent = notes.join(' ');
      detectionNote.hidden = false;
    }
    setState('done', `${results.length} translated`);
  }

  function showError(message) {
    errorMessage.textContent = message;
    errorMessage.hidden = false;
    setState('', 'Needs attention');
  }

  $('clearInput').addEventListener('click', () => {
    sourceText.value = '';
    updateCount();
    sourceText.focus();
  });
  sourceText.addEventListener('input', updateCount);
  translateBtn.addEventListener('click', translate);
  singleModeBtn.addEventListener('click', () => setMode('single'));
  batchModeBtn.addEventListener('click', () => setMode('batch'));

  $('swapLanguages').addEventListener('click', () => {
    if (!sourceLanguage.value) {
      showToast('Translate once first to identify the source language, or select it manually.');
      return;
    }
    const oldSource = sourceLanguage.value;
    sourceLanguage.value = targetLanguage.value;
    targetLanguage.value = oldSource;
    $('resultLanguage').textContent = languageNames[targetLanguage.value];
    showToast('Languages swapped');
  });

  copyBtn.addEventListener('click', async () => {
    if (!lastTranslation) return;
    try {
      await navigator.clipboard.writeText(lastTranslation);
      showToast('Translation copied to clipboard');
    } catch (_) {
      const range = document.createRange();
      range.selectNodeContents(translatedText);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      showToast('Select the highlighted text and copy it');
    }
  });

  sourceText.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') translate();
  });

  targetLanguage.addEventListener('change', () => {
    $('resultLanguage').textContent = languageNames[targetLanguage.value];
  });

  // The page and API share the same origin, so no CORS setup is needed.
  updateCount();
})();
