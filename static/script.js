Warning: truncated output (original token count: 59354)
Total output lines: 5334

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
let _galleryModalTrigger = null;

// PNG Info page
let pngInfoImage = null;
let pngInfoParameters = null;

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
const _selectedModel = { sd: '', img2img: '', inpaint: '', xyplot: '' };
// モデルリストの初回ロード済みフラグ（タブ切り替え時の再構築を防ぐ）
const _modelsLoaded = { sd: false, img2img: false, inpaint: false, xyplot: false };

// FE-2: Status check promise cache (prevents concurrent duplicate fetches)
const _sdStatusPromise = { sd: null, img2img: null, inpaint: null, xyplot: null };

// FE-1: Multi-model running guard
let _multiModelRunning = false;

// XY Plot job state
let _xyPlotJobId = null;
let _xyPlotWs = null;
let _xyPlotRunning = false;

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
    _setup('xyplot', setupXYPlotPage);
    _setup('compare', setupComparePage);
    _setup('gallery', setupGalleryPage);
    _setup('pnginfo', setupPngInfoPage);
    _setup('stats', setupStatsPage);
    _setup('wildcards', setupWildcardsPage);
    _setup('backup', setupBackupPage);
    _setup('weightEditors', setupWeightEditors);
    checkStatus();
    loadProviders();
    checkProviderHealth();
    setInterval(checkProviderHealth, 30000);

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
    checkXYPlotStatus();

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
            } else if (pageId === 'page-xyplot') {
                const btn = document.getElementById('xyplot-run-btn');
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
            const modals = ['shortcuts-modal', 'preset-modal', 'model-confirm-modal', 'version-modal'];
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
        if (page === 'xyplot') checkXYPlotStatus();
        if (page === 'compare') checkCompareStatus();
        if (page === 'gallery') { loadGallery(); loadGalleryFilters(); }
        if (page === 'stats') loadStats();
        if (page === 'backup') loadBackups();
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

// ------------------------------------------------------------------ //
// Provider Health Monitoring (#85)
// ------------------------------------------------------------------ //

async function checkProviderHealth() {
    const container = document.getElementById('provider-health');
    if (!container) return;
    try {
        const r = await fetch('/api/llm/health');
        if (!r.ok) { container.innerHTML = ''; return; }
        const data = await r.json();
        if (!data.providers || Object.keys(data.providers).length === 0) {
            container.innerHTML = '';
            return;
        }
        const dots = Object.entries(data.providers).map(([name, info]) => {
            const color = info.status === 'healthy' ? 'ok' : info.status === 'degraded' ? 'warn' : 'error';
            const ms = Math.round(info.response_time_ms);
            return `<span class="health-dot ${color}" title="${name}: ${info.status} (${ms}ms)"></span><span class="health-label">${name}</span>`;
        }).join(' ');
        const chainInfo = data.fallback_chain.length > 0 ? `<span class="health-chain">Fallback: ${data.fallback_chain.join(' → ')}</span>` : '';
        container.innerHTML = dots + chainInfo;
    } catch { container.innerHTML = ''; }
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
                        if (d.models?.length) await populateMultiModelList(d.models);
                        populateControlNetSelectors('sd', d.controlnet_models, d.controlnet_modules);
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
            tab.setAttribute('aria-selected', 'true');
            document.querySelectorAll('.inner-tab').forEach(t => {
                if (t !== tab) t.setAttribute('aria-selected', 'false');
            });
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

    const blendInput = document.getElementById('blend-image-input');
    blendInput?.addEventListener('change', updateBlendRoles);

    // Generate button
    document.getElementById('generate-btn').addEventListener('click', generatePrompt);
    document.getElementById('generate-and-multi-btn').addEventListener('click', generatePromptAndMultiGenerate);

    // Analysis mode (LLM / Tagger / Hybrid) toggle
    document.getElementById('select-analysis-mode').addEventListener('change', updateAnalysisModeUI);
    updateAnalysisModeUI();

    // ストリーミング生成のキャンセル（接続切断でサーバー側の生成も中断される）
    document.getElementById('cancel-stream-btn')?.addEventListener('click', () => streamAbort?.abort());

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
    if (!file || !file.type.startsWith('image/')) {
        toast('画像ファイルを選択してください', 'error');
        return Promise.resolve(false);
    }
    if (file.size > 10 * 1024 * 1024) {
        toast('ファイルサイズが10MBを超えています', 'error');
        return Promise.resolve(false);
    }
    selectedImage = file;
    return new Promise(resolve => {
        const reader = new FileReader();
        reader.onload = e => {
            document.getElementById('preview-image').src = e.target.result;
            document.getElementById('preview-wrap').classList.remove('hidden');
            document.getElementById('upload-area').classList.add('hidden');
            updateGenerateBtn();
            resolve(true);
        };
        reader.onerror = () => {
            toast('画像の読み込みに失敗しました', 'error');
            resolve(false);
        };
        reader.readAsDataURL(file);
    });
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
    const blendFiles = document.getElementById('blend-image-input')?.files;
    const enabled = currentTab === 'tab-img'
        ? !!selectedImage
        : currentTab === 'tab-blend'
            ? !!blendFiles && blendFiles.length >= 2 && blendFiles.length <= 3
            : !!document.getElementById('description-input').value.trim();
    btn.disabled = !enabled;
    if (multiBtn) multiBtn.disabled = !enabled;
}

function updateAnalysisModeUI() {
    const mode = document.getElementById('select-analysis-mode').value;
    const taggerGroup = document.getElementById('tagger-model-group');
    if (taggerGroup) taggerGroup.classList.toggle('hidden', mode === 'llm');
}

// SSE ストリーミング生成のキャンセル用 AbortController
let streamAbort = null;

function _parseSSEBlock(block) {
    let event = null;
    let dataLine = null;
    for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLine = line.slice(5).trim();
    }
    if (!event || dataLine === null) return null;
    try {
        return { event, data: JSON.parse(dataLine) };
    } catch (e) {
        return null;
    }
}

// /api/generate-prompts-stream を叩き、token イベントをタイプライター表示する。
// 戻り値: done イベントのデータ。エンドポイント未対応(404/405・ネットワーク層失敗)は
// null を返し、呼び出し元が従来の一括エンドポイントへフォールバックする。
async function generatePromptViaStream({ isImageTab, style, tone, quality, presetId }) {
    const fd = new FormData();
    if (isImageTab) {
        fd.append('file', selectedImage);
    } else {
        fd.append('description', document.getElementById('description-input').value.trim());
    }
    fd.append('style', style);
    fd.append('tone', tone);
    fd.append('quality', quality);
    fd.append('preset_id', presetId);

    streamAbort = new AbortController();
    let r;
    try {
        r = await fetch('/api/generate-prompts-stream', { method: 'POST', body: fd, signal: streamAbort.signal });
    } catch (e) {
        if (e.name === 'AbortError') throw e;
        return null; // ネットワーク層の失敗 → 従来エンドポイントにフォールバック
    }
    if (r.status === 404 || r.status === 405) return null; // 旧サーバー → フォールバック
    if (!r.ok) throw new Error((await r.json()).detail || '生成に失敗しました');
    const ct = r.headers.get('content-type') || '';
    if (!ct.includes('text/event-stream') || !r.body) return null;

    const preview = document.getElementById('stream-preview');
    const cancelBtn = document.getElementById('cancel-stream-btn');
    preview.textContent = '';
    preview.classList.remove('hidden');
    cancelBtn.classList.remove('hidden');

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let doneData = null;
    let errMsg = null;
    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n\n')) !== -1) {
            const evt = _parseSSEBlock(buf.slice(0, idx));
            buf = buf.slice(idx + 2);
            if (!evt) continue;
            if (evt.event === 'token') {
                preview.textContent += evt.data.text;
                preview.scrollTop = preview.scrollHeight;
            } else if (evt.event === 'done') {
                doneData = evt.data;
            } else if (evt.event === 'error') {
                errMsg = evt.data.error;
            }
        }
    }
    if (errMsg) throw new Error(errMsg);
    if (!doneData) throw new Error(I18n.t('toast.stream_incomplete') || 'ストリーミングが完了しませんでした');
    return doneData;
}

