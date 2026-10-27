/* CareQual QMS - chart rendering. Data comes from Flask as JSON (#chart-data); colours come from the CSS theme. */
(function () {
  'use strict';
  if (typeof Chart === 'undefined') return;
  var dataEl = document.getElementById('chart-data');
  if (!dataEl) return;
  var DATA = JSON.parse(dataEl.textContent);
  var charts = [];
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var css = function (name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); };
  var toneColor = function (tone) { return css('--c-' + (tone || 'neutral')) || css('--c-neutral'); };
  var SEVERITY_TONE = { Critical: 'danger', High: 'orange', Medium: 'warning', Low: 'info' };

  var centerText = {
    id: 'centerText',
    afterDraw: function (chart) {
      var el = chart.canvas, text = el.getAttribute('data-center');
      if (!text) return;
      var a = chart.chartArea, x = (a.left + a.right) / 2, y = (a.top + a.bottom) / 2, ctx = chart.ctx;
      ctx.save(); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillStyle = css('--text'); ctx.font = '600 26px Sora, "IBM Plex Sans", sans-serif'; ctx.fillText(text, x, y - 7);
      ctx.fillStyle = css('--muted'); ctx.font = '12px "IBM Plex Sans", sans-serif'; ctx.fillText(el.getAttribute('data-center-label') || '', x, y + 15);
      ctx.restore();
    }
  };

  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  function legend(key, rows) {
    var ul = document.querySelector('[data-legend="' + key + '"]'); if (!ul) return;
    var total = rows.reduce(function (n, r) { return n + (r.total != null ? r.total : r.value); }, 0);
    ul.innerHTML = rows.map(function (r) {
      var pct = total ? Math.round((r.total != null ? r.total : r.value) / total * 100) : 0;
      return '<li><span class="sw" style="background:' + r.color + '"></span><span class="lb">' + esc(r.label) + '</span>' +
        '<span class="n">' + r.value + '</span><span class="p">' + (r.suffix != null ? esc(r.suffix) : pct + '%') + '</span></li>';
    }).join('');
  }

  function showEmpty(canvas, text) {
    var box = canvas.parentElement;
    box.innerHTML = '<div class="chart-empty"><span>' + esc(text) + '</span></div>';
    var ul = document.querySelector('[data-legend="' + canvas.getAttribute('data-chart') + '"]'); if (ul) ul.innerHTML = '';
  }

  function base() {
    return {
      responsive: true, maintainAspectRatio: false,
      animation: reduceMotion ? false : { duration: 450 },
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: css('--surface-3'), titleColor: css('--text'), bodyColor: css('--text-2'), borderColor: css('--line'), borderWidth: 1, padding: 10, cornerRadius: 8, displayColors: true, boxPadding: 4 }
      }
    };
  }

  function build() {
    charts.forEach(function (c) { c.destroy(); }); charts = [];
    Chart.defaults.font.family = '"IBM Plex Sans", system-ui, sans-serif';
    Chart.defaults.color = css('--text-2');
    document.querySelectorAll('canvas[data-chart]').forEach(function (canvas) {
      var key = canvas.getAttribute('data-chart'), type = canvas.getAttribute('data-type'), d = DATA[key];
      if (!d) return;
      var emptyText = canvas.getAttribute('data-empty') || 'No data recorded yet';
      var sum = (d.values || []).reduce(function (a, b) { return a + b; }, 0) + (d.open || []).reduce(function (a, b) { return a + b; }, 0) + (d.closed || []).reduce(function (a, b) { return a + b; }, 0);
      if (!sum) { if (!canvas.parentElement.querySelector('.chart-empty')) showEmpty(canvas, emptyText); return; }
      var colors = (d.tones || []).map(toneColor), opts = base(), cfg;

      if (type === 'doughnut') {
        opts.cutout = '72%';
        cfg = { type: 'doughnut', plugins: [centerText], options: opts,
          data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: colors, borderColor: css('--surface'), borderWidth: 3, hoverOffset: 4 }] } };
        legend(key, d.labels.map(function (l, i) { return { label: l, value: d.values[i], color: colors[i] }; }));
      } else if (type === 'hbar') {
        opts.indexAxis = 'y';
        opts.scales = { x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: css('--line-soft') }, border: { display: false } },
                        y: { grid: { display: false }, border: { display: false } } };
        cfg = { type: 'bar', options: opts,
          data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: colors, borderRadius: 5, barThickness: 18 }] } };
        legend(key, d.labels.map(function (l, i) { return { label: l, value: d.values[i], color: colors[i] }; }));
      } else if (type === 'severity') {
        var sevColors = d.labels.map(function (l) { return toneColor(SEVERITY_TONE[l]); });
        opts.scales = { x: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0 } },
                        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, grid: { color: css('--line-soft') }, border: { display: false } } };
        cfg = { type: 'bar', options: opts, data: { labels: d.labels, datasets: [
          { label: 'Not closed', data: d.open, backgroundColor: sevColors, borderRadius: 4, maxBarThickness: 46 },
          { label: 'Closed', data: d.closed, backgroundColor: toneColor('neutral') + '66', borderRadius: 4, maxBarThickness: 46 } ] } };
        legend(key, d.labels.map(function (l, i) {
          return { label: l, value: d.open[i], total: d.open[i] + d.closed[i], color: sevColors[i], suffix: 'of ' + (d.open[i] + d.closed[i]) };
        }));
      }
      if (cfg) charts.push(new Chart(canvas.getContext('2d'), cfg));
    });
  }

  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(build);
  document.addEventListener('cq:theme', build);
})();
