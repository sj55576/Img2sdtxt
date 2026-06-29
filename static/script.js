/* =====================================================================
   App State
   ===================================================================== */
let selectedImage = null;
let batchFiles = [];
let currentTab = 'tab-img'; // 'tab-img' | 'tab-txt'
let presetsCache = [];
let inpaintSelectedImage = null;
let _galleryCache = {};   // key: "mode|date|offset" → API response
let _galleryOffset = 0;   // 現在の Load More オフセット
let _gallerySelectionMode = false;
let _gallerySelectedPaths = new Set();

// Gallery modal navigation
let _galleryImages = [];
let _galleryCurrentIndex = -1;

// Negative prompt templates
const NEGATIVE_TEMPLATES = {
    'general': { label: '🎯 汎用', text: 'lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry' },
    'portrait': { label: '👤 人物', text: 'deformed iris, deformed pupils, bad eyes, cross-eyed, poorly drawn face, cloned face, extra fingers, mutated hands, fused fingers, too many fingers, extra arms, extra legs, malformed limbs, missing arms, missing legs, poorly drawn hands, bad proportions, ugly, duplicate, morbid, mutilated' },
    'anime': { label: '🎨 アニメ', text: 'lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, artist name, bad-artist, bad_prompt' },
    'landscape': { label: '🏔️ 風景', text: 'lowres, text, error, cropped, worst quality, low quality, jpeg artifacts, ugly, duplicate, blurry, bad photo, bad photography, watermark, signature, username, logo' },
    'realistic': { label: '📷 リアル', text: 'illustration, painting, drawing, art, sketch, anime, cartoon, 3d render, lowres, text, error, cropped, worst quality, low quality, jpeg artifacts, ugly, duplicate, blurry, deformed, disfigured, mutation, extra limbs' }
};

function populateNegTemplates(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    sel.innerHTML = '<option value="">📝 テンプレート挿入...</option>';
    for (const [key, tmpl] of Object.entries(NEGATIVE_TEMPLATES)) {
        sel.innerHTML += `<option value="${key}">${tmpl.label}</option>`;
    }
}

function applyNegTemplate(selectId, textareaId, tokenCounterId) {
    const sel = document.getElementById(selectId);
    const textarea = document.getElementById(textareaId);
    if (!sel || !textarea || !sel.value) return;
    const tmpl = NEGATIVE_TEMPLATES[sel.value];
    if (!tmpl) return;
    textarea.value = textarea.value ? textarea.value + ', ' + tmpl.text : tmpl.text;
    sel.value = '';
    if (tokenCounterId) updateTokenCounter(textareaId, tokenCounterId);
    toast('テンプレートを挿入しました', 'success');
}

function estimateTokens(text) {
    if (!text.trim()) return 0;
    const words = text.replace(/[,()[\]{}:]/g, ' $& ').split(/\s+/).filter(Boolean);
    return words.length;
}

function updateTokenCounter(textareaId, counterId) {
    const textarea = document.getElementById(textareaId);
    const counter = document.getElementById(counterId);
    if (!textarea || !counter) return;
    const count = estimateTokens(textarea.value);
    counter.textContent = count > 0 ? `~${count} tokens` : '';
    counter.classList.remove('warning', 'danger');
    if (count > 150) counter.classList.add('danger');
    else if (count > 75) counter.classList.add('warning');
}

// モデル選択の永続化（タブ切り替えでリセットされないよう変数で保持）
const _selectedModel = { sd: '', img2img: '', inpaint: '' };
// モデルリストの初回ロード済みフラグ（タブ切り替え時の再構築を防ぐ）
const _modelsLoaded = { sd: false, img2img: false, inpaint: false };

// FE-2: Status check promise cache (prevents concurrent duplicate fetches)
const _sdStatusPromise = { sd: null, img2img: null, inpaint: null };

// FE-1: Multi-model running guard
let _multiModelRunning = false;

// FE-6: History items map (id → item object)
const _historyItems = new Map();


function updateConnectionHelp(service, isOk, detail = '') {
    const help = document.getElementById('connection-help');
    if (!help) return;

    const state = help.dataset.state ? JSON.parse(help.dataset.state) : {};
    state[service] = { ok: isOk, detail };
    help.dataset.state = JSON.stringify(state);

    const llm = state.llm;
    const sd = state.sd;
    help.classList.remove('ok', 'warn');

    if (llm?.ok && sd?.ok) {
        help.classList.add('ok');
        help.innerHTML = '<strong>接続済み</strong><span>LLM と SD API を利用できます。</span>';
        return;
    }

    help.classList.add('warn');
    if (llm && !llm.ok) {
        help.innerHTML = '<strong>LLM 未接続</strong><span>プロンプト生成には LLM サーバー設定を確認してください。</span>';
        return;
    }
    if (sd && !sd.ok) {
        help.innerHTML = '<strong>SD API 未接続</strong><span>SD Generate を使うには WebUI API 起動と接続設定を確認してください。</span>';
        return;
    }

    help.innerHTML = '<strong>接続を確認中...</strong><span>LLM / SD API の状態を確認しています。</span>';
}

/* =====================================================================
   Theme Management
   ===================================================================== */
(function initThemeEarly() {
    // Apply theme before first paint to avoid flash
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'light');
    if (theme === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
})();

function applyTheme(theme) {
    if (theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
        btn.textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
        btn.title = theme === 'dark' ? 'ライトモードに切り替え' : 'ダークモードに切り替え';
    }
}

function setupThemeToggle() {
    // Determine initial theme: localStorage → system preference → light
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    let currentTheme = saved || (prefersDark ? 'dark' : 'light');
    applyTheme(currentTheme);

    // Listen for system preference changes (only when no user override)
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        if (!localStorage.getItem('theme')) {
            currentTheme = e.matches ? 'dark' : 'light';
            applyTheme(currentTheme);
        }
    });

    // Toggle button handler
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
        btn.addEventListener('click', () => {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            currentTheme = isDark ? 'light' : 'dark';
            localStorage.setItem('theme', currentTheme);
            applyTheme(currentTheme);
        });
    }
}

/* =====================================================================
   Init
   ===================================================================== */
document.addEventListener('DOMContentLoaded', () => {
    // i18n initialization
    if (typeof I18n !== 'undefined') {
        I18n.init();
        const langBtn = document.getElementById('lang-toggle-btn');
        if (langBtn) {
            langBtn.textContent = I18n.getLocale() === 'ja' ? '🌐 日本語' : '🌐 English';
            langBtn.addEventListener('click', () => {
                const next = I18n.getLocale() === 'ja' ? 'en' : 'ja';
                I18n.setLocale(next);
                langBtn.textContent = next === 'ja' ? '🌐 日本語' : '🌐 English';
            });
        }
    }

    const _setup = (name, fn) => { try { fn(); } catch(e) { console.error(`[SETUP] ${name} failed:`, e); } };
    _setup('theme', setupThemeToggle);
    _setup('navigation', setupNavigation);
    _setup('generate', setupGeneratePage);
    _setup('batch', setupBatchPage);
    _setup('refine', setupRefinePage);
    _setup('history', setupHistoryPage);
    _setup('presets', setupPresetsPage);
    _setup('sd', setupSDPage);
    _setup('img2img', setupImg2ImgPage);
    _setup('inpaint', setupInpaintPage);
    _setup('gallery', setupGalleryPage);
    _setup('weightEditors', setupWeightEditors);
    checkStatus();
    loadProviders();

    document.getElementById('llm-provider-select')?.addEventListener('change', function() {
        updateProviderUI();
        const modelInput = document.getElementById('provider-model');
        const opt = this.options[this.selectedIndex];
        if (modelInput && opt) modelInput.value = opt.dataset.defaultModel || '';
    });
    document.getElementById('provider-apply-btn')?.addEventListener('click', applyProvider);

    // Initialize SD and Img2Img selectors early for parameter restoration
    checkSDStatus();
    checkImg2ImgStatus();
    checkInpaintStatus();

    // FE-5: Ctrl+Enter shortcut to trigger generation
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            const activePage = document.querySelector('.page.active');
            if (!activePage) return;
            const pageId = activePage.id;
            if (pageId === 'page-generate') {
                const btn = document.getElementById('generate-btn');
                if (!btn.disabled) btn.click();
            } else if (pageId === 'page-refine') {
                const btn = document.getElementById('refine-btn');
                if (!btn.disabled) btn.click();
            } else if (pageId === 'page-sd') {
                const btn = document.getElementById('sd-generate-btn');
                if (btn && !btn.disabled) btn.click();
            } else if (pageId === 'page-img2img') {
                const btn = document.getElementById('i2i-generate-btn');
                if (btn && !btn.disabled) btn.click();
            } else if (pageId === 'page-inpaint') {
                const btn = document.getElementById('inpaint-generate-btn');
                if (btn && !btn.disabled) btn.click();
            }
        }
    });

    // Keyboard shortcuts system
    document.addEventListener('keydown', e => {
        const tag = document.activeElement?.tagName;
        const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

        // ? key - show shortcuts help (when not in input)
        if (e.key === '?' && !isInput) {
            e.preventDefault();
            const modal = document.getElementById('shortcuts-modal');
            modal.classList.toggle('hidden');
            return;
        }

        // Escape - close any open modal
        if (e.key === 'Escape') {
            const modals = ['shortcuts-modal', 'preset-modal', 'model-confirm-modal'];
            for (const id of modals) {
                const m = document.getElementById(id);
                if (m && !m.classList.contains('hidden')) {
                    m.classList.add('hidden');
                    e.preventDefault();
                    return;
                }
            }
            return;
        }

        // Number keys 1-9 for page navigation (when not in input)
        if (!isInput && !e.ctrlKey && !e.metaKey && !e.altKey) {
            const pages = ['generate', 'batch', 'refine', 'history', 'presets', 'sd', 'img2img', 'inpaint', 'gallery'];
            const num = parseInt(e.key);
            if (num >= 1 && num <= pages.length) {
                e.preventDefault();
                const btn = document.querySelector(`.nav-btn[data-page="${pages[num - 1]}"]`);
                if (btn) btn.click();
                return;
            }
        }
    });

    // Shortcuts modal close button
    document.getElementById('shortcuts-modal-close')?.addEventListener('click', () => {
        document.getElementById('shortcuts-modal').classList.add('hidden');
    });
    document.getElementById('shortcuts-modal')?.addEventListener('click', e => {
        if (e.target === e.currentTarget) {
            e.currentTarget.classList.add('hidden');
        }
    });

    // Prevent default drag and drop behavior on document
    document.addEventListener('dragover', e => {
        e.preventDefault();
        e.stopPropagation();
    });
    document.addEventListener('dragleave', e => {
        e.preventDefault();
        e.stopPropagation();
    });
    document.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
    });

    // Global paste handler: Ctrl+V でクリップボードの画像を読み込む（全ブラウザ対応）
    document.addEventListener('paste', e => {
        const items = e.clipboardData?.items;
        if (!items) return;
        for (const item of items) {
            if (item.type.startsWith('image/')) {
                const file = item.getAsFile();
                if (file) {
                    handleSingleImageSelect(file);
                    e.preventDefault();
                    break;
                }
            }
        }
    });
});

/* =====================================================================
   Navigation
   ===================================================================== */
function setupNavigation() {
    function navigateTo(page) {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.mobile-nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

        document.querySelectorAll(`.nav-btn[data-page="${page}"], .mobile-nav-btn[data-page="${page}"]`).forEach(b => b.classList.add('active'));
        document.getElementById(`page-${page}`).classList.add('active');

        // Lazy-load page data
        if (page === 'history') loadHistory();
        if (page === 'presets') loadPresets();
        if (page === 'sd') checkSDStatus();
        if (page === 'img2img') checkImg2ImgStatus();
        if (page === 'inpaint') checkInpaintStatus();
        if (page === 'gallery') { loadGallery(); loadGalleryFilters(); }
    }

    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => navigateTo(btn.dataset.page));
    });
    document.querySelectorAll('.mobile-nav-btn').forEach(btn => {
        btn.addEventListener('click', () => navigateTo(btn.dataset.page));
    });
}

/* =====================================================================
   Status Checks
   ===================================================================== */
async function checkStatus() {
    const llmEl = document.getElementById('llm-status');
    llmEl.classList.remove('ok', 'error');
    llmEl.classList.add('checking');
    try {
        const r = await fetch('/health');
        if (r.ok) {
            const d = await r.json();
            const isHealthy = d.status === 'ok' || d.status === 'healthy';
            llmEl.classList.remove('checking');
            llmEl.classList.add(isHealthy ? 'ok' : 'error');
            llmEl.querySelector('.label').textContent = isHealthy ? 'LLM ✓' : 'LLM ✗';
            updateConnectionHelp('llm', isHealthy, d.components?.llm?.url || '');
        } else { throw new Error(); }
    } catch {
        llmEl.classList.remove('checking');
        llmEl.classList.add('error');
        llmEl.querySelector('.label').textContent = 'LLM ✗';
        updateConnectionHelp('llm', false);
    }
}

// ------------------------------------------------------------------ //
// LLM Provider Management
// ------------------------------------------------------------------ //

async function loadProviders() {
    try {
        const r = await fetch('/api/llm/providers');
        if (!r.ok) return;
        const data = await r.json();
        const sel = document.getElementById('llm-provider-select');
        if (!sel) return;
        sel.innerHTML = '';
        (data.providers || []).forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name + (p.configured ? '' : ' (未設定)');
            opt.dataset.requiresApiKey = p.requires_api_key ? '1' : '0';
            opt.dataset.defaultModel = p.default_model || '';
            sel.appendChild(opt);
        });
        if (data.current) {
            sel.value = data.current.provider;
            const modelInput = document.getElementById('provider-model');
            if (modelInput) modelInput.value = data.current.model || '';
        }
        updateProviderUI();
    } catch (e) {
        console.error('Failed to load providers:', e);
    }
}

function updateProviderUI() {
    const sel = document.getElementById('llm-provider-select');
    const keyGroup = document.getElementById('provider-api-key-group');
    const modelGroup = document.getElementById('provider-model-group');
    const applyBtn = document.getElementById('provider-apply-btn');
    if (!sel) return;
    const opt = sel.options[sel.selectedIndex];
    const needsKey = opt && opt.dataset.requiresApiKey === '1';
    keyGroup.style.display = needsKey ? 'block' : 'none';
    modelGroup.style.display = (sel.value !== 'openai_compatible') ? 'block' : 'none';
    applyBtn.style.display = 'block';
    if (opt && opt.dataset.defaultModel) {
        const modelInput = document.getElementById('provider-model');
        if (modelInput && !modelInput.value) {
            modelInput.value = opt.dataset.defaultModel;
        }
    }
}