async function generatePrompt() {
    if (currentTab === 'tab-blend') {
        await generateBlendedPrompt();
        return;
    }
    const loading = document.getElementById('loading-generate');
    const resultBox = document.getElementById('result-box');

    loading.classList.remove('hidden');
    resultBox.classList.add('hidden');

    const style = document.getElementById('select-style').value;
    const tone = document.getElementById('select-tone').value;
    const quality = document.getElementById('select-quality').value;
    const presetId = document.getElementById('select-preset').value;
    const analysisMode = document.getElementById('select-analysis-mode').value;
    const taggerModel = document.getElementById('select-tagger-model').value;

    // Save parameters for next startup
    saveLastParams('generate', {
        style, tone, quality, preset_id: presetId,
        analysis_mode: analysisMode, tagger_model: taggerModel
    });

    const isImageTab = currentTab === 'tab-img';

    try {
        let data = null;

        // LLM モードは SSE ストリーミングで逐次表示（tagger/hybrid はストリーム非対応）
        const canStream = !isImageTab || analysisMode === 'llm';
        if (canStream) {
            data = await generatePromptViaStream({ isImageTab, style, tone, quality, presetId });
        }

        if (data === null) {
            // ストリーム非対応モード or ストリームエンドポイント未到達時の一括生成
            if (isImageTab) {
                const fd = new FormData();
                fd.append('file', selectedImage);
                fd.append('style', style);
                fd.append('tone', tone);
                fd.append('quality', quality);
                fd.append('preset_id', presetId);
                fd.append('analysis_mode', analysisMode);
                fd.append('tagger_model', taggerModel);
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
        }

        document.getElementById('pos-prompt').value = data.positive;
        document.getElementById('neg-prompt').value = data.negative;
        updateTokenCounter('pos-prompt', 'positive-output-tokens');
        updateTokenCounter('neg-prompt', 'negative-output-tokens');
        resultBox.classList.remove('hidden');
        toast('プロンプト生成完了！', 'success');
    } catch (e) {
        if (e.name === 'AbortError') {
            toast(I18n.t('toast.generation_cancelled') || '生成をキャンセルしました', 'info');
        } else {
            toast(e.message || '生成に失敗しました', 'error');
        }
    } finally {
        loading.classList.add('hidden');
        document.getElementById('stream-preview')?.classList.add('hidden');
        document.getElementById('cancel-stream-btn')?.classList.add('hidden');
        streamAbort = null;
    }
}

function updateBlendRoles() {
    const files = Array.from(document.getElementById('blend-image-input')?.files || []);
    const fields = document.getElementById('blend-role-fields');
    if (!fields) return;
    if (files.length > 3) {
        toast('参照画像は3枚までです', 'error');
        document.getElementById('blend-image-input').value = '';
        fields.replaceChildren();
        updateGenerateBtn();
        return;
    }
    const defaults = ['被写体・構図', '背景・画風', '補助要素'];
    fields.replaceChildren();
    files.forEach((file, index) => {
        const label = document.createElement('label');
        label.textContent = `${file.name} の役割`;
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'blend-role-input';
        input.maxLength = 80;
        input.value = defaults[index];
        input.setAttribute('aria-label', `${file.name} の役割`);
        label.appendChild(input);
        fields.appendChild(label);
    });
    updateGenerateBtn();
}

async function generateBlendedPrompt() {
    const files = Array.from(document.getElementById('blend-image-input')?.files || []);
    const roles = Array.from(document.querySelectorAll('.blend-role-input')).map(input => input.value.trim());
    if (files.length < 2 || files.length > 3 || roles.some(role => !role)) {
        toast('2〜3枚の画像と各画像の役割を指定してください', 'error');
        return;
    }
    const loading = document.getElementById('loading-generate');
    const resultBox = document.getElementById('result-box');
    loading.classList.remove('hidden');
    resultBox.classList.add('hidden');
    try {
        const fd = new FormData();
        files.forEach(file => fd.append('files', file));
        roles.forEach(role => fd.append('roles', role));
        fd.append('style', document.getElementById('select-style').value);
        fd.append('tone', document.getElementById('select-tone').value);
        fd.append('quality', document.getElementById('select-quality').value);
        fd.append('preset_id', document.getElementById('select-preset').value);
        const response = await fetch('/api/generate-prompts-blend', { method: 'POST', body: fd });
        if (!response.ok) throw new Error((await response.json()).detail || '合成に失敗しました');
        const data = (await response.json()).data;
        document.getElementById('pos-prompt').value = data.positive;
        document.getElementById('neg-prompt').value = data.negative;
        updateTokenCounter('pos-prompt', 'positive-output-tokens');
        updateTokenCounter('neg-prompt', 'negative-output-tokens');
        resultBox.classList.remove('hidden');
        toast('参照画像を合成したプロンプトを生成しました', 'success');
    } catch (e) {
        toast(e.message || '合成に失敗しました', 'error');
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
                parent_id: _refineParentId || undefined,
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
        _refineParentId = null;
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

    document.getElementById('version-modal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeVersionModal();
    });
}

async function loadHistory() {
    const loading = document.getElementById('history-loading');
    const empty = document.getElementById('history-empty');
    const list = document.getElementById('history-list');
    …29354 tokens truncated…(opt);
            });
        }
    } catch (e) {
        // Silently fail - filters will just show default options
    }
}

function closeGalleryModal() {
    document.getElementById('gallery-modal').classList.add('hidden');
    document.getElementById('gallery-modal-image').src = '';
    _galleryModalTrigger?.focus();
    _galleryModalTrigger = null;
}

/* =====================================================================
   PNG Info Page
   ===================================================================== */
function setupPngInfoPage() {
    const uploadArea = document.getElementById('pnginfo-upload-area');
    const imageInput = document.getElementById('pnginfo-image-input');
    if (!uploadArea || !imageInput) return;

    uploadArea.addEventListener('click', () => imageInput.click());
    imageInput.addEventListener('change', e => handlePngInfoImageSelect(e.target.files[0]));
    uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
    uploadArea.addEventListener('drop', e => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) handlePngInfoImageSelect(e.dataTransfer.files[0]);
    });

    document.getElementById('pnginfo-clear-btn')?.addEventListener('click', clearPngInfo);
    document.getElementById('pnginfo-send-sd-btn')?.addEventListener('click', sendPngInfoToSD);
    document.getElementById('pnginfo-send-img2img-btn')?.addEventListener('click', sendPngInfoToImg2Img);
    document.getElementById('pnginfo-copy-prompt-btn')?.addEventListener('click', copyPngInfoPrompt);
}

function handlePngInfoImageSelect(file) {
    if (!file || !file.type.startsWith('image/')) {
        toast(I18n.t('toast.image_file_required') || '画像ファイルを選択してください', 'error');
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        toast(I18n.t('toast.file_too_large') || 'ファイルサイズが10MBを超えています', 'error');
        return;
    }
    pngInfoImage = file;
    const reader = new FileReader();
    reader.onload = e => {
        document.getElementById('pnginfo-preview-image').src = e.target.result;
        document.getElementById('pnginfo-preview-wrap').classList.remove('hidden');
        document.getElementById('pnginfo-upload-area').classList.add('hidden');
    };
    reader.readAsDataURL(file);
    analyzePngInfo(file);
}

function clearPngInfo() {
    pngInfoImage = null;
    pngInfoParameters = null;
    document.getElementById('pnginfo-image-input').value = '';
    document.getElementById('pnginfo-preview-wrap').classList.add('hidden');
    document.getElementById('pnginfo-upload-area').classList.remove('hidden');
    document.getElementById('pnginfo-result').classList.add('hidden');
    document.getElementById('pnginfo-empty').classList.add('hidden');
    document.getElementById('pnginfo-loading').classList.add('hidden');
}

