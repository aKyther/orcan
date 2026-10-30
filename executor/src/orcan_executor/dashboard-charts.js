'use strict';
// Local assets only. Charts use the same bounded snapshot as the accessible table.
let executorChartSnapshot = null;
function drawExecutorCharts(snapshot) {
  executorChartSnapshot = snapshot;
  const rows = snapshot.timeline || [];
  const configs = [
    ['tasks-chart', [['passed', 'Poprawne', '#5ddbb0'], ['problems', 'Pozostałe', '#ff8c98']], 'zadania'],
    ['bytes-chart', [['log_bytes', 'Pełne logi', '#6aa8ff'], ['returned', 'Wynik + doczytania', '#ebc974']], 'KiB'],
    ['time-chart', [['queue_seconds', 'Śr. kolejka', '#ebc974'], ['run_seconds', 'Śr. wykonanie', '#5ddbb0']], 's'],
  ];
  for (const [id, series, unit] of configs) {
    const canvas = document.getElementById(id);
    if (!canvas) continue;
    const width = Math.max(280, canvas.getBoundingClientRect().width);
    const height = 210, ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio; canvas.height = height * ratio;
    const ctx = canvas.getContext('2d');
    if (!ctx) continue;
    ctx.scale(ratio, ratio); ctx.font = '11px system-ui';
    ctx.fillStyle = '#91a0b9';
    if (!rows.length) {ctx.fillText('Brak zakończonych zadań w tym okresie.', 16, 100); continue;}
    const value = (row, key) => (key === 'returned' ? row.result_bytes + row.detail_wire_bytes : row[key]) / (unit === 'KiB' ? 1024 : 1);
    const maximum = Math.max(1, ...rows.flatMap(row => series.map(([key]) => value(row, key))));
    const left = 52, top = 32, bottom = 174, plotWidth = width - left - 12;
    ctx.fillText(unit, 4, 15);
    for (let n = 0; n <= 4; n++) {
      const y = bottom - (bottom - top) * n / 4;
      ctx.strokeStyle = '#24314a'; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - 8, y); ctx.stroke();
      ctx.fillStyle = '#91a0b9'; ctx.fillText((maximum * n / 4).toFixed(maximum < 10 ? 1 : 0), 3, y + 4);
    }
    const first = rows[0].bucket, span = Math.max(snapshot.timeline_bucket_seconds || 300, rows.at(-1).bucket - first);
    for (const [index, [key, label, color]] of series.entries()) {
      ctx.fillStyle = color; ctx.fillText(label, left + index * Math.max(110, plotWidth / 2), 15);
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
      rows.forEach((row, n) => {
        const x = left + (row.bucket - first) / span * plotWidth;
        const y = bottom - value(row, key) / maximum * (bottom - top);
        if (!n) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
      for (const row of rows) {
        const x = left + (row.bucket - first) / span * plotWidth;
        const y = bottom - value(row, key) / maximum * (bottom - top);
        ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.fillStyle = '#91a0b9';
    const label = bucket => new Date(bucket * 1000).toLocaleString([], {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    ctx.fillText(label(first), left, 199);
    ctx.textAlign = 'right'; ctx.fillText(label(rows.at(-1).bucket), width - 8, 199);
  }
  const body = document.getElementById('timeline-rows');
  if (body) {
    body.replaceChildren();
    for (const row of rows) {
      const tr = document.createElement('tr');
      for (const value of [new Date(row.bucket * 1000).toLocaleString(), row.jobs, row.log_bytes, row.result_bytes + row.detail_wire_bytes, row.queue_seconds.toFixed(2), row.run_seconds.toFixed(2)]) {
        const td = document.createElement('td'); td.textContent = String(value); tr.append(td);
      }
      body.append(tr);
    }
  }
}
window.addEventListener('resize', () => {if (executorChartSnapshot) drawExecutorCharts(executorChartSnapshot);});
