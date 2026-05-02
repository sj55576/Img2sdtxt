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

// モデル選択の永続化（タブ切り替えでリセットされないよう変数で保持）
const _selectedModel = { sd: '', img2img: '', inpaint: '' };
// モデルリストの初回ロード済みフラグ（タブ切り替え時の再構築を防ぐ）
const _modelsLoaded = { sd: false, img2img: false, inpaint: false };

/* =====================================================================
   Init
   ===================================================================== */
document.addEventListener('DOMContentLoaded', () => {
    const _setup = (name, fn) => { try { fn(); } catch(e) { console.error(`[SETUP] ${name} failed:`, e); } };
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
    checkStatus();

    // Initialize SD and Img2Img selectors early for parameter restoration
    checkSDStatus();
    checkImg2ImgStatus();
    checkInpaintStatus();

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
        if (page === 'gallery') loadGallery();
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
    llmEl.classList.add('checking');
    try {
        const r = await fetch('/health');
        if (r.ok) {
            const d = await r.json();
            llmEl.classList.remove('checking');
            llmEl.classList.add(d.status === 'healthy' ? 'ok' : 'error');
            llmEl.querySelector('.label').textContent = 'LLM ✓';
        } else { throw new Error(); }
    } catch {
        llmEl.classList.remove('checking');
        llmEl.classList.add('error');
        llmEl.querySelector('.label').textContent = 'LLM ✗';
    }
}

async function checkSDStatus() {
    const sdEl = document.getElementById('sd-status');
    const badge = document.getElementById('sd-api-badge');
    sdEl.classList.add('checking');
    try {
        const r = await fetch('/api/sd/status');
        const d = await r.json();
        sdEl.classList.remove('checking');
        if (d.available) {
            sdEl.classList.add('ok');
            sdEl.querySelector('.label').textContent = 'SD ✓';
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
            badge.className = 'badge badge-red';
            badge.textContent = 'Disconnected';
        }
    } catch {
        sdEl.classList.remove('checking');
        sdEl.classList.add('error');
        badge.className = 'badge badge-red';
        badge.textContent = 'Error';
    }
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
        loraSel.innerHTML = '<option value="">-- LoRA選択 --</option>' +
            loras.map(l => {
                const name = l.name || '';
                const alias = l.alias || name;
                const display = alias !== name ? `${alias} (${name})` : name;
                return `<option value="${name}">${display}</option>`;
            }).join('');
    } catch (e) {
        console.error(`[LORA] Failed to load LoRAs for ${prefix}:`, e);
    }
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
        const allFiles = e.target.files;
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
    await new Promise(r => setTimeout(r, 150));
    runSDGenerate();
}

async function sendToSDAndMultiGenerate() {
    document.getElementById('sd-positive').value = document.getElementById('pos-prompt').value;
    document.getElementById('sd-negative').value = document.getElementById('neg-prompt').value;
    document.querySelector('[data-page="sd"]').click();
    await new Promise(r => setTimeout(r, 150));
    runMultiModelGenerate();
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
    await new Promise(r => setTimeout(r, 150));
    runSDGenerate();
}

