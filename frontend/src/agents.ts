import type {Metadata,TeamId} from './types';
// Who generated a strategy. Mirrors rmuc_arena/showcase.py: twelve LLM makers plus people and unknown authors.
export type LlmProvider='openai'|'anthropic'|'google'|'meta'|'spacexai'|'moonshot'|'zai'|'xiaomi'|'deepseek'|'qwen'|'tencent-hy'|'bytedance-seed';
export type AgentProvider=LlmProvider|'human'|'unknown';
export interface AgentInfo{provider:AgentProvider;model?:string}
export interface ProviderInfo{name:string;maker:string;color:string;examples:string}
export const LLM_PROVIDERS:LlmProvider[]=['openai','anthropic','google','meta','spacexai','moonshot','zai','xiaomi','deepseek','qwen','tencent-hy','bytedance-seed'];
export const PROVIDERS:Record<AgentProvider,ProviderInfo>={
  openai:{name:'OpenAI',maker:'OpenAI',color:'#10a37f',examples:'GPT · o 系列 · Codex'},
  anthropic:{name:'Anthropic',maker:'Anthropic',color:'#d97757',examples:'Claude Opus · Sonnet · Haiku'},
  google:{name:'Google',maker:'Google DeepMind',color:'#4285f4',examples:'Gemini · Gemma'},
  meta:{name:'Meta',maker:'Meta',color:'#0866ff',examples:'Llama'},
  spacexai:{name:'SpaceXAI',maker:'SpaceX · xAI',color:'#e8e8e8',examples:'Grok'},
  moonshot:{name:'Moonshot',maker:'月之暗面',color:'#7c8cff',examples:'Kimi'},
  zai:{name:'Z.ai',maker:'智谱',color:'#3d6bff',examples:'GLM'},
  xiaomi:{name:'Xiaomi',maker:'小米',color:'#ff6900',examples:'MiMo'},
  deepseek:{name:'DeepSeek',maker:'深度求索',color:'#4d6bfe',examples:'DeepSeek V · R'},
  qwen:{name:'Qwen',maker:'阿里通义',color:'#615ced',examples:'Qwen · QwQ'},
  'tencent-hy':{name:'Tencent HY',maker:'腾讯混元',color:'#0052d9',examples:'Hunyuan'},
  'bytedance-seed':{name:'ByteDance Seed',maker:'字节跳动',color:'#3c8cff',examples:'Seed · 豆包'},
  human:{name:'人类作者',maker:'手写',color:'#e8c36a',examples:'人工编写'},
  unknown:{name:'未标注',maker:'来源未知',color:'#8d98a6',examples:'未标注生成者'},
};
// Same order and patterns as the backend: specific product names first.
const DETECT:[LlmProvider,RegExp][]=[
  ['anthropic',/claude|anthropic|opus|sonnet|haiku|fable/],
  ['openai',/openai|chatgpt|gpt|codex|\bo[1-9](?:-|\b)|davinci/],
  ['google',/gemini|gemma|google|bard|palm|deepmind/],
  ['meta',/llama|meta\b|meta-|meta ai|facebook/],
  ['spacexai',/grok|xai|x\.ai|spacex/],
  ['moonshot',/kimi|moonshot|月之暗面/],
  ['zai',/glm|zhipu|chatglm|z\.ai|\bzai\b|智谱|清言/],
  ['xiaomi',/mimo|xiaomi|小米/],
  ['deepseek',/deepseek|深度求索/],
  ['qwen',/qwen|qwq|tongyi|通义|千问|alibaba|阿里/],
  ['tencent-hy',/hunyuan|混元|tencent|腾讯|\bhy[-\s]?\d|\bhy\b/],
  ['bytedance-seed',/doubao|豆包|seed|bytedance|字节|volc/],
];
export function detectProvider(text:string):LlmProvider|null{const value=text.toLowerCase();return DETECT.find(([,pattern])=>pattern.test(value))?.[0]??null;}
export const providerOf=(agent?:AgentInfo|null):AgentProvider=>agent&&agent.provider in PROVIDERS?agent.provider:'unknown';
export const agentLabel=(agent?:AgentInfo|null)=>agent?.model||PROVIDERS[providerOf(agent)].name;
export const sameAgent=(a?:AgentInfo|null,b?:AgentInfo|null)=>providerOf(a)===providerOf(b)&&(a?.model||'')===(b?.model||'');

// Per-robot agents of a match. Older replays carry none and fall back to the team emblem.
export type RobotAgent=AgentInfo&{strategy?:string};
const OPUS_2027:AgentInfo={provider:'anthropic',model:'Claude Opus 5.5'};
// Earlier replays used the bundle category as the author. Correct known 2027
// examples while leaving user submissions and their recorded model untouched.
function recordedAgent(agent:RobotAgent|null|undefined,metadata:Metadata|null|undefined,team:TeamId):RobotAgent|null{
  const name=agent?.strategy||metadata?.teams[team]?.name||'';
  const legacy=agent?.provider as string|undefined;
  const known2027=[name,metadata?.teams[team]?.name||''].some(n=>/^official_2027_(?:team|hold|squad|distributed|adaptive_\d+(?:_(?:assault|guard))?)$/.test(n));
  if(legacy==='official')return {...agent,...(known2027||metadata?.season==='2027'||metadata?.map==='rmuc2027'?OPUS_2027:{provider:'unknown' as const})};
  if(!agent&&known2027)return {...OPUS_2027,strategy:name};
  return agent??null;
}
export function robotAgent(metadata:Metadata|null|undefined,team:TeamId,slot:number):RobotAgent|null{
  const agents=metadata?.agents?.[team];return recordedAgent(agents?.[String(slot)]??metadata?.teams[team]?.agent,metadata,team);
}
// One agent, several (shown with the mixed emblem), or none recorded.
export function teamAgents(metadata:Metadata|null|undefined,team:TeamId):RobotAgent[]{
  const per=metadata?.agents?.[team],raw=per?Object.values(per):[metadata?.teams[team]?.agent],list=raw.map(a=>recordedAgent(a,metadata,team)).filter((a):a is RobotAgent=>a!==null);
  return list.filter((a,i)=>list.findIndex(b=>sameAgent(a,b))===i);
}
export function teamEmblem(metadata:Metadata|null|undefined,team:TeamId):AgentProvider|'mixed'|null{
  const agents=teamAgents(metadata,team);if(!agents.length)return null;
  return new Set(agents.map(providerOf)).size>1?'mixed':providerOf(agents[0]);
}
