/**
 * Prompt Weight Editor
 * SD プロンプト内の (tag:weight) をスライダーで視覚的に調整するコンポーネント
 */
(function () {
  'use strict';

  const WEIGHT_MIN = 0.1;
  const WEIGHT_MAX = 2.0;
  const WEIGHT_STEP = 0.05;
  const DEFAULT_WEIGHT = 1.0;

  /**
   * Parse an SD prompt string into an array of token objects.
   * Handles: plain tags, (tag:1.2), (tag), ((tag)), [tag]
   */
  function parsePrompt(text) {
    if (!text || !text.trim()) return [];

    const tokens = [];
    const parts = text.split(',');

    for (const raw of parts) {
      const trimmed = raw.trim();
      if (!trimmed) continue;

      let tag = trimmed;
      let weight = DEFAULT_WEIGHT;
      let format = 'plain';

      // (tag:weight) format
      const explicitMatch = trimmed.match(/^\(+([^()]+):(\d+\.?\d*)\)+$/);
      if (explicitMatch) {
        tag = explicitMatch[1].trim();
        weight = parseFloat(explicitMatch[2]);
        format = 'explicit';
      }
      // ((tag)) or (tag) without explicit weight
      else if (/^\(+[^():]+\)+$/.test(trimmed)) {
        const parens = trimmed.match(/^(\(+)/)[1].length;
        tag = trimmed.replace(/^\(+|\)+$/g, '').trim();
        weight = Math.round(Math.pow(1.1, parens) * 100) / 100;
        format = 'parens';
      }
      // [tag] format (de-emphasis)
      else if (/^\[+[^\[\]]+\]+$/.test(trimmed)) {
        const brackets = trimmed.match(/^(\[+)/)[1].length;
        tag = trimmed.replace(/^\[+|\]+$/g, '').trim();
        weight = Math.round(Math.pow(1 / 1.1, brackets) * 100) / 100;
        format = 'brackets';
      }

      tokens.push({ tag, weight, format, original: trimmed });
    }
    return tokens;
  }

  /**
   * Reconstruct prompt string from token objects.
   */
  function buildPrompt(tokens) {
    return tokens.map(t => {
      const w = Math.round(t.weight * 100) / 100;
      if (Math.abs(w - DEFAULT_WEIGHT) < 0.01) {
        return t.tag;
      }
      return `(${t.tag}:${w.toFixed(2)})`;
    }).join(', ');
  }

  /**
   * Get color for a weight value.
   */
  function weightColor(w) {
    if (w > 1.3) return '#e74c3c';
    if (w > 1.1) return '#e67e22';
    if (w > 1.0 + 0.01) return '#f39c12';
    if (w < 0.7) return '#3498db';
    if (w < 0.9) return '#2980b9';
    if (w < 1.0 - 0.01) return '#5dade2';
    return 'var(--text-primary, #333)';
  }

  /**
   * Create the weight editor panel for a given textarea.
   * @param {HTMLTextAreaElement} textarea - The prompt textarea to attach to
   * @param {object} opts - Options
   * @param {string} opts.containerId - ID for the editor container
   * @returns {object} Editor API { refresh(), destroy() }
   */
  function createWeightEditor(textarea, opts = {}) {
    const containerId = opts.containerId || `weight-editor-${Date.now()}`;

    // Create container
    const container = document.createElement('div');
    container.id = containerId;
    container.className = 'weight-editor';

    const header = document.createElement('div');
    header.className = 'weight-editor-header';
    header.innerHTML = `
      <span class="weight-editor-title">Weight Editor</span>
      <button class="weight-editor-toggle btn btn-sm btn-ghost" type="button" title="Toggle weight editor">
        ⚖️
      </button>
    `;
    container.appendChild(header);

    const body = document.createElement('div');
    body.className = 'weight-editor-body';
    container.appendChild(body);

    textarea.parentNode.insertBefore(container, textarea.nextSibling);

    let expanded = false;
    let tokens = [];

    const toggleBtn = header.querySelector('.weight-editor-toggle');
    const titleSpan = header.querySelector('.weight-editor-title');

    function toggle() {
      expanded = !expanded;
      body.classList.toggle('expanded', expanded);
      container.classList.toggle('active', expanded);
      if (expanded) refresh();
    }

    titleSpan.addEventListener('click', toggle);
    toggleBtn.addEventListener('click', toggle);

    function refresh() {
      tokens = parsePrompt(textarea.value);
      renderTokens();
    }

    function renderTokens() {
      body.innerHTML = '';

      if (tokens.length === 0) {
        body.innerHTML = '<div class="weight-editor-empty">プロンプトを入力すると、ここでウェイトを調整できます</div>';
        return;
      }

      tokens.forEach((token, idx) => {
        const row = document.createElement('div');
        row.className = 'weight-editor-row';

        const tagLabel = document.createElement('span');
        tagLabel.className = 'weight-tag-label';
        tagLabel.textContent = token.tag;
        tagLabel.style.color = weightColor(token.weight);
        tagLabel.title = token.original;

        const sliderWrap = document.createElement('div');
        sliderWrap.className = 'weight-slider-wrap';

        const slider = document.createElement('input');
        slider.type = 'range';
        slider.className = 'weight-slider';
        slider.min = WEIGHT_MIN;
        slider.max = WEIGHT_MAX;
        slider.step = WEIGHT_STEP;
        slider.value = token.weight;

        const valueDisplay = document.createElement('span');
        valueDisplay.className = 'weight-value';
        valueDisplay.textContent = token.weight.toFixed(2);
        valueDisplay.style.color = weightColor(token.weight);

        const resetBtn = document.createElement('button');
        resetBtn.type = 'button';
        resetBtn.className = 'weight-reset-btn';
        resetBtn.textContent = '↺';
        resetBtn.title = 'Reset to 1.00';

        slider.addEventListener('input', () => {
          const w = parseFloat(slider.value);
          token.weight = w;
          valueDisplay.textContent = w.toFixed(2);
          valueDisplay.style.color = weightColor(w);
          tagLabel.style.color = weightColor(w);
          updateTextarea();
        });

        resetBtn.addEventListener('click', () => {
          token.weight = DEFAULT_WEIGHT;
          slider.value = DEFAULT_WEIGHT;
          valueDisplay.textContent = DEFAULT_WEIGHT.toFixed(2);
          valueDisplay.style.color = weightColor(DEFAULT_WEIGHT);
          tagLabel.style.color = weightColor(DEFAULT_WEIGHT);
          updateTextarea();
        });

        sliderWrap.appendChild(slider);

        row.appendChild(tagLabel);
        row.appendChild(sliderWrap);
        row.appendChild(valueDisplay);
        row.appendChild(resetBtn);
        body.appendChild(row);
      });
    }

    function updateTextarea() {
      const newText = buildPrompt(tokens);
      textarea.value = newText;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // Debounced refresh on textarea input
    let debounceTimer = null;
    function onTextareaInput() {
      if (!expanded) return;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(refresh, 500);
    }
    textarea.addEventListener('input', onTextareaInput);

    function destroy() {
      textarea.removeEventListener('input', onTextareaInput);
      container.remove();
    }

    return { refresh, destroy, toggle, container };
  }

  // Expose globally
  window.WeightEditor = {
    create: createWeightEditor,
    parse: parsePrompt,
    build: buildPrompt,
  };
})();