async function analyzePngInfo(file) {
    const loading = document.getElementById('pnginfo-loading');
    const emptyBox = document.getElementById('pnginfo-empty');
    const resultBox = document.getElementById('pnginfo-result');

    loading.classList.remove('hidden');
    emptyBox.classList.add('hidden');
    resultBox.classList.add('hidden');
    pngInfoParameters = null;

    try {
        const fd = new FormData();
        fd.append('file', file);
        const r = await fetch('/api/png-info', { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail);
        const data = await r.json();

        if (!data.has_metadata) {
            emptyBox.classList.remove('hidden');
            return;
        }
        pngInfoParameters = data.parameters || {};
        renderPngInfoResult(pngInfoParameters);
        resultBox.classList.remove('hidden');
    } catch (e) {
        toast(e.message || I18n.t('toast.pnginfo_parse_failed') || 'PNG情報の解析に失敗しました', 'error');
    } finally {
        loading.classList.add('hidden');
    }
}

function renderPngInfoResult(p) {
    document.getElementById('pnginfo-positive').value = p.positive_prompt || '';

    const negCard = document.getElementById('pnginfo-negative-card');
    if (p.negative_prompt) {
        document.getElementById('pnginfo-negative').value = p.negative_prompt;
        negCard.classList.remove('hidden');
    } else {
        document.getElementById('pnginfo-negative').value = '';
        negCard.classList.add('hidden');
    }

    const rows = [
        [I18n.t('page.pnginfo.param_steps') || 'Steps', p.steps],
        [I18n.t('page.pnginfo.param_sampler') || 'Sampler', p.sampler],
        [I18n.t('page.pnginfo.param_cfg') || 'CFG Scale', p.cfg_scale],
        [I18n.t('page.pnginfo.param_seed') || 'Seed', p.seed],
        [I18n.t('page.pnginfo.param_size') || 'Size', (p.width && p.height) ? `${p.width}×${p.height}` : undefined],
        [I18n.t('page.pnginfo.param_model') || 'Model', p.model],
        [I18n.t('page.pnginfo.param_denoising') || 'Denoising strength', p.denoising_strength],
    ].filter(([, v]) => v !== undefined && v !== null && v !== '');

    if (p.extras && typeof p.extras === 'object') {
        for (const [key, val] of Object.entries(p.extras)) {
            if (val !== undefined && val !== null && val !== '') rows.push([key, val]);
        }
    }

    document.getElementById('pnginfo-params').innerHTML = rows.map(([label, value]) => `
        <div class="gallery-param-row">
            <span class="gallery-param-label">${escHtml(label)}</span>
            <span class="gallery-param-value">${escHtml(String(value))}</span>
        </div>
    `).join('');
    document.getElementById('pnginfo-params-panel').classList.toggle('hidden', rows.length === 0);

    document.getElementById('pnginfo-raw').textContent = p.raw || '';
}

// 対象 <select> に一致する <option> がある場合のみ値を設定する（無ければ変更しない）
function _pngInfoSetSelectIfExists(id, val) {
    const el = document.getElementById(id);
    if (!el || val === undefined || val === null || val === '') return;
    const match = Array.from(el.options).some(o => o.value === String(val));
    if (match) el.value = val;
}

function _pngInfoSetField(id, val) {
    if (val === undefined || val === null || val === '') return;
    const el = document.getElementById(id);
    if (!el) return;
    if (el.tagName === 'SELECT') {
        _pngInfoSetSelectIfExists(id, val);
    } else {
        el.value = val;
    }
}

function sendPngInfoToSD() {
    const p = pngInfoParameters;
    if (!p) return;
    _pngInfoSetField('sd-positive', p.positive_prompt);
    _pngInfoSetField('sd-negative', p.negative_prompt);
    _pngInfoSetField('sd-steps', p.steps);
    _pngInfoSetField('sd-cfg', p.cfg_scale);
    _pngInfoSetField('sd-seed', p.seed);
    _pngInfoSetField('sd-width', p.width);
    _pngInfoSetField('sd-height', p.height);
    _pngInfoSetSelectIfExists('sd-sampler', p.sampler);
    document.querySelector('[data-page="sd"]').click();
    checkSDStatus();
    toast(I18n.t('toast.pnginfo_sent_to_sd') || 'txt2imgにパラメータを送りました', 'success');
}

function sendPngInfoToImg2Img() {
    const p = pngInfoParameters;
    if (!p) return;
    _pngInfoSetField('i2i-positive', p.positive_prompt);
    _pngInfoSetField('i2i-negative', p.negative_prompt);
    _pngInfoSetField('i2i-steps', p.steps);
    _pngInfoSetField('i2i-cfg', p.cfg_scale);
    _pngInfoSetField('i2i-seed', p.seed);
    _pngInfoSetField('i2i-width', p.width);
    _pngInfoSetField('i2i-height', p.height);
    _pngInfoSetField('i2i-denoising', p.denoising_strength);
    _pngInfoSetSelectIfExists('i2i-sampler', p.sampler);
    document.querySelector('[data-page="img2img"]').click();
    checkImg2ImgStatus();
    toast(I18n.t('toast.pnginfo_sent_to_img2img') || 'img2imgにパラメータを送りました', 'success');
}

function copyPngInfoPrompt() {
    const p = pngInfoParameters;
    if (!p) return;
    const pos = p.positive_prompt || '';
    const neg = p.negative_prompt || '';
    const text = neg ? `Positive:\n${pos}\n\nNegative:\n${neg}` : pos;
    navigator.clipboard.writeText(text)
        .then(() => toast(I18n.t('toast.prompts_copied') || 'プロンプトをコピーしました', 'success'))
        .catch(() => toast(I18n.t('toast.copy_failed') || 'コピーに失敗しました', 'error'));
}

/* =====================================================================
   Stats Page
   ===================================================================== */
let _statsData = null;
let _statsTagKind = 'positive';

function setupStatsPage() {
    document.getElementById('refresh-stats-btn')?.addEventListener('click', () => { loadStats(); loadSystemStatus(); });
    document.getElementById('stats-top-n')?.addEventListener('change', loadStats);

    document.getElementById('stats-tag-toggle')?.addEventListener('click', e => {
        const btn = e.target.closest('button[data-tag-kind]');
        if (!btn) return;
        _statsTagKind = btn.dataset.tagKind;
        document.querySelectorAll('#stats-tag-toggle button').forEach(b => {
            const active = b.dataset.tagKind === _statsTagKind;
            b.classList.toggle('active', active);
            b.classList.toggle('btn-accent', active);
            b.classList.toggle('btn-secondary', !active);
        });
        renderStatsTags();
    });

    // タグバーをクリックすると History ページへ遷移し、そのタグで検索する
    document.getElementById('stats-tags-chart')?.addEventListener('click', e => {
        const row = e.target.closest('.stats-bar-row--clickable');
        if (!row) return;
        goToHistoryWithSearch(row.dataset.tag || '');
    });

    document.getElementById('clear-cache-btn')?.addEventListener('click', async () => {
        try {
            const r = await fetch('/api/cache', { method: 'DELETE' });
            if (!r.ok) throw new Error();
            const d = await r.json();
            toast(`キャッシュを${d.cleared}件削除しました`, 'success');
        } catch {
            toast('キャッシュのクリアに失敗しました', 'error');
        } finally {
            loadSystemStatus();
        }
    });

    loadSystemStatus();
}

async function loadSystemStatus() {
    try {
        const r = await fetch('/api/cache/stats');
        if (r.ok) {
            const d = await r.json();
            document.getElementById('cache-hit-rate').textContent = `${d.hit_rate_pct}%`;
            document.getElementById('cache-size').textContent = d.size;
            document.getElementById('cache-hits-misses').textContent = `${d.hits} / ${d.misses}`;
        }
    } catch { /* leave placeholders */ }

    try {
        const r = await fetch('/api/jobs/queue/stats');
        if (r.ok) {
            const d = await r.json();
            const s = d.stats || {};
            document.getElementById('queue-pending').textContent = s.queue_size ?? '--';
            document.getElementById('queue-running').textContent = s.running ?? '--';
            document.getElementById('queue-total').textContent = s.total ?? '--';
        }
    } catch { /* leave placeholders */ }
}

async function loadStats() {
    const loading = document.getElementById('stats-loading');
    const empty = document.getElementById('stats-empty');
    const content = document.getElementById('stats-content');
    loading.classList.remove('hidden');
    empty.classList.add('hidden');
    content.classList.add('hidden');

    const topN = parseInt(document.getElementById('stats-top-n')?.value, 10) || 20;

    try {
        const r = await fetch(`/api/stats?top_n=${topN}`);
        if (!r.ok) throw new Error();
        const d = await r.json();
        _statsData = d;

        if (!d.total_history && !d.total_generated_images) {
            empty.classList.remove('hidden');
            return;
        }

        renderStatsSummary(d);
        renderStatsTags();
        renderStatsBreakdown('stats-styles-chart', d.styles, 'common.style');
        renderStatsBreakdown('stats-tones-chart', d.tones, 'common.tone');
        renderStatsBreakdown('stats-quality-chart', d.quality_levels, 'common.quality');
        renderStatsCountList('stats-models-chart', d.models);
        renderStatsCountList('stats-samplers-chart', d.samplers);
        renderStatsDailyChart(d.activity.daily);
        renderStatsWeeklyChart(d.activity.weekly);

        content.classList.remove('hidden');
    } catch (e) {
        toast(I18n.t('toast.stats_load_failed') || '統計の読み込みに失敗しました', 'error');
    } finally {
        loading.classList.add('hidden');
    }
}

function renderStatsSummary(d) {
    document.getElementById('stats-total-history').textContent = d.total_history;
    document.getElementById('stats-total-images').textContent = d.total_generated_images;
    document.getElementById('stats-favorite-rate').textContent = `${d.favorite_rate}%`;
    document.getElementById('stats-avg-prompt-length').textContent = d.avg_prompt_length;
    document.getElementById('stats-avg-tag-count').textContent = d.avg_tag_count;
}

function _statsNoDataHtml() {
    return `<p class="stats-empty-hint">${escHtml(I18n.t('page.stats.no_data') || 'データがありません')}</p>`;
}

function _statsTranslateOrRaw(namespace, value) {
    if (!namespace) return value;
    const key = `${namespace}.${value}`;
    const translated = I18n.t(key);
    return translated && translated !== key ? translated : value;
}

function renderStatsTags() {
    if (!_statsData) return;
    const items = (_statsData.top_tags || {})[_statsTagKind] || [];
    const colorVar = _statsTagKind === 'positive' ? 'var(--success)' : 'var(--danger)';
    const container = document.getElementById('stats-tags-chart');
    if (!items.length) {
        container.innerHTML = _statsNoDataHtml();
        return;
    }
    const max = Math.max(...items.map(i => i.count));
    container.innerHTML = items.map(item => {
        const pct = max ? Math.round((item.count / max) * 100) : 0;
        return `
            <div class="stats-bar-row stats-bar-row--clickable" data-tag="${escHtml(item.tag)}" title="${escHtml(item.tag)}: ${item.count}">
                <span class="stats-bar-label">${escHtml(item.tag)}</span>
                <div class="stats-bar-track"><div class="stats-bar-fill" style="width:${pct}%;background:${colorVar};"></div></div>
                <span class="stats-bar-value">${item.count}</span>
            </div>`;
    }).join('');
}

function renderStatsBreakdown(containerId, breakdown, namespace) {
    const container = document.getElementById(containerId);
    const counts = breakdown?.counts || [];
    if (!counts.length) {
        container.innerHTML = _statsNoDataHtml();
        return;
    }
    const max = Math.max(...counts.map(c => c.count));
    container.innerHTML = counts.map(c => {
        const pct = max ? Math.round((c.count / max) * 100) : 0;
        const label = _statsTranslateOrRaw(namespace, c.value);
        return `
            <div class="stats-bar-row" title="${escHtml(label)}: ${c.count} (${c.percent}%)">
                <span class="stats-bar-label">${escHtml(label)}</span>
                <div class="stats-bar-track"><div class="stats-bar-fill" style="width:${pct}%;background:var(--accent);"></div></div>
                <span class="stats-bar-value">${c.count} (${c.percent}%)</span>
            </div>`;
    }).join('');
}

function renderStatsCountList(containerId, items) {
    const container = document.getElementById(containerId);
    if (!items?.length) {
        container.innerHTML = _statsNoDataHtml();
        return;
    }
    const max = Math.max(...items.map(i => i.count));
    container.innerHTML = items.map(item => {
        const pct = max ? Math.round((item.count / max) * 100) : 0;
        return `
            <div class="stats-bar-row" title="${escHtml(item.value)}: ${item.count}">
                <span class="stats-bar-label">${escHtml(item.value)}</span>
                <div class="stats-bar-track"><div class="stats-bar-fill" style="width:${pct}%;background:var(--accent);"></div></div>
                <span class="stats-bar-value">${item.count}</span>
            </div>`;
    }).join('');
}

function renderStatsDailyChart(daily) {
    const container = document.getElementById('stats-daily-chart');
    if (!daily?.length) {
        container.innerHTML = _statsNoDataHtml();
        return;
    }
    const max = Math.max(...daily.map(d => d.count), 1);
    container.innerHTML = daily.map((d, idx) => {
        const pct = Math.round((d.count / max) * 100);
        const showLabel = idx % 5 === 0 || idx === daily.length - 1;
        const shortDate = d.date.slice(5).replace('-', '/'); // MM/DD
        return `
            <div class="stats-daily-col" title="${d.date}: ${d.count}">
                <div class="stats-daily-track"><div class="stats-daily-fill" style="height:${pct}%;"></div></div>
                <span class="stats-daily-date">${showLabel ? shortDate : ''}</span>
            </div>`;
    }).join('');
}

function renderStatsWeeklyChart(weekly) {
    const container = document.getElementById('stats-weekly-chart');
    if (!weekly?.length) {
        container.innerHTML = _statsNoDataHtml();
        return;
    }
    const max = Math.max(...weekly.map(w => w.count));
    container.innerHTML = weekly.map(w => {
        const pct = max ? Math.round((w.count / max) * 100) : 0;
        return `
            <div class="stats-bar-row" title="${w.week_start}〜: ${w.count}">
                <span class="stats-bar-label">${escHtml(w.week_start)}〜</span>
                <div class="stats-bar-track"><div class="stats-bar-fill" style="width:${pct}%;background:var(--accent);"></div></div>
                <span class="stats-bar-value">${w.count}</span>
            </div>`;
    }).join('');
}

function goToHistoryWithSearch(tag) {
    const navBtn = document.querySelector('.nav-btn[data-page="history"]');
    if (navBtn) navBtn.click();
    const input = document.getElementById('history-search');
    if (input) input.value = tag;
    loadHistory();
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

// ------------------------------------------------------------------ //
// Wildcards Page (#82)
// ------------------------------------------------------------------ //

let _wcEditingName = null;

function setupWildcardsPage() {
    document.getElementById('wc-create-btn')?.addEventListener('click', wcStartCreate);
    document.getElementById('wc-save-btn')?.addEventListener('click', wcSave);
    document.getElementById('wc-delete-btn')?.addEventListener('click', wcDelete);
    document.getElementById('wc-preview-btn')?.addEventListener('click', wcPreview);
    document.getElementById('wc-count-btn')?.addEventListener('click', wcCount);
    document.getElementById('sd-expand-btn')?.addEventListener('click', sdExpandPrompt);
    loadWildcards();
}

async function loadWildcards() {
    const list = document.getElementById('wc-list');
    if (!list) return;
    try {
        const r = await fetch('/api/wildcards/');
        if (!r.ok) return;
        const data = await r.json();
        if (!data.wildcards || data.wildcards.length === 0) {
            list.innerHTML = '<div class="wc-empty">No wildcard files yet. Click "+ New" to create one.</div>';
            return;
        }
        list.innerHTML = data.wildcards.map(w =>
            `<div class="wc-item" data-name="${escHtml(w.name)}">
                <strong>__${escHtml(w.name)}__</strong>
                <span class="wc-count">${w.count} entries</span>
                <div class="wc-preview-tags">${escHtml(w.preview.slice(0, 3).join(', '))}${w.count > 3 ? '...' : ''}</div>
            </div>`
        ).join('');
        list.querySelectorAll('.wc-item').forEach(el => {
            el.addEventListener('click', () => wcLoadEdit(el.dataset.name));
        });
    } catch (e) {
        console.error('Failed to load wildcards:', e);
    }
}

function wcStartCreate() {
    _wcEditingName = null;
    const editor = document.getElementById('wc-editor');
    editor.style.display = '';
    document.getElementById('wc-editor-title').textContent = 'New Wildcard';
    document.getElementById('wc-name-input').value = '';
    document.getElementById('wc-name-input').disabled = false;
    document.getElementById('wc-entries-input').value = '';
    document.getElementById('wc-delete-btn').style.display = 'none';
}

async function wcLoadEdit(name) {
    try {
        const r = await fetch(`/api/wildcards/${name}`);
        if (!r.ok) return;
        const data = await r.json();
        _wcEditingName = name;
        const editor = document.getElementById('wc-editor');
        editor.style.display = '';
        document.getElementById('wc-editor-title').textContent = `Edit: __${name}__`;
        document.getElementById('wc-name-input').value = name;
        document.getElementById('wc-name-input').disabled = true;
        document.getElementById('wc-entries-input').value = data.entries.join('\n');
        document.getElementById('wc-delete-btn').style.display = '';
    } catch (e) {
        console.error('Failed to load wildcard:', e);
    }
}

async function wcSave() {
    const name = document.getElementById('wc-name-input').value.trim();
    const entriesRaw = document.getElementById('wc-entries-input').value;
    const entries = entriesRaw.split('\n').map(s => s.trim()).filter(Boolean);
    if (!name || entries.length === 0) return;
    const isNew = !_wcEditingName;
    const url = isNew ? '/api/wildcards/' : `/api/wildcards/${_wcEditingName}`;
    const method = isNew ? 'POST' : 'PUT';
    const body = isNew ? { name, entries } : { entries };
    try {
        const r = await fetch(url, {
            method, headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (r.ok) {
            _wcEditingName = name;
            document.getElementById('wc-name-input').disabled = true;
            document.getElementById('wc-delete-btn').style.display = '';
            document.getElementById('wc-editor-title').textContent = `Edit: __${name}__`;
            loadWildcards();
        } else {
            const d = await r.json().catch(() => ({}));
            alert(d.detail || 'Save failed');
        }
    } catch (e) { alert('Network error'); }
}

async function wcDelete() {
    if (!_wcEditingName) return;
    if (!confirm(`Delete wildcard "__${_wcEditingName}__"?`)) return;
    try {
        await fetch(`/api/wildcards/${_wcEditingName}`, { method: 'DELETE' });
        _wcEditingName = null;
        document.getElementById('wc-editor').style.display = 'none';
        loadWildcards();
    } catch (e) { console.error(e); }
}

async function wcPreview() {
    const template = document.getElementById('wc-expand-template')?.value?.trim();
    if (!template) return;
    const results = document.getElementById('wc-expand-results');
    try {
        const r = await fetch('/api/wildcards/expand', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ template, mode: 'preview', count: 5 })
        });
        const data = await r.json();
        if (r.ok) {
            results.innerHTML = `<div class="wc-combo-count">${data.combination_count} total combinations</div>`
                + data.expanded.map((s, i) => `<div class="wc-result-item">${i+1}. ${escHtml(s)}</div>`).join('');
        } else {
            results.innerHTML = `<div class="wc-error">${escHtml(errDetail(data, 'Error'))}</div>`;
        }
    } catch { results.innerHTML = '<div class="wc-error">Network error</div>'; }
}

async function wcCount() {
    const template = document.getElementById('wc-expand-template')?.value?.trim();
    if (!template) return;
    const results = document.getElementById('wc-expand-results');
    try {
        const r = await fetch('/api/wildcards/expand', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ template, mode: 'preview', count: 1 })
        });
        const data = await r.json();
        if (r.ok) {
            results.innerHTML = `<div class="wc-combo-count">${data.combination_count} total combinations</div>`;
        }
    } catch {}
}