function copyAllPrompts() {
    const text = `Positive:\n${document.getElementById('pos-prompt').value}\n\nNegative:\n${document.getElementById('neg-prompt').value}`;
    navigator.clipboard.writeText(text).then(() => toast('全プロンプトをコピーしました', 'success'));
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
        navigator.clipboard.writeText(text).then(() => toast('全プロンプトをコピーしました', 'success'));
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
        await fetch('/api/history', { method: 'DELETE' });
        loadHistory();
        toast('履歴を削除しました', 'success');
    });
    document.getElementById('export-history-btn').addEventListener('click', () => {
        window.location.href = '/api/history/export';
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

    const params = new URLSearchParams({ limit: 100 });
    if (search) params.set('search', search);
    if (style) params.set('style', style);
    if (quality) params.set('quality', quality);
    if (favoritesOnly) params.set('favorites_only', 'true');

    try {
        const r = await fetch('/api/history?' + params.toString());
        const d = await r.json();
        loading.classList.add('hidden');

        if (!d.items?.length) { empty.classList.remove('hidden'); return; }

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
            </div>
        `).join('');
    } catch (e) {
        loading.classList.add('hidden');
        toast('履歴の読み込みに失敗しました', 'error');
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
    const el = document.getElementById(`hist-${id}`);
    if (!el) return;
    const positive = el.querySelectorAll('.history-prompt')[0]?.textContent.replace(/^Positive\s*/i, '').trim() || '';
    const negative = el.querySelectorAll('.history-prompt')[1]?.textContent.replace(/^Negative\s*/i, '').trim() || '';
    sendToRefine(positive, negative);
}

function loadHistoryItem(id) {
    const el = document.getElementById(`hist-${id}`);
    if (!el) return;
    const positive = el.querySelectorAll('.history-prompt')[0]?.textContent.replace(/^Positive\s*/i, '').trim() || '';
    const negative = el.querySelectorAll('.history-prompt')[1]?.textContent.replace(/^Negative\s*/i, '').trim() || '';
    document.getElementById('pos-prompt').value = positive;
    document.getElementById('neg-prompt').value = negative;
    document.getElementById('result-box').classList.remove('hidden');
    document.querySelector('[data-page="generate"]').click();
    toast('履歴を読み込みました', 'info');
}

async function deleteHistoryItem(id) {
    await fetch(`/api/history/${id}`, { method: 'DELETE' });
    document.getElementById(`hist-${id}`)?.remove();
    toast('削除しました', 'success');
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
        });
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
    const r = await fetch(`/api/presets/${id}`, { method: 'DELETE' });
    if (r.ok) { loadPresets(); toast('削除しました', 'success'); }
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

    // Restore last used parameters (with delay for async operations)
    setTimeout(() => loadLastParams('sd'), 100);
}

async function runSDGenerate() {
    const positive = document.getElementById('sd-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); return; }
    const _sdModel = document.getElementById('sd-model').value.trim();
    if (!_sdModel) { toast('モデルを選択してください', 'error'); return; }
    if (!await confirmModel(_sdModel)) return;

    const loading = document.getElementById('sd-loading');
    const results = document.getElementById('sd-results');
    const imagesEl = document.getElementById('sd-images');

    loading.classList.remove('hidden');
    results.classList.add('hidden');

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
        loading.classList.add('hidden');
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
    const positive = document.getElementById('sd-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); return; }

    const selectedModels = Array.from(document.querySelectorAll('.multi-model-checkbox:checked')).map(cb => cb.value);
    if (!selectedModels.length) { toast('1つ以上のモデルを選択してください', 'error'); return; }

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

    for (let i = 0; i < selectedModels.length; i++) {
        const model = selectedModels[i];
        const card = imagesEl.children[i];
        loadingText.textContent = `${i + 1} / ${selectedModels.length} モデル処理中... (${model})`;
        card.querySelector('.multi-model-result-header').textContent = `⏳ ${model}`;
        card.querySelector('.multi-model-result-images').textContent = '生成中...';
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

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
        }
    }

    loading.classList.add('hidden');
    toast(`${successCount} / ${selectedModels.length} モデルで生成完了`, successCount > 0 ? 'success' : 'error');
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

    // Restore last used parameters (with delay for selector population)
    setTimeout(() => loadLastParams('img2img'), 150);
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
}

async function runImg2Img() {
    if (!i2iSelectedImage) { toast('入力画像を選択してください', 'error'); return; }

    const positive = document.getElementById('i2i-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); return; }
    const _i2iModel = document.getElementById('i2i-model').value.trim();
    if (!_i2iModel) { toast('モデルを選択してください', 'error'); return; }
    if (!await confirmModel(_i2iModel)) return;

    const loading = document.getElementById('i2i-loading');
    const results = document.getElementById('i2i-results');
    const imagesEl = document.getElementById('i2i-images');

    loading.classList.remove('hidden');
    results.classList.add('hidden');

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
    } catch (e) {
        toast(e.message || '生成に失敗しました', 'error');
    } finally {
        loading.classList.add('hidden');
    }
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

    setTimeout(() => loadLastParams('inpaint'), 150);
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
    if (!inpaintSelectedImage) { toast('入力画像を選択してください', 'error'); return; }
    const positive = document.getElementById('inpaint-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); return; }
    const _inpaintModel = document.getElementById('inpaint-model').value.trim();
    if (!_inpaintModel) { toast('モデルを選択してください', 'error'); return; }
    if (!await confirmModel(_inpaintModel)) return;

    const maskBase64 = getMaskBase64();

    const loading = document.getElementById('inpaint-loading');
    const results = document.getElementById('inpaint-results');
    const imagesEl = document.getElementById('inpaint-images');

    loading.classList.remove('hidden');
    results.classList.add('hidden');

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
        loading.classList.add('hidden');
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
    });
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
    });
    document.getElementById('gallery-filter-mode').addEventListener('change', debouncedLoad);
    document.getElementById('gallery-filter-date').addEventListener('change', debouncedLoad);
    document.getElementById('gallery-load-more-btn').addEventListener('click', () => {
        loadGallery(_galleryOffset);
    });
    document.getElementById('gallery-modal-close').addEventListener('click', closeGalleryModal);
    document.getElementById('gallery-modal').addEventListener('click', e => {
        if (e.target === document.getElementById('gallery-modal')) closeGalleryModal();
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
        const cacheKey = `${modeFilter}|${dateFilter}|${offset}`;
        let d;
        if (!forceRefresh && _galleryCache[cacheKey]) {
            d = _galleryCache[cacheKey];
        } else {
            const params = new URLSearchParams();
            if (modeFilter) params.set('mode', modeFilter);
            if (dateFilter) params.set('date', dateFilter);
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
            div.addEventListener('click', () => openGalleryModal(JSON.stringify(img)));
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

    modal.classList.remove('hidden');
}

function closeGalleryModal() {
    document.getElementById('gallery-modal').classList.add('hidden');
    document.getElementById('gallery-modal-image').src = '';
}
