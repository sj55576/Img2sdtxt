const I18n = (() => {
    let _locale = localStorage.getItem('app-locale') || 'ja';
    let _messages = {};
    let _fallbackMessages = {};

    function _resolve(obj, path) {
        return path.split('.').reduce((o, k) => o?.[k], obj);
    }

    async function load(locale) {
        try {
            const resp = await fetch(`/static/i18n/${locale}.json?v=${Date.now()}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        } catch (e) {
            console.warn(`[i18n] Failed to load ${locale}:`, e);
            return {};
        }
    }

    function t(key, fallback) {
        return _resolve(_messages, key) || _resolve(_fallbackMessages, key) || fallback || key;
    }

    function applyToDOM() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const val = t(key);
            if (val && val !== key) {
                el.textContent = val;
            }
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            const val = t(key);
            if (val && val !== key) {
                el.placeholder = val;
            }
        });
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            const val = t(key);
            if (val && val !== key) {
                el.title = val;
            }
        });
        document.documentElement.lang = _locale;
    }

    async function init() {
        _fallbackMessages = await load('ja');
        if (_locale !== 'ja') {
            _messages = await load(_locale);
        } else {
            _messages = _fallbackMessages;
        }
        applyToDOM();
    }

    async function setLocale(locale) {
        _locale = locale;
        localStorage.setItem('app-locale', locale);
        _messages = await load(locale);
        applyToDOM();
    }

    function getLocale() {
        return _locale;
    }

    return { init, t, setLocale, getLocale, applyToDOM };
})();
