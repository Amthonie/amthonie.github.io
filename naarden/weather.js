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
     * @property {number} [wind_bearing]
     * @property {boolean} [is_dark]
     * @property {number} [precipitation_today]
     * @property {string} [sunrise]
     * @property {string} [sunset]
     * @property {string} [moon_fase]
     * @property {string} [forecast_day_1]
     * @property {string} [forecast_day_2]
     * @property {string} [forecast_day_3]
     * @property {string} [updated]
     */
    const GIST = "https://gist.githubusercontent.com/Amthonie/6e1d57a913650f780d441db67d8d0ca6/raw/weather-naarden.json";
    const ICONS = "/vendor/meteocons/"; // root-absolute so the card works at any page depth
    const ICON = { "clear-night":"clear-night","cloudy":"overcast","fog":"fog","hail":"hail","lightning":"thunderstorms","lightning-rainy":"thunderstorms-rain","partlycloudy":"partly-cloudy-day","pouring":"rain","rainy":"rain","snowy":"snow","snowy-rainy":"sleet","sunny":"clear-day","windy":"wind","windy-variant":"wind","exceptional":"not-available" };
    const LABEL = { "clear-night":"Clear","cloudy":"Cloudy","fog":"Fog","hail":"Hail","lightning":"Thunder","lightning-rainy":"Thunderstorms","partlycloudy":"Partly cloudy","pouring":"Pouring","rainy":"Rainy","snowy":"Snowy","snowy-rainy":"Sleet","sunny":"Sunny","windy":"Windy","windy-variant":"Windy","exceptional":"Exceptional" };
    const DIRS = ["N","NE","E","SE","S","SW","W","NW"];
    const BFT = ["Calm","Light air","Light breeze","Gentle breeze","Moderate breeze","Fresh breeze","Strong breeze","Near gale","Gale","Strong gale","Storm","Violent storm","Hurricane"];
    const MOON = { new_moon:["moon-new","New moon"], waxing_crescent:["moon-waxing-crescent","Waxing crescent"], first_quarter:["moon-first-quarter","First quarter"], waxing_gibbous:["moon-waxing-gibbous","Waxing gibbous"], full_moon:["moon-full","Full moon"], waning_gibbous:["moon-waning-gibbous","Waning gibbous"], last_quarter:["moon-last-quarter","Last quarter"], waning_crescent:["moon-waning-crescent","Waning crescent"] };

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
    function ago(iso) {
        const t = Date.parse(iso); if (isNaN(t)) return "";
        const s = Math.max(0, (Date.now() - t) / 1000);
        if (s < 90) return "just now";
        const m = Math.round(s / 60); if (m < 60) return m + " min ago";
        const h = Math.round(m / 60); if (h < 24) return h + (h === 1 ? " hour ago" : " hours ago");
        const d = Math.round(h / 24); return d + (d === 1 ? " day ago" : " days ago");
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
            set("wx-humidity", d.humidity != null ? ("Humidity " + Math.round(d.humidity) + "%") : "");
            const rain = d.precipitation_today;
            set("wx-rain", rain != null ? (Math.round(rain * 10) / 10) + " mm rain today so far · " : "");
            if (d.wind_bearing != null) {
                set("wx-winddir", dir8(d.wind_bearing));
                const mk = document.getElementById("wx-windmarker");
                if (mk) mk.setAttribute("transform", "rotate(" + d.wind_bearing + " 50 50)");
            }
            const bft = d.wind_speed != null ? toBft(d.wind_speed, d.wind_unit) : null;
            set("wx-bft", bft != null ? bft : "—");
            set("wx-beaufort", bft != null && BFT[bft] ? BFT[bft] : "");
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
            set("wx-updated", "Updated " + ago(d.updated));
            document.getElementById("weather").hidden = false;
        })
        .catch(function () { /* leave the tile hidden on any error */ });
})();
