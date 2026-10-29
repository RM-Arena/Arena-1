import {defineConfig} from 'vitepress';

export default defineConfig({
  title:'Arena-1', description:'从零看懂机器人对抗，开发你的策略 · RMUC 2027 / 2026', lang:'zh-CN', base:'/Arena-1/',
  cleanUrls:true, lastUpdated:true, head:[['link',{rel:'icon',href:'/Arena-1/logo.png'}]],
  themeConfig:{
    logo:'/logo.png',
    nav:[{text:'认识比赛',link:'/guide/what-is-arena'},{text:'2027 规则',link:'/guide/rules-2027'},{text:'实际演示',link:'/demo'},{text:'开始使用',link:'/guide/getting-started'},{text:'策略开发',link:'/guide/strategies'}],
    sidebar:[
      {text:'从零认识比赛',items:[{text:'Arena-1 与 RoboMaster',link:'/guide/what-is-arena'},{text:'2027 规则图解',link:'/guide/rules-2027'},{text:'2027 与 2026 对照',link:'/guide/seasons'},{text:'术语速查',link:'/guide/glossary'}]},
      {text:'使用 Arena-1',items:[{text:'安装与第一场比赛',link:'/guide/getting-started'},{text:'训练、对战与回放',link:'/guide/features'},{text:'开发你的第一份策略',link:'/guide/strategies'},{text:'常见问题',link:'/guide/faq'}]},
      {text:'开发与贡献',items:[{text:'从源码运行',link:'/guide/development'},{text:'CLI、并行与强化学习',link:'/guide/cli'},{text:'系统架构',link:'/development/architecture'},{text:'构建与发布',link:'/development/releases'},{text:'许可证与素材',link:'/license'}]},
    ],
    socialLinks:[{icon:'github',link:'https://github.com/RM-Arena/Arena-1'}],
    editLink:{pattern:'https://github.com/RM-Arena/Arena-1/edit/main/site/:path',text:'在 GitHub 上编辑此页'},
    footer:{message:'仅限非商业学习使用 · 商业用途需事先书面授权',copyright:'Copyright © 2026 RM-Arena and contributors'},
    search:{provider:'local'},
    outline:{label:'本页内容',level:[2,3]},
    docFooter:{prev:'上一页',next:'下一页'},
    sidebarMenuLabel:'目录',returnToTopLabel:'返回顶部',lastUpdatedText:'最后更新',
  },
});