async function applyProvider() {
    const sel = document.getElementById('llm-provider-select');
    const apiKeyInput = document.getElementById('provider-api-key');
    const modelInput = document.getElementById('provider-model');
    const statusMsg = document.getElementById('provider-status-msg');
    if (!sel) return;
    const body = { provider: sel.value };
    if (modelInput && modelInput.value.trim()) body.model = modelInput.value.trim();
    if (apiKeyInput && apiKeyInput.value.trim()) body.api_key = apiKeyInput.value.trim();
    statusMsg.textContent = '切替中...';
    statusMsg.className = 'provider-status-msg';
    try {
        const r = await fetch('/api/llm/provider', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await r.json();
        if (r.ok && data.success) {
            statusMsg.textContent = `${data.provider} (${data.model}) に切替完了`;
            statusMsg.className = 'provider-status-msg success';
            if (apiKeyInput) apiKeyInput.value = '';
            checkStatus();
        } else {
            statusMsg.textContent = data.detail || '切替に失敗しました';
            statusMsg.className = 'provider-status-msg error';
        }
    } catch (e) {
        statusMsg.textContent = '通信エラー';
        statusMsg.className = 'provider-status-msg error';
    }
}

async function checkSDStatus() {
    if (!_sdStatusPromise.sd) {
        _sdStatusPromise.sd = (async () => {
            const sdEl = document.getElementById('sd-status');
            const badge = document.getElementById('sd-api-badge');
            sdEl.classList.remove('ok', 'error');
            sdEl.classList.add('checking');
            try {
                const r = await fetch('/api/sd/status');
                const d = await r.json();
                sdEl.classList.remove('checking');
                if (d.available) {
                    sdEl.classList.add('ok');
                    sdEl.querySelector('.label').textContent = 'SD ✓';
                    updateConnectionHelp('sd', true);
                    badge.className = 'badge badge-green';
                    badge.textContent = 'Connected';

                    if (!_modelsLoaded.sd) {
                        // 初回のみリストを構築
                        if (d.samplers?.length) {
                            const sel = document.getElementById('sd-sampler');
                            sel.innerHTML = d.samplers.map(s => `<option>${s}</option>`).join('');
                            if (sel.dataset.pendingValue) { sel.value = sel.dataset.pendingValue; delete sel.dataset.pendingValue; }
                        }
                        if (d.models?.length) {
                            const modelSel = document.getElementById('sd-model');
                            const toRestore = _selectedModel.sd || modelSel.dataset.pendingValue || d.model || '';
                            modelSel.innerHTML = d.models.map(m => {
                                const name = m.model_name || m.title || '';
                                return `<option value="${name}">${name}</option>`;
                            }).join('');
                            if (toRestore) modelSel.value = toRestore;
                            if (modelSel.dataset.pendingValue) delete modelSel.dataset.pendingValue;
                            if (modelSel.value) _selectedModel.sd = modelSel.value;
                        }
                        if (d.upscalers?.length) {
                            const upscalerSel = document.getElementById('sd-hr-upscaler');
                            upscalerSel.innerHTML = d.upscalers.map(u =>
                                `<option${u === 'R-ESRGAN 4x+' ? ' selected' : ''}>${u}</option>`
                            ).join('');
                            if (upscalerSel.dataset.pendingValue) { upscalerSel.value = upscalerSel.dataset.pendingValue; delete upscalerSel.dataset.pendingValue; }
                        }
                        await loadLoras('sd', d.loras || []);
                        if (d.models?.length) populateMultiModelList(d.models);
                        _modelsLoaded.sd = true;
                    } else {
                        // タブ切り替え時は選択を復元するのみ
                        const modelSel = document.getElementById('sd-model');
                        if (_selectedModel.sd && modelSel.value !== _selectedModel.sd) {
                            modelSel.value = _selectedModel.sd;
                        }
                    }
                } else {
                    sdEl.classList.add('error');
                    sdEl.querySelector('.label').textContent = 'SD ✗';
                    updateConnectionHelp('sd', false);
                    badge.className = 'badge badge-red';
                    badge.textContent = 'Disconnected';
                }
            } catch {
                sdEl.classList.remove('checking');
                sdEl.classList.add('error');
                sdEl.querySelector('.label').textContent = 'SD ✗';
                updateConnectionHelp('sd', false);
                badge.className = 'badge badge-red';
                badge.textContent = 'Error';
            }
        })().finally(() => { _sdStatusPromise.sd = null; });
    }
    return _sdStatusPromise.sd;
}

async function loadLoras(prefix, preloadedLoras = null) {
    try {
        let loras;
        if (preloadedLoras !== null) {
            loras = preloadedLoras;
        } else {
            const r = await fetch('/api/sd/loras');
            if (!r.ok) return;
            const d = await r.json();
            if (!d.success) return;
            loras = d.loras || [];
        }
        const loraSel = document.getElementById(`${prefix}-lora-select`);
        if (!loraSel) return;

        // Store full list for filtering
        if (!window._allLoras) window._allLoras = {};
        window._allLoras[prefix] = loras;

        // Clear search box and render all options
        const searchEl = document.getElementById(`${prefix}-lora-search`);
        if (searchEl) searchEl.value = '';
        _renderLoraOptions(prefix, loras);

        const countEl = document.getElementById(`${prefix}-lora-count`);
        if (countEl) countEl.textContent = `${loras.length} 件`;
    } catch (e) {
        console.error(`[LORA] Failed to load LoRAs for ${prefix}:`, e);
    }
}

function _renderLoraOptions(prefix, loras) {
    const loraSel = document.getElementById(`${prefix}-lora-select`);
    if (!loraSel) return;
    loraSel.innerHTML = '<option value="">-- LoRA選択 --</option>' +
        loras.map(l => {
            const name = l.name || '';
            const alias = l.alias || name;
            const display = alias !== name ? `${alias} (${name})` : name;
            return `<option value="${name}">${display}</option>`;
        }).join('');
}

function filterLoras(prefix, query) {
    const q = query.toLowerCase().trim();
    const all = (window._allLoras && window._allLoras[prefix]) || [];
    const filtered = q ? all.filter(l => (l.name || '').toLowerCase().includes(q) || (l.alias || '').toLowerCase().includes(q)) : all;
    _renderLoraOptions(prefix, filtered);
    const countEl = document.getElementById(`${prefix}-lora-count`);
    if (countEl) countEl.textContent = q ? `${filtered.length} / ${all.length}` : `${all.length} 件`;
}

function exportHistory(format) {
    const url = `/api/history/export?format=${format}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = `prompt_history.${format}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function addLora(prefix) {
    const sel = document.getElementById(`${prefix}-lora-select`);
    const name = sel.value;
    if (!name) { return; }
    const weight = parseFloat(document.getElementById(`${prefix}-lora-weight`).value) || 1.0;
    const tag = `<lora:${name}:${weight}>`;
    const lorasInput = document.getElementById(`${prefix}-loras`);
    lorasInput.value = lorasInput.value ? lorasInput.value + tag : tag;
    sel.value = '';
}

/* =====================================================================
   Generate Page
   ===================================================================== */
function setupGeneratePage() {
    // Inner tabs
    document.querySelectorAll('.inner-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            currentTab = tab.dataset.inner;
            document.querySelectorAll('.inner-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.inner-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(currentTab).classList.add('active');
            updateGenerateBtn();
        });
    });

    // Upload area
    const uploadArea = document.getElementById('upload-area');
    const imageInput = document.getElementById('image-input');
    uploadArea.addEventListener('click', () => imageInput.click());
    imageInput.addEventListener('change', e => handleSingleImageSelect(e.target.files[0]));
    uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
    uploadArea.addEventListener('drop', e => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) handleSingleImageSelect(e.dataTransfer.files[0]);
    });

    document.getElementById('clear-image-btn').addEventListener('click', clearSingleImage);

    // Random folder load
    const randomFolderInput = document.getElementById('random-folder-input');
    document.getElementById('random-folder-btn').addEventListener('click', () => randomFolderInput.click());
    randomFolderInput.addEventListener('change', e => {
        const file = pickRandomImageFromFolder(e.target.files);
        if (file) handleSingleImageSelect(file);
        randomFolderInput.value = '';
    });

    // Random folder load + generate + multi-model (one-click)
    const randomFolderAutoInput = document.getElementById('random-folder-auto-input');
    document.getElementById('random-folder-auto-btn').addEventListener('click', () => randomFolderAutoInput.click());
    randomFolderAutoInput.addEventListener('change', async e => {
        const count = Math.max(1, parseInt(document.getElementById('random-folder-count').value) || 1);
        const allFiles = Array.from(e.target.files);
        randomFolderAutoInput.value = '';
        if (count === 1) {
            const file = pickRandomImageFromFolder(allFiles);
            if (!file) return;
            handleSingleImageSelect(file);
            await generatePromptAndMultiGenerate();
        } else {
            await runFolderBatchAutoRun(allFiles, count);
        }
    });

    // Clipboard load
    document.getElementById('clipboard-load-btn').addEventListener('click', loadImageFromClipboard);

    // Clipboard load + generate + multi-model (one-click)
    document.getElementById('clipboard-auto-btn').addEventListener('click', clipboardAutoRun);

    // Text input enable button
    document.getElementById('description-input').addEventListener('input', updateGenerateBtn);

    // Generate button
    document.getElementById('generate-btn').addEventListener('click', generatePrompt);
    document.getElementById('generate-and-multi-btn').addEventListener('click', generatePromptAndMultiGenerate);

    // Result actions
    document.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', () => copyText(btn.dataset.target, btn));
    });
    document.getElementById('copy-all-btn').addEventListener('click', copyAllPrompts);
    document.getElementById('refine-prompt-btn').addEventListener('click', () => sendToRefine(
        document.getElementById('pos-prompt').value,
        document.getElementById('neg-prompt').value
    ));
    document.getElementById('send-to-sd-btn').addEventListener('click', sendToSDPage);
    document.getElementById('send-to-sd-and-generate-btn').addEventListener('click', sendToSDPageAndGenerate);
    document.getElementById('send-to-sd-and-multi-generate-btn').addEventListener('click', sendToSDAndMultiGenerate);
    document.getElementById('send-to-img2img-btn').addEventListener('click', sendToImg2ImgPage);

    // Load presets into select
    loadPresetsIntoSelects();

    // Restore last used parameters
    loadLastParams('generate');
}

function handleSingleImageSelect(file) {
    if (!file || !file.type.startsWith('image/')) { toast('画像ファイルを選択してください', 'error'); return; }
    if (file.size > 10 * 1024 * 1024) { toast('ファイルサイズが10MBを超えています', 'error'); return; }
    selectedImage = file;
    const reader = new FileReader();
    reader.onload = e => {
        document.getElementById('preview-image').src = e.target.result;
        document.getElementById('preview-wrap').classList.remove('hidden');
        document.getElementById('upload-area').classList.add('hidden');
        updateGenerateBtn();
    };
    reader.readAsDataURL(file);
}

function clearSingleImage() {
    selectedImage = null;
    document.getElementById('image-input').value = '';
    document.getElementById('preview-wrap').classList.add('hidden');
    document.getElementById('upload-area').classList.remove('hidden');
    updateGenerateBtn();
}

function updateGenerateBtn() {
    const btn = document.getElementById('generate-btn');
    const multiBtn = document.getElementById('generate-and-multi-btn');
    const enabled = currentTab === 'tab-img' ? !!selectedImage : !!document.getElementById('description-input').value.trim();
    btn.disabled = !enabled;
    if (multiBtn) multiBtn.disabled = !enabled;
}

async function generatePrompt() {
    const loading = document.getElementById('loading-generate');
    const resultBox = document.getElementById('result-box');

    loading.classList.remove('hidden');
    resultBox.classList.add('hidden');

    const style = document.getElementById('select-style').value;
    const tone = document.getElementById('select-tone').value;
    const quality = document.getElementById('select-quality').value;
    const presetId = document.getElementById('select-preset').value;

    // Save parameters for next startup
    saveLastParams('generate', { style, tone, quality, preset_id: presetId });

    try {
        let data;
        if (currentTab === 'tab-img') {
            const fd = new FormData();
            fd.append('file', selectedImage);
            fd.append('style', style);
            fd.append('tone', tone);
            fd.append('quality', quality);
            fd.append('preset_id', presetId);
            const r = await fetch('/api/generate-prompts', { method: 'POST', body: fd });
            if (!r.ok) throw new Error((await r.json()).detail);
            data = (await r.json()).data;
        } else {
            const r = await fetch('/api/generate-prompts-text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    description: document.getElementById('description-input').value.trim(),
                    style, tone, quality, preset_id: presetId
                })
            });
            if (!r.ok) throw new Error((await r.json()).detail);
            data = (await r.json()).data;
        }

        document.getElementById('pos-prompt').value = data.positive;
        document.getElementById('neg-prompt').value = data.negative;
        updateTokenCounter('pos-prompt', 'positive-output-tokens');
        updateTokenCounter('neg-prompt', 'negative-output-tokens');
        resultBox.classList.remove('hidden');
        toast('プロンプト生成完了！', 'success');
    } catch (e) {
        toast(e.message || '生成に失敗しました', 'error');
    } finally {
        loading.classList.add('hidden');
    }
}

function sendToSDPage() {
    document.getElementById('sd-positive').value = document.getElementById('pos-prompt').value;
    document.getElementById('sd-negative').value = document.getElementById('neg-prompt').value;
    document.querySelector('[data-page="sd"]').click();
    checkSDStatus();
}

function sendToImg2ImgPage() {
    document.getElementById('i2i-positive').value = document.getElementById('pos-prompt').value;
    document.getElementById('i2i-negative').value = document.getElementById('neg-prompt').value;
    document.querySelector('[data-page="img2img"]').click();
    checkImg2ImgStatus();
}

async function sendToSDPageAndGenerate() {
    document.getElementById('sd-positive').value = document.getElementById('pos-prompt').value;
    document.getElementById('sd-negative').value = document.getElementById('neg-prompt').value;
    document.querySelector('[data-page="sd"]').click();
    await checkSDStatus();
    runSDGenerate();
}