async function sdExpandPrompt() {
    const textarea = document.getElementById('sd-positive');
    if (!textarea) return;
    const template = textarea.value.trim();
    if (!template || (!template.includes('{') && !template.includes('__'))) return;
    try {
        const r = await fetch('/api/wildcards/expand', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ template, mode: 'random' })
        });
        const data = await r.json();
        if (r.ok && data.expanded && data.expanded.length > 0) {
            textarea.value = data.expanded[0];
            textarea.dispatchEvent(new Event('input'));
        }
    } catch (e) { console.error('Expand failed:', e); }
}

/* =====================================================================
   Compare Page (Prompt A/B Comparison - issue #77)
   ===================================================================== */
const COMPARE_STYLE_OPTIONS = [
    ['', '-- なし --'], ['photorealistic', 'Photorealistic'], ['anime', 'Anime'],
    ['painting', 'Painting'], ['watercolor', 'Watercolor'], ['concept_art', 'Concept Art'],
    ['sketch', 'Sketch'], ['pixel_art', 'Pixel Art'], ['3d_render', '3D Render']
];
const COMPARE_TONE_OPTIONS = [
    ['', '-- なし --'], ['natural', 'Natural'], ['vibrant', 'Vibrant'], ['warm', 'Warm'],
    ['cool', 'Cool'], ['dark', 'Dark'], ['soft', 'Soft'], ['dramatic', 'Dramatic'], ['cinematic', 'Cinematic']
];
const COMPARE_QUALITY_OPTIONS = [['standard', 'Standard'], ['high', 'High'], ['ultra', 'Ultra']];

