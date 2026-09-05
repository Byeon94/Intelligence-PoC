/* 의존성 없는 인라인 SVG 차트 (라인 / 스택 바 / 도넛). 모바일 가독성 우선. */
(function (global) {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var SERIES_VARS = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6"];

  function el(name, attrs) {
    var node = document.createElementNS(NS, name);
    for (var k in attrs) if (attrs.hasOwnProperty(k)) node.setAttribute(k, attrs[k]);
    return node;
  }
  function fmt(n) {
    if (n == null || isNaN(n)) return "-";
    var abs = Math.abs(n);
    if (abs >= 100) return Math.round(n).toLocaleString("ko-KR");
    if (abs >= 10) return n.toFixed(1);
    return n.toFixed(2);
  }
  function clear(box) { while (box.firstChild) box.removeChild(box.firstChild); }
  function tickEvery(n) { return Math.max(1, Math.ceil(n / 6)); }

  /* ── 라인 차트 ─────────────────────────────────────────────── */
  function lineChart(box, opts) {
    clear(box);
    var labels = opts.labels || [];
    var series = opts.series || [];           // [{name, values, varName?}]
    var W = 340, H = 190, padL = 34, padR = 10, padT = 10, padB = 22;
    var n = labels.length;
    if (!n) { box.textContent = ""; return; }

    var all = [];
    series.forEach(function (s) { (s.values || []).forEach(function (v) { if (v != null) all.push(v); }); });
    if (!all.length) { box.innerHTML = '<div class="chart-error">표시할 값이 없습니다</div>'; return; }
    var min = Math.min.apply(null, all), max = Math.max.apply(null, all);
    var span = (max - min) || 1;
    min -= span * 0.12; max += span * 0.12;

    var x = function (i) { return padL + (W - padL - padR) * (n === 1 ? 0.5 : i / (n - 1)); };
    var y = function (v) { return padT + (H - padT - padB) * (1 - (v - min) / (max - min)); };

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img" });

    for (var g = 0; g <= 3; g++) {
      var gy = padT + (H - padT - padB) * g / 3;
      svg.appendChild(el("line", { class: "gridline", x1: padL, y1: gy, x2: W - padR, y2: gy }));
      var gv = max - (max - min) * g / 3;
      var tl = el("text", { class: "axis-label", x: padL - 5, y: gy + 3, "text-anchor": "end" });
      tl.textContent = fmt(gv);
      svg.appendChild(tl);
    }

    var step = tickEvery(n);
    var lastYear = null;
    for (var i = 0; i < n; i += step) {
      var xt = el("text", { class: "axis-label", x: x(i), y: H - 6, "text-anchor": "middle" });
      xt.textContent = tickLabel(labels[i], lastYear);
      var yr = yearOf(labels[i]); if (yr) lastYear = yr;
      svg.appendChild(xt);
    }

    series.forEach(function (s, si) {
      var col = "var(" + (s.varName || SERIES_VARS[si % SERIES_VARS.length]) + ")";
      var d = "", started = false;
      s.values.forEach(function (v, i) {
        if (v == null) { started = false; return; }
        d += (started ? " L" : " M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
        started = true;
      });
      svg.appendChild(el("path", { d: d.trim(), fill: "none", stroke: col, "stroke-width": 2,
        "stroke-linejoin": "round", "stroke-linecap": "round" }));
      var last = s.values[n - 1];
      if (last != null) svg.appendChild(el("circle", { cx: x(n - 1), cy: y(last), r: 3, fill: col }));
    });

    box.appendChild(svg);
    box.appendChild(legend(series.map(function (s, si) {
      return { name: s.name, varName: s.varName || SERIES_VARS[si % SERIES_VARS.length] };
    })));
  }

  /* ── 스택 바 차트 ─────────────────────────────────────────── */
  function stackBar(box, opts) {
    clear(box);
    var labels = opts.labels || [];
    var series = opts.series || [];           // [{name, values, varName?}]
    var W = 340, H = 190, padL = 34, padR = 10, padT = 10, padB = 22;
    var n = labels.length;
    if (!n) { box.textContent = ""; return; }

    var totals = labels.map(function (_, i) {
      return series.reduce(function (a, s) { return a + ((s.values || [])[i] || 0); }, 0);
    });
    var max = (Math.max.apply(null, totals) || 0) * 1.12 || 1;
    var bw = (W - padL - padR) / n * 0.62;
    var y = function (v) { return padT + (H - padT - padB) * (1 - v / max); };

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img" });
    for (var g = 0; g <= 3; g++) {
      var gy = padT + (H - padT - padB) * g / 3;
      svg.appendChild(el("line", { class: "gridline", x1: padL, y1: gy, x2: W - padR, y2: gy }));
      var t = el("text", { class: "axis-label", x: padL - 5, y: gy + 3, "text-anchor": "end" });
      t.textContent = fmt(max - max * g / 3);
      svg.appendChild(t);
    }

    var step = tickEvery(n);
    var lastYear = null;
    for (var i = 0; i < n; i++) {
      var cx = padL + (W - padL - padR) * (i + 0.5) / n;
      var base = y(0), acc = 0;
      series.forEach(function (s, si) {
        var v = s.values[i] || 0;
        if (v <= 0) return;
        acc += v;
        var top = y(acc);
        svg.appendChild(el("rect", { x: cx - bw / 2, y: top, width: bw, height: base - top,
          fill: "var(" + (s.varName || SERIES_VARS[si % SERIES_VARS.length]) + ")",
          rx: 1.5 }));
        base = top;
      });
      if (i % step === 0) {
        var xt = el("text", { class: "axis-label", x: cx, y: H - 6, "text-anchor": "middle" });
        xt.textContent = tickLabel(labels[i], lastYear);
        var yr = yearOf(labels[i]); if (yr) lastYear = yr;
        svg.appendChild(xt);
      }
    }
    box.appendChild(svg);
    box.appendChild(legend(series.map(function (s, si) {
      return { name: s.name, varName: s.varName || SERIES_VARS[si % SERIES_VARS.length] };
    })));
  }

  /* ── 도넛 차트 ─────────────────────────────────────────────── */
  function donut(box, opts) {
    clear(box);
    var items = (opts.items || []).filter(function (d) { return d.share > 0; });
    var centerLabel = opts.centerLabel || "";
    var centerValue = opts.centerValue || "";
    var R = 60, SW = 20, C = 2 * Math.PI * R, cx = 75, cy = 75;

    var svg = el("svg", { class: "donut-svg", viewBox: "0 0 150 150", role: "img" });
    svg.appendChild(el("circle", { cx: cx, cy: cy, r: R, fill: "none",
      stroke: "var(--border2)", "stroke-width": SW }));
    var offset = 0;
    items.forEach(function (d, i) {
      var len = C * d.share / 100;
      var ring = el("circle", { cx: cx, cy: cy, r: R, fill: "none",
        stroke: "var(" + SERIES_VARS[i % SERIES_VARS.length] + ")", "stroke-width": SW,
        "stroke-dasharray": len.toFixed(2) + " " + (C - len).toFixed(2),
        "stroke-dashoffset": (-offset).toFixed(2),
        transform: "rotate(-90 " + cx + " " + cy + ")" });
      svg.appendChild(ring);
      offset += len;
    });
    var v = el("text", { class: "donut-center-v", x: cx, y: cy - 2, "text-anchor": "middle",
      "font-size": "17" });
    v.textContent = centerValue;
    svg.appendChild(v);
    var l = el("text", { class: "donut-center-l", x: cx, y: cy + 15, "text-anchor": "middle",
      "font-size": "9" });
    l.textContent = centerLabel;
    svg.appendChild(l);
    box.appendChild(svg);

    var lg = document.createElement("div");
    lg.className = "donut-legend";
    items.forEach(function (d, i) {
      var row = document.createElement("div");
      row.className = "dl";
      row.innerHTML =
        '<i style="background:var(' + SERIES_VARS[i % SERIES_VARS.length] + ')"></i>' +
        '<span class="dl-name">' + d.type + '</span>' +
        '<span class="dl-val">' + d.share.toFixed(1) + '%</span>' +
        (d.balance != null ? '<span class="dl-bal">' + fmt(d.balance) + '조</span>' : '');
      lg.appendChild(row);
    });
    box.appendChild(lg);
  }

  function legend(entries) {
    var wrap = document.createElement("div");
    wrap.className = "chart-legend";
    entries.forEach(function (e) {
      var s = document.createElement("span");
      s.className = "lg";
      s.innerHTML = '<i style="background:var(' + e.varName + ')"></i>' + e.name;
      wrap.appendChild(s);
    });
    return wrap;
  }
  function yearOf(s) {
    var m = /^(\d{4})-\d{2}$/.exec(s);
    return m ? m[1] : null;
  }
  function tickLabel(s, lastYear) {
    // 연도가 바뀌는 지점(및 첫 눈금)에만 연도를 함께 표시: "’25 8월" / 그 외 "8월"
    var m = /^(\d{4})-(\d{2})$/.exec(s);
    if (!m) return s;
    var mon = parseInt(m[2], 10) + "월";
    return m[1] !== lastYear ? "’" + m[1].slice(2) + " " + mon : mon;
  }

  global.Charts = { line: lineChart, stackBar: stackBar, donut: donut };
})(window);