async function sendToSDAndMultiGenerate() {
    document.getElementById('sd-positive').value = document.getElementById('pos-prompt').value;
    document.getElementById('sd-negative').value = document.getElementById('neg-prompt').value;
    document.querySelector('[data-page="sd"]').click();
    await checkSDStatus();
    await runMultiModelGenerate();
}

async function generatePromptAndMultiGenerate() {
    await generatePrompt();
    const resultBox = document.getElementById('result-box');
    if (!resultBox.classList.contains('hidden')) {
        await sendToSDAndMultiGenerate();
    }
}

async function loadImageFromClipboard() {
    // Clipboard API (navigator.clipboard.read) は HTTPS またはローカルホスト、
    // かつ Chrome / Edge でのみ動作する。使えない場合は Ctrl+V を案内する。
    if (!navigator.clipboard || typeof navigator.clipboard.read !== 'function') {
        toast('Ctrl+V でクリップボードから画像を貼り付けてください', 'info');
        return;
    }
    try {
        const items = await navigator.clipboard.read();
        let found = false;
        for (const item of items) {
            const imageType = item.types.find(t => t.startsWith('image/'));
            if (imageType) {
                const blob = await item.getType(imageType);
                const ext = imageType.split('/')[1]?.trim() || 'png';
                const file = new File([blob], `clipboard.${ext}`, { type: imageType });
                handleSingleImageSelect(file);
                found = true;
                break;
            }
        }
        if (!found) toast('クリップボードに画像がありません', 'error');
    } catch (e) {
        if (e.name === 'NotAllowedError') {
            toast('クリップボードへのアクセスが拒否されました。ブラウザの権限設定を確認してください', 'error');
        } else if (e.name === 'TypeError') {
            toast('クリップボードの読み込みに失敗しました。Ctrl+V で貼り付けてください', 'error');
        } else {
            toast('クリップボードから読み込めませんでした', 'error');
        }
    }
}

async function clipboardAutoRun() {
    await loadImageFromClipboard();
    if (!selectedImage) return;
    await generatePromptAndMultiGenerate();
}

async function refineToSDPageAndGenerate() {
    document.getElementById('sd-positive').value = document.getElementById('refine-pos-output').value;
    document.getElementById('sd-negative').value = document.getElementById('refine-neg-output').value;
    document.querySelector('[data-page="sd"]').click();
    await checkSDStatus();
    runSDGenerate();
}

function copyAllPrompts() {
    const text = `Positive:\n${document.getElementById('pos-prompt').value}\n\nNegative:\n${document.getElementById('neg-prompt').value}`;
    navigator.clipboard.writeText(text)
        .then(() => toast('全プロンプトをコピーしました', 'success'))
        .catch(() => toast('コピーに失敗しました', 'error'));
}

/* =====================================================================
   Batch Page
   ===================================================================== */
function setupBatchPage() {
    const batchArea = document.getElementById('batch-upload-area');
    const batchInput = document.getElementById('batch-input');

    batchArea.addEventListener('click', () => batchInput.click());
    batchInput.addEventListener('change', e => handleBatchFiles(e.target.files));
    batchArea.addEventListener('dragover', e => { e.preventDefault(); batchArea.classList.add('drag-over'); });
    batchArea.addEventListener('dragleave', () => batchArea.classList.remove('drag-over'));
    batchArea.addEventListener('drop', e => {
        e.preventDefault();
        batchArea.classList.remove('drag-over');
        handleBatchFiles(e.dataTransfer.files);
    });

    document.getElementById('batch-generate-btn').addEventListener('click', runBatch);
}

function handleBatchFiles(files) {
    batchFiles = Array.from(files).filter(f => f.type.startsWith('image/')).slice(0, 10);
    const list = document.getElementById('batch-file-list');
    if (!batchFiles.length) { list.classList.add('hidden'); return; }

    list.innerHTML = batchFiles.map(f => `
        <div class="batch-file-item">
            <span class="file-name">${escHtml(f.name)}</span>
            <span class="file-size">${(f.size / 1024).toFixed(0)} KB</span>
        </div>
    `).join('');
    list.classList.remove('hidden');
    document.getElementById('batch-generate-btn').disabled = false;
    loadPresetsIntoSelect('batch-preset');
}

async function runBatch() {
    const loading = document.getElementById('batch-loading');
    const results = document.getElementById('batch-results');
    loading.classList.remove('hidden');
    results.classList.add('hidden');

    const fd = new FormData();
    batchFiles.forEach(f => fd.append('files', f));
    fd.append('style', document.getElementById('batch-style').value);
    fd.append('quality', document.getElementById('batch-quality').value);
    fd.append('preset_id', document.getElementById('batch-preset').value);

    try {
        document.getElementById('batch-progress-text').textContent = `${batchFiles.length}枚を処理中...`;
        const r = await fetch('/api/generate-prompts-batch', { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();

        results.innerHTML = d.results.map(item => {
            if (item.success) {
                return `<div class="batch-result-item success">
                    <div class="batch-result-filename">✅ ${escHtml(item.filename)}</div>
                    <div class="batch-result-prompts">
                        <strong>Positive:</strong> ${escHtml(item.positive)}<br>
                        <strong>Negative:</strong> ${escHtml(item.negative)}
                    </div>
                </div>`;
            } else {
                return `<div class="batch-result-item error-item">
                    <div class="batch-result-filename">❌ ${escHtml(item.filename)}</div>
                    <div class="batch-result-prompts">${escHtml(item.error)}</div>
                </div>`;
            }
        }).join('');

        results.classList.remove('hidden');
        toast(`完了: ${d.results.filter(r => r.success).length}/${d.total} 成功`, 'success');
    } catch (e) {
        toast(e.message || 'バッチ処理に失敗しました', 'error');
    } finally {
        loading.classList.add('hidden');
    }
}

/* =====================================================================
   History Page
   ===================================================================== */
function sendToRefine(positive, negative) {
    document.getElementById('refine-positive-input').value = positive || '';
    document.getElementById('refine-negative-input').value = negative || '';
    document.querySelector('[data-page="refine"]').click();
    toast('Refineページに送りました', 'info');
}

/* =====================================================================
   Refine Page
   ===================================================================== */
function setupRefinePage() {
    document.getElementById('refine-btn').addEventListener('click', doRefinePrompt);

    document.querySelectorAll('#page-refine .copy-btn').forEach(btn => {
        btn.addEventListener('click', () => copyText(btn.dataset.target, btn));
    });

    document.getElementById('refine-copy-all-btn').addEventListener('click', () => {
        const pos = document.getElementById('refine-pos-output').value;
        const neg = document.getElementById('refine-neg-output').value;
        const text = `Positive:\n${pos}\n\nNegative:\n${neg}`;
        navigator.clipboard.writeText(text)
            .then(() => toast('全プロンプトをコピーしました', 'success'))
            .catch(() => toast('コピーに失敗しました', 'error'));
    });

    document.getElementById('refine-send-to-sd-btn').addEventListener('click', () => {
        document.getElementById('sd-positive').value = document.getElementById('refine-pos-output').value;
        document.getElementById('sd-negative').value = document.getElementById('refine-neg-output').value;
        document.querySelector('[data-page="sd"]').click();
        checkSDStatus();
    });

    document.getElementById('refine-send-to-sd-and-generate-btn').addEventListener('click', () => {
        refineToSDPageAndGenerate();
    });

    document.getElementById('refine-apply-btn').addEventListener('click', () => {
        document.getElementById('refine-positive-input').value = document.getElementById('refine-pos-output').value;
        document.getElementById('refine-negative-input').value = document.getElementById('refine-neg-output').value;
        document.getElementById('refine-result-box').classList.add('hidden');
        toast('入力フィールドに反映しました', 'success');
    });
}

async function doRefinePrompt() {
    const positive = document.getElementById('refine-positive-input').value.trim();
    if (!positive) { toast('Positiveプロンプトを入力してください', 'error'); return; }

    const loading = document.getElementById('loading-refine');
    const resultBox = document.getElementById('refine-result-box');
    loading.classList.remove('hidden');
    resultBox.classList.add('hidden');

    try {
        const r = await fetch('/api/refine-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                positive,
                negative: document.getElementById('refine-negative-input').value.trim(),
                instruction: document.getElementById('refine-instruction-input').value.trim(),
                style: document.getElementById('refine-style').value,
                tone: document.getElementById('refine-tone').value,
                quality: document.getElementById('refine-quality').value,
            })
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = (await r.json()).data;

        document.getElementById('refine-pos-output').value = d.positive;
        document.getElementById('refine-neg-output').value = d.negative;

        const changesBox = document.getElementById('refine-changes-box');
        if (d.changes) {
            document.getElementById('refine-changes-text').textContent = d.changes;
            changesBox.classList.remove('hidden');
        } else {
            changesBox.classList.add('hidden');
        }

        resultBox.classList.remove('hidden');
        toast('プロンプトを改善しました！', 'success');
    } catch (e) {
        toast(e.message || '改善に失敗しました', 'error');
    } finally {
        loading.classList.add('hidden');
    }
}

/* =====================================================================
   History Page
   ===================================================================== */
let _historyDebounceTimer = null;

function setupHistoryPage() {
    document.getElementById('refresh-history-btn').addEventListener('click', loadHistory);
    document.getElementById('clear-history-btn').addEventListener('click', async () => {
        if (!confirm('全履歴を削除しますか？')) return;
        const res = await fetch('/api/history', { method: 'DELETE' });
        if (res.ok) { loadHistory(); toast('履歴を削除しました', 'success'); }
        else { toast('削除に失敗しました', 'error'); }
    });
    document.getElementById('export-history-btn').addEventListener('click', () => {
        exportHistory('json');
    });

    const debouncedLoad = () => {
        clearTimeout(_historyDebounceTimer);
        _historyDebounceTimer = setTimeout(loadHistory, 300);
    };
    document.getElementById('history-search').addEventListener('input', debouncedLoad);
    document.getElementById('history-filter-style').addEventListener('change', loadHistory);
    document.getElementById('history-filter-quality').addEventListener('change', loadHistory);

    document.getElementById('history-favorites-toggle').addEventListener('click', function () {
        const active = this.dataset.active === 'true';
        this.dataset.active = String(!active);
        this.classList.toggle('btn-accent', !active);
        this.classList.toggle('btn-secondary', active);
        loadHistory();
    });
    document.getElementById('history-filter-tag').addEventListener('input', debouncedLoad);
}

async function loadHistory() {
    const loading = document.getElementById('history-loading');
    const empty = document.getElementById('history-empty');
    const list = document.getElementById('history-list');
    loading.classList.remove('hidden');
    empty.classList.add('hidden');
    list.innerHTML = '';

    const search = document.getElementById('history-search')?.value.trim() || '';
    const style = document.getElementById('history-filter-style')?.value || '';
    const quality = document.getElementById('history-filter-quality')?.value || '';
    const favoritesOnly = document.getElementById('history-favorites-toggle')?.dataset.active === 'true';
    const tagFilter = document.getElementById('history-filter-tag')?.value.trim() || '';

    const params = new URLSearchParams({ limit: 100 });
    if (search) params.set('search', search);
    if (style) params.set('style', style);
    if (quality) params.set('quality', quality);
    if (favoritesOnly) params.set('favorites_only', 'true');
    if (tagFilter) params.set('tag', tagFilter);

    try {
        const r = await fetch('/api/history?' + params.toString());
        const d = await r.json();

        if (!d.items?.length) { empty.classList.remove('hidden'); return; }

        d.items.forEach(item => _historyItems.set(item.id, item));

        list.innerHTML = d.items.map(item => `
            <div class="history-item" id="hist-${item.id}">
                <div class="history-item-header">
                    <div class="history-item-meta">
                        <span class="image-name">${escHtml(item.image_name || 'Unknown')}</span><br>
                        ${item.style ? `<span>${item.style}</span> · ` : ''}
                        ${item.quality ? `<span>${item.quality}</span> · ` : ''}
                        ${item.created_at ? `<span>${new Date(item.created_at).toLocaleString('ja-JP')}</span>` : ''}
                    </div>
                    <div class="history-item-actions">
                        <button class="btn btn-sm ${item.is_favorite ? 'btn-favorite-active' : 'btn-ghost'}"
                            onclick="toggleFavorite(${item.id})" title="${item.is_favorite ? 'お気に入り解除' : 'お気に入り登録'}">⭐</button>
                        <button class="btn btn-sm btn-secondary" onclick="loadHistoryItem(${item.id})">使用</button>
                        <button class="btn btn-sm btn-secondary" onclick="sendToRefineFromHistory(${item.id})">🔧</button>
                        <button class="btn btn-sm btn-ghost" onclick="copyHistoryPrompts(${item.id})" title="プロンプトをコピー">📋</button>
                        <button class="btn btn-sm btn-secondary" onclick="sendHistoryToSD(${item.id})" title="SDページへ送る">🎨 SDへ送る</button>
                        <button class="btn btn-sm btn-ghost" onclick="deleteHistoryItem(${item.id})">🗑️</button>
                    </div>
                </div>
                <div class="history-prompt">
                    <div class="label">Positive</div>
                    ${escHtml(item.positive)}
                </div>
                <div class="history-prompt">
                    <div class="label">Negative</div>
                    ${escHtml(item.negative)}
                </div>
                <div class="history-tags">
                    ${(item.tags || []).map(t => `<span class="history-tag" onclick="removeTagFromHistory(${item.id}, '${escHtml(t)}')" title="クリックで削除">${escHtml(t)}</span>`).join('')}
                    <button class="btn-add-tag" onclick="showAddTagInput(${item.id})" title="タグを追加">+ タグ</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        toast('履歴の読み込みに失敗しました', 'error');
    } finally {
        loading.classList.add('hidden');
    }
}

async function toggleFavorite(id) {
    try {
        const r = await fetch(`/api/history/${id}/favorite`, { method: 'PUT' });
        if (!r.ok) throw new Error();
        const item = (await r.json()).item;
        const btn = document.querySelector(`#hist-${id} .history-item-actions button:first-child`);
        if (btn) {
            btn.className = `btn btn-sm ${item.is_favorite ? 'btn-favorite-active' : 'btn-ghost'}`;
            btn.title = item.is_favorite ? 'お気に入り解除' : 'お気に入り登録';
        }
        toast(item.is_favorite ? '⭐ お気に入りに追加' : 'お気に入りを解除', 'success');
    } catch {
        toast('更新に失敗しました', 'error');
    }
}

function sendToRefineFromHistory(id) {
    const item = _historyItems.get(id);
    if (!item) return;
    sendToRefine(item.positive, item.negative);
}

function loadHistoryItem(id) {
    const item = _historyItems.get(id);
    if (!item) return;
    document.getElementById('pos-prompt').value = item.positive || '';
    document.getElementById('neg-prompt').value = item.negative || '';
    document.getElementById('result-box').classList.remove('hidden');
    document.querySelector('[data-page="generate"]').click();
    toast('履歴を読み込みました', 'info');
}

function copyHistoryPrompts(id) {
    const item = _historyItems.get(id);
    if (!item) return;
    const text = `Positive:\n${item.positive || ''}\n\nNegative:\n${item.negative || ''}`;
    navigator.clipboard.writeText(text)
        .then(() => toast('プロンプトをコピーしました', 'success'))
        .catch(() => toast('コピーに失敗しました', 'error'));
}

function sendHistoryToSD(id) {
    const item = _historyItems.get(id);
    if (!item) return;
    document.getElementById('sd-positive').value = item.positive || '';
    document.getElementById('sd-negative').value = item.negative || '';
    document.querySelector('[data-page="sd"]').click();
    toast('SDページに送りました', 'info');
}

async function addTagToHistory(historyId, tagInput) {
    const tags = tagInput.value.trim().split(',').map(t => t.trim()).filter(Boolean);
    if (!tags.length) return;
    try {
        const r = await fetch(`/api/history/${historyId}/tags`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tags })
        });
        if (!r.ok) throw new Error();
        loadHistory();
        toast('タグを追加しました', 'success');
    } catch {
        toast('タグの追加に失敗しました', 'error');
    }
}

