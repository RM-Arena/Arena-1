const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

// `require('electron')` returns the binary path when this file runs under plain Node (which is how
// `python scripts/project.py desktop` starts it) and the Electron API when Node mode is left on.
function electronBinary() {
  try {
    const resolved = require('electron');
    if (typeof resolved === 'string' && fs.existsSync(resolved)) return resolved;
  } catch {}
  const name = process.platform === 'win32' ? 'electron.exe'
    : process.platform === 'darwin' ? path.join('Electron.app', 'Contents', 'MacOS', 'Electron')
    : 'electron';
  const fallback = path.join(__dirname, '..', 'node_modules', 'electron', 'dist', name);
  return fs.existsSync(fallback) ? fallback : null;
}

const electron = electronBinary();
if (!electron) {
  console.error('Electron is not installed. Run `bun install` (or `npm install`) in the repository root first.');
  process.exit(1);
}

// Electron reads ELECTRON_RUN_AS_NODE as a flag: an empty value still means "run as Node", so the
// app would load main.cjs without the Electron API and abort on `app.setName`. The variable has to be
// removed from the child environment, not blanked.
const env = {...process.env};
delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electron, ['.', ...process.argv.slice(2)], {stdio:'inherit', cwd:path.resolve(__dirname, '..'), env});
child.once('error', error=>{console.error(error);process.exitCode=1;});
child.once('exit', code=>{process.exitCode=code??1;});