let compareSelectedImage = null;
let _compareVariantSeq = 0;
let _abHistoryLoaded = false;

async function checkCompareStatus() {
    const badge = document.getElementById('compare-api-badge');
    if (badge) { badge.className = 'badge badge-gray'; badge.textContent = 'Checking...'; }
    try {
        const r = await fetch('/api/sd/status');
        const d = await r.json();
        if (d.available) {
            if (badge) { badge.className = 'badge badge-green'; badge.textContent = 'Connected'; }
            if (d.samplers?.length) {
                const sel = document.getElementById('ab-sampler');
                if (sel) sel.innerHTML = d.samplers.map(s => `<option>${s}</option>`).join('');
            }
        } else if (badge) {
            badge.className = 'badge badge-red'; badge.textContent = 'Disconnected';
        }
    } catch {
        if (badge) { badge.className = 'badge badge-red'; badge.textContent = 'Error'; }
    }
}

function _compareBuildSelect(id, options, selectedValue) {
    const sel = document.createElement('select');
    sel.id = id;
    options.forEach(([value, label]) => {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        if (value === selectedValue) opt.selected = true;
        sel.appendChild(opt);
    });
    return sel;
}

function setupComparePage() {
    // Image upload
    const uploadArea = document.getElementById('compare-upload-area');
    const imageInput = document.getElementById('compare-image-input');
    uploadArea?.addEventListener('click', () => imageInput.click());
    imageInput?.addEventListener('change', e => handleCompareImageSelect(e.target.files[0]));
    uploadArea?.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
    uploadArea?.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
    uploadArea?.addEventListener('drop', e => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) handleCompareImageSelect(file);
    });
    document.getElementById('compare-clear-image-btn')?.addEventListener('click', clearCompareImage);

    // Variants
    document.getElementById('compare-add-variant-btn')?.addEventListener('click', () => addCompareVariant());
    addCompareVariant();
    addCompareVariant();

    document.getElementById('compare-generate-btn')?.addEventListener('click', runPromptCompare);

    // A/B test
    document.getElementById('ab-generate-btn')?.addEventListener('click', runABGenerate);
    document.getElementById('ab-history-toggle-btn')?.addEventListener('click', toggleABHistory);

    checkCompareStatus();
    updateCompareVariantButtons();
}

function handleCompareImageSelect(file) {
    if (!file || !file.type.startsWith('image/')) { toast('画像ファイルを選択してください', 'error'); return; }
    if (file.size > 10 * 1024 * 1024) { toast('ファイルサイズが10MBを超えています', 'error'); return; }
    compareSelectedImage = file;
    const reader = new FileReader();
    reader.onload = e => {
        document.getElementById('compare-preview-image').src = e.target.result;
        document.getElementById('compare-preview-wrap').classList.remove('hidden');
        document.getElementById('compare-upload-area').classList.add('hidden');
    };
    reader.readAsDataURL(file);
}

function clearCompareImage() {
    compareSelectedImage = null;
    const input = document.getElementById('compare-image-input');
    if (input) input.value = '';
    document.getElementById('compare-preview-wrap')?.classList.add('hidden');
    document.getElementById('compare-upload-area')?.classList.remove('hidden');
}