async function removeTagFromHistory(id, tag) {
    try {
        const r = await fetch(`/api/history/${id}/tags/${encodeURIComponent(tag)}`, { method: 'DELETE' });
        if (!r.ok) throw new Error();
        loadHistory();
        toast('タグを削除しました', 'success');
    } catch {
        toast('タグの削除に失敗しました', 'error');
    }
}

function showAddTagInput(historyId) {
    const existing = document.getElementById(`tag-input-${historyId}`);
    if (existing) { existing.focus(); return; }
    const container = document.querySelector(`#hist-${historyId} .history-tags`);
    if (!container) return;
    const input = document.createElement('input');
    input.type = 'text';
    input.id = `tag-input-${historyId}`;
    input.className = 'tag-input-inline';
    input.placeholder = 'タグ入力 (カンマ区切り)';
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') { addTagToHistory(historyId, input); }
        if (e.key === 'Escape') { input.remove(); }
    });
    input.addEventListener('blur', () => {
        if (input.value.trim()) addTagToHistory(historyId, input);
        else input.remove();
    });
    container.insertBefore(input, container.querySelector('.btn-add-tag'));
    input.focus();
}

async function deleteHistoryItem(id) {
    const res = await fetch(`/api/history/${id}`, { method: 'DELETE' });
    if (res.ok) { document.getElementById(`hist-${id}`)?.remove(); toast('削除しました', 'success'); }
    else { toast('削除に失敗しました', 'error'); }
}

/* =====================================================================
   Presets Page
   ===================================================================== */
function setupPresetsPage() {
    document.getElementById('add-preset-btn').addEventListener('click', () => {
        document.getElementById('preset-modal').classList.remove('hidden');
    });
    document.getElementById('cancel-preset-btn').addEventListener('click', closePresetModal);
    document.getElementById('save-preset-btn').addEventListener('click', savePreset);
    document.getElementById('preset-modal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closePresetModal();
    });
}

async function loadPresets() {
    const r = await fetch('/api/presets');
    const d = await r.json();
    presetsCache = d.presets || [];

    const list = document.getElementById('presets-list');
    list.innerHTML = presetsCache.map(p => `
        <div class="preset-card ${p.is_default ? 'is-default' : ''}">
            <div class="preset-card-header">
                <span class="preset-card-name">${escHtml(p.name)}</span>
                ${!p.is_default ? `<button class="btn btn-sm btn-ghost" onclick="deletePreset('${p.id}')">🗑️</button>` : ''}
            </div>
            <div class="preset-card-desc">${escHtml(p.description || '')}</div>
            <div class="preset-card-tags">
                ${p.is_default ? '<span class="tag default">Built-in</span>' : ''}
                ${p.style ? `<span class="tag">${p.style}</span>` : ''}
                ${p.quality ? `<span class="tag">${p.quality}</span>` : ''}
            </div>
            <div class="preset-card-suffix">+ ${escHtml(p.positive_suffix)}</div>
            <div class="preset-card-suffix">- ${escHtml(p.negative_suffix)}</div>
        </div>
    `).join('');

    loadPresetsIntoSelects();
}

function loadPresetsIntoSelects() {
    if (!presetsCache.length) {
        fetch('/api/presets').then(r => r.json()).then(d => {
            presetsCache = d.presets || [];
            refreshPresetSelects();
        }).catch(e => console.warn('[PRESETS] Failed to load:', e));
    } else {
        refreshPresetSelects();
    }
}

function refreshPresetSelects() {
    const options = `<option value="">-- なし --</option>` + presetsCache.map(p =>
        `<option value="${p.id}">${escHtml(p.name)}</option>`
    ).join('');
    ['select-preset', 'batch-preset'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.innerHTML = options;
            if (el.dataset.pendingValue) {
                el.value = el.dataset.pendingValue;
                delete el.dataset.pendingValue;
            }
        }
    });
}

function loadPresetsIntoSelect(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = `<option value="">-- なし --</option>` + presetsCache.map(p =>
        `<option value="${p.id}">${escHtml(p.name)}</option>`
    ).join('');
}

async function savePreset() {
    const name = document.getElementById('preset-name').value.trim();
    const pos = document.getElementById('preset-pos').value.trim();
    const neg = document.getElementById('preset-neg').value.trim();
    if (!name || !pos || !neg) { toast('名前・Positive・Negativeは必須です', 'error'); return; }

    const preset = {
        name,
        description: document.getElementById('preset-desc').value.trim(),
        positive_suffix: pos,
        negative_suffix: neg,
        style: document.getElementById('preset-style').value,
        quality: document.getElementById('preset-quality').value
    };

    try {
        const r = await fetch('/api/presets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(preset)
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        closePresetModal();
        loadPresets();
        toast('プリセットを保存しました', 'success');
    } catch (e) {
        toast(e.message || '保存に失敗しました', 'error');
    }
}

async function deletePreset(id) {
    if (!confirm('このプリセットを削除しますか？')) return;
    try {
        const r = await fetch(`/api/presets/${id}`, { method: 'DELETE' });
        if (r.ok) { loadPresets(); toast('削除しました', 'success'); }
        else { toast('削除に失敗しました', 'error'); }
    } catch { toast('削除に失敗しました', 'error'); }
}

function closePresetModal() {
    document.getElementById('preset-modal').classList.add('hidden');
    ['preset-name', 'preset-desc', 'preset-pos', 'preset-neg'].forEach(id => {
        document.getElementById(id).value = '';
    });
}

/* =====================================================================
   SD Generate Page
   ===================================================================== */
function setupSDPage() {
    document.getElementById('sd-generate-btn').addEventListener('click', runSDGenerate);
    document.getElementById('sd-enable-hr').addEventListener('change', e => {
        document.getElementById('sd-hr-settings').classList.toggle('hidden', !e.target.checked);
    });
    document.getElementById('sd-model').addEventListener('change', e => {
        _selectedModel.sd = e.target.value;
    });
    document.getElementById('sd-multi-generate-btn').addEventListener('click', runMultiModelGenerate);

    // Token counters
    document.getElementById('sd-positive')?.addEventListener('input', () => updateTokenCounter('sd-positive', 'sd-positive-tokens'));
    document.getElementById('sd-negative')?.addEventListener('input', () => updateTokenCounter('sd-negative', 'sd-negative-tokens'));

    // Negative prompt templates
    populateNegTemplates('sd-neg-template');
    document.getElementById('sd-neg-template')?.addEventListener('change', () => applyNegTemplate('sd-neg-template', 'sd-negative', 'sd-negative-tokens'));

    // Restore last used parameters after status check populates selectors
    checkSDStatus().then(() => loadLastParams('sd'));
}

async function runSDGenerate() {
    const btn = document.getElementById('sd-generate-btn');
    if (btn.disabled) return;
    const positive = document.getElementById('sd-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); return; }
    const _sdModel = document.getElementById('sd-model').value.trim();
    if (!_sdModel) { toast('モデルを選択してください', 'error'); return; }
    if (!await confirmModel(_sdModel)) return;

    btn.disabled = true;
    const loading = document.getElementById('sd-loading');
    const results = document.getElementById('sd-results');
    const imagesEl = document.getElementById('sd-images');

    loading.classList.remove('hidden');
    results.classList.add('hidden');
    const stopProgress = startSDProgress(loading);

    const enableHr = document.getElementById('sd-enable-hr').checked;
    const payload = {
        positive,
        negative: document.getElementById('sd-negative').value.trim(),
        width: parseInt(document.getElementById('sd-width').value),
        height: parseInt(document.getElementById('sd-height').value),
        steps: parseInt(document.getElementById('sd-steps').value),
        cfg_scale: parseFloat(document.getElementById('sd-cfg').value),
        sampler: document.getElementById('sd-sampler').value,
        batch_size: parseInt(document.getElementById('sd-batch').value),
        seed: parseInt(document.getElementById('sd-seed').value),
        model: document.getElementById('sd-model').value.trim(),
        loras: document.getElementById('sd-loras').value.trim(),
        enable_hr: enableHr,
        hr_scale: parseFloat(document.getElementById('sd-hr-scale').value),
        hr_upscaler: document.getElementById('sd-hr-upscaler').value,
        hr_second_pass_steps: parseInt(document.getElementById('sd-hr-steps').value),
        hr_denoising_strength: parseFloat(document.getElementById('sd-hr-denoising').value)
    };

    // Save parameters for next startup
    saveLastParams('sd', payload);

    try {
        const r = await fetch('/api/sd/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();

        imagesEl.innerHTML = d.images.map((img, i) => `
            <div class="sd-image-wrap">
                <img src="data:image/png;base64,${img}" alt="Generated ${i + 1}">
                <button class="sd-image-download" onclick="downloadImage('${img}', ${i + 1})">⬇ 保存</button>
            </div>
        `).join('');

        results.classList.remove('hidden');
        toast(`${d.count}枚の画像を生成しました`, 'success');
    } catch (e) {
        toast(e.message || '生成に失敗しました', 'error');
    } finally {
        stopProgress();
        loading.classList.add('hidden');
        btn.disabled = false;
    }
}

function downloadImage(base64, index) {
    const a = document.createElement('a');
    a.href = `data:image/png;base64,${base64}`;
    a.download = `sd_generated_${index}.png`;
    a.click();
}

/* =====================================================================
   Multi-model Generation
   ===================================================================== */
function populateMultiModelList(models) {
    const list = document.getElementById('sd-multi-model-list');
    if (!list) return;
    if (!models || !models.length) {
        list.innerHTML = '<p class="multi-model-empty">利用可能なモデルがありません</p>';
        return;
    }
    list.innerHTML = models.map(m => {
        const name = m.model_name || m.title || '';
        if (!name) return '';
        return `<label class="multi-model-item">
            <input type="checkbox" class="multi-model-checkbox" value="${escHtml(name)}" onchange="updateMultiModelCount(); saveMultiModelSelection();">
            <span>${escHtml(name)}</span>
        </label>`;
    }).join('');
    updateMultiModelCount();
    // Restore saved model selections after populating
    loadMultiModelSelection();
}

function updateMultiModelCount() {
    const checked = document.querySelectorAll('.multi-model-checkbox:checked');
    const countEl = document.getElementById('sd-multi-model-count');
    const btn = document.getElementById('sd-multi-generate-btn');
    if (countEl) countEl.textContent = `${checked.length} モデル選択中`;
    if (btn) btn.disabled = checked.length === 0;
}

function selectAllModels(checked) {
    document.querySelectorAll('.multi-model-checkbox').forEach(cb => { cb.checked = checked; });
    updateMultiModelCount();
    saveMultiModelSelection();
}

function saveMultiModelSelection() {
    const selected = Array.from(document.querySelectorAll('.multi-model-checkbox:checked')).map(cb => cb.value);
    saveLastParams('multi_model', { models: selected });
}

async function loadMultiModelSelection() {
    try {
        const r = await fetch('/api/last-params/multi_model');
        if (!r.ok) return;
        const d = await r.json();
        const savedModels = d.params?.models;
        if (!savedModels || !savedModels.length) return;
        const savedSet = new Set(savedModels);
        document.querySelectorAll('.multi-model-checkbox').forEach(cb => {
            if (savedSet.has(cb.value)) cb.checked = true;
        });
        updateMultiModelCount();
    } catch (e) {
        console.error('[MULTI-MODEL] Failed to restore selection:', e);
    }
}

async function runMultiModelGenerate() {
    if (_multiModelRunning) return;
    const btn = document.getElementById('sd-multi-generate-btn');
    if (btn) btn.disabled = true;

    const positive = document.getElementById('sd-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); if (btn) btn.disabled = false; return; }

    const selectedModels = Array.from(document.querySelectorAll('.multi-model-checkbox:checked')).map(cb => cb.value);
    if (!selectedModels.length) { toast('1つ以上のモデルを選択してください', 'error'); if (btn) btn.disabled = false; return; }

    _multiModelRunning = true;

    const loading = document.getElementById('sd-multi-loading');
    const loadingText = document.getElementById('sd-multi-loading-text');
    const results = document.getElementById('sd-multi-results');
    const imagesEl = document.getElementById('sd-multi-images');

    document.getElementById('sd-results').classList.add('hidden');
    loading.classList.remove('hidden');
    results.classList.remove('hidden');
    imagesEl.innerHTML = '';

    const enableHr = document.getElementById('sd-enable-hr').checked;
    const basePayload = {
        positive,
        negative: document.getElementById('sd-negative').value.trim(),
        width: parseInt(document.getElementById('sd-width').value),
        height: parseInt(document.getElementById('sd-height').value),
        steps: parseInt(document.getElementById('sd-steps').value),
        cfg_scale: parseFloat(document.getElementById('sd-cfg').value),
        sampler: document.getElementById('sd-sampler').value,
        batch_size: parseInt(document.getElementById('sd-batch').value),
        seed: parseInt(document.getElementById('sd-seed').value),
        loras: document.getElementById('sd-loras').value.trim(),
        enable_hr: enableHr,
        hr_scale: parseFloat(document.getElementById('sd-hr-scale').value),
        hr_upscaler: document.getElementById('sd-hr-upscaler').value,
        hr_second_pass_steps: parseInt(document.getElementById('sd-hr-steps').value),
        hr_denoising_strength: parseFloat(document.getElementById('sd-hr-denoising').value),
    };

    // 全モデル分のプレースホルダーカードを事前に作成
    selectedModels.forEach(model => {
        const card = document.createElement('div');
        card.className = 'multi-model-result-card';
        card.innerHTML = `
            <div class="multi-model-result-header pending">⏳ ${escHtml(model)}</div>
            <div class="multi-model-result-images pending-msg">待機中...</div>`;
        imagesEl.appendChild(card);
    });

    let successCount = 0;

    try {
        for (let i = 0; i < selectedModels.length; i++) {
            const model = selectedModels[i];
            const card = imagesEl.children[i];
            loadingText.textContent = `${i + 1} / ${selectedModels.length} モデル処理中... (${model})`;
            card.querySelector('.multi-model-result-header').textContent = `⏳ ${model}`;
            card.querySelector('.multi-model-result-images').textContent = '生成中...';
            card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

            const stopProgress = startSDProgress(loading);
            try {
                const r = await fetch('/api/sd/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ...basePayload, model })
                });
                if (!r.ok) throw new Error((await r.json()).detail);
                const d = await r.json();

                successCount++;
                const imgs = d.images.map((img, j) => `
                    <div class="sd-image-wrap">
                        <img src="data:image/png;base64,${img}" alt="${escHtml(model)} ${j + 1}">
                        <button class="sd-image-download" onclick="downloadImage('${img}', ${j + 1})">⬇ 保存</button>
                    </div>`).join('');
                card.innerHTML = `
                    <div class="multi-model-result-header success">✅ ${escHtml(model)} <span class="multi-model-result-count">${d.count}枚</span></div>
                    <div class="multi-model-result-images">${imgs}</div>`;
            } catch (e) {
                card.innerHTML = `
                    <div class="multi-model-result-header error">❌ ${escHtml(model)}</div>
                    <div style="padding:10px 14px;font-size:0.82rem;color:var(--danger)">${escHtml(e.message || '生成に失敗しました')}</div>`;
            } finally {
                stopProgress();
            }
        }

        toast(`${successCount} / ${selectedModels.length} モデルで生成完了`, successCount > 0 ? 'success' : 'error');
    } finally {
        loading.classList.add('hidden');
        _multiModelRunning = false;
        if (btn) btn.disabled = selectedModels.length === 0;
        updateMultiModelCount();
    }
}

/* =====================================================================
   Img2Img Page
   ===================================================================== */
let i2iSelectedImage = null;

function setupImg2ImgPage() {
    const uploadArea = document.getElementById('i2i-upload-area');
    const imageInput = document.getElementById('i2i-image-input');
    const clearBtn = document.getElementById('i2i-clear-btn');
    const generateBtn = document.getElementById('i2i-generate-btn');
    const enableHrCheckbox = document.getElementById('i2i-enable-hr');
    const hrSettings = document.getElementById('i2i-hr-settings');

    if (!uploadArea || !imageInput) {
        console.error('[IMG2IMG] Upload elements not found!');
        return;
    }

    // Click to upload
    uploadArea.addEventListener('click', () => {
        imageInput.click();
    });

    // File input change
    imageInput.addEventListener('change', e => {
        handleI2IImageSelect(e.target.files[0]);
    });

    // Drag over
    uploadArea.addEventListener('dragover', e => {
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.add('drag-over');
    });

    // Drag leave
    uploadArea.addEventListener('dragleave', e => {
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.remove('drag-over');
    });

    // Drop
    uploadArea.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) {
            handleI2IImageSelect(e.dataTransfer.files[0]);
        }
    });

    if (clearBtn) clearBtn.addEventListener('click', clearI2IImage);
    if (generateBtn) generateBtn.addEventListener('click', runImg2Img);

    document.getElementById('i2i-model').addEventListener('change', e => {
        _selectedModel.img2img = e.target.value;
    });

    // Random folder load
    const i2iRandomFolderInput = document.getElementById('i2i-random-folder-input');
    const i2iRandomFolderBtn = document.getElementById('i2i-random-folder-btn');
    if (i2iRandomFolderBtn && i2iRandomFolderInput) {
        i2iRandomFolderBtn.addEventListener('click', () => i2iRandomFolderInput.click());
        i2iRandomFolderInput.addEventListener('change', e => {
            const file = pickRandomImageFromFolder(e.target.files);
            if (file) handleI2IImageSelect(file);
            i2iRandomFolderInput.value = '';
        });
    }
    if (enableHrCheckbox && hrSettings) {
        enableHrCheckbox.addEventListener('change', e => {
            hrSettings.classList.toggle('hidden', !e.target.checked);
        });
    }

    // Token counters
    document.getElementById('i2i-positive')?.addEventListener('input', () => updateTokenCounter('i2i-positive', 'img2img-positive-tokens'));
    document.getElementById('i2i-negative')?.addEventListener('input', () => updateTokenCounter('i2i-negative', 'img2img-negative-tokens'));

    // Negative prompt templates
    populateNegTemplates('img2img-neg-template');
    document.getElementById('img2img-neg-template')?.addEventListener('change', () => applyNegTemplate('img2img-neg-template', 'i2i-negative', 'img2img-negative-tokens'));

    // Restore last used parameters after status check populates selectors
    checkImg2ImgStatus().then(() => loadLastParams('img2img'));
}

