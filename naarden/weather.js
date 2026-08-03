// Live weather tile: fetches the Home-Assistant-pushed gist and populates #weather.
// Day/night icon swap keys off the gist's `is_dark` flag (HA-corrected, since the
// forecast service can report 'day' after sunset). Fails silently → tile stays hidden.
(function () {
    /**
     * Shape of the weather JSON that Home Assistant pushes to the gist.
     * @typedef {Object} WeatherData
     * @property {string} condition
     * @property {number} temperature
     * @property {number} [apparent]
     * @property {number} [humidity]
     * @property {number} [wind_speed]
     * @property {string} [wind_unit]
     * @property {number} [wind_gust_speed]
     * @property {number} [wind_bearing]
     * @property {boolean} [is_dark]
     * @property {number} [precipitation_today]
     * @property {number} [dew_point]
     * @property {number} [air_pressure]
     * @property {number} [uv_index]
     * @property {number} [cloud_coverage]
     * @property {number} [visibility]
     * @property {string} [visibility_unit]
     * @property {string} [sunrise]
     * @property {string} [sunset]
     * @property {string} [moon_fase]
     * @property {string} [forecast_day_1]
     * @property {string} [forecast_day_2]
     * @property {string} [forecast_day_3]
     * @property {string} [updated]
     */
    const GIST = "https://gist.githubusercontent.com/Amthonie/6e1d57a913650f780d441db67d8d0ca6/raw/weather-naarden.json";
    const FORECAST = "https://gist.githubusercontent.com/Amthonie/6e1d57a913650f780d441db67d8d0ca6/raw/forecast_naarden.txt"; // plain-text forecast in words, same gist
    const ICONS = "/vendor/meteocons/"; // root-absolute so the card works at any page depth
    const ICON = { "clear-night":"clear-night","cloudy":"overcast","fog":"fog","hail":"hail","lightning":"thunderstorms","lightning-rainy":"thunderstorms-rain","partlycloudy":"partly-cloudy-day","pouring":"rain","rainy":"rain","snowy":"snow","snowy-rainy":"sleet","sunny":"clear-day","windy":"wind","windy-variant":"wind","exceptional":"not-available" };
    const LABEL = { "clear-night":"Clear","cloudy":"Cloudy","fog":"Fog","hail":"Hail","lightning":"Thunder","lightning-rainy":"Thunderstorms","partlycloudy":"Partly cloudy","pouring":"Pouring","rainy":"Rainy","snowy":"Snowy","snowy-rainy":"Sleet","sunny":"Sunny","windy":"Windy","windy-variant":"Windy","exceptional":"Exceptional" };
    const DIRS = ["N","NE","E","SE","S","SW","W","NW"];
    const BFT = ["Calm","Light air","Light breeze","Gentle breeze","Moderate breeze","Fresh breeze","Strong breeze","Near gale","Gale","Strong gale","Storm","Violent storm","Hurricane"];
    const MOON = { new_moon:["moon-new","New moon"], waxing_crescent:["moon-waxing-crescent","Waxing crescent"], first_quarter:["moon-first-quarter","First quarter"], waxing_gibbous:["moon-waxing-gibbous","Waxing gibbous"], full_moon:["moon-full","Full moon"], waning_gibbous:["moon-waning-gibbous","Waning gibbous"], last_quarter:["moon-last-quarter","Last quarter"], waning_crescent:["moon-waning-crescent","Waning crescent"] };

    // Secondary-data ticker: the extra gist fields that don't fit the card, in display
    // order. Rendered as a marquee across the top of the card (see #weather .wx-ticker-*
    // in weather.css). Inline line icons stroked in the brand colour; NNBSP between value
    // and unit (site copy convention). Humidity & rain live here too now (they used to be
    // the ghosted sub-label / footer text).
    const TICKER_ICONS = {
        droplet:'<path d="M12 3s6 7 6 11a6 6 0 1 1-12 0c0-4 6-11 6-11z"/>',
        gauge:'<circle cx="12" cy="12" r="9"/><path d="M12 12l3.5-3"/>',
        cloud:'<path d="M6 16a4 4 0 0 1 .5-8A5.5 5.5 0 0 1 17 8a4 4 0 0 1 1 8H6z"/>',
        rain:'<path d="M8 17l-1 3M12 17l-1 3M16 17l-1 3"/><path d="M6 14a4 4 0 0 1 .5-8A5.5 5.5 0 0 1 17 7a4 4 0 0 1 1 7.9"/>',
        eye:'<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
        uv:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>'
    };
    const NNBSP = " ";
    const r1 = v => { const n = parseFloat(v); return Number.isFinite(n) ? Math.round(n * 10) / 10 : v; };
    const r0 = v => { const n = parseFloat(v); return Number.isFinite(n) ? Math.round(n) : v; };
    const TICKER_FIELDS = [
        { key:"humidity",            icon:"droplet", label:"Humidity",    fmt:v => r0(v) + "%" },
        { key:"precipitation_today", icon:"rain",    label:"Rain today",  fmt:v => r1(v) + NNBSP + "mm" },
        { key:"dew_point",           icon:"droplet", label:"Dew point",   fmt:v => r1(v) + "°C" },
        { key:"air_pressure",        icon:"gauge",   label:"Pressure",    fmt:v => r0(v) + NNBSP + "hPa" },
        { key:"cloud_coverage",      icon:"cloud",   label:"Cloud cover", fmt:v => r0(v) + "%" },
        { key:"visibility",          icon:"eye",     label:"Visibility",  fmt:(v, d) => r1(v) + NNBSP + (d.visibility_unit || "km") },
        { key:"uv_index",            icon:"uv",      label:"UV index",    fmt:v => r1(v) }
    ];

    function iconFor(c, dark) {
        let n = ICON[c] || "not-available";
        if (dark && c === "sunny") n = "clear-night";
        if (dark && c === "partlycloudy") n = "partly-cloudy-night";
        return n;
    }
    function dir8(b) { b = ((b % 360) + 360) % 360; return DIRS[Math.round(b / 45) % 8]; }
    // Wind speed → Beaufort force (0–12). Converts when the gist unit is km/h (or,
    // defensively, when a value is out of the 0–12 Beaufort range so must be a real
    // speed); passes the value through when the gist already sends Beaufort.
    function toBft(speed, unit) {
        const v = parseFloat(speed);
        if (isNaN(v)) return null;
        const u = String(unit || "").toLowerCase().replace(/\s/g, "");
        if (u.indexOf("km") !== -1 || u.indexOf("kph") !== -1 || v > 12) {
            return Math.min(12, Math.round((v / (0.836 * 3.6)) ** (2 / 3))); // km/h → Bft (same curve as HA)
        }
        return Math.max(0, Math.min(12, Math.round(v))); // already Beaufort
    }
    // Literal update time in Naarden's timezone (matches sunrise/sunset, which are
    // already local HH:MM). A relative "x min ago" would be wrong here: the page never
    // auto-reloads, so a relative stamp freezes at page-load and drifts out of date.
    // Time-only when the reading is from today; a short date is prepended otherwise, so
    // a tab left open overnight can't read a stale time as if it were current.
    function stamp(iso) {
        const t = Date.parse(iso); if (isNaN(t)) return "";
        const when = new Date(t);
        const TZ = "Europe/Amsterdam";
        // timeZoneName:"short" appends the correct abbreviation for the date — CEST in
        // summer, CET in winter — so the DST switch needs no manual handling.
        const time = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" }).format(when);
        const day = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short" });
        return day.format(when) === day.format(new Date()) ? time : day.format(when) + ", " + time;
    }
    function set(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
    function fcell(cls, txt) { const s = document.createElement("span"); if (cls) s.className = cls; s.textContent = txt; return s; }
    function addForecast(box, label, str) {
        const p = String(str).split("|");           // day | condition | Tmin | Tmax | precip mm | wind bearing | beaufort
        if (p.length < 7) return;
        box.appendChild(fcell("wx-fc-day", label || p[0])); // empty label → use the day name from the piped string
        const im = document.createElement("img");
        im.className = "wx-fc-icon"; im.width = 28; im.height = 28;
        im.src = ICONS + iconFor(p[1], false) + ".svg"; im.alt = LABEL[p[1]] || p[1] || "";
        box.appendChild(im);
        const t = document.createElement("span");
        t.appendChild(fcell("wx-fc-hi", Math.round(parseFloat(p[3])) + "°"));
        t.appendChild(document.createTextNode(" / "));
        t.appendChild(fcell("wx-fc-lo", Math.round(parseFloat(p[2])) + "°"));
        box.appendChild(t);
        box.appendChild(fcell("wx-fc-sub", (Math.round(parseFloat(p[4]) * 10) / 10) + " mm"));
        box.appendChild(fcell("wx-fc-sub", dir8(parseFloat(p[5])) + " " + p[6] + " Bft"));
    }
    // Build the secondary-data marquee from whichever ticker fields the gist carries.
    // Content is emitted twice so the CSS translateX(0→-50%) loop is seamless. innerHTML
    // is safe here: every value comes from our own fmt() over numeric gist fields.
    function buildTicker(d) {
        const el = document.getElementById("wx-ticker");
        if (!el) return;
        const items = TICKER_FIELDS
            .filter(f => d[f.key] != null)
            .map(f => '<span class="wx-ticker-item"><svg viewBox="0 0 24 24" aria-hidden="true">' + TICKER_ICONS[f.icon] + '</svg>' + f.label + ' <span class="v">' + f.fmt(d[f.key], d) + '</span></span><span class="wx-ticker-sep">•</span>')
            .join("");
        el.innerHTML = items + items;
    }

    // Card: re-fetch the gist JSON and repaint #weather in place. On a failed refresh the
    // .catch does nothing, so the last-good card stays put — a network blip never blanks a
    // tile that's already showing (and a first-load failure just leaves it hidden, as before).
    function loadCard() {
        fetch(GIST + "?t=" + Math.floor(Date.now() / 300000), { cache: "no-store" }) // 5-min bucket: fresh within 5 min, still CDN-shareable inside each window
            .then(function (r) { if (!r.ok) throw 0; return r.json(); })
            .then(function (/** @type {WeatherData} */ d) {
                if (d == null || d.temperature == null) throw 0;
                const dark = !!d.is_dark;
                const img = document.getElementById("wx-icon");
                img.src = ICONS + iconFor(d.condition, dark) + ".svg";
                img.alt = LABEL[d.condition] || d.condition || "Weather";
                set("wx-condition", LABEL[d.condition] || d.condition || "—");
                set("wx-temp", Math.round(d.temperature));
                set("wx-feels", d.apparent != null ? ("Feels like " + Math.round(d.apparent) + "°") : "");
                buildTicker(d); // humidity, rain & the other secondary fields now live in the top marquee
                if (d.wind_bearing != null) {
                    set("wx-winddir", dir8(d.wind_bearing));
                    const mk = document.getElementById("wx-windmarker");
                    if (mk) mk.setAttribute("transform", "rotate(" + d.wind_bearing + " 50 50)");
                }
                const bft = d.wind_speed != null ? toBft(d.wind_speed, d.wind_unit) : null;
                const gust = d.wind_gust_speed != null ? toBft(d.wind_gust_speed, d.wind_unit) : null;
                const gusty = bft != null && gust != null && gust > bft + 1; // only when the gust is ≥2 forces above the sustained wind (a gust barely higher isn't really "gusty")
                set("wx-bft", bft != null ? bft : "—");                  // sustained value (primary tone in the HTML)
                set("wx-bft-gust", gusty ? " - " + gust : "");             // gust upper bound in the #wx-bft-gust span; "" hides it
                // Label tracks the sustained wind; " with gusts" appended (in the muted label tone) when a gust shows.
                set("wx-beaufort", bft != null && BFT[bft] ? BFT[bft] + (gusty ? " with gusts" : "") : "");
                const fc = document.getElementById("wx-forecast");
                if (fc) {
                    fc.innerHTML = "";
                    if (d.forecast_day_1) addForecast(fc, "Today", d.forecast_day_1);
                    if (d.forecast_day_2) addForecast(fc, "Tomorrow", d.forecast_day_2);
                    if (d.forecast_day_3) addForecast(fc, "", d.forecast_day_3);
                    const fcCard = document.getElementById("weather-fc");
                    if (fcCard) fcCard.hidden = fc.childElementCount === 0;
                }
                const astro = document.getElementById("wx-astro");
                if (astro) {
                    const showItem = function (id, ok) { const el = document.getElementById(id); if (el) el.style.display = ok ? "" : "none"; };
                    showItem("wx-astro-sunrise", !!d.sunrise); if (d.sunrise) set("wx-sunrise", d.sunrise);
                    showItem("wx-astro-sunset", !!d.sunset); if (d.sunset) set("wx-sunset", d.sunset);
                    const moon = d.moon_fase && MOON[d.moon_fase];
                    showItem("wx-astro-moon", !!moon);
                    if (moon) {
                        const mi = document.getElementById("wx-moon-icon");
                        if (mi) { mi.src = ICONS + moon[0] + ".svg"; mi.alt = moon[1]; }
                        set("wx-moon", moon[1]);
                    }
                    astro.hidden = !(d.sunrise || d.sunset || moon);
                }
                set("wx-updated", "Updated " + stamp(d.updated));
                document.getElementById("weather").hidden = false;
            })
            .catch(function () { /* leave the tile as-is on any error */ });
    }

    // Forecast in words: a separate plain-text file in the same gist, shown in the
    // #wx-forecast-text box above the card (on both /naarden/ and the checking page).
    // Fetched independently of the JSON card so one failing doesn't hide the other;
    // textContent (not innerHTML) so the gist text can't inject markup. No-op when
    // the box isn't on the page.
    function loadForecast() {
        const box = document.getElementById("wx-forecast-text");
        const body = document.getElementById("wx-forecast-text-body");
        if (!box || !body) return;
        fetch(FORECAST + "?t=" + Math.floor(Date.now() / 300000), { cache: "no-store" }) // same 5-min freshness bucket as the card
            .then(function (r) { if (!r.ok) throw 0; return r.text(); })
            .then(function (text) {
                text = text.trim();
                if (!text) return;              // empty file → leave the box hidden
                body.textContent = text;
                box.hidden = false;
            })
            .catch(function () { /* leave the box hidden on any error */ });
    }

    function refresh() { loadCard(); loadForecast(); }

    // Keep an open tab current without a page reload — a reload would re-download assets,
    // flash, drop scroll/lightbox state and log a phantom Umami pageview. Instead re-fetch
    // the data and repaint in place. Poll every 10 min, but skip the poll while the tab is
    // hidden (a backgrounded tab shouldn't hit the network for hours), and refresh at once
    // when the tab returns to the foreground so a long-open tab is current the instant it's
    // looked at. The gist's ~5-min CDN cache means a faster poll wouldn't surface fresher
    // data anyway.
    refresh();
    setInterval(function () { if (document.visibilityState === "visible") refresh(); }, 10 * 60 * 1000);
    document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") refresh(); });
})();