function addCompareVariant() {
    const list = document.getElementById('compare-variants-list');
    if (!list) return;
    const count = list.querySelectorAll('.compare-variant-row').length;
    if (count >= 4) { toast(I18n.t('page.compare.max_variants', 'バリエーションは最大4個までです'), 'error'); return; }

    const seq = ++_compareVariantSeq;
    const row = document.createElement('div');
    row.className = 'compare-variant-row';
    row.dataset.seq = String(seq);

    const header = document.createElement('div');
    header.className = 'compare-variant-row-header';
    const title = document.createElement('span');
    title.textContent = `# ${count + 1}`;
    header.appendChild(title);
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn btn-sm btn-ghost compare-variant-remove-btn';
    removeBtn.textContent = '✕';
    removeBtn.addEventListener('click', () => removeCompareVariant(seq));
    header.appendChild(removeBtn);
    row.appendChild(header);

    const grid = document.createElement('div');
    grid.className = 'form-grid';

    const styleGroup = document.createElement('div');
    styleGroup.className = 'form-group';
    const styleLabel = document.createElement('label');
    styleLabel.textContent = I18n.t('page.compare.style_label', 'スタイル');
    styleGroup.appendChild(styleLabel);
    styleGroup.appendChild(_compareBuildSelect(`compare-variant-${seq}-style`, COMPARE_STYLE_OPTIONS, ''));
    grid.appendChild(styleGroup);

    const toneGroup = document.createElement('div');
    toneGroup.className = 'form-group';
    const toneLabel = document.createElement('label');
    toneLabel.textContent = I18n.t('page.compare.tone_label', 'トーン');
    toneGroup.appendChild(toneLabel);
    toneGroup.appendChild(_compareBuildSelect(`compare-variant-${seq}-tone`, COMPARE_TONE_OPTIONS, ''));
    grid.appendChild(toneGroup);

    const qualityGroup = document.createElement('div');
    qualityGroup.className = 'form-group';
    const qualityLabel = document.createElement('label');
    qualityLabel.textContent = I18n.t('page.compare.quality_label', '品質');
    qualityGroup.appendChild(qualityLabel);
    qualityGroup.appendChild(_compareBuildSelect(`compare-variant-${seq}-quality`, COMPARE_QUALITY_OPTIONS, 'high'));
    grid.appendChild(qualityGroup);

    row.appendChild(grid);
    list.appendChild(row);
    updateCompareVariantButtons();
}

function removeCompareVariant(seq) {
    const list = document.getElementById('compare-variants-list');
    if (!list) return;
    if (list.querySelectorAll('.compare-variant-row').length <= 2) {
        toast(I18n.t('page.compare.min_variants', 'バリエーションは最低2個必要です'), 'error');
        return;
    }
    const row = list.querySelector(`.compare-variant-row[data-seq="${seq}"]`);
    row?.remove();
    list.querySelectorAll('.compare-variant-row').forEach((r, i) => {
        const t = r.querySelector('.compare-variant-row-header span');
        if (t) t.textContent = `# ${i + 1}`;
    });
    updateCompareVariantButtons();
}

function updateCompareVariantButtons() {
    const list = document.getElementById('compare-variants-list');
    const count = list ? list.querySelectorAll('.compare-variant-row').length : 0;
    const addBtn = document.getElementById('compare-add-variant-btn');
    if (addBtn) addBtn.disabled = count >= 4;
    document.querySelectorAll('.compare-variant-remove-btn').forEach(btn => {
        btn.disabled = count <= 2;
    });
}

function _collectCompareVariants() {
    const rows = document.querySelectorAll('#compare-variants-list .compare-variant-row');
    const variants = [];
    rows.forEach(row => {
        const seq = row.dataset.seq;
        const style = document.getElementById(`compare-variant-${seq}-style`)?.value || '';
        const tone = document.getElementById(`compare-variant-${seq}-tone`)?.value || '';
        const quality = document.getElementById(`compare-variant-${seq}-quality`)?.value || 'high';
        variants.push({ style, tone, quality });
    });
    return variants;
}

async function runPromptCompare() {
    if (!compareSelectedImage) { toast(I18n.t('page.compare.no_image', '画像を選択してください'), 'error'); return; }
    const variants = _collectCompareVariants();
    if (variants.length < 2) { toast(I18n.t('page.compare.min_variants', 'バリエーションは最低2個必要です'), 'error'); return; }

    const btn = document.getElementById('compare-generate-btn');
    const loading = document.getElementById('compare-loading');
    const errorEl = document.getElementById('compare-error');
    const resultsEl = document.getElementById('compare-results');
    btn.disabled = true;
    loading.classList.remove('hidden');
    errorEl.classList.add('hidden');
    resultsEl.classList.add('hidden');
    while (resultsEl.firstChild) resultsEl.removeChild(resultsEl.firstChild);

    try {
        const fd = new FormData();
        fd.append('file', compareSelectedImage);
        fd.append('variants', JSON.stringify(variants));
        fd.append('save_history', 'true');
        const r = await fetch('/api/generate-prompts-compare', { method: 'POST', body: fd });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || data.message || I18n.t('page.compare.generate_failed', '比較生成に失敗しました'));
        renderCompareResults(data.results || [], variants);
        toast(I18n.t('page.compare.generate_success', '比較生成が完了しました'), 'success');
    } catch (e) {
        errorEl.textContent = e.message || I18n.t('page.compare.generate_failed', '比較生成に失敗しました');
        errorEl.classList.remove('hidden');
        toast(e.message || I18n.t('page.compare.generate_failed', '比較生成に失敗しました'), 'error');
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
}

function renderCompareResults(results, variants) {
    const resultsEl = document.getElementById('compare-results');
    while (resultsEl.firstChild) resultsEl.removeChild(resultsEl.firstChild);

    results.forEach((res, i) => {
        const variant = variants[i] || {};
        const card = document.createElement('div');
        card.className = 'compare-result-card' + (res.success ? '' : ' compare-result-card-error');

        const header = document.createElement('div');
        header.className = 'compare-result-card-header';
        const labelParts = [variant.style, variant.tone, variant.quality].filter(Boolean);
        header.textContent = `#${i + 1} ${labelParts.join(' / ') || I18n.t('page.compare.no_settings', '(設定なし)')}`;
        card.appendChild(header);

        if (res.success) {
            const posLabel = document.createElement('div');
            posLabel.className = 'label';
            posLabel.textContent = I18n.t('page.compare.positive_label', 'Positive Prompt');
            card.appendChild(posLabel);
            const posTa = document.createElement('textarea');
            posTa.className = 'prompt-ta';
            posTa.rows = 4;
            posTa.readOnly = true;
            posTa.id = `compare-result-pos-${i}`;
            posTa.value = res.positive || '';
            card.appendChild(posTa);

            const negLabel = document.createElement('div');
            negLabel.className = 'label';
            negLabel.textContent = I18n.t('page.compare.negative_label', 'Negative Prompt');
            card.appendChild(negLabel);
            const negTa = document.createElement('textarea');
            negTa.className = 'prompt-ta';
            negTa.rows = 3;
            negTa.readOnly = true;
            negTa.id = `compare-result-neg-${i}`;
            negTa.value = res.negative || '';
            card.appendChild(negTa);

            const actions = document.createElement('div');
            actions.className = 'compare-result-actions';
            const copyBtn = document.createElement('button');
            copyBtn.type = 'button';
            copyBtn.className = 'btn btn-sm btn-secondary';
            copyBtn.textContent = I18n.t('page.compare.copy_btn', '📋 コピー');
            copyBtn.addEventListener('click', () => {
                const text = `Positive:\n${res.positive || ''}\n\nNegative:\n${res.negative || ''}`;
                navigator.clipboard.writeText(text)
                    .then(() => toast(I18n.t('toast.copied', 'コピーしました'), 'success'))
                    .catch(() => toast(I18n.t('toast.copy_failed', 'コピーに失敗しました'), 'error'));
            });
            actions.appendChild(copyBtn);

            const sendBtn = document.createElement('button');
            sendBtn.type = 'button';
            sendBtn.className = 'btn btn-sm btn-accent';
            sendBtn.textContent = I18n.t('page.compare.send_to_sd_btn', 'この設定でSD生成へ');
            sendBtn.addEventListener('click', () => sendCompareResultToSD(res));
            actions.appendChild(sendBtn);

            card.appendChild(actions);
        } else {
            const errDiv = document.createElement('div');
            errDiv.className = 'compare-result-error';
            errDiv.textContent = res.error || I18n.t('page.compare.status_failed', '失敗');
            card.appendChild(errDiv);
        }

        resultsEl.appendChild(card);
    });

    resultsEl.classList.remove('hidden');
}

function sendCompareResultToSD(res) {
    document.getElementById('sd-positive').value = res.positive || '';
    document.getElementById('sd-negative').value = res.negative || '';
    document.querySelector('[data-page="sd"]').click();
    checkSDStatus();
    toast(I18n.t('page.compare.sent_to_sd', 'SDページに送りました'), 'info');
}

