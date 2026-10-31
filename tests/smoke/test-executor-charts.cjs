const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

function draw(rows) {
  const calls = {}, table = [];
  const element = () => ({children:[], append(child) {this.children.push(child);}});
  const canvases = Object.fromEntries(['tasks-chart','bytes-chart','time-chart'].map(id => {
    calls[id] = [];
    const ctx = new Proxy({}, {get: (_target, key) => (...args) => calls[id].push([key,...args]), set:()=>true});
    return [id, {getBoundingClientRect:()=>({width:300}), getContext:()=>ctx}];
  }));
  const context = vm.createContext({window:{devicePixelRatio:2,addEventListener(){}},document:{
    getElementById:id => id === 'timeline-rows' ? {replaceChildren(){table.length=0;},append:row=>table.push(row)} : canvases[id],
    createElement:element,
  }});
  vm.runInContext(readFileSync('executor/src/orcan_executor/dashboard-charts.js','utf8'),context);
  context.drawExecutorCharts({timeline:rows,timeline_bucket_seconds:300});
  for (const items of Object.values(calls)) for (const [, ...args] of items)
    for (const arg of args) if (typeof arg === 'number') assert.ok(Number.isFinite(arg));
  return {calls,table};
}
const row = (bucket, overrides={}) => ({bucket,jobs:1,passed:1,problems:0,cancelled:0,
  log_bytes:1024,returned_bytes:100,queue_seconds:2,queue_p95_seconds:3,run_seconds:5,
  log_jobs:1,return_jobs:1,queue_jobs:1,run_jobs:1,...overrides});

test('volume uses bars; cancelled jobs are a separate series and p95 is plotted', () => {
  const {calls,table} = draw([row(300,{passed:0,cancelled:1})]);
  assert.equal(calls['tasks-chart'].filter(c=>c[0]==='fillRect').length,3);
  assert.equal(calls['bytes-chart'].filter(c=>c[0]==='fillRect').length,2);
  assert.equal(calls['time-chart'].filter(c=>c[0]==='arc').length,3);
  assert.equal(table[0].children[2].textContent,'1');
  assert.equal(table[0].children[6].textContent,'3.00');
});

test('partial measurements leave gaps and disclose coverage in the data table', () => {
  const {calls,table} = draw([row(300,{jobs:2})]);
  assert.equal(calls['bytes-chart'].filter(c=>c[0]==='fillRect').length,0);
  assert.equal(calls['time-chart'].filter(c=>c[0]==='arc').length,0);
  assert.match(table[0].children[3].textContent,/1\/2/);
});

test('idle periods break duration lines; measured zero remains a point', () => {
  const {calls} = draw([row(300,{queue_seconds:0}),row(600,{jobs:0,queue_jobs:0,run_jobs:0,queue_seconds:null,queue_p95_seconds:null,run_seconds:null}),row(900)]);
  const time = calls['time-chart'];
  assert.equal(time.filter(c=>c[0]==='arc').length,6);
  assert.equal(time.filter(c=>c[0]==='lineTo').length,5); // Only the five horizontal grid lines.
});

test('empty history renders an explicit empty state', () => {
  const {calls,table} = draw([]);
  assert.equal(table.length,0);
  assert.ok(calls['tasks-chart'].some(c=>c[0]==='fillText' && c[1].includes('Brak zakończonych')));
});
