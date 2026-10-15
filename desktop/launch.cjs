const {spawn} = require('node:child_process');
const electron = require('electron');
const child = spawn(electron, ['.', ...process.argv.slice(2)], {stdio:'inherit', env:{...process.env,ELECTRON_RUN_AS_NODE:''}});
child.once('error', error=>{console.error(error);process.exitCode=1;});
child.once('exit', code=>{process.exitCode=code??1;});
