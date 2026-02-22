/* =====================================================================
   App State
   ===================================================================== */
let selectedImage = null;
let batchFiles = [];
let currentTab = 'tab-img'; // 'tab-img' | 'tab-txt'
let presetsCache = [];

/* =====================================================================
   Init
   ===================================================================== */
document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    setupGeneratePage();
    setupBatchPage();
    setupHistoryPage();
    setupPresetsPage();
    setupSDPage();
    setupImg2ImgPage();
    checkStatus();

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
});

/* =====================================================================
   Navigation
   ===================================================================== */
function setupNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const page = btn.dataset.page;
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`page-${page}`).classList.add('active');

            // Lazy-load page data
            if (page === 'history') loadHistory();
            if (page === 'presets') loadPresets();
            if (page === 'sd') checkSDStatus();
            if (page === 'img2img') checkImg2ImgStatus();
        });
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

            // Sampler更新
            if (d.samplers?.length) {
                const sel = document.getElementById('sd-sampler');
                sel.innerHTML = d.samplers.map(s => `<option>${s}</option>`).join('');
                if (sel.dataset.pendingValue) { sel.value = sel.dataset.pendingValue; delete sel.dataset.pendingValue; }
            }

            // モデル一覧を更新
            if (d.models?.length) {
                const modelSel = document.getElementById('sd-model');
                modelSel.innerHTML = '<option value="">-- デフォルト --</option>' +
                    d.models.map(m => {
                        const name = m.model_name || m.title || '';
                        return `<option value="${name}">${name}</option>`;
                    }).join('');
                if (modelSel.dataset.pendingValue) { modelSel.value = modelSel.dataset.pendingValue; delete modelSel.dataset.pendingValue; }
            }

            // アップスケーラー一覧を更新
            if (d.upscalers?.length) {
                const upscalerSel = document.getElementById('sd-hr-upscaler');
                upscalerSel.innerHTML = d.upscalers.map(u =>
                    `<option${u === 'R-ESRGAN 4x+' ? ' selected' : ''}>${u}</option>`
                ).join('');
                if (upscalerSel.dataset.pendingValue) { upscalerSel.value = upscalerSel.dataset.pendingValue; delete upscalerSel.dataset.pendingValue; }
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

    // Text input enable button
    document.getElementById('description-input').addEventListener('input', updateGenerateBtn);

    // Generate button
    document.getElementById('generate-btn').addEventListener('click', generatePrompt);

    // Result actions
    document.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', () => copyText(btn.dataset.target, btn));
    });
    document.getElementById('copy-all-btn').addEventListener('click', copyAllPrompts);
    document.getElementById('send-to-sd-btn').addEventListener('click', sendToSDPage);
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
    if (currentTab === 'tab-img') {
        btn.disabled = !selectedImage;
    } else {
        btn.disabled = !document.getElementById('description-input').value.trim();
    }
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
function setupHistoryPage() {
    document.getElementById('refresh-history-btn').addEventListener('click', loadHistory);
    document.getElementById('clear-history-btn').addEventListener('click', async () => {
        if (!confirm('全履歴を削除しますか？')) return;
        await fetch('/api/history', { method: 'DELETE' });
        loadHistory();
        toast('履歴を削除しました', 'success');
    });
}

