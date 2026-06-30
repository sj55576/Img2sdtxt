/**
 * Tag Autocomplete
 * Stable Diffusion プロンプト用のタグ補完コンポーネント。
 * `.prompt-ta` テキストエリアにアタッチし、カンマ区切りの「現在の単語」を
 * クライアントサイドの JSON データから検索してドロップダウン表示する。
 */
(function () {
  'use strict';

  const TAGS_URL = '/static/data/tags.json';
  const MIN_CHARS = 2;
  const MAX_RESULTS = 15;
  const DEBOUNCE_MS = 150;
  const BLUR_CLOSE_DELAY_MS = 150;

  // ---- Lazy-loaded tag data (cached in closure) ----
  let tagDataPromise = null;
  let tagList = null; // array of { name, cat, a: [...], p }

  function loadTagData() {
    if (tagDataPromise) return tagDataPromise;
    tagDataPromise = fetch(TAGS_URL)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load tag data: ' + res.status);
        return res.json();
      })
      .then((json) => {
        tagList = Array.isArray(json && json.tags) ? json.tags : [];
        return tagList;
      })
      .catch((err) => {
        console.error('[TagAutocomplete] Failed to load tags.json', err);
        tagList = [];
        return tagList;
      });
    return tagDataPromise;
  }

  // ---- Scoring / search ----
  function scoreTag(tag, query) {
    const q = query.toLowerCase();
    const name = tag.name.toLowerCase();
    const priority = typeof tag.p === 'number' ? tag.p : 0;

    if (name === q) return 10000 + priority;
    if (name.startsWith(q)) return 5000 + priority;

    if (Array.isArray(tag.a)) {
      for (const alias of tag.a) {
        const a = String(alias).toLowerCase();
        if (a.startsWith(q)) return 3000 + priority;
      }
    }

    if (name.includes(q)) return 1000 + priority;

    if (Array.isArray(tag.a)) {
      for (const alias of tag.a) {
        const a = String(alias).toLowerCase();
        if (a.includes(q)) return 500 + priority;
      }
    }

    return 0;
  }

  function searchTags(query) {
    if (!tagList || !query) return [];
    const results = [];
    for (const tag of tagList) {
      const score = scoreTag(tag, query);
      if (score > 0) results.push({ tag, score });
    }
    results.sort((a, b) => b.score - a.score);
    return results.slice(0, MAX_RESULTS).map((r) => r.tag);
  }

  // ---- Current word extraction ----
  /**
   * Given full text and cursor position, return info about the
   * comma-separated "current word" the cursor is inside of.
   */
  function getCurrentWordInfo(text, cursorPos) {
    const upToCursor = text.slice(0, cursorPos);
    const lastComma = upToCursor.lastIndexOf(',');
    const wordStartRaw = lastComma === -1 ? 0 : lastComma + 1;

    // Find end of word: next comma at/after cursor, or end of text.
    const fromCursor = text.slice(cursorPos);
    const nextCommaRel = fromCursor.indexOf(',');
    const wordEndRaw = nextCommaRel === -1 ? text.length : cursorPos + nextCommaRel;

    const rawWord = text.slice(wordStartRaw, cursorPos);
    const trimmed = rawWord.trim();

    // Compute the actual start offset of the trimmed word within the text,
    // so we know exactly what range to replace.
    const leadingWhitespace = rawWord.length - rawWord.replace(/^\s+/, '').length;
    const trimmedStart = wordStartRaw + leadingWhitespace;
    const trimmedEnd = trimmedStart + trimmed.length;

    return {
      word: trimmed,
      start: trimmedStart,
      end: trimmedEnd,
      wordEndRaw,
    };
  }

  // ---- Category badge helper ----
  function catClass(cat) {
    const safe = (cat || 'other').toLowerCase().replace(/[^a-z0-9_-]/g, '');
    return 'tag-ac-cat-' + (safe || 'other');
  }

  // ---- Dropdown (single shared instance) ----
  let dropdownEl = null;
  let listEl = null;
  let activeIndex = -1;
  let currentResults = [];
  let activeTextarea = null;
  let activeWordInfo = null;

  function ensureDropdown() {
    if (dropdownEl) return dropdownEl;

    dropdownEl = document.createElement('div');
    dropdownEl.className = 'tag-ac-dropdown';
    dropdownEl.style.display = 'none';

    listEl = document.createElement('ul');
    listEl.className = 'tag-ac-list';
    dropdownEl.appendChild(listEl);

    document.body.appendChild(dropdownEl);

    // Mousedown (not click) so it fires before textarea blur.
    listEl.addEventListener('mousedown', (e) => {
      const item = e.target.closest('.tag-ac-item');
      if (!item) return;
      e.preventDefault();
      const idx = parseInt(item.dataset.index, 10);
      if (!Number.isNaN(idx)) {
        selectSuggestion(idx);
      }
    });

    document.addEventListener('mousedown', (e) => {
      if (!dropdownEl || dropdownEl.style.display === 'none') return;
      if (dropdownEl.contains(e.target) || e.target === activeTextarea) return;
      closeDropdown();
    });

    window.addEventListener('resize', () => {
      if (isOpen()) positionDropdown();
    });
    window.addEventListener('scroll', () => {
      if (isOpen()) positionDropdown();
    }, true);

    return dropdownEl;
  }

  function isOpen() {
    return !!dropdownEl && dropdownEl.style.display !== 'none';
  }

  function positionDropdown() {
    if (!activeTextarea) return;
    const rect = activeTextarea.getBoundingClientRect();
    const viewportH = window.innerHeight;

    dropdownEl.style.visibility = 'hidden';
    dropdownEl.style.display = 'block';
    const ddHeight = dropdownEl.offsetHeight;
    const ddWidth = Math.min(400, Math.max(260, rect.width));
    dropdownEl.style.width = ddWidth + 'px';

    const spaceBelow = viewportH - rect.bottom;
    let top;
    if (spaceBelow < ddHeight + 8 && rect.top > ddHeight + 8) {
      // Not enough room below, but enough above: show above.
      top = rect.top - ddHeight - 4;
    } else {
      top = rect.bottom + 4;
    }

    let left = rect.left;
    const maxLeft = window.innerWidth - ddWidth - 8;
    if (left > maxLeft) left = Math.max(8, maxLeft);

    dropdownEl.style.top = Math.max(4, top) + 'px';
    dropdownEl.style.left = left + 'px';
    dropdownEl.style.visibility = 'visible';
  }

  function renderResults(results) {
    listEl.innerHTML = '';
    results.forEach((tag, idx) => {
      const li = document.createElement('li');
      li.className = 'tag-ac-item';
      li.dataset.index = String(idx);

      const nameSpan = document.createElement('span');
      nameSpan.className = 'tag-ac-name';
      nameSpan.textContent = tag.name;
      li.appendChild(nameSpan);

      if (tag.cat) {
        const badge = document.createElement('span');
        badge.className = 'tag-ac-badge ' + catClass(tag.cat);
        badge.textContent = tag.cat;
        li.appendChild(badge);
      }

      listEl.appendChild(li);
    });
  }

  function setActiveIndex(idx) {
    const items = listEl.querySelectorAll('.tag-ac-item');
    items.forEach((it) => it.classList.remove('active'));
    if (idx >= 0 && idx < items.length) {
      const el = items[idx];
      el.classList.add('active');
      el.scrollIntoView({ block: 'nearest' });
    }
    activeIndex = idx;
  }

  function openDropdownWithResults(textarea, wordInfo, results) {
    ensureDropdown();
    activeTextarea = textarea;
    activeWordInfo = wordInfo;
    currentResults = results;
    renderResults(results);
    setActiveIndex(results.length ? 0 : -1);
    positionDropdown();
  }

  function closeDropdown() {
    if (!dropdownEl) return;
    dropdownEl.style.display = 'none';
    currentResults = [];
    activeIndex = -1;
    activeTextarea = null;
    activeWordInfo = null;
  }

  function selectSuggestion(idx) {
    if (!activeTextarea || !activeWordInfo) return;
    const tag = currentResults[idx];
    if (!tag) return;

    const textarea = activeTextarea;
    const text = textarea.value;
    const { start, end } = activeWordInfo;

    const before = text.slice(0, start);
    let after = text.slice(end);
    const insertion = tag.name + ', ';

    // Strip leading comma (with surrounding whitespace) from `after`
    // to avoid double-comma when replacing a word that precedes one.
    after = after.replace(/^\s*,\s*/, '');
    const newText = before + insertion + after;

    textarea.value = newText;
    const newCursor = (before + insertion).length;
    textarea.setSelectionRange(newCursor, newCursor);
    textarea.focus();

    textarea.dispatchEvent(new Event('input', { bubbles: true }));

    closeDropdown();
  }

  // ---- Per-textarea state ----
  const attachedTextareas = new WeakSet();
  const cleanupFns = new WeakMap();

  function triggerSearch(textarea) {
    const text = textarea.value;
    const cursorPos = textarea.selectionStart;
    const wordInfo = getCurrentWordInfo(text, cursorPos);

    if (wordInfo.word.length < MIN_CHARS) {
      closeDropdown();
      return;
    }

    loadTagData().then(() => {
      // Re-check the textarea is still focused on roughly the same word,
      // in case of fast typing / blur in the meantime.
      if (document.activeElement !== textarea) return;
      const results = searchTags(wordInfo.word);
      if (!results.length) {
        closeDropdown();
        return;
      }
      openDropdownWithResults(textarea, wordInfo, results);
    });
  }

  function attach(textarea) {
    if (!textarea || attachedTextareas.has(textarea)) return;
    attachedTextareas.add(textarea);

    let debounceTimer = null;
    let blurTimer = null;

    function onInput() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => triggerSearch(textarea), DEBOUNCE_MS);
    }

    function onKeydown(e) {
      if (!isOpen() || activeTextarea !== textarea) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (currentResults.length) {
          setActiveIndex((activeIndex + 1) % currentResults.length);
        }
        return;
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (currentResults.length) {
          setActiveIndex((activeIndex - 1 + currentResults.length) % currentResults.length);
        }
        return;
      }

      if (e.key === 'Tab' || e.key === 'Enter') {
        if (activeIndex >= 0 && currentResults[activeIndex]) {
          e.preventDefault();
          selectSuggestion(activeIndex);
        }
        return;
      }

      if (e.key === 'Escape') {
        e.preventDefault();
        closeDropdown();
        return;
      }

      // Any other key: let it type normally; input handler re-triggers search.
    }

    function onBlur() {
      // Delay to allow mousedown-based click selection on the dropdown.
      blurTimer = setTimeout(() => {
        if (activeTextarea === textarea) closeDropdown();
      }, BLUR_CLOSE_DELAY_MS);
    }

    function onFocus() {
      clearTimeout(blurTimer);
    }

    textarea.addEventListener('input', onInput);
    textarea.addEventListener('keydown', onKeydown);
    textarea.addEventListener('blur', onBlur);
    textarea.addEventListener('focus', onFocus);

    cleanupFns.set(textarea, () => {
      clearTimeout(debounceTimer);
      clearTimeout(blurTimer);
      textarea.removeEventListener('input', onInput);
      textarea.removeEventListener('keydown', onKeydown);
      textarea.removeEventListener('blur', onBlur);
      textarea.removeEventListener('focus', onFocus);
      attachedTextareas.delete(textarea);
      if (activeTextarea === textarea) closeDropdown();
    });
  }

  function detach(textarea) {
    const cleanup = cleanupFns.get(textarea);
    if (cleanup) {
      cleanup();
      cleanupFns.delete(textarea);
    }
  }

  function attachAll(root) {
    const scope = root || document;
    scope.querySelectorAll('textarea.prompt-ta').forEach(attach);
  }

  // ---- Mutation observer for dynamically added textareas ----
  let mutationObserver = null;

  function startObserving() {
    if (mutationObserver) return;
    mutationObserver = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType !== 1) return; // ELEMENT_NODE
          if (node.matches && node.matches('textarea.prompt-ta')) {
            attach(node);
          }
          if (node.querySelectorAll) {
            node.querySelectorAll('textarea.prompt-ta').forEach(attach);
          }
        });
      }
    });
    mutationObserver.observe(document.body, { childList: true, subtree: true });
  }

  function stopObserving() {
    if (mutationObserver) {
      mutationObserver.disconnect();
      mutationObserver = null;
    }
  }

  // ---- Public API ----
  function init() {
    attachAll(document);
    startObserving();
  }

  function destroy() {
    stopObserving();
    document.querySelectorAll('textarea.prompt-ta').forEach(detach);
    closeDropdown();
    if (dropdownEl) {
      dropdownEl.remove();
      dropdownEl = null;
      listEl = null;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.TagAutocomplete = { init, destroy };
})();