function handleI2IImageSelect(file) {
    if (!file) {
        console.error('[IMG2IMG] No file provided');
        toast('画像ファイルを選択してください', 'error');
        return;
    }

    if (!file.type.startsWith('image/')) {
        console.error('[IMG2IMG] Invalid file type:', file.type);
        toast('画像ファイルを選択してください', 'error');
        return;
    }

    if (file.size > 10 * 1024 * 1024) {
        console.error('[IMG2IMG] File too large:', file.size);
        toast('ファイルサイズが10MBを超えています', 'error');
        return;
    }

    i2iSelectedImage = file;

    const reader = new FileReader();
    reader.onload = e => {
        const previewImg = document.getElementById('i2i-preview-image');
        const previewWrap = document.getElementById('i2i-preview-wrap');
        const uploadArea = document.getElementById('i2i-upload-area');
        const genBtn = document.getElementById('i2i-generate-btn');

        if (previewImg) previewImg.src = e.target.result;
        if (previewWrap) previewWrap.classList.remove('hidden');
        if (uploadArea) uploadArea.classList.add('hidden');
        if (genBtn) genBtn.disabled = false;

        toast('画像を読み込みました', 'success');
    };
    reader.onerror = () => {
        console.error('[IMG2IMG] FileReader error');
        toast('ファイルの読み込みに失敗しました', 'error');
    };
    reader.readAsDataURL(file);
}

function clearI2IImage() {
    i2iSelectedImage = null;

    const imageInput = document.getElementById('i2i-image-input');
    const previewWrap = document.getElementById('i2i-preview-wrap');
    const uploadArea = document.getElementById('i2i-upload-area');
    const genBtn = document.getElementById('i2i-generate-btn');

    if (imageInput) imageInput.value = '';
    if (previewWrap) previewWrap.classList.add('hidden');
    if (uploadArea) uploadArea.classList.remove('hidden');
    if (genBtn) genBtn.disabled = true;
}

async function checkImg2ImgStatus() {
    if (!_sdStatusPromise.img2img) {
        _sdStatusPromise.img2img = (async () => {
            const badge = document.getElementById('i2i-api-badge');
            badge.className = 'badge badge-gray';
            badge.textContent = 'Checking...';
            try {
                const r = await fetch('/api/sd/status');
                const d = await r.json();
                if (d.available) {
                    badge.className = 'badge badge-green';
                    badge.textContent = 'Connected';

                    if (!_modelsLoaded.img2img) {
                        if (d.samplers?.length) {
                            const sel = document.getElementById('i2i-sampler');
                            sel.innerHTML = d.samplers.map(s => `<option>${s}</option>`).join('');
                            if (sel.dataset.pendingValue) { sel.value = sel.dataset.pendingValue; delete sel.dataset.pendingValue; }
                        }
                        if (d.models?.length) {
                            const modelSel = document.getElementById('i2i-model');
                            const toRestore = _selectedModel.img2img || modelSel.dataset.pendingValue || d.model || '';
                            modelSel.innerHTML = d.models.map(m => {
                                const name = m.model_name || m.title || '';
                                return `<option value="${name}">${name}</option>`;
                            }).join('');
                            if (toRestore) modelSel.value = toRestore;
                            if (modelSel.dataset.pendingValue) delete modelSel.dataset.pendingValue;
                            if (modelSel.value) _selectedModel.img2img = modelSel.value;
                        }
                        if (d.upscalers?.length) {
                            const upscalerSel = document.getElementById('i2i-hr-upscaler');
                            upscalerSel.innerHTML = d.upscalers.map(u =>
                                `<option${u === 'R-ESRGAN 4x+' ? ' selected' : ''}>${u}</option>`
                            ).join('');
                            if (upscalerSel.dataset.pendingValue) { upscalerSel.value = upscalerSel.dataset.pendingValue; delete upscalerSel.dataset.pendingValue; }
                        }
                        await loadLoras('i2i', d.loras || []);
                        _modelsLoaded.img2img = true;
                    } else {
                        const modelSel = document.getElementById('i2i-model');
                        if (_selectedModel.img2img && modelSel.value !== _selectedModel.img2img) {
                            modelSel.value = _selectedModel.img2img;
                        }
                    }
                } else {
                    badge.className = 'badge badge-red';
                    badge.textContent = 'Disconnected';
                }
            } catch {
                badge.className = 'badge badge-red';
                badge.textContent = 'Error';
            }
        })().finally(() => { _sdStatusPromise.img2img = null; });
    }
    return _sdStatusPromise.img2img;
}