async function loadHistory() {
    const loading = document.getElementById('history-loading');
    const empty = document.getElementById('history-empty');
    const list = document.getElementById('history-list');
    loading.classList.remove('hidden');
    empty.classList.add('hidden');
    list.innerHTML = '';

    try {
        const r = await fetch('/api/history?limit=100');
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
                        <button class="btn btn-sm btn-secondary" onclick="loadHistoryItem(${item.id})">使用</button>
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
        if (el) el.innerHTML = options;
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

    // Restore last used parameters
    loadLastParams('sd');
}

async function runSDGenerate() {
    const positive = document.getElementById('sd-positive').value.trim();
    if (!positive) { toast('ポジティブプロンプトを入力してください', 'error'); return; }

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

    console.log('[IMG2IMG] setupImg2ImgPage called');
    console.log('[IMG2IMG] uploadArea:', uploadArea);
    console.log('[IMG2IMG] imageInput:', imageInput);

    if (!uploadArea || !imageInput) {
        console.error('[IMG2IMG] Upload elements not found!');
        return;
    }

    // Click to upload
    uploadArea.addEventListener('click', () => {
        console.log('[IMG2IMG] Click on upload area');
        imageInput.click();
    });

    // File input change
    imageInput.addEventListener('change', e => {
        console.log('[IMG2IMG] File input changed:', e.target.files);
        handleI2IImageSelect(e.target.files[0]);
    });

    // Drag over
    uploadArea.addEventListener('dragover', e => {
        console.log('[IMG2IMG] Dragover');
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.add('drag-over');
    });

    // Drag leave
    uploadArea.addEventListener('dragleave', e => {
        console.log('[IMG2IMG] Dragleave');
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.remove('drag-over');
    });

    // Drop
    uploadArea.addEventListener('drop', e => {
        console.log('[IMG2IMG] Drop event:', e.dataTransfer.files);
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) {
            handleI2IImageSelect(e.dataTransfer.files[0]);
        }
    });

    if (clearBtn) clearBtn.addEventListener('click', clearI2IImage);
    if (generateBtn) generateBtn.addEventListener('click', runImg2Img);
    if (enableHrCheckbox && hrSettings) {
        enableHrCheckbox.addEventListener('change', e => {
            hrSettings.classList.toggle('hidden', !e.target.checked);
        });
    }

    console.log('[IMG2IMG] setupImg2ImgPage completed');

    // Restore last used parameters
    loadLastParams('img2img');
}

function handleI2IImageSelect(file) {
    console.log('[IMG2IMG] handleI2IImageSelect called with file:', file);

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
    console.log('[IMG2IMG] File stored, reading as DataURL');

    const reader = new FileReader();
    reader.onload = e => {
        console.log('[IMG2IMG] FileReader onload completed');
        const previewImg = document.getElementById('i2i-preview-image');
        const previewWrap = document.getElementById('i2i-preview-wrap');
        const uploadArea = document.getElementById('i2i-upload-area');
        const genBtn = document.getElementById('i2i-generate-btn');

        if (previewImg) previewImg.src = e.target.result;
        if (previewWrap) previewWrap.classList.remove('hidden');
        if (uploadArea) uploadArea.classList.add('hidden');
        if (genBtn) genBtn.disabled = false;

        console.log('[IMG2IMG] Preview updated');
        toast('画像を読み込みました', 'success');
    };
    reader.onerror = () => {
        console.error('[IMG2IMG] FileReader error');
        toast('ファイルの読み込みに失敗しました', 'error');
    };
    reader.readAsDataURL(file);
}

