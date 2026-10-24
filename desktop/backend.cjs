const {spawn} = require('node:child_process');
const {randomUUID} = require('node:crypto');
const path = require('node:path');
const fs = require('node:fs');
const {EventEmitter} = require('node:events');

function runtimeLayout({packaged, resourcesPath, projectRoot, platform = process.platform}) {
  const base = packaged ? path.join(resourcesPath, 'runtime') : projectRoot;
  return {
    root: packaged ? path.join(base, 'app') : base,
    python: packaged
      ? path.join(base, 'python', ...(platform === 'win32' ? ['python.exe'] : ['bin', 'python3']))
      : process.env.RMUC_PYTHON || path.join(base, '.venv', ...(platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python'])),
  };
}

class Backend extends EventEmitter {
  constructor(layout, dataDir, sandbox, lan = false) {
    super(); Object.assign(this, {layout, dataDir, sandbox, lan, instance: randomUUID(), logs: '', stopping: false});
  }
  async start() {
    if (!fs.existsSync(this.layout.python)) throw new Error('Python runtime missing. Run the setup or desktop:prepare command.');
    const child = this.child = spawn(this.layout.python,
      ['-B', '-X', 'utf8', '-m', 'rmuc_arena.desktop', '--data-dir', this.dataDir, '--sandbox', this.sandbox,
        ...(this.lan ? ['--lan'] : [])], {
        cwd: this.layout.root, windowsHide: true, detached: process.platform !== 'win32', stdio: ['pipe', 'pipe', 'pipe'],
        env: {...process.env, PYTHONUNBUFFERED: '1', PYTHONDONTWRITEBYTECODE: '1', PYTHONUTF8: '1',
          RMUC_RESOURCE_ROOT: this.layout.root, RMUC_USER_DATA: this.dataDir, RMUC_DESKTOP_INSTANCE: this.instance},
      });
    this.exited = new Promise(resolve => child.once('exit', (code, signal) => {
      resolve(); if (!this.stopping) this.emit('crash', {code, signal, logs: this.logs});
    }));
    child.stderr.on('data', data => {this.logs = (this.logs + data).slice(-16000);});
    child.stdin.on('error', () => {});
    const url = await new Promise((resolve, reject) => {
      let pending = '';
      const timer = setTimeout(() => reject(new Error('Backend startup timed out.\n' + this.logs)), 90000);
      const cleanup = () => clearTimeout(timer);
      child.once('error', error => {cleanup(); reject(error);});
      child.once('exit', code => {cleanup(); reject(new Error(`Backend exited (${code}).\n${this.logs}`));});
      child.stdout.on('data', data => {
        pending += data;
        let index;
        while ((index = pending.indexOf('\n')) !== -1) {
          const line = pending.slice(0, index); pending = pending.slice(index + 1);
          try {
            const ready = JSON.parse(line);
            if (ready.desktop_ready && /^http:\/\/127\.0\.0\.1:\d+$/.test(ready.url)) {
              this.lanUrls = Array.isArray(ready.lan_urls) ? ready.lan_urls : [];
              this.pin = ready.pin || null;
              cleanup(); resolve(ready.url);
            }
          } catch { /* Non-protocol log lines are not readiness signals. */ }
        }
      });
    });
    for (let attempt = 0; attempt < 120; attempt++) {
      if (child.exitCode !== null) throw new Error('Backend exited before becoming ready.\n' + this.logs);
      try {
        const response = await fetch(url + '/api/desktop/health', {signal: AbortSignal.timeout(1500)});
        const health = await response.json();
        if (response.ok && health.instance === this.instance && health.engine === 'rust') {this.url = url; return url;}
      } catch { /* The listening socket is reserved before uvicorn is ready. */ }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('Backend health check timed out.\n' + this.logs);
  }
  async stop() {
    this.stopping = true;
    const child = this.child;
    if (!child || child.exitCode !== null) return;
    child.stdin.end('shutdown\n');
    const ended = await Promise.race([this.exited.then(() => true), new Promise(resolve => {
      const timer = setTimeout(() => resolve(false), 15000); timer.unref();
    })]);
    if (!ended) {
      if (process.platform === 'win32') {
        await new Promise(resolve => {const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {windowsHide: true}); killer.once('exit', resolve); killer.once('error', resolve);});
      } else {
        try {process.kill(-child.pid, 'SIGKILL');} catch (error) {if (error.code !== 'ESRCH') throw error;}
      }
      await this.exited;
    }
  }
}
module.exports = {Backend, runtimeLayout};
