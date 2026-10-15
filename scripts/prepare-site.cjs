const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const source=path.join(root,'docs/media'),target=path.join(root,'site/public/media');
fs.mkdirSync(target,{recursive:true});
fs.cpSync(source,target,{recursive:true});