async function runImg2Img() {
    const btn = document.getElementById('i2i-generate-btn');
    if (btn.disabled) return;
    if (!i2iSelectedImage) { toast('入力画像を選択してください', 'error'); return; }

    const positive = document.getElementById('i2i-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); return; }
    const _i2iModel = document.getElementById('i2i-model').value.trim();
    if (!_i2iModel) { toast('モデルを選択してください', 'error'); return; }
    if (!await confirmModel(_i2iModel)) return;

    btn.disabled = true;
    const loading = document.getElementById('i2i-loading');
    const results = document.getElementById('i2i-results');
    const imagesEl = document.getElementById('i2i-images');

    loading.classList.remove('hidden');
    results.classList.add('hidden');
    const stopProgress = startSDProgress(loading);

    const i2iEnableHr = document.getElementById('i2i-enable-hr').checked;
    const i2iParams = {
        positive,
        negative: document.getElementById('i2i-negative').value.trim(),
        denoising_strength: parseFloat(document.getElementById('i2i-denoising').value),
        resize_mode: parseInt(document.getElementById('i2i-resize-mode').value),
        width: parseInt(document.getElementById('i2i-width').value),
        height: parseInt(document.getElementById('i2i-height').value),
        steps: parseInt(document.getElementById('i2i-steps').value),
        cfg_scale: parseFloat(document.getElementById('i2i-cfg').value),
        sampler: document.getElementById('i2i-sampler').value,
        batch_size: parseInt(document.getElementById('i2i-batch').value),
        seed: parseInt(document.getElementById('i2i-seed').value),
        model: document.getElementById('i2i-model').value.trim(),
        loras: document.getElementById('i2i-loras').value.trim(),
        enable_hr: i2iEnableHr,
        hr_scale: parseFloat(document.getElementById('i2i-hr-scale').value),
        hr_upscaler: document.getElementById('i2i-hr-upscaler').value,
        hr_second_pass_steps: parseInt(document.getElementById('i2i-hr-steps').value),
        hr_denoising_strength: parseFloat(document.getElementById('i2i-hr-denoising').value)
    };

    // Save parameters for next startup
    saveLastParams('img2img', i2iParams);

    const fd = new FormData();
    fd.append('file', i2iSelectedImage);
    fd.append('positive', positive);
    fd.append('negative', i2iParams.negative);
    fd.append('denoising_strength', i2iParams.denoising_strength);
    fd.append('resize_mode', i2iParams.resize_mode);
    fd.append('width', i2iParams.width);
    fd.append('height', i2iParams.height);
    fd.append('steps', i2iParams.steps);
    fd.append('cfg_scale', i2iParams.cfg_scale);
    fd.append('sampler', i2iParams.sampler);
    fd.append('batch_size', i2iParams.batch_size);
    fd.append('seed', i2iParams.seed);
    fd.append('model', i2iParams.model);
    fd.append('loras', i2iParams.loras);
    fd.append('enable_hr', i2iEnableHr ? 'true' : 'false');
    fd.append('hr_scale', i2iParams.hr_scale);
    fd.append('hr_upscaler', i2iParams.hr_upscaler);
    fd.append('hr_second_pass_steps', i2iParams.hr_second_pass_steps);
    fd.append('hr_denoising_strength', i2iParams.hr_denoising_strength);

    try {
        const r = await fetch('/api/sd/img2img', { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();

        imagesEl.innerHTML = d.images.map((img, i) => `
            <div class="sd-image-wrap">
                <img src="data:image/png;base64,${img}" alt="Generated ${i + 1}">
                <button class="sd-image-download" onclick="downloadImage('${img}', ${i + 1})">⬇ 保存</button>
            </div>
        `).join('');

        results.classList.remove('hidden');
        toast(`${d.count}枚の画像を生成しました`, 'success');

        // Show comparison slider for first generated image
        if (d.images && d.images.length > 0) {
            const beforeSrc = document.getElementById('i2i-preview-image').src;
            const afterSrc = `data:image/png;base64,${d.images[0]}`;
            showImageComparison(beforeSrc, afterSrc);
        }
    } catch (e) {
        toast(e.message || '生成に失敗しました', 'error');
    } finally {
        stopProgress();
        loading.classList.add('hidden');
        btn.disabled = false;
    }
}

/* =====================================================================
   Image Compare Slider (FE3-3)
   ===================================================================== */
(function initImageCompare() {
    let _dragging = false;

    function setComparePosition(container, pct) {
        const after = container.querySelector('.compare-after');
        const divider = container.querySelector('.compare-divider');
        after.style.clipPath = `inset(0 0 0 ${pct}%)`;
        divider.style.left = `${pct}%`;
    }

    function getEventPct(container, e) {
        const rect = container.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
        return pct;
    }

    function onStart(e) {
        _dragging = true;
        e.preventDefault();
        const container = document.getElementById('img2img-compare');
        if (container) setComparePosition(container, getEventPct(container, e));
    }

    function onMove(e) {
        if (!_dragging) return;
        const container = document.getElementById('img2img-compare');
        if (container && !container.classList.contains('hidden')) {
            setComparePosition(container, getEventPct(container, e));
        }
    }

    function onEnd() {
        _dragging = false;
    }

    document.addEventListener('DOMContentLoaded', () => {
        const container = document.getElementById('img2img-compare');
        if (!container) return;

        container.addEventListener('mousedown', onStart);
        container.addEventListener('touchstart', onStart, { passive: false });
        document.addEventListener('mousemove', onMove);
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('mouseup', onEnd);
        document.addEventListener('touchend', onEnd);
    });
})();

function showImageComparison(beforeSrc, afterSrc) {
    const container = document.getElementById('img2img-compare');
    if (!container) return;

    const beforeImg = container.querySelector('.compare-before');
    const afterImg = container.querySelector('.compare-after');
    const divider = container.querySelector('.compare-divider');

    beforeImg.src = beforeSrc;
    afterImg.src = afterSrc;

    // Reset to 50%
    afterImg.style.clipPath = 'inset(0 0 0 50%)';
    divider.style.left = '50%';

    container.classList.remove('hidden');
}

/* =====================================================================
   Inpaint Page
   ===================================================================== */
// Canvas state
const _inpaint = {
    drawing: false,
    mode: 'draw',   // 'draw' | 'erase'
    brushSize: 30,
    maskOpacity: 0.5,
    canvasW: 0,
    canvasH: 0
};

function setupInpaintPage() {
    const uploadArea = document.getElementById('inpaint-upload-area');
    const imageInput = document.getElementById('inpaint-image-input');
    const clearImageBtn = document.getElementById('inpaint-clear-image-btn');
    const clearMaskBtn = document.getElementById('inpaint-clear-mask-btn');
    const fillMaskBtn = document.getElementById('inpaint-fill-mask-btn');
    const generateBtn = document.getElementById('inpaint-generate-btn');
    const drawBtn = document.getElementById('inpaint-tool-draw');
    const eraseBtn = document.getElementById('inpaint-tool-erase');
    const brushSlider = document.getElementById('inpaint-brush-size');
    const brushVal = document.getElementById('inpaint-brush-size-val');
    const opacitySlider = document.getElementById('inpaint-mask-opacity');
    const opacityVal = document.getElementById('inpaint-mask-opacity-val');
    const maskCanvas = document.getElementById('inpaint-mask-canvas');

    uploadArea.addEventListener('click', () => imageInput.click());
    imageInput.addEventListener('change', e => handleInpaintImageSelect(e.target.files[0]));
    uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
    uploadArea.addEventListener('drop', e => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) handleInpaintImageSelect(e.dataTransfer.files[0]);
    });

    clearImageBtn.addEventListener('click', clearInpaintImage);
    clearMaskBtn.addEventListener('click', clearInpaintMask);
    fillMaskBtn.addEventListener('click', fillInpaintMask);
    generateBtn.addEventListener('click', runInpaint);

    document.getElementById('inpaint-model').addEventListener('change', e => {
        _selectedModel.inpaint = e.target.value;
    });

    drawBtn.addEventListener('click', () => {
        _inpaint.mode = 'draw';
        drawBtn.classList.add('active-tool');
        eraseBtn.classList.remove('active-tool');
    });
    eraseBtn.addEventListener('click', () => {
        _inpaint.mode = 'erase';
        eraseBtn.classList.add('active-tool');
        drawBtn.classList.remove('active-tool');
    });

    brushSlider.addEventListener('input', () => {
        _inpaint.brushSize = parseInt(brushSlider.value);
        brushVal.textContent = brushSlider.value;
    });
    opacitySlider.addEventListener('input', () => {
        _inpaint.maskOpacity = parseInt(opacitySlider.value) / 100;
        opacityVal.textContent = opacitySlider.value;
        updateMaskCanvasOpacity();
    });

    // Canvas mouse/touch drawing
    maskCanvas.addEventListener('mousedown', e => { _inpaint.drawing = true; paintMask(e); });
    maskCanvas.addEventListener('mousemove', e => { if (_inpaint.drawing) paintMask(e); });
    maskCanvas.addEventListener('mouseup', () => { _inpaint.drawing = false; });
    maskCanvas.addEventListener('mouseleave', () => { _inpaint.drawing = false; });
    maskCanvas.addEventListener('touchstart', e => { e.preventDefault(); _inpaint.drawing = true; paintMask(e.touches[0]); }, { passive: false });
    maskCanvas.addEventListener('touchmove', e => { e.preventDefault(); if (_inpaint.drawing) paintMask(e.touches[0]); }, { passive: false });
    maskCanvas.addEventListener('touchend', () => { _inpaint.drawing = false; });

    // Token counters
    document.getElementById('inpaint-positive')?.addEventListener('input', () => updateTokenCounter('inpaint-positive', 'inpaint-positive-tokens'));
    document.getElementById('inpaint-negative')?.addEventListener('input', () => updateTokenCounter('inpaint-negative', 'inpaint-negative-tokens'));

    // Negative prompt templates
    populateNegTemplates('inpaint-neg-template');
    document.getElementById('inpaint-neg-template')?.addEventListener('change', () => applyNegTemplate('inpaint-neg-template', 'inpaint-negative', 'inpaint-negative-tokens'));

    // Restore last used parameters after status check populates selectors
    checkInpaintStatus().then(() => loadLastParams('inpaint'));
}

function handleInpaintImageSelect(file) {
    if (!file || !file.type.startsWith('image/')) { toast('画像ファイルを選択してください', 'error'); return; }
    if (file.size > 10 * 1024 * 1024) { toast('ファイルサイズが10MBを超えています', 'error'); return; }
    inpaintSelectedImage = file;

    const reader = new FileReader();
    reader.onload = e => {
        const img = new Image();
        img.onload = () => {
            const baseCanvas = document.getElementById('inpaint-base-canvas');
            const maskCanvas = document.getElementById('inpaint-mask-canvas');
            const container = document.querySelector('.inpaint-canvas-container');

            // Limit display size to 600px wide
            const maxW = 600;
            const scale = img.width > maxW ? maxW / img.width : 1;
            const displayW = Math.round(img.width * scale);
            const displayH = Math.round(img.height * scale);

            _inpaint.canvasW = img.width;
            _inpaint.canvasH = img.height;

            baseCanvas.width = img.width;
            baseCanvas.height = img.height;
            maskCanvas.width = img.width;
            maskCanvas.height = img.height;

            container.style.maxWidth = displayW + 'px';

            const bCtx = baseCanvas.getContext('2d');
            bCtx.drawImage(img, 0, 0);

            clearInpaintMask();

            document.getElementById('inpaint-upload-area').classList.add('hidden');
            document.getElementById('inpaint-canvas-wrap').classList.remove('hidden');
            document.getElementById('inpaint-generate-btn').disabled = false;
            toast('画像を読み込みました', 'success');
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function paintMask(e) {
    const maskCanvas = document.getElementById('inpaint-mask-canvas');
    const rect = maskCanvas.getBoundingClientRect();
    const scaleX = maskCanvas.width / rect.width;
    const scaleY = maskCanvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;
    const ctx = maskCanvas.getContext('2d');
    const radius = _inpaint.brushSize * scaleX;

    ctx.save();
    if (_inpaint.mode === 'erase') {
        ctx.globalCompositeOperation = 'destination-out';
        ctx.fillStyle = 'rgba(0,0,0,1)';
    } else {
        ctx.globalCompositeOperation = 'source-over';
        ctx.fillStyle = `rgba(255,100,0,${_inpaint.maskOpacity})`;
    }
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
}

function clearInpaintMask() {
    const maskCanvas = document.getElementById('inpaint-mask-canvas');
    const ctx = maskCanvas.getContext('2d');
    ctx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
}

function fillInpaintMask() {
    const maskCanvas = document.getElementById('inpaint-mask-canvas');
    const ctx = maskCanvas.getContext('2d');
    ctx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
    ctx.fillStyle = `rgba(255,100,0,${_inpaint.maskOpacity})`;
    ctx.fillRect(0, 0, maskCanvas.width, maskCanvas.height);
}

function updateMaskCanvasOpacity() {
    // The mask opacity is encoded at draw-time via _inpaint.maskOpacity.
    // Existing strokes cannot be retroactively changed; the slider only affects new strokes.
    // This function is intentionally a no-op — updating _inpaint.maskOpacity (already done by the
    // slider event listener) is sufficient.
}

function clearInpaintImage() {
    inpaintSelectedImage = null;
    document.getElementById('inpaint-image-input').value = '';
    document.getElementById('inpaint-canvas-wrap').classList.add('hidden');
    document.getElementById('inpaint-upload-area').classList.remove('hidden');
    document.getElementById('inpaint-generate-btn').disabled = true;
    clearInpaintMask();
}

async function checkInpaintStatus() {
    if (!_sdStatusPromise.inpaint) {
        _sdStatusPromise.inpaint = (async () => {
            const badge = document.getElementById('inpaint-api-badge');
            if (!badge) return;
            badge.className = 'badge badge-gray';
            badge.textContent = 'Checking...';
            try {
                const r = await fetch('/api/sd/status');
                const d = await r.json();
                if (d.available) {
                    badge.className = 'badge badge-green';
                    badge.textContent = 'Connected';

                    if (!_modelsLoaded.inpaint) {
                        if (d.samplers?.length) {
                            const sel = document.getElementById('inpaint-sampler');
                            sel.innerHTML = d.samplers.map(s => `<option>${s}</option>`).join('');
                            if (sel.dataset.pendingValue) { sel.value = sel.dataset.pendingValue; delete sel.dataset.pendingValue; }
                        }
                        if (d.models?.length) {
                            const modelSel = document.getElementById('inpaint-model');
                            const toRestore = _selectedModel.inpaint || modelSel.dataset.pendingValue || d.model || '';
                            modelSel.innerHTML = d.models.map(m => {
                                const name = m.model_name || m.title || '';
                                return `<option value="${name}">${name}</option>`;
                            }).join('');
                            if (toRestore) modelSel.value = toRestore;
                            if (modelSel.dataset.pendingValue) delete modelSel.dataset.pendingValue;
                            if (modelSel.value) _selectedModel.inpaint = modelSel.value;
                        }
                        await loadLoras('inpaint', d.loras || []);
                        _modelsLoaded.inpaint = true;
                    } else {
                        const modelSel = document.getElementById('inpaint-model');
                        if (_selectedModel.inpaint && modelSel.value !== _selectedModel.inpaint) {
                            modelSel.value = _selectedModel.inpaint;
                        }
                    }
                } else {
                    badge.className = 'badge badge-red';
                    badge.textContent = 'Disconnected';
                }
            } catch {
                badge.className = 'badge badge-red';
                badge.textContent = 'Error';
            }
        })().finally(() => { _sdStatusPromise.inpaint = null; });
    }
    return _sdStatusPromise.inpaint;
}

function getMaskBase64() {
    const maskCanvas = document.getElementById('inpaint-mask-canvas');
    const W = maskCanvas.width;
    const H = maskCanvas.height;
    const ctx = maskCanvas.getContext('2d');
    const imageData = ctx.getImageData(0, 0, W, H);

    // Minimum alpha to consider a pixel as part of the mask (painted area)
    const MASK_ALPHA_THRESHOLD = 10;

    // Build a greyscale mask canvas: painted pixels → white, rest → black
    const bwCanvas = document.createElement('canvas');
    bwCanvas.width = W;
    bwCanvas.height = H;
    const bwCtx = bwCanvas.getContext('2d');
    const bwData = bwCtx.createImageData(W, H);

    for (let i = 0; i < imageData.data.length; i += 4) {
        const alpha = imageData.data[i + 3];
        const val = alpha > MASK_ALPHA_THRESHOLD ? 255 : 0;
        bwData.data[i] = val;
        bwData.data[i + 1] = val;
        bwData.data[i + 2] = val;
        bwData.data[i + 3] = 255;
    }
    bwCtx.putImageData(bwData, 0, 0);

    // Return base64 without data URL prefix
    return bwCanvas.toDataURL('image/png').split(',')[1];
}

async function runInpaint() {
    const btn = document.getElementById('inpaint-generate-btn');
    if (btn.disabled) return;
    if (!inpaintSelectedImage) { toast('入力画像を選択してください', 'error'); return; }
    const positive = document.getElementById('inpaint-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); return; }
    const _inpaintModel = document.getElementById('inpaint-model').value.trim();
    if (!_inpaintModel) { toast('モデルを選択してください', 'error'); return; }
    if (!await confirmModel(_inpaintModel)) return;

    btn.disabled = true;
    const maskBase64 = getMaskBase64();

    const loading = document.getElementById('inpaint-loading');
    const results = document.getElementById('inpaint-results');
    const imagesEl = document.getElementById('inpaint-images');

    loading.classList.remove('hidden');
    results.classList.add('hidden');
    const stopProgress = startSDProgress(loading);

    const params = {
        positive,
        negative: document.getElementById('inpaint-negative').value.trim(),
        denoising_strength: parseFloat(document.getElementById('inpaint-denoising').value),
        width: parseInt(document.getElementById('inpaint-width').value),
        height: parseInt(document.getElementById('inpaint-height').value),
        steps: parseInt(document.getElementById('inpaint-steps').value),
        cfg_scale: parseFloat(document.getElementById('inpaint-cfg').value),
        sampler: document.getElementById('inpaint-sampler').value,
        batch_size: parseInt(document.getElementById('inpaint-batch').value),
        seed: parseInt(document.getElementById('inpaint-seed').value),
        model: document.getElementById('inpaint-model').value.trim(),
        loras: document.getElementById('inpaint-loras').value.trim(),
        mask_blur: parseInt(document.getElementById('inpaint-mask-blur').value),
        inpainting_fill: parseInt(document.getElementById('inpaint-fill-mode').value),
        inpaint_full_res: document.getElementById('inpaint-full-res').checked,
        inpaint_full_res_padding: parseInt(document.getElementById('inpaint-full-res-padding').value)
    };

    saveLastParams('inpaint', params);

    const fd = new FormData();
    fd.append('file', inpaintSelectedImage);
    fd.append('mask', maskBase64);
    fd.append('positive', params.positive);
    fd.append('negative', params.negative);
    fd.append('denoising_strength', params.denoising_strength);
    fd.append('width', params.width);
    fd.append('height', params.height);
    fd.append('steps', params.steps);
    fd.append('cfg_scale', params.cfg_scale);
    fd.append('sampler', params.sampler);
    fd.append('batch_size', params.batch_size);
    fd.append('seed', params.seed);
    fd.append('model', params.model);
    fd.append('loras', params.loras);
    fd.append('mask_blur', params.mask_blur);
    fd.append('inpainting_fill', params.inpainting_fill);
    fd.append('inpaint_full_res', params.inpaint_full_res ? 'true' : 'false');
    fd.append('inpaint_full_res_padding', params.inpaint_full_res_padding);

    try {
        const r = await fetch('/api/sd/inpaint', { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();

        imagesEl.innerHTML = d.images.map((img, i) => `
            <div class="sd-image-wrap">
                <img src="data:image/png;base64,${img}" alt="Inpainted ${i + 1}">
                <button class="sd-image-download" onclick="downloadImage('${img}', ${i + 1})">⬇ 保存</button>
            </div>
        `).join('');

        results.classList.remove('hidden');
        toast(`${d.count}枚の画像を生成しました`, 'success');
    } catch (e) {
        toast(e.message || '生成に失敗しました', 'error');
    } finally {
        stopProgress();
        loading.classList.add('hidden');
        btn.disabled = false;
    }
}

/* =====================================================================
   Last Parameter History
   ===================================================================== */
async function saveLastParams(feature, params) {
    try {
        const r = await fetch(`/api/last-params/${feature}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        if (!r.ok) {
            console.error(`[PARAMS] Save failed for ${feature}:`, r.status);
        }
    } catch (e) {
        console.error(`[PARAMS] Save failed for ${feature}:`, e);
    }
}

async function loadLastParams(feature) {
    try {
        const r = await fetch(`/api/last-params/${feature}`);
        if (!r.ok) {
            console.warn(`[PARAMS] API response not OK for ${feature}:`, r.status);
            return;
        }
        const d = await r.json();
        if (d.params && Object.keys(d.params).length > 0) {
            applyLastParams(feature, d.params);
        }
    } catch (e) {
        console.error(`[PARAMS] Load failed for ${feature}:`, e);
    }
}

function applyLastParams(feature, params) {
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined && val !== null) {
            // For select elements, try to set value directly first
            if (el.tagName === 'SELECT') {
                // If option exists, set it directly
                if (el.querySelector(`option[value="${val}"]`)) {
                    el.value = val;
                    return;
                } else if (val && !el.dataset.pendingValue) {
                    // Otherwise, use pendingValue for later
                    el.dataset.pendingValue = val;
                    return;
                }
            }
            // For text inputs and other elements
            el.value = val;
        }
    };
    const setPending = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined && val !== null) {
            el.dataset.pendingValue = val;
        }
    };

    if (feature === 'generate') {
        setVal('select-style', params.style);
        setVal('select-tone', params.tone);
        setVal('select-quality', params.quality);
        setPending('select-preset', params.preset_id);

    } else if (feature === 'sd') {
        setVal('sd-positive', params.positive);
        setVal('sd-negative', params.negative);
        setVal('sd-width', params.width);
        setVal('sd-height', params.height);
        setVal('sd-steps', params.steps);
        setVal('sd-cfg', params.cfg_scale);
        setVal('sd-batch', params.batch_size);
        setVal('sd-seed', params.seed);
        setVal('sd-model', params.model);
        if (params.model) _selectedModel.sd = params.model;
        setVal('sd-loras', params.loras);
        setVal('sd-hr-scale', params.hr_scale);
        setVal('sd-hr-steps', params.hr_second_pass_steps);
        setVal('sd-hr-denoising', params.hr_denoising_strength);
        setVal('sd-sampler', params.sampler);
        setVal('sd-hr-upscaler', params.hr_upscaler);
        if (params.enable_hr !== undefined) {
            const hrChk = document.getElementById('sd-enable-hr');
            if (hrChk) {
                hrChk.checked = params.enable_hr;
                document.getElementById('sd-hr-settings').classList.toggle('hidden', !params.enable_hr);
            }
        }

    } else if (feature === 'img2img') {
        setVal('i2i-positive', params.positive);
        setVal('i2i-negative', params.negative);
        setVal('i2i-denoising', params.denoising_strength);
        setVal('i2i-resize-mode', params.resize_mode);
        setVal('i2i-width', params.width);
        setVal('i2i-height', params.height);
        setVal('i2i-steps', params.steps);
        setVal('i2i-cfg', params.cfg_scale);
        setVal('i2i-batch', params.batch_size);
        setVal('i2i-seed', params.seed);
        setVal('i2i-model', params.model);
        if (params.model) _selectedModel.img2img = params.model;
        setVal('i2i-loras', params.loras);
        setVal('i2i-hr-scale', params.hr_scale);
        setVal('i2i-hr-steps', params.hr_second_pass_steps);
        setVal('i2i-hr-denoising', params.hr_denoising_strength);
        setVal('i2i-sampler', params.sampler);
        setVal('i2i-hr-upscaler', params.hr_upscaler);
        if (params.enable_hr !== undefined) {
            const hrChk = document.getElementById('i2i-enable-hr');
            if (hrChk) {
                hrChk.checked = params.enable_hr;
                document.getElementById('i2i-hr-settings').classList.toggle('hidden', !params.enable_hr);
            }
        }

    } else if (feature === 'inpaint') {
        setVal('inpaint-positive', params.positive);
        setVal('inpaint-negative', params.negative);
        setVal('inpaint-denoising', params.denoising_strength);
        setVal('inpaint-width', params.width);
        setVal('inpaint-height', params.height);
        setVal('inpaint-steps', params.steps);
        setVal('inpaint-cfg', params.cfg_scale);
        setVal('inpaint-batch', params.batch_size);
        setVal('inpaint-seed', params.seed);
        setVal('inpaint-model', params.model);
        if (params.model) _selectedModel.inpaint = params.model;
        setVal('inpaint-loras', params.loras);
        setVal('inpaint-mask-blur', params.mask_blur);
        setVal('inpaint-fill-mode', params.inpainting_fill);
        setVal('inpaint-full-res-padding', params.inpaint_full_res_padding);
        setVal('inpaint-sampler', params.sampler);
        if (params.inpaint_full_res !== undefined) {
            const chk = document.getElementById('inpaint-full-res');
            if (chk) { chk.checked = params.inpaint_full_res; }
        }
    }
}

/* =====================================================================
   SD Progress Bar (FE-3)
   ===================================================================== */
function startSDProgress(containerEl) {
    const wrap = containerEl.querySelector('.sd-progress-bar-wrap');
    if (!wrap) return () => {};
    const fill = wrap.querySelector('.sd-progress-fill');
    const text = wrap.querySelector('.sd-progress-text');
    wrap.classList.remove('hidden');
    fill.style.width = '0%';
    text.textContent = '';

    let stopped = false;

    function applyProgress(d) {
        if (!d || !d.available) return;
        const pct = Math.round((d.progress || 0) * 100);
        fill.style.width = pct + '%';
        const eta = d.eta_relative != null ? ` (ETA: ${Math.ceil(d.eta_relative)}s)` : '';
        text.textContent = `${pct}%${eta}`;
    }

    let ws = null;
    let timer = null;

    function startPollingFallback() {
        if (stopped || timer) return;
        timer = setInterval(async () => {
            try {
                const r = await fetch('/api/sd/progress');
                if (!r.ok) return;
                applyProgress(await r.json());
            } catch {}
        }, 1000);
    }

    try {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/api/sd/progress/ws`);
        ws.onmessage = (e) => { try { applyProgress(JSON.parse(e.data)); } catch {} };
        ws.onerror = () => { ws.close(); startPollingFallback(); };
        ws.onclose = () => { if (!stopped) startPollingFallback(); };
    } catch {
        startPollingFallback();
    }

    return () => {
        stopped = true;
        if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
        if (timer) clearInterval(timer);
        wrap.classList.add('hidden');
        fill.style.width = '0%';
        text.textContent = '';
    };
}

/* =====================================================================
   Utilities
   ===================================================================== */

/**
 * フォルダ内の画像ファイルをランダムに1枚選択して返す。
 * 画像が見つからない場合は null を返す。
 */
function pickRandomImageFromFolder(files) {
    if (!files || files.length === 0) return null;
    const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'));
    if (!imageFiles.length) {
        toast('フォルダ内に画像ファイルが見つかりませんでした', 'error');
        return null;
    }
    const idx = Math.floor(Math.random() * imageFiles.length);
    return imageFiles[idx];
}

/**
 * フォルダ内の画像ファイルからランダムに n 枚を重複なしで選択して返す。
 * フォルダ内の画像数が n 未満の場合は全件返す。
 */
function pickNRandomImagesFromFolder(files, n) {
    if (!files || files.length === 0) return [];
    const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'));
    if (!imageFiles.length) {
        toast('フォルダ内に画像ファイルが見つかりませんでした', 'error');
        return [];
    }
    const count = Math.min(n, imageFiles.length);
    // Fisher-Yates shuffle then take first `count` elements
    const arr = [...imageFiles];
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr.slice(0, count);
}

/**
 * フォルダから n 枚の画像をランダムに選び、各画像に対して
 * 「プロンプト生成」→「マルチモデル生成」を順番に連続実行する。
 */
async function runFolderBatchAutoRun(files, n) {
    const images = pickNRandomImagesFromFolder(files, n);
    if (!images.length) return;

    const autoBtn = document.getElementById('random-folder-auto-btn');
    if (autoBtn) autoBtn.disabled = true;

    // Short delay to allow the image preview to render before processing
    const IMAGE_PREVIEW_RENDER_DELAY = 100;

    try {
        for (let i = 0; i < images.length; i++) {
            toast(`[${i + 1}/${images.length}] ${images[i].name} を処理中...`, 'info');
            handleSingleImageSelect(images[i]);
            await new Promise(r => setTimeout(r, IMAGE_PREVIEW_RENDER_DELAY));
            await generatePrompt();
            const resultBox = document.getElementById('result-box');
            if (resultBox && !resultBox.classList.contains('hidden')) {
                await sendToSDAndMultiGenerate();
            }
        }
        toast(`一括実行完了 (${images.length} 枚)`, 'success');
    } finally {
        if (autoBtn) autoBtn.disabled = false;
    }
}


function copyText(elementId, btn) {
    const el = document.getElementById(elementId);
    navigator.clipboard.writeText(el.value).then(() => {
        const orig = btn.textContent;
        btn.textContent = '✓ OK';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); }, 1800);
    }).catch(e => toast('コピーに失敗しました', 'error'));
}

// モデル確認ダイアログ（Promise を返す）
function confirmModel(modelName) {
    return new Promise(resolve => {
        const modal = document.getElementById('model-confirm-modal');
        document.getElementById('model-confirm-name').textContent = modelName;
        modal.classList.remove('hidden');
        const okBtn = document.getElementById('model-confirm-ok');
        const cancelBtn = document.getElementById('model-confirm-cancel');
        const cleanup = (result) => {
            modal.classList.add('hidden');
            okBtn.removeEventListener('click', onOk);
            cancelBtn.removeEventListener('click', onCancel);
            resolve(result);
        };
        const onOk = () => cleanup(true);
        const onCancel = () => cleanup(false);
        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
    });
}

let toastTimer;
function toast(msg, type = 'info') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `toast ${type}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.add('hidden'), 3500);
}

function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* =====================================================================
   Gallery Page
   ===================================================================== */
function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function setupGalleryPage() {
    const debouncedLoad = debounce(() => { _galleryOffset = 0; loadGallery(0); }, 300);
    document.getElementById('refresh-gallery-btn').addEventListener('click', () => {
        _galleryCache = {};
        _galleryOffset = 0;
        loadGallery(0, true);
        loadGalleryFilters();
    });
    document.getElementById('gallery-filter-mode').addEventListener('change', debouncedLoad);
    document.getElementById('gallery-filter-date').addEventListener('change', debouncedLoad);

    // Metadata search & filters
    const searchInput = document.getElementById('gallery-search');
    if (searchInput) searchInput.addEventListener('input', debouncedLoad);
    const modelFilter = document.getElementById('gallery-filter-model');
    if (modelFilter) modelFilter.addEventListener('change', debouncedLoad);
    const samplerFilter = document.getElementById('gallery-filter-sampler');
    if (samplerFilter) samplerFilter.addEventListener('change', debouncedLoad);

    // Selection mode
    const selectModeBtn = document.getElementById('gallery-select-mode-btn');
    if (selectModeBtn) selectModeBtn.addEventListener('click', toggleGallerySelectionMode);
    const selectAllBtn = document.getElementById('gallery-select-all-btn');
    if (selectAllBtn) selectAllBtn.addEventListener('click', gallerySelectAll);
    const deselectAllBtn = document.getElementById('gallery-deselect-all-btn');
    if (deselectAllBtn) deselectAllBtn.addEventListener('click', galleryDeselectAll);
    const downloadZipBtn = document.getElementById('gallery-download-zip-btn');
    if (downloadZipBtn) downloadZipBtn.addEventListener('click', downloadSelectedAsZip);

    document.getElementById('gallery-load-more-btn').addEventListener('click', () => {
        loadGallery(_galleryOffset);
    });
    document.getElementById('gallery-modal-close').addEventListener('click', closeGalleryModal);
    document.getElementById('gallery-modal').addEventListener('click', e => {
        if (e.target === document.getElementById('gallery-modal')) closeGalleryModal();
    });
    document.getElementById('gallery-modal-prev').addEventListener('click', (e) => { e.stopPropagation(); galleryNavigate(-1); });
    document.getElementById('gallery-modal-next').addEventListener('click', (e) => { e.stopPropagation(); galleryNavigate(1); });
    document.addEventListener('keydown', e => {
        const modal = document.getElementById('gallery-modal');
        if (modal.classList.contains('hidden')) return;
        if (e.key === 'ArrowLeft') { e.preventDefault(); galleryNavigate(-1); }
        else if (e.key === 'ArrowRight') { e.preventDefault(); galleryNavigate(1); }
        else if (e.key === 'Escape') { e.preventDefault(); closeGalleryModal(); }
    });
}

async function loadGallery(offset = 0, forceRefresh = false) {
    const loading = document.getElementById('gallery-loading');
    const empty = document.getElementById('gallery-empty');
    const grid = document.getElementById('gallery-grid');
    const modeFilter = document.getElementById('gallery-filter-mode').value;
    const dateFilter = document.getElementById('gallery-filter-date').value;

    loading.classList.remove('hidden');
    empty.classList.add('hidden');
    if (offset === 0) grid.innerHTML = '';

    try {
        const searchText_ck = (document.getElementById('gallery-search') || {}).value || '';
        const modelFilter_ck = (document.getElementById('gallery-filter-model') || {}).value || '';
        const samplerFilter_ck = (document.getElementById('gallery-filter-sampler') || {}).value || '';
        const cacheKey = `${modeFilter}|${dateFilter}|${searchText_ck}|${modelFilter_ck}|${samplerFilter_ck}|${offset}`;
        let d;
        if (!forceRefresh && _galleryCache[cacheKey]) {
            d = _galleryCache[cacheKey];
        } else {
            const params = new URLSearchParams();
            if (modeFilter) params.set('mode', modeFilter);
            if (dateFilter) params.set('date', dateFilter);
            const searchText = (document.getElementById('gallery-search') || {}).value || '';
            const modelFilterVal = (document.getElementById('gallery-filter-model') || {}).value || '';
            const samplerFilterVal = (document.getElementById('gallery-filter-sampler') || {}).value || '';
            if (searchText) params.set('search', searchText);
            if (modelFilterVal) params.set('model', modelFilterVal);
            if (samplerFilterVal) params.set('sampler', samplerFilterVal);
            params.set('offset', offset);
            params.set('limit', 24);

            const r = await fetch('/api/outputs?' + params.toString());
            if (!r.ok) throw new Error('Failed to load gallery');
            d = await r.json();
            _galleryCache[cacheKey] = d;
        }

        // 最初のロード時のみ日付フィルターを更新
        if (offset === 0 && d.dates) {
            const dateSelect = document.getElementById('gallery-filter-date');
            const currentDate = dateSelect.value;
            dateSelect.innerHTML = '<option value="">全日付</option>';
            d.dates.forEach(date => {
                const opt = document.createElement('option');
                opt.value = date;
                opt.textContent = date;
                if (date === currentDate) opt.selected = true;
                dateSelect.appendChild(opt);
            });
        }

        if (offset === 0 && (!d.images || d.images.length === 0)) {
            empty.classList.remove('hidden');
            document.getElementById('gallery-load-more-wrap').classList.add('hidden');
            return;
        }

        // DocumentFragment で効率的にアイテムを追加
        const fragment = document.createDocumentFragment();
        (d.images || []).forEach(img => {
            const modeLabel = img.mode === 'img2img' ? 'Img2Img' : img.mode === 'inpaint' ? 'Inpaint' : 'SD';
            const modeClass = img.mode === 'img2img' ? 'badge-img2img' : img.mode === 'inpaint' ? 'badge-inpaint' : 'badge-sd';
            const prompt = img.parameters.positive_prompt || '';
            const shortPrompt = prompt.length > 60 ? prompt.slice(0, 60) + '…' : prompt;
            const div = document.createElement('div');
            div.className = 'gallery-item';
            if (_gallerySelectionMode && _gallerySelectedPaths.has(img.url)) {
                div.classList.add('selected');
            }
            div.addEventListener('click', () => {
                if (_gallerySelectionMode) {
                    div.classList.toggle('selected');
                    if (div.classList.contains('selected')) {
                        _gallerySelectedPaths.add(img.url);
                    } else {
                        _gallerySelectedPaths.delete(img.url);
                    }
                    updateGallerySelectedCount();
                } else {
                    openGalleryModal(JSON.stringify(img));
                }
            });
            div.innerHTML = `
                <div class="gallery-thumb-wrap">
                    <img class="gallery-thumb" src="${escHtml(img.thumb_url || img.url)}" alt="${escHtml(img.filename)}" loading="lazy">
                    <span class="gallery-mode-badge ${escHtml(modeClass)}">${escHtml(modeLabel)}</span>
                </div>
                <div class="gallery-item-info">
                    <div class="gallery-item-date">${escHtml(img.date)}</div>
                    ${shortPrompt ? `<div class="gallery-item-prompt">${escHtml(shortPrompt)}</div>` : ''}
                </div>`;
            fragment.appendChild(div);
        });
        if (offset === 0) _galleryImages = d.images || [];
        else _galleryImages = _galleryImages.concat(d.images || []);
        grid.appendChild(fragment);

        // Load More ボタンの表示制御
        const loaded = offset + (d.images ? d.images.length : 0);
        const loadMoreWrap = document.getElementById('gallery-load-more-wrap');
        if (d.total && loaded < d.total) {
            loadMoreWrap.classList.remove('hidden');
            _galleryOffset = loaded;
        } else {
            loadMoreWrap.classList.add('hidden');
            _galleryOffset = 0;
        }
    } catch (e) {
        toast('ギャラリーの読み込みに失敗しました', 'error');
    } finally {
        loading.classList.add('hidden');
    }
}

function openGalleryModal(imgJsonStr) {
    const img = JSON.parse(imgJsonStr);
    const modal = document.getElementById('gallery-modal');
    const modalImg = document.getElementById('gallery-modal-image');
    const modalTitle = document.getElementById('gallery-modal-title');
    const modalDownload = document.getElementById('gallery-modal-download');
    const modalParams = document.getElementById('gallery-modal-params');

    modalImg.src = img.url;
    modalTitle.textContent = img.filename;
    modalDownload.href = img.url;
    modalDownload.download = img.filename;

    // Update navigation index
    _galleryCurrentIndex = _galleryImages.findIndex(i => i.filename === img.filename);
    const prevBtn = document.getElementById('gallery-modal-prev');
    const nextBtn = document.getElementById('gallery-modal-next');
    if (prevBtn) prevBtn.style.display = _galleryCurrentIndex > 0 ? '' : 'none';
    if (nextBtn) nextBtn.style.display = _galleryCurrentIndex < _galleryImages.length - 1 ? '' : 'none';

    const p = img.parameters || {};
    const rows = [
        ['モード', img.mode === 'img2img' ? 'Img2Img' : img.mode === 'inpaint' ? 'Inpaint' : 'SD Generate'],
        ['日付', img.date],
        ['Positive', p.positive_prompt || ''],
        ['Negative', p.negative_prompt || ''],
        ['Model', p.model || '(default)'],
        ['Size', p.width && p.height ? `${p.width}×${p.height}` : ''],
        ['Steps', p.steps || ''],
        ['CFG Scale', p.cfg_scale || ''],
        ['Sampler', p.sampler || ''],
        ['Seed', p.seed !== undefined ? p.seed : ''],
        ['LoRA', p.loras || ''],
    ].filter(([, v]) => v !== '' && v !== undefined && v !== null);

    if (img.mode === 'img2img' && p.denoising_strength !== undefined) {
        rows.push(['Denoising', p.denoising_strength]);
    }
    if (img.mode === 'inpaint' && p.denoising_strength !== undefined) {
        rows.push(['Denoising', p.denoising_strength]);
    }

    modalParams.innerHTML = rows.map(([label, value]) => `
        <div class="gallery-param-row">
            <span class="gallery-param-label">${escHtml(label)}</span>
            <span class="gallery-param-value">${escHtml(String(value))}</span>
        </div>
    `).join('');

    const copyBtn = document.getElementById('gallery-modal-copy-btn');
    if (copyBtn) {
        copyBtn.onclick = () => {
            const pos = p.positive_prompt || '';
            const neg = p.negative_prompt || '';
            const text = neg ? `Positive:\n${pos}\n\nNegative:\n${neg}` : pos;
            navigator.clipboard.writeText(text)
                .then(() => toast('プロンプトをコピーしました', 'success'))
                .catch(() => toast('コピーに失敗しました', 'error'));
        };
    }

    const sendBtn = document.getElementById('gallery-modal-send-sd');
    if (sendBtn) {
        sendBtn.onclick = () => {
            const params = img.parameters || {};
            // Navigate to SD page
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.querySelector('.nav-btn[data-page="sd"]').classList.add('active');
            document.getElementById('page-sd').classList.add('active');
            // Fill parameters
            const sdPos = document.getElementById('sd-positive');
            const sdNeg = document.getElementById('sd-negative');
            if (sdPos) sdPos.value = params.positive_prompt || '';
            if (sdNeg) sdNeg.value = params.negative_prompt || '';
            const fields = {
                'sd-steps': params.steps,
                'sd-cfg': params.cfg_scale,
                'sd-seed': params.seed,
                'sd-width': params.width,
                'sd-height': params.height,
            };
            for (const [id, val] of Object.entries(fields)) {
                const el = document.getElementById(id);
                if (el && val != null) el.value = val;
            }
            if (params.sampler) {
                const samplerEl = document.getElementById('sd-sampler');
                if (samplerEl) samplerEl.value = params.sampler;
            }
            closeGalleryModal();
            checkSDStatus();
            toast('パラメータをSD生成に送りました', 'success');
        };
    }

    modal.classList.remove('hidden');
}

function galleryNavigate(direction) {
    const newIndex = _galleryCurrentIndex + direction;
    if (newIndex < 0 || newIndex >= _galleryImages.length) return;
    openGalleryModal(JSON.stringify(_galleryImages[newIndex]));
}

function toggleGallerySelectionMode() {
    _gallerySelectionMode = !_gallerySelectionMode;
    const grid = document.getElementById('gallery-grid');
    const actions = document.getElementById('gallery-select-actions');
    const btn = document.getElementById('gallery-select-mode-btn');

    if (_gallerySelectionMode) {
        grid.classList.add('selection-mode');
        if (actions) actions.classList.remove('hidden');
        if (btn) btn.classList.add('active');
        toast(I18n.t('page.gallery.select_mode_on') || '選択モードON', 'info');
    } else {
        grid.classList.remove('selection-mode');
        if (actions) actions.classList.add('hidden');
        if (btn) btn.classList.remove('active');
        _gallerySelectedPaths.clear();
        grid.querySelectorAll('.gallery-item.selected').forEach(el => el.classList.remove('selected'));
        updateGallerySelectedCount();
    }
}

function gallerySelectAll() {
    const grid = document.getElementById('gallery-grid');
    grid.querySelectorAll('.gallery-item').forEach(el => {
        el.classList.add('selected');
    });
    _gallerySelectedPaths.clear();
    _galleryImages.forEach(img => _gallerySelectedPaths.add(img.url));
    updateGallerySelectedCount();
}

function galleryDeselectAll() {
    const grid = document.getElementById('gallery-grid');
    grid.querySelectorAll('.gallery-item.selected').forEach(el => el.classList.remove('selected'));
    _gallerySelectedPaths.clear();
    updateGallerySelectedCount();
}

function updateGallerySelectedCount() {
    const countEl = document.getElementById('gallery-selected-count');
    if (countEl) {
        const count = _gallerySelectedPaths.size;
        countEl.textContent = (I18n.t('page.gallery.selected_count') || '{count}枚選択中').replace('{count}', count);
    }
}

async function downloadSelectedAsZip() {
    if (_gallerySelectedPaths.size === 0) {
        toast(I18n.t('toast.no_images_selected') || 'ダウンロードする画像を選択してください', 'error');
        return;
    }
    try {
        const resp = await fetch('/api/outputs/download-zip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paths: Array.from(_gallerySelectedPaths) }),
        });
        if (!resp.ok) throw new Error('ZIP download failed');
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'gallery_images.zip';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast(I18n.t('toast.zip_download_started') || 'ZIPダウンロードを開始しました', 'success');
    } catch (e) {
        toast(I18n.t('toast.zip_download_failed') || 'ZIPダウンロードに失敗しました', 'error');
    }
}

async function loadGalleryFilters() {
    try {
        const resp = await fetch('/api/outputs/filters');
        if (!resp.ok) return;
        const data = await resp.json();
        const modelSelect = document.getElementById('gallery-filter-model');
        const samplerSelect = document.getElementById('gallery-filter-sampler');
        if (modelSelect && data.models) {
            const current = modelSelect.value;
            modelSelect.innerHTML = '<option value="">' + (I18n.t('page.gallery.filter_all_models') || '全モデル') + '</option>';
            data.models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                if (m === current) opt.selected = true;
                modelSelect.appendChild(opt);
            });
        }
        if (samplerSelect && data.samplers) {
            const current = samplerSelect.value;
            samplerSelect.innerHTML = '<option value="">' + (I18n.t('page.gallery.filter_all_samplers') || '全サンプラー') + '</option>';
            data.samplers.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s;
                if (s === current) opt.selected = true;
                samplerSelect.appendChild(opt);
            });
        }
    } catch (e) {
        // Silently fail - filters will just show default options
    }
}

function closeGalleryModal() {
    document.getElementById('gallery-modal').classList.add('hidden');
    document.getElementById('gallery-modal-image').src = '';
}

// ------------------------------------------------------------------ //
// Weight Editors
// ------------------------------------------------------------------ //
function setupWeightEditors() {
    if (typeof WeightEditor === 'undefined') return;
    const targets = [
        'sd-positive', 'sd-negative',
        'i2i-positive', 'i2i-negative',
        'refine-positive-input', 'refine-negative-input',
    ];
    for (const id of targets) {
        const ta = document.getElementById(id);
        if (ta) WeightEditor.create(ta, { containerId: `we-${id}` });
    }
}
