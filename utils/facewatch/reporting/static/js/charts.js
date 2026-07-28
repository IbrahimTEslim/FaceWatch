// Global Chart.js dark theme defaults
Chart.defaults.color          = '#888';
Chart.defaults.borderColor    = '#1e1e1e';
Chart.defaults.font.family    = 'Inter, sans-serif';
Chart.defaults.font.size      = 12;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#1a1a1a';
Chart.defaults.plugins.tooltip.borderColor      = '#2a2a2a';
Chart.defaults.plugins.tooltip.borderWidth      = 1;
Chart.defaults.plugins.tooltip.titleColor       = '#f0f0f0';
Chart.defaults.plugins.tooltip.bodyColor        = '#aaa';
Chart.defaults.plugins.tooltip.padding          = 10;
Chart.defaults.plugins.tooltip.cornerRadius     = 8;

const ACCENT  = '#00dcb4';
const RED     = '#e05050';
const YELLOW  = '#f0c040';
const MUTED   = '#2a2a2a';

function accentGradient(ctx, alpha1 = 0.35, alpha2 = 0.0) {
  const g = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
  g.addColorStop(0, `rgba(0,220,180,${alpha1})`);
  g.addColorStop(1, `rgba(0,220,180,${alpha2})`);
  return g;
}

// ── Focus line chart ──────────────────────────────────────────────────────────
function initFocusChart(canvasId, hours, scores) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: hours.map(h => h + ':00'),
      datasets: [{
        data: scores,
        borderColor: ACCENT,
        borderWidth: 2,
        backgroundColor: accentGradient(ctx),
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: ACCENT,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 100, grid: { color: '#1e1e1e' },
             ticks: { callback: v => v + '%' } },
        x: { grid: { display: false } }
      }
    }
  });
}

// ── Gaze off-screen bar chart ─────────────────────────────────────────────────
function initGazeChart(canvasId, hours, offSecs) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: hours.map(h => h + ':00'),
      datasets: [{
        data: offSecs,
        backgroundColor: `rgba(224,80,80,0.7)`,
        borderRadius: 4,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { grid: { color: '#1e1e1e' },
             ticks: { callback: v => v + 's' } },
        x: { grid: { display: false } }
      }
    }
  });
}

// ── Expression doughnut ───────────────────────────────────────────────────────
function initExpressionChart(canvasId, data) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Neutral', 'Drowsy', 'Smile', 'Angry', 'Surprised'],
      datasets: [{
        data: [
          data.neutral_pct, data.drowsy_pct,
          data.smile_count, data.angry_count, data.surprised_count
        ],
        backgroundColor: [ACCENT, YELLOW, '#60d0a0', RED, '#a080f0'],
        borderWidth: 0,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '68%',
      plugins: { legend: { display: true, position: 'right',
        labels: { boxWidth: 10, padding: 12, color: '#aaa' } } }
    }
  });
}

// ── Blink rate line chart ─────────────────────────────────────────────────────
function initBlinkChart(canvasId, hours, left, right) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: hours.map(h => h + ':00'),
      datasets: [
        { label: 'Left',  data: left,  borderColor: ACCENT, borderWidth: 2,
          tension: 0.4, pointRadius: 2, fill: false },
        { label: 'Right', data: right, borderColor: '#a080f0', borderWidth: 2,
          tension: 0.4, pointRadius: 2, fill: false },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: true,
        labels: { boxWidth: 10, padding: 12, color: '#aaa' } } },
      scales: {
        y: { grid: { color: '#1e1e1e' } },
        x: { grid: { display: false } }
      }
    }
  });
}

// ── Distance line chart ───────────────────────────────────────────────────────
function initDistanceChart(canvasId, hours, dists, alertCm) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: hours.map(h => h + ':00'),
      datasets: [{
        data: dists,
        borderColor: YELLOW,
        borderWidth: 2,
        backgroundColor: 'rgba(240,192,64,0.08)',
        fill: true,
        tension: 0.4,
        pointRadius: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { grid: { color: '#1e1e1e' },
             ticks: { callback: v => v + ' cm' } },
        x: { grid: { display: false } }
      },
      plugins: {
        annotation: alertCm ? {
          annotations: { line1: {
            type: 'line', yMin: alertCm, yMax: alertCm,
            borderColor: RED, borderWidth: 1, borderDash: [4, 4],
          }}
        } : {}
      }
    }
  });
}

// ── App usage doughnut ────────────────────────────────────────────────────────
function initAppsChart(canvasId, categories, seconds) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  const palette = [ACCENT, '#a080f0', YELLOW, RED, '#60d0a0', '#f08060', '#80a0f0'];
  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: categories,
      datasets: [{
        data: seconds,
        backgroundColor: palette.slice(0, categories.length),
        borderWidth: 0,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '68%',
      plugins: { legend: { display: true, position: 'right',
        labels: { boxWidth: 10, padding: 12, color: '#aaa' } } }
    }
  });
}

// ── History focus line chart ──────────────────────────────────────────────────
function initHistoryChart(canvasId, days, scores) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: days,
      datasets: [{
        data: scores,
        borderColor: ACCENT,
        borderWidth: 2,
        backgroundColor: accentGradient(ctx),
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointBackgroundColor: ACCENT,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 100, grid: { color: '#1e1e1e' },
             ticks: { callback: v => v + '%' } },
        x: { grid: { display: false } }
      }
    }
  });
}

// ── Heatmap ───────────────────────────────────────────────────────────────────
function initHeatmap(containerId, hours, scores) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const map = {};
  hours.forEach((h, i) => { map[parseInt(h)] = scores[i]; });
  const max = Math.max(...scores, 1);
  for (let h = 0; h < 24; h++) {
    const cell = container.querySelector(`[data-hour="${h}"]`);
    if (!cell) continue;
    const val = map[h] ?? 0;
    const t   = val / max;
    cell.style.background = val === 0
      ? 'var(--surface2)'
      : `rgba(0,220,180,${0.15 + t * 0.85})`;
    cell.title = `${h}:00 — Focus ${val}%`;
  }
}