/* ---- A/B Test ---- */
async function runABGenerate() {
    const btn = document.getElementById('ab-generate-btn');
    const loading = document.getElementById('ab-loading');
    const errorEl = document.getElementById('ab-error');
    const resultsEl = document.getElementById('ab-results');

    const positiveA = document.getElementById('ab-a-positive').value.trim();
    const positiveB = document.getElementById('ab-b-positive').value.trim();
    if (!positiveA || !positiveB) {
        toast(I18n.t('page.compare.ab_no_prompt', 'A・B両方のPositive Promptを入力してください'), 'error');
        return;
    }

    const steps = parseInt(document.getElementById('ab-steps').value) || 20;
    const cfg_scale = parseFloat(document.getElementById('ab-cfg').value) || 7;
    const sampler = document.getElementById('ab-sampler').value;
    const width = parseInt(document.getElementById('ab-width').value) || 512;
    const height = parseInt(document.getElementById('ab-height').value) || 512;
    const seed = parseInt(document.getElementById('ab-seed').value);

    const payload = {
        config_a: { positive: positiveA, negative: document.getElementById('ab-a-negative').value.trim(), steps, cfg_scale, sampler, width, height },
        config_b: { positive: positiveB, negative: document.getElementById('ab-b-negative').value.trim(), steps, cfg_scale, sampler, width, height },
        seed: Number.isFinite(seed) ? seed : -1
    };

    btn.disabled = true;
    loading.classList.remove('hidden');
    errorEl.classList.add('hidden');
    resultsEl.classList.add('hidden');
    while (resultsEl.firstChild) resultsEl.removeChild(resultsEl.firstChild);

    try {
        const r = await fetch('/api/compare/ab-generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || data.message || I18n.t('page.compare.ab_generate_failed', 'A/B生成に失敗しました'));
        renderABResult(data);
        toast(I18n.t('page.compare.ab_generate_success', 'A/B生成が完了しました'), 'success');
        _abHistoryLoaded = false;
    } catch (e) {
        errorEl.textContent = e.message || I18n.t('page.compare.ab_generate_failed', 'A/B生成に失敗しました');
        errorEl.classList.remove('hidden');
        toast(e.message || I18n.t('page.compare.ab_generate_failed', 'A/B生成に失敗しました'), 'error');
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
}

function _buildABColumn(label, images, comparisonId, winnerKey, currentWinner) {
    const col = document.createElement('div');
    col.className = 'ab-result-col';

    const h = document.createElement('h4');
    h.textContent = label;
    if (currentWinner === winnerKey) {
        const badge = document.createElement('span');
        badge.className = 'ab-winner-badge';
        badge.textContent = I18n.t('page.compare.ab_winner_badge', '🏆 採用');
        h.appendChild(badge);
    }
    col.appendChild(h);

    (images || []).forEach(b64 => {
        const img = document.createElement('img');
        img.src = `data:image/png;base64,${b64}`;
        img.className = 'ab-result-image';
        col.appendChild(img);
    });

    const voteBtn = document.createElement('button');
    voteBtn.type = 'button';
    voteBtn.className = 'btn btn-sm btn-primary ab-vote-btn';
    voteBtn.textContent = I18n.t('page.compare.ab_vote_btn', 'こちらを採用');
    voteBtn.dataset.comparisonId = comparisonId;
    voteBtn.dataset.winner = winnerKey;
    if (currentWinner) voteBtn.disabled = true;
    voteBtn.addEventListener('click', () => voteAB(comparisonId, winnerKey, col.parentElement));
    col.appendChild(voteBtn);

    return col;
}

function renderABResult(data) {
    const resultsEl = document.getElementById('ab-results');
    while (resultsEl.firstChild) resultsEl.removeChild(resultsEl.firstChild);

    const seedInfo = document.createElement('div');
    seedInfo.className = 'ab-seed-info';
    seedInfo.textContent = `${I18n.t('page.compare.ab_used_seed', '使用シード')}: ${data.seed}`;
    resultsEl.appendChild(seedInfo);

    const wrap = document.createElement('div');
    wrap.className = 'ab-result-cols';
    wrap.appendChild(_buildABColumn('A', data.a?.images, data.comparison_id, 'a', null));
    wrap.appendChild(_buildABColumn('B', data.b?.images, data.comparison_id, 'b', null));
    resultsEl.appendChild(wrap);

    resultsEl.classList.remove('hidden');
}

async function voteAB(comparisonId, winner, wrapEl) {
    try {
        const r = await fetch(`/api/compare/ab/${comparisonId}/vote`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ winner })
        });
        if (!r.ok) {
            const d = await r.json().catch(() => ({}));
            throw new Error(d.detail || d.message || I18n.t('page.compare.ab_vote_failed', '投票に失敗しました'));
        }
        wrapEl?.querySelectorAll('.ab-vote-btn').forEach(btn => { btn.disabled = true; });
        const winnerCol = wrapEl?.querySelector(`.ab-vote-btn[data-winner="${winner}"]`)?.closest('.ab-result-col');
        if (winnerCol) {
            const h = winnerCol.querySelector('h4');
            if (h && !h.querySelector('.ab-winner-badge')) {
                const badge = document.createElement('span');
                badge.className = 'ab-winner-badge';
                badge.textContent = I18n.t('page.compare.ab_winner_badge', '🏆 採用');
                h.appendChild(badge);
            }
        }
        toast(I18n.t('page.compare.ab_voted', '投票しました'), 'success');
        _abHistoryLoaded = false;
    } catch (e) {
        toast(e.message || I18n.t('page.compare.ab_vote_failed', '投票に失敗しました'), 'error');
    }
}

async function toggleABHistory() {
    const list = document.getElementById('ab-history-list');
    if (!list) return;
    const nowHidden = list.classList.toggle('hidden');
    if (!nowHidden && !_abHistoryLoaded) {
        await loadABHistory();
    }
}

function _truncate(text, max) {
    if (!text) return '';
    return text.length > max ? text.slice(0, max) + '…' : text;
}

