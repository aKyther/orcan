// Isolated browser smoke. Requires local Playwright/Chromium, never a live executor.
const {chromium} = require('playwright');
const {spawn, spawnSync} = require('node:child_process');
const {mkdtempSync, rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const {join} = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');

(async () => {
  const root = mkdtempSync(join(tmpdir(), 'orcan-dashboard-smoke-'));
  const env = {...process.env, ORCAN_EXECUTOR_STATE_DIR: root, TTYD_CREDENTIAL: ''};
  let server, browser;
  try {
    const fixture = `
from pathlib import Path
from orcan_executor import store
job=dict(id='fixture',repo='/fixture/project',git_dir='/fixture/git',sha='a'*40,task='Fixture build',profile='build',lane='heavy',selectors=[],timeout=30)
store.create(job)
store.start('fixture',Path('/fixture/worktree'))
store.finish('fixture','passed',dict(tests=0,passed=0,failed=0,errors=0,skipped=0,seconds=5,metrics=dict(log_bytes=1000000,log_lines=1000,queue_seconds=1,executor_cpu_seconds=0.01,child_cpu_seconds=2)),Path('/fixture/report.json'))
store.create(job | dict(id='recovered',repo='unknown (restored from Redis AOF)',task='Recovered fixture'))
store.finish('recovered','passed',dict(tests=3,seconds=0,metrics=dict(log_bytes=100,result_bytes=10)),None)
with store.database() as db:
    db.execute("UPDATE jobs SET details_expired=1,report=NULL WHERE id='recovered'")
store.create(job | dict(id='obsolete',sha='c'*40,task='Superseded fixture',replace_group='fixture-build',replace_owner=''))
with store.database() as db:
    db.execute("UPDATE jobs SET superseded_by='fixture' WHERE id='obsolete'")
    store._finish(db,'obsolete','cancelled',dict(tests=0,passed=0,failed=0,errors=0,skipped=0,superseded_by='fixture'),None)
store.create(job | dict(id='orphan',sha='b'*40,task='Interrupted fixture'))
store.start('orphan',Path('/fixture/interrupted'))
store.save_health(dict(sampled_at=store.now(),status='degraded',ping_ms=.4,redis=dict(used_memory_bytes=900,maxmemory_bytes=1000,aof_enabled=1,aof_write_status='err'),warnings=['aof_write_error','interrupted_jobs'],lanes={},jobs=dict(interrupted=1,oldest_queued_seconds=None,jobs=[dict(id='orphan',sha='b'*40,condition='interrupted')])))

`;
    const seed = spawnSync('uv', ['run', '--project', 'executor', '--locked', 'python', '-c', fixture], {env, encoding:'utf8'});
    assert.equal(seed.status, 0, seed.stderr?.slice(-2000));
    const socket = net.createServer();
    await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
    const port = socket.address().port;
    await new Promise(resolve => socket.close(resolve));
    server = spawn('uv', ['run', '--project', 'executor', '--locked', 'python', '-m', 'uvicorn', 'orcan_executor.web:app', '--host', '127.0.0.1', '--port', String(port)], {env, stdio:'ignore', detached:true});
    const url = `http://127.0.0.1:${port}`;
    for (let n=0; n<50; n++) {
      try {if ((await fetch(url)).ok) break;} catch {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({headless:true});
    const page = await browser.newPage({viewport:{width:1400,height:1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.waitForFunction(() => document.getElementById('passed').textContent === '2');
    assert.equal(await page.locator('canvas').count(), 3);
    assert.ok((await page.locator('#redis-health').innerText()).includes('degraded'));
    assert.ok((await page.locator('#recovery-candidates').innerText()).includes('orcan-executor recover --job orphan'));
    assert.ok(await page.locator('#timeline-rows tr').count() > 1);
    assert.ok((await page.locator('#coverage-note').innerText()).includes('Zakończone zadania: 3'));
    assert.ok((await page.locator('#coverage-note').innerText()).includes('Odzyskane wpisy: 1'));
    await page.getByText('Dane wykresów i zastosowania', {exact:true}).click();
    assert.ok((await page.locator('#timeline-rows').innerText()).includes('brak pełnych danych'));
    assert.ok(await page.locator('#tasks-chart').evaluate(canvas => canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data.some(value => value !== 0)));
    await page.locator('#jobs tr').first().click();
    assert.ok((await page.locator('#detail').innerText()).includes('heavy'));
    await page.locator('#jobs tr').filter({hasText:'Superseded fixture'}).click();
    assert.ok((await page.locator('#detail').innerText()).includes('Zastąpione przez zadanie'));
    assert.ok((await page.locator('#measurement-note').innerText()).includes('Zastąpione przed uruchomieniem: 1'));
    await page.selectOption('#hours', '720');
    await page.waitForFunction(() => document.getElementById('measurement-note').textContent.includes('720 godzin'));
    await page.screenshot({path: process.env.ORCAN_DASHBOARD_SCREENSHOT || '/tmp/orcan-executor-dashboard.png', fullPage:true});
    await page.setViewportSize({width:420,height:900});
    await page.waitForTimeout(100);
    assert.deepEqual(errors, []);
    console.log('Executor dashboard browser smoke passed: charts, table, details, time window, narrow viewport');
  } finally {
    if (browser) await browser.close();
    if (server && server.exitCode === null) {process.kill(-server.pid, 'SIGTERM'); await new Promise(resolve => server.once('exit', resolve));}
    rmSync(root, {recursive:true, force:true});
  }
})().catch(error => {console.error(error);process.exitCode=1;});
