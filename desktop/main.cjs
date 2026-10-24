const electron = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const {Backend, runtimeLayout} = require('./backend.cjs');

// Under `ELECTRON_RUN_AS_NODE` the module resolves to the binary path, so the app would crash on the
// first `app` call; say what went wrong instead.
if (typeof electron === 'string') {
  console.error('Arena-1 needs the Electron runtime, not Node. Start it with `python scripts/project.py desktop` or `bun run desktop:dev`.');
  process.exit(1);
}
const {app, BrowserWindow, Menu, dialog, shell, session} = electron;

app.setName('Arena-1');
if (process.env.RMUC_DESKTOP_DATA) app.setPath('userData', path.resolve(process.env.RMUC_DESKTOP_DATA));
const smoke = process.argv.includes('--smoke-test');
if (!app.requestSingleInstanceLock()) app.quit();
else {
  let window, backend, quitting = false, stopped = false, restarting = false;
  const dataDir = app.getPath('userData');
  const settingsFile = path.join(dataDir, 'desktop-settings.json');
  let sandbox = 'trusted-local';
  try {if (JSON.parse(fs.readFileSync(settingsFile, 'utf8')).sandbox === 'docker') sandbox = 'docker';} catch {}
  const docs = 'https://rm-arena.github.io/Arena-1/';
  const layout = runtimeLayout({packaged: app.isPackaged, resourcesPath: process.resourcesPath, projectRoot: path.resolve(__dirname, '..')});

  function menu() {
    const execution = value => ({label: value === 'docker' ? 'Docker 隔离 / Container isolation' : '可信本地策略 / Trusted local policies', type: 'radio', checked: sandbox === value,
      click: async () => {
        if (sandbox === value || restarting) return;
        const answer = await dialog.showMessageBox(window, {type:'question', buttons:['切换并重启 / Restart','取消 / Cancel'], defaultId:1, cancelId:1,
          message:'切换执行模式会停止当前比赛。 / Switching mode stops the current match.'});
        if (answer.response !== 0) {menu(); return;}
        sandbox = value; fs.writeFileSync(settingsFile, JSON.stringify({sandbox}, null, 2));
        restarting = true; await backend.stop(); restarting = false;
        try {await start();} catch (error) {dialog.showErrorBox('Arena-1', error.message); app.quit();}
      }});
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      ...(process.platform === 'darwin' ? [{role:'appMenu'}] : []),
      {label:'文件 / File', submenu:[{label:'打开数据目录 / Open data folder',click:()=>shell.openPath(dataDir)}, {type:'separator'}, {role:'quit'}]},
      {label:'执行模式 / Execution',submenu:[execution('trusted-local'), execution('docker')]},
      {label:'编辑 / Edit',submenu:[{role:'undo'},{role:'redo'},{type:'separator'},{role:'cut'},{role:'copy'},{role:'paste'},{role:'selectAll'}]},
      {label:'视图 / View',submenu:[{role:'reload'},{role:'togglefullscreen'},{role:'resetZoom'},{role:'zoomIn'},{role:'zoomOut'},...(!app.isPackaged?[{role:'toggleDevTools'}]:[])]},
      {label:'帮助 / Help',submenu:[{label:'项目文档 / Documentation',click:()=>shell.openExternal(docs)},
        {label:'许可证 / License',click:()=>shell.openPath(path.join(layout.root,'LICENSE'))},
        {label:'关于 / About',click:()=>dialog.showMessageBox(window,{message:`Arena-1 ${app.getVersion()}`,detail:'非商业学习专用 / Non-commercial learning only\nRust simulation · Python policies · React Three Fiber\nDefault local mode executes trusted code on this computer.'})}]},
    ]));
  }
  async function start() {
    backend = new Backend(layout, dataDir, sandbox);
    backend.on('crash', ({logs}) => {
      if (!quitting && !restarting) {dialog.showErrorBox('Arena-1 backend stopped', logs || 'The local backend stopped unexpectedly.'); app.quit();}
    });
    const url = await backend.start();
    if (!window || window.isDestroyed()) {
      window = new BrowserWindow({width:1600,height:1000,minWidth:1000,minHeight:680,show:false,backgroundColor:'#08131c',
        webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true,backgroundThrottling:false}});
      window.webContents.setWindowOpenHandler(({url:target}) => {
        if (target.startsWith(docs)) shell.openExternal(target);
        return {action:'deny'};
      });
      window.webContents.on('will-navigate', (event, target) => {if (new URL(target).origin !== backend.url) event.preventDefault();});
      window.webContents.on('will-attach-webview', event => event.preventDefault());
      window.on('closed', () => {window = null; app.quit();});
    }
    await window.loadURL(url);
    window.show(); menu();
    if (smoke) {
      const result = await window.webContents.executeJavaScript(`new Promise((resolve,reject)=>{
        const end=Date.now()+60000;const check=()=>{const d=window.arenaDiagnostics?.();
          if(d?.connected&&d.engine==='rust')resolve({engine:d.engine,robots:d.robots,url:location.origin,webgl:!!document.createElement('canvas').getContext('webgl2')});
          else if(Date.now()>end)reject(new Error('Renderer did not connect'));else setTimeout(check,100);};check();})`);
      const health = await window.webContents.executeJavaScript('fetch("/api/health").then(response=>response.json())');
      result.season = health.season;
      result.version = health.version;
      if (result.robots !== health.team_size * 2 || !result.webgl) throw new Error('Desktop renderer failed: '+JSON.stringify(result));
      if (process.env.RMUC_SMOKE_SCREENSHOT) {
        await new Promise(resolve=>setTimeout(resolve,2500));
        fs.writeFileSync(process.env.RMUC_SMOKE_SCREENSHOT,(await window.webContents.capturePage()).toPNG());
      }
      console.log('ARENA_SMOKE_RESULT='+JSON.stringify(result)); app.quit();
    }
  }
  app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.focus();}});
  app.on('before-quit', event => {
    quitting = true;
    if (!stopped) {event.preventDefault(); stopped = true; Promise.resolve(backend?.stop()).finally(()=>app.quit());}
  });
  app.whenReady().then(async()=>{
    // The cockpit captures the mouse with the Pointer Lock API. Electron routes that through the
    // permission handlers, so denying everything but fullscreen left desktop aiming on the
    // pointer-capture fallback: the cursor stayed visible and could leave the window. Grant
    // `pointerLock` to the app's own page; the OS then hides and confines the cursor while piloting.
    const permitted = (contents, permission) => !!backend?.url &&
      contents?.getURL().startsWith(backend.url + '/') && ['fullscreen','pointerLock','clipboard-sanitized-write'].includes(permission);
    session.defaultSession.setPermissionRequestHandler((contents,permission,callback)=>callback(permitted(contents,permission)));
    session.defaultSession.setPermissionCheckHandler((contents,permission)=>permitted(contents,permission));
    session.defaultSession.on('will-download', (_event,item)=>{
      item.setSaveDialogOptions({defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))});
    });
    await start();
  }).catch(async error=>{console.error(error);if(!smoke)dialog.showErrorBox('Arena-1 could not start',error.message);quitting=true;await backend?.stop();app.exit(1);});
}
