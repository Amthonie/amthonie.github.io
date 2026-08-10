/*
 * Behaviour for /melodies/ — hand-authored companion to the generated
 * index.html (like naarden/weather/weather.js), loaded after the vendored
 * rtttl-play player so window.rtttlPlay exists. Two jobs:
 *   1. Wire the Play/Stop buttons (per-tune + the "Try it yourself" playbox).
 *   2. The optional, opt-in "remember my tinkering" cookies (see below).
 */
(() => {
    document.querySelectorAll('.rtttl-play').forEach((btn) => {
        btn.addEventListener('click', () => rtttlPlay.play(btn.dataset.rtttl));
    });
    document.querySelectorAll('.rtttl-stop').forEach((btn) => {
        btn.addEventListener('click', () => rtttlPlay.stop());
    });

    // "Try it yourself" box — plays the textarea's current value rather than a
    // fixed data-rtttl attribute, so it needs its own listener.
    const input = document.getElementById('rtttl-input');
    const inputPlay = document.getElementById('rtttl-input-play');
    if (input && inputPlay) {
        inputPlay.addEventListener('click', () => rtttlPlay.play(input.value));
    }

    // Optional "remember my tinkering" — the site's only cookies, and only if
    // you opt in. When on, we keep the playbox text (and the switch state) in
    // two simple first-party cookies for a week so a melody survives leaving
    // the page; off deletes both. Nothing else is stored, and there's no
    // tracking. Values are percent-encoded (RTTTL contains ; , = : which are
    // cookie-illegal raw); Secure is added only over https so local http
    // preview still works; scoped to /melodies/ since nothing else uses them.
    const remember = document.getElementById('rtttl-remember');
    if (input && remember) {
        const PREF = 'rtttl_remember';
        const TUNE = 'rtttl_tune';
        const MAX_AGE = 7 * 24 * 60 * 60;                 // one week, seconds
        const secure = location.protocol === 'https:' ? '; Secure' : '';

        const readCookie = (name) => {
            const m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
            return m ? decodeURIComponent(m[1]) : null;
        };
        const writeCookie = (name, value) => {
            document.cookie = name + '=' + encodeURIComponent(value) +
                '; Max-Age=' + MAX_AGE + '; Path=/melodies/; SameSite=Lax' + secure;
        };
        const deleteCookie = (name) => {
            document.cookie = name + '=; Max-Age=0; Path=/melodies/; SameSite=Lax' + secure;
        };

        // Persist the current playbox text, rolling the week forward on each
        // save; an empty box clears the tune cookie rather than storing "".
        const save = () => {
            if (input.value.trim()) writeCookie(TUNE, input.value);
            else deleteCookie(TUNE);
            writeCookie(PREF, '1');
        };

        // Restore on load, only if the switch was left on.
        if (readCookie(PREF) === '1') {
            remember.checked = true;
            const saved = readCookie(TUNE);
            if (saved) input.value = saved;
        }

        remember.addEventListener('change', () => {
            if (remember.checked) {
                save();
            } else {
                deleteCookie(TUNE);
                deleteCookie(PREF);
            }
        });

        // Save edits while enabled, debounced so we're not writing per keystroke.
        let debounce;
        input.addEventListener('input', () => {
            if (!remember.checked) return;
            clearTimeout(debounce);
            debounce = setTimeout(save, 400);
        });
    }
})();