function clearI2IImage() {
    console.log('[IMG2IMG] clearI2IImage called');
    i2iSelectedImage = null;

    const imageInput = document.getElementById('i2i-image-input');
    const previewWrap = document.getElementById('i2i-preview-wrap');
    const uploadArea = document.getElementById('i2i-upload-area');
    const genBtn = document.getElementById('i2i-generate-btn');

    if (imageInput) imageInput.value = '';
    if (previewWrap) previewWrap.classList.add('hidden');
    if (uploadArea) uploadArea.classList.remove('hidden');
    if (genBtn) genBtn.disabled = true;

    console.log('[IMG2IMG] Image cleared');
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

            if (d.samplers?.length) {
                const sel = document.getElementById('i2i-sampler');
                sel.innerHTML = d.samplers.map(s => `<option>${s}</option>`).join('');
                if (sel.dataset.pendingValue) { sel.value = sel.dataset.pendingValue; delete sel.dataset.pendingValue; }
            }
            if (d.models?.length) {
                const modelSel = document.getElementById('i2i-model');
                modelSel.innerHTML = '<option value="">-- デフォルト --</option>' +
                    d.models.map(m => {
                        const name = m.model_name || m.title || '';
                        return `<option value="${name}">${name}</option>`;
                    }).join('');
                if (modelSel.dataset.pendingValue) { modelSel.value = modelSel.dataset.pendingValue; delete modelSel.dataset.pendingValue; }
            }

            // アップスケーラー一覧を更新
            if (d.upscalers?.length) {
                const upscalerSel = document.getElementById('i2i-hr-upscaler');
                upscalerSel.innerHTML = d.upscalers.map(u =>
                    `<option${u === 'R-ESRGAN 4x+' ? ' selected' : ''}>${u}</option>`
                ).join('');
                if (upscalerSel.dataset.pendingValue) { upscalerSel.value = upscalerSel.dataset.pendingValue; delete upscalerSel.dataset.pendingValue; }
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

    const loading = document.getElementById('i2i-loading');
    const results = document.getElementById('i2i-results');
    const imagesEl = document.getElementById('i2i-images');

    loading.classList.remove('hidden');
    results.classList.add('hidden');

    const i2iEnableHr = document.getElementById('i2i-enable-hr').checked;
    const i2iParams = {
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
   Last Parameter History
   ===================================================================== */
async function saveLastParams(feature, params) {
    try {
        await fetch(`/api/last-params/${feature}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
    } catch (e) {
        // 保存失敗は無視
    }
}

async function loadLastParams(feature) {
    try {
        const r = await fetch(`/api/last-params/${feature}`);
        if (!r.ok) return;
        const d = await r.json();
        if (d.params && Object.keys(d.params).length > 0) {
            applyLastParams(feature, d.params);
        }
    } catch (e) {
        // 読み込み失敗は無視
    }
}

function applyLastParams(feature, params) {
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined && val !== null) el.value = val;
    };
    const setPending = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined && val !== null) el.dataset.pendingValue = val;
    };

    if (feature === 'generate') {
        setVal('select-style', params.style);
        setVal('select-tone', params.tone);
        setVal('select-quality', params.quality);
        setVal('select-preset', params.preset_id);

    } else if (feature === 'sd') {
        setVal('sd-negative', params.negative);
        setVal('sd-width', params.width);
        setVal('sd-height', params.height);
        setVal('sd-steps', params.steps);
        setVal('sd-cfg', params.cfg_scale);
        setVal('sd-batch', params.batch_size);
        setVal('sd-seed', params.seed);
        setVal('sd-model', params.model);
        setVal('sd-loras', params.loras);
        setVal('sd-hr-scale', params.hr_scale);
        setVal('sd-hr-steps', params.hr_second_pass_steps);
        setVal('sd-hr-denoising', params.hr_denoising_strength);
        setPending('sd-sampler', params.sampler);
        setPending('sd-hr-upscaler', params.hr_upscaler);
        if (params.enable_hr !== undefined) {
            const hrChk = document.getElementById('sd-enable-hr');
            if (hrChk) {
                hrChk.checked = params.enable_hr;
                document.getElementById('sd-hr-settings').classList.toggle('hidden', !params.enable_hr);
            }
        }

    } else if (feature === 'img2img') {
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
        setVal('i2i-loras', params.loras);
        setVal('i2i-hr-scale', params.hr_scale);
        setVal('i2i-hr-steps', params.hr_second_pass_steps);
        setVal('i2i-hr-denoising', params.hr_denoising_strength);
        setPending('i2i-sampler', params.sampler);
        setPending('i2i-hr-upscaler', params.hr_upscaler);
        if (params.enable_hr !== undefined) {
            const hrChk = document.getElementById('i2i-enable-hr');
            if (hrChk) {
                hrChk.checked = params.enable_hr;
                document.getElementById('i2i-hr-settings').classList.toggle('hidden', !params.enable_hr);
            }
        }
    }
}

/* =====================================================================
   Utilities
   ===================================================================== */
function copyText(elementId, btn) {
    const el = document.getElementById(elementId);
    navigator.clipboard.writeText(el.value).then(() => {
        const orig = btn.textContent;
        btn.textContent = '✓ OK';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); }, 1800);
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