async function loadABHistory() {
    const list = document.getElementById('ab-history-list');
    if (!list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    try {
        const r = await fetch('/api/compare/ab-history');
        const data = await r.json();
        const items = data.comparisons || [];
        if (!items.length) {
            const empty = document.createElement('p');
            empty.className = 'ab-history-empty';
            empty.textContent = I18n.t('page.compare.ab_history_empty', 'A/B履歴がありません');
            list.appendChild(empty);
        } else {
            items.forEach(item => {
                const row = document.createElement('div');
                row.className = 'ab-history-item';

                const meta = document.createElement('div');
                meta.className = 'ab-history-item-meta';
                const created = item.created_at ? new Date(item.created_at).toLocaleString('ja-JP') : '';
                meta.textContent = created;
                if (item.winner) {
                    const badge = document.createElement('span');
                    badge.className = 'ab-winner-badge';
                    badge.textContent = `🏆 ${item.winner.toUpperCase()}`;
                    meta.appendChild(badge);
                }
                row.appendChild(meta);

                const promptA = document.createElement('div');
                promptA.className = 'ab-history-item-prompt';
                promptA.textContent = `A: ${_truncate(item.config_a?.positive || item.positive_a || '', 80)}`;
                row.appendChild(promptA);

                const promptB = document.createElement('div');
                promptB.className = 'ab-history-item-prompt';
                promptB.textContent = `B: ${_truncate(item.config_b?.positive || item.positive_b || '', 80)}`;
                row.appendChild(promptB);

                list.appendChild(row);
            });
        }
        _abHistoryLoaded = true;
    } catch {
        const err = document.createElement('p');
        err.className = 'ab-history-empty';
        err.textContent = I18n.t('page.compare.ab_history_load_failed', 'A/B履歴の読み込みに失敗しました');
        list.appendChild(err);
    }
}

/* =====================================================================
   Backup Page (Data backup / restore - issue #97)
   ===================================================================== */
let _backupsCache = [];

function setupBackupPage() {
    document.getElementById('backup-create-btn')?.addEventListener('click', createBackup);
    document.getElementById('refresh-backups-btn')?.addEventListener('click', loadBackups);
    document.getElementById('backup-restore-notice-dismiss')?.addEventListener('click', () => {
        document.getElementById('backup-restore-notice').classList.add('hidden');
    });

    const confirmCb = document.getElementById('backup-restore-confirm-checkbox');
    const fileInput = document.getElementById('backup-restore-file-input');
    const uploadBtn = document.getElementById('backup-restore-upload-btn');
    const updateUploadBtnState = () => {
        uploadBtn.disabled = !(confirmCb?.checked && fileInput?.files?.length);
    };
    confirmCb?.addEventListener('change', updateUploadBtnState);
    fileInput?.addEventListener('change', updateUploadBtnState);
    uploadBtn?.addEventListener('click', restoreFromUpload);
}

function _formatBackupSize(bytes) {
    if (bytes === null || bytes === undefined) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

async function loadBackups() {
    const loading = document.getElementById('backup-loading');
    const empty = document.getElementById('backup-empty');
    const list = document.getElementById('backup-list');
    if (!list) return;
    loading.classList.remove('hidden');
    empty.classList.add('hidden');
    list.innerHTML = '';

    try {
        const r = await fetch('/api/backup/list');
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        _backupsCache = d.backups || [];

        if (!_backupsCache.length) {
            empty.classList.remove('hidden');
            return;
        }

        list.innerHTML = _backupsCache.map(b => {
            const created = b.created_at ? new Date(b.created_at).toLocaleString() : '';
            const invalid = b.valid === false;
            const badges = `
                ${b.include_outputs ? `<span class="badge badge-green">${escHtml(I18n.t('page.backup.badge_outputs_included', 'Outputs included'))}</span>` : ''}
                ${invalid ? `<span class="badge badge-red">${escHtml(I18n.t('page.backup.badge_invalid', 'Invalid'))}</span>` : ''}
            `;
            // onclick="fn('${b.id}')" は escHtml() が単引用符をエスケープしないため
            // JS文字列リテラルをエスケープできる。id/filename は data-* 属性へ渡し、
            // 挿入後に addEventListener でバインドする。
            const actions = invalid
                ? `<button class="btn btn-sm btn-ghost" data-backup-action="delete" data-backup-id="${escHtml(b.id)}">🗑️ ${escHtml(I18n.t('common.delete', 'Delete'))}</button>`
                : `
                    <button class="btn btn-sm btn-secondary" data-backup-action="download" data-backup-id="${escHtml(b.id)}" data-backup-filename="${escHtml(b.filename)}" title="${escHtml(I18n.t('page.backup.download_btn', 'Download'))}">⬇</button>
                    <button class="btn btn-sm btn-secondary" data-backup-action="restore" data-backup-id="${escHtml(b.id)}" title="${escHtml(I18n.t('page.backup.restore_btn', 'Restore'))}">♻️</button>
                    <button class="btn btn-sm btn-ghost" data-backup-action="delete" data-backup-id="${escHtml(b.id)}" title="${escHtml(I18n.t('common.delete', 'Delete'))}">🗑️</button>
                `;
            return `
                <div class="history-item ${invalid ? 'backup-item-invalid' : ''}" data-id="${escHtml(b.id)}">
                    <div class="history-item-header">
                        <div class="history-item-meta">
                            <span class="image-name">${escHtml(b.filename)}</span><br>
                            <span>${escHtml(created)}</span> ·
                            <span>${escHtml(_formatBackupSize(b.size))}</span> ·
                            <span>${b.file_count ?? 0} ${escHtml(I18n.t('page.backup.file_count_unit', 'files'))}</span>
                            ${badges}
                        </div>
                        <div class="history-item-actions">
                            ${actions}
                        </div>
                    </div>
                </div>`;
        }).join('');

        list.querySelectorAll('[data-backup-action]').forEach(el => {
            const id = el.dataset.backupId;
            const action = el.dataset.backupAction;
            if (action === 'delete') {
                el.addEventListener('click', () => deleteBackup(id));
            } else if (action === 'download') {
                el.addEventListener('click', () => downloadBackup(id, el.dataset.backupFilename));
            } else if (action === 'restore') {
                el.addEventListener('click', () => restoreBackupById(id));
            }
        });
    } catch (e) {
        toast(e.message || I18n.t('toast.backup_list_failed', 'バックアップ一覧の読み込みに失敗しました'), 'error');
    } finally {
        loading.classList.add('hidden');
    }
}

async function createBackup() {
    const btn = document.getElementById('backup-create-btn');
    if (!btn || btn.disabled) return;
    const includeOutputs = document.getElementById('backup-include-outputs')?.checked || false;

    btn.disabled = true;
    const origText = btn.textContent;
    btn.textContent = I18n.t('page.backup.creating', '作成中...');

    try {
        const r = await fetch('/api/backup/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ include_outputs: includeOutputs })
        });
        if (!r.ok) throw new Error((await r.json()).detail);
        toast(I18n.t('toast.backup_create_success', 'バックアップを作成しました'), 'success');
        loadBackups();
    } catch (e) {
        toast(e.message || I18n.t('toast.backup_create_failed', 'バックアップの作成に失敗しました'), 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = origText;
    }
}

function downloadBackup(id, filename) {
    const a = document.createElement('a');
    a.href = `/api/backup/download/${id}`;
    a.download = filename || `backup_${id}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

async function deleteBackup(id) {
    if (!confirm(I18n.t('page.backup.confirm_delete', 'このバックアップを削除しますか？'))) return;
    try {
        const r = await fetch(`/api/backup/${id}`, { method: 'DELETE' });
        if (!r.ok) throw new Error((await r.json()).detail);
        toast(I18n.t('toast.deleted', 'Deleted'), 'success');
        loadBackups();
    } catch (e) {
        toast(e.message || I18n.t('toast.delete_failed', 'Failed to delete'), 'error');
    }
}

async function restoreBackupById(id) {
    if (!confirm(I18n.t('page.backup.confirm_restore', '既存のデータが上書きされます。復元を続行しますか？（復元前に安全バックアップを作成します）'))) return;
    // サーバー上に既にあるバックアップはサーバー側で復元する
    // （ZIPをブラウザ経由でダウンロード＋再アップロードしない）
    try {
        const r = await fetch(`/api/backup/restore/${encodeURIComponent(id)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: true, create_safety_backup: true })
        });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail);
        const d = await r.json();
        toast(I18n.t('toast.backup_restore_success', '復元が完了しました'), 'success');
        showRestoreNotice(d);
        loadBackups();
    } catch (e) {
        toast(e.message || I18n.t('toast.backup_restore_failed', '復元に失敗しました'), 'error');
    }
}

async function restoreFromUpload() {
    const fileInput = document.getElementById('backup-restore-file-input');
    const confirmCb = document.getElementById('backup-restore-confirm-checkbox');
    const safetyCb = document.getElementById('backup-restore-safety-checkbox');
    const file = fileInput?.files?.[0];
    if (!file) { toast(I18n.t('toast.backup_file_required', 'バックアップZIPファイルを選択してください'), 'error'); return; }
    if (!confirmCb?.checked) { toast(I18n.t('toast.backup_confirm_required', '上書き確認のチェックが必要です'), 'error'); return; }
    if (!confirm(I18n.t('page.backup.confirm_restore', '既存のデータが上書きされます。復元を続行しますか？（復元前に安全バックアップを作成します）'))) return;

    const btn = document.getElementById('backup-restore-upload-btn');
    if (btn) btn.disabled = true;
    try {
        await performRestore(file, file.name, safetyCb?.checked ?? true);
        fileInput.value = '';
        confirmCb.checked = false;
    } finally {
        if (btn) btn.disabled = !(confirmCb?.checked && fileInput?.files?.length);
    }
}

async function performRestore(fileBlob, filename, createSafetyBackup) {
    const fd = new FormData();
    fd.append('file', fileBlob, filename);
    fd.append('confirm', 'true');
    fd.append('create_safety_backup', createSafetyBackup ? 'true' : 'false');

    try {
        const r = await fetch('/api/backup/restore', { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail);
        const d = await r.json();
        toast(I18n.t('toast.backup_restore_success', '復元が完了しました'), 'success');
        showRestoreNotice(d);
        loadBackups();
    } catch (e) {
        toast(e.message || I18n.t('toast.backup_restore_failed', '復元に失敗しました'), 'error');
    }
}

function showRestoreNotice(result) {
    const notice = document.getElementById('backup-restore-notice');
    const safetyLine = document.getElementById('backup-restore-safety-line');
    if (!notice) return;
    if (safetyLine) {
        if (result && result.safety_backup_id) {
            safetyLine.textContent = `${I18n.t('page.backup.safety_backup_id_label', 'Safety backup ID')}: ${result.safety_backup_id}`;
            safetyLine.classList.remove('hidden');
        } else {
            safetyLine.classList.add('hidden');
        }
    }
    notice.classList.remove('hidden');
    notice.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
