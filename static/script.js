// DOM Elements
const uploadArea = document.getElementById('upload-area');
const imageInput = document.getElementById('image-input');
const previewSection = document.getElementById('preview-section');
const previewImage = document.getElementById('preview-image');
const generateBtn = document.getElementById('generate-btn');
const clearImageBtn = document.getElementById('clear-image-btn');
const loadingSpinner = document.getElementById('loading-spinner');
const resultsSection = document.getElementById('results-section');
const errorSection = document.getElementById('error-section');
const statusBox = document.getElementById('status-box');
const positivePromptArea = document.getElementById('positive-prompt');
const negativePromptArea = document.getElementById('negative-prompt');
const tabButtons = document.querySelectorAll('.tab-button');
const tabContents = document.querySelectorAll('.tab-content');
const descriptionInput = document.getElementById('description-input');
const generateTextBtn = document.getElementById('generate-text-btn');
const configInfo = document.getElementById('config-info');

let selectedImage = null;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    setupEventListeners();
    await loadConfig();
    await checkLLMServer();
});

// Setup Event Listeners
function setupEventListeners() {
    // Image Upload
    uploadArea.addEventListener('click', () => imageInput.click());
    imageInput.addEventListener('change', handleImageSelect);
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);

    // Buttons
    generateBtn.addEventListener('click', generatePromptsFromImage);
    clearImageBtn.addEventListener('click', clearImage);
    generateTextBtn.addEventListener('click', generatePromptsFromText);

    // Tab Navigation
    tabButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            switchTab(e.target.dataset.tab);
        });
    });

    // Copy Buttons
    document.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            copyToClipboard(e.target.dataset.target);
        });
    });

    // Action Buttons
    document.getElementById('copy-all-btn')?.addEventListener('click', copyAllPrompts);
    document.getElementById('clear-results-btn')?.addEventListener('click', clearResults);
    document.getElementById('clear-error-btn')?.addEventListener('click', clearError);
}

// Image Handling
function handleImageSelect(e) {
    const file = e.target.files[0];
    if (file) {
        displayImage(file);
    }
}

function handleDragOver(e) {
    e.preventDefault();
    uploadArea.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');

    const files = e.dataTransfer.files;
    if (files[0]) {
        displayImage(files[0]);
    }
}

function displayImage(file) {
    if (!file.type.startsWith('image/')) {
        showError('Please select a valid image file');
        return;
    }

    if (file.size > 10 * 1024 * 1024) {
        showError('Image size exceeds 10MB limit');
        return;
    }

    selectedImage = file;
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        previewSection.classList.remove('hidden');
        uploadArea.classList.add('hidden');
        generateBtn.disabled = false;
        clearError();
    };
    reader.readAsDataURL(file);
}

function clearImage() {
    selectedImage = null;
    imageInput.value = '';
    previewSection.classList.add('hidden');
    uploadArea.classList.remove('hidden');
    generateBtn.disabled = true;
    clearError();
    clearResults();
}

// Tab Navigation
function switchTab(tabId) {
    tabContents.forEach(content => content.classList.remove('active'));
    tabButtons.forEach(button => button.classList.remove('active'));

    document.getElementById(tabId).classList.add('active');
    event.target.classList.add('active');

    clearError();
    clearResults();
}

// API Calls
async function generatePromptsFromImage() {
    if (!selectedImage) {
        showError('Please select an image first');
        return;
    }

    const formData = new FormData();
    formData.append('file', selectedImage);

    await callGenerateAPI('/api/generate-prompts', formData);
}

async function generatePromptsFromText() {
    const description = descriptionInput.value.trim();
    if (!description) {
        showError('Please enter a description');
        return;
    }

    await callGenerateAPI('/api/generate-prompts-text', { description });
}

async function callGenerateAPI(endpoint, data) {
    try {
        showLoading(true);
        clearError();
        clearResults();

        const options = {
            method: 'POST',
            headers: data instanceof FormData ? {} : { 'Content-Type': 'application/json' }
        };

        if (data instanceof FormData) {
            options.body = data;
        } else {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(endpoint, options);

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `Error: ${response.status}`);
        }

        const result = await response.json();

        if (result.success && result.data) {
            displayResults(result.data);
            showStatus('Prompts generated successfully!', 'success');
        } else {
            throw new Error('Invalid response format');
        }
    } catch (error) {
        console.error('Error:', error);
        showError(error.message || 'Failed to generate prompts');
    } finally {
        showLoading(false);
    }
}

function displayResults(data) {
    positivePromptArea.value = data.positive || '';
    negativePromptArea.value = data.negative || '';
    resultsSection.classList.remove('hidden');
}

function clearResults() {
    resultsSection.classList.add('hidden');
    positivePromptArea.value = '';
    negativePromptArea.value = '';
}

// Utility Functions
function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    const button = event.target;

    element.select();
    document.execCommand('copy');

    const originalText = button.textContent;
    button.textContent = '✓ Copied!';
    button.classList.add('copied');

    setTimeout(() => {
        button.textContent = originalText;
        button.classList.remove('copied');
    }, 2000);
}

function copyAllPrompts() {
    const allText = `Positive:\n${positivePromptArea.value}\n\nNegative:\n${negativePromptArea.value}`;
    navigator.clipboard.writeText(allText).then(() => {
        showStatus('All prompts copied to clipboard!', 'success');
    }).catch(() => {
        showError('Failed to copy to clipboard');
    });
}

function showLoading(show) {
    loadingSpinner.classList.toggle('hidden', !show);
}

function showError(message) {
    const errorMessage = document.getElementById('error-message');
    errorMessage.textContent = message;
    errorSection.classList.remove('hidden');
}

function clearError() {
    errorSection.classList.add('hidden');
}

function showStatus(message, type = 'info') {
    const statusMessage = document.getElementById('status-message');
    statusMessage.textContent = message;
    statusBox.className = `status-box ${type}`;
    statusBox.classList.remove('hidden');

    setTimeout(() => {
        statusBox.classList.add('hidden');
    }, 4000);
}

// Configuration
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const config = await response.json();
            configInfo.innerHTML = `
                <small>
                    Server: ${config.llm_server}<br>
                    Model: ${config.model}
                </small>
            `;
        }
    } catch (error) {
        console.warn('Failed to load config:', error);
    }
}

async function checkLLMServer() {
    try {
        const response = await fetch('/health');
        if (response.ok) {
            const health = await response.json();
            if (health.status === 'healthy') {
                showStatus('LLM server connected ✓', 'success');
            } else {
                showStatus('LLM server: ' + health.llm_server, 'info');
            }
        }
    } catch (error) {
        console.warn('LLM server health check failed:', error);
        showError('Warning: LLM server is not responding. Make sure LM Studio or Lemonade Server is running.');
    }
}
