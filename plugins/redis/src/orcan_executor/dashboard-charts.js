'use strict';
// Local assets only. Charts and the accessible table share one database snapshot.
let executorChartSnapshot = null;
function drawExecutorCharts(snapshot) {
  executorChartSnapshot = snapshot;
  const rows = snapshot.timeline || [];
  const configs = [
    ['tasks-chart', [['passed', 'Poprawne', '#5ddbb0'], ['problems', 'Błędy', '#ff8c98'], ['cancelled', 'Anulowane', '#ebc974']], 'zadania', true],
    ['bytes-chart', [['log_bytes', 'Logi', '#6aa8ff'], ['returned_bytes', 'Wynik + doczytania', '#ebc974']], 'KiB', true],
    ['time-chart', [['queue_seconds', 'Kolejka: średnia', '#ebc974'], ['queue_p95_seconds', 'Kolejka: p95', '#ff8c98'], ['run_seconds', 'Wykonanie: średnia', '#5ddbb0']], 's', false],
  ];
  for (const [id, series, unit, bars] of configs) {
    const canvas = document.getElementById(id);
    if (!canvas) continue;
    const width = Math.max(280, canvas.getBoundingClientRect().width);
    const height = 230, ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio; canvas.height = height * ratio;
    const ctx = canvas.getContext('2d');
    if (!ctx) continue;
    ctx.scale(ratio, ratio); ctx.font = '11px system-ui'; ctx.fillStyle = '#91a0b9';
    if (!rows.some(row => row.jobs > 0)) {ctx.fillText('Brak zakończonych zadań w tym okresie.', 16, 100); continue;}
    // A partial bucket is unknown for that series, never a measured zero.
    const value = (row, key) => {
      const coverage = {log_bytes:'log_jobs', returned_bytes:'return_jobs', queue_seconds:'queue_jobs', queue_p95_seconds:'queue_jobs', run_seconds:'run_jobs'}[key];
      if (coverage && row.jobs && row[coverage] !== row.jobs) return null;
      const raw = row[key];
      return Number.isFinite(raw) ? raw / (unit === 'KiB' ? 1024 : 1) : null;
    };
    const maximum = Math.max(1, ...rows.flatMap(row => series.map(([key]) => value(row, key)).filter(Number.isFinite)));
    const left = 52, top = 60, bottom = 194, plotWidth = width - left - 12;
    const interval = snapshot.timeline_bucket_seconds || 300;
    const first = rows[0].bucket, span = Math.max(interval, rows.at(-1).bucket - first + interval);
    const cell = plotWidth * interval / span;
    const xAt = row => left + (row.bucket - first + interval / 2) / span * plotWidth;
    ctx.fillText(unit, 4, 15);
    for (let n = 0; n <= 4; n++) {
      const y = bottom - (bottom - top) * n / 4;
      ctx.strokeStyle = '#24314a'; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - 8, y); ctx.stroke();
      ctx.fillStyle = '#91a0b9'; ctx.fillText((maximum * n / 4).toFixed(maximum < 10 ? 1 : 0), 3, y + 4);
    }
    for (const [index, [key, label, color]] of series.entries()) {
      ctx.fillStyle = color; ctx.fillText(label, left + (index % 2) * Math.max(110, plotWidth / 2), 15 + Math.floor(index / 2) * 18);
      ctx.strokeStyle = color; ctx.lineWidth = 2;
      let previous = null;
      for (const row of rows) {
        const amount = value(row, key);
        if (amount === null) {previous = null; continue;}
        const x = xAt(row), y = bottom - amount / maximum * (bottom - top);
        if (bars) {
          const barWidth = Math.max(.5, cell * .8 / series.length);
          ctx.fillRect(x - cell * .4 + index * barWidth, y, barWidth, bottom - y);
        } else {
          if (previous && row.bucket - previous.bucket === interval) {
            ctx.beginPath(); ctx.moveTo(previous.x, previous.y); ctx.lineTo(x, y); ctx.stroke();
          }
          ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill();
          previous = {bucket:row.bucket, x, y};
        }
      }
    }
    ctx.fillStyle = '#91a0b9';
    const label = bucket => new Date(bucket * 1000).toLocaleString([], {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    ctx.fillText(label(first), left, 219);
    ctx.textAlign = 'right'; ctx.fillText(label(rows.at(-1).bucket + interval), width - 8, 219);
  }
  const body = document.getElementById('timeline-rows');
  if (body) {
    body.replaceChildren();
    const measured = (value, count, total, digits = 0) => Number.isFinite(value) && count === total ? value.toFixed(digits) : 'brak pełnych danych (' + count + '/' + total + ')';
    for (const row of rows) {
      const tr = document.createElement('tr');
      for (const value of [new Date(row.bucket * 1000).toLocaleString(), row.jobs, row.cancelled,
        measured(row.log_bytes, row.log_jobs, row.jobs), measured(row.returned_bytes, row.return_jobs, row.jobs),
        measured(row.queue_seconds, row.queue_jobs, row.jobs, 2), measured(row.queue_p95_seconds, row.queue_jobs, row.jobs, 2),
        measured(row.run_seconds, row.run_jobs, row.jobs, 2)]) {
        const td = document.createElement('td'); td.textContent = String(value); tr.append(td);
      }
      body.append(tr);
    }
  }
}
window.addEventListener('resize', () => {if (executorChartSnapshot) drawExecutorCharts(executorChartSnapshot);});
