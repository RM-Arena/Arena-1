import {defineConfig} from 'vitepress';

export default defineConfig({
  title:'Arena-1', description:'跨平台机器人策略竞技场 · 非商业学习专用', lang:'zh-CN', base:'/Arena-1/',
  cleanUrls:true, lastUpdated:true, head:[['link',{rel:'icon',href:'/Arena-1/logo.png'}]],
  themeConfig:{
    logo:'/logo.png',
    nav:[{text:'实际演示',link:'/demo'},{text:'开始使用',link:'/guide/getting-started'},{text:'策略开发',link:'/guide/strategies'},{text:'工程开发',link:'/development/architecture'}],
    sidebar:[
      {text:'使用 Arena-1',items:[{text:'安装与启动',link:'/guide/getting-started'},{text:'训练、对战与回放',link:'/guide/features'},{text:'开发策略',link:'/guide/strategies'},{text:'常见问题',link:'/guide/faq'}]},
      {text:'开发与贡献',items:[{text:'从源码运行',link:'/guide/development'},{text:'系统架构',link:'/development/architecture'},{text:'构建与发布',link:'/development/releases'},{text:'许可证与素材',link:'/license'}]},
    ],
    socialLinks:[{icon:'github',link:'https://github.com/RM-Arena/Arena-1'}],
    editLink:{pattern:'https://github.com/RM-Arena/Arena-1/edit/main/site/:path',text:'在 GitHub 上编辑此页'},
    footer:{message:'仅限非商业学习使用 · 商业用途需事先书面授权',copyright:'Copyright © 2026 RM-Arena and contributors'},
    search:{provider:'local'},
  },
});
