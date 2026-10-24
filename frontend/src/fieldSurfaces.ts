import * as THREE from 'three';

// RMUC 2027 field surfaces after manual figures 4-1..4-3: mottled grey concrete on the highlands and kerbs, a near-black
// floor with fine light speckle. Each set has a colour map, a bump map (pits and grain) and a roughness map, so the key
// light and the environment break up across the surface instead of shading it flat. Every map tiles.
export interface SurfaceSet {map:THREE.CanvasTexture;bump:THREE.CanvasTexture;rough:THREE.CanvasTexture}

const SIZE=1024;
const random=(seed:number)=>{let s=seed>>>0||1;return()=>{s=(s*1664525+1013904223)>>>0;return s/4294967296;};};

// Tileable value noise in [0,1]: a cells x cells random lattice upscaled by the canvas's smoothing, with a one-cell
// wrapped border so opposite edges meet.
function lattice(cells:number,next:()=>number){
  const n=cells+2,small=document.createElement('canvas');small.width=small.height=n;const ctx=small.getContext('2d')!;
  const values=Array.from({length:cells*cells},next),image=ctx.createImageData(n,n);
  for(let y=0;y<n;y++)for(let x=0;x<n;x++){const v=values[((y-1+cells)%cells)*cells+(x-1+cells)%cells]*255,o=(y*n+x)*4;image.data[o]=image.data[o+1]=image.data[o+2]=v;image.data[o+3]=255;}
  ctx.putImageData(image,0,0);
  const big=document.createElement('canvas');big.width=big.height=SIZE;const out=big.getContext('2d')!;out.imageSmoothingEnabled=true;out.imageSmoothingQuality='high';
  out.drawImage(small,1,1,cells,cells,0,0,SIZE,SIZE);
  const data=out.getImageData(0,0,SIZE,SIZE).data,field=new Float32Array(SIZE*SIZE);
  for(let i=0;i<field.length;i++)field[i]=data[i*4]/255;
  return field;
}
// Fractal sum of lattices: weights per cell count, normalised to [-1, 1] around zero.
function fbm(octaves:[number,number][],next:()=>number){
  const sum=new Float32Array(SIZE*SIZE);let total=0;
  for(const [cells,weight] of octaves){const f=lattice(cells,next);total+=weight;for(let i=0;i<sum.length;i++)sum[i]+=(f[i]-.5)*2*weight;}
  for(let i=0;i<sum.length;i++)sum[i]/=total;
  return sum;
}
// Sparse round dots (pits or flecks) of 1..r px, wrapped at the edges.
function dots(count:number,radius:number,next:()=>number){
  const out=new Float32Array(SIZE*SIZE);
  for(let k=0;k<count;k++){const cx=next()*SIZE,cy=next()*SIZE,r=.6+next()*radius,depth=.5+next()*.5;
    for(let dy=-Math.ceil(r);dy<=Math.ceil(r);dy++)for(let dx=-Math.ceil(r);dx<=Math.ceil(r);dx++){const d=Math.hypot(dx,dy);if(d>r)continue;
      const x=(Math.floor(cx)+dx+SIZE)%SIZE,y=(Math.floor(cy)+dy+SIZE)%SIZE;out[y*SIZE+x]=Math.max(out[y*SIZE+x],depth*(1-d/(r+.5)));}}
  return out;
}
function texture(values:(i:number)=>[number,number,number],srgb:boolean,repeat:number){
  const canvas=document.createElement('canvas');canvas.width=canvas.height=SIZE;const ctx=canvas.getContext('2d')!,image=ctx.createImageData(SIZE,SIZE);
  for(let i=0;i<SIZE*SIZE;i++){const [r,g,b]=values(i);image.data[i*4]=r;image.data[i*4+1]=g;image.data[i*4+2]=b;image.data[i*4+3]=255;}
  ctx.putImageData(image,0,0);
  const t=new THREE.CanvasTexture(canvas);t.colorSpace=srgb?THREE.SRGBColorSpace:THREE.NoColorSpace;t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(repeat,repeat);t.anisotropy=8;return t;
}
const hex=(c:string)=>[parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16)] as const;

// Highland and kerb concrete: broad blotches, medium mottling, fine aggregate and pores. The field UVs carry 0.4 per
// metre, so `repeat` 0.42 tiles every 6 m (5.9 mm per pixel).
export function concreteSurface(base:string,seed:number,repeat=.42):SurfaceSet{
  const next=random(seed),blotch=fbm([[3,1],[5,.8],[9,.55]],next),mottle=fbm([[17,1],[31,.7]],next),grain=fbm([[96,1],[180,.8]],next);
  const pores=dots(1800,1.3,next),voids=dots(140,2.6,next),flecks=dots(700,1,next),[R,G,B]=hex(base);
  const shade=new Float32Array(SIZE*SIZE),noise=new Float32Array(SIZE*SIZE);
  for(let i=0;i<shade.length;i++){noise[i]=next()-.5;shade[i]=1+blotch[i]*.12+mottle[i]*.07+grain[i]*.04+noise[i]*.045-pores[i]*.16-voids[i]*.22+flecks[i]*.08;}
  return {
    map:texture(i=>[R*shade[i],G*shade[i],B*shade[i]],true,repeat),
    // Height: pores and grain low, mottling a gentle swell.
    bump:texture(i=>{const h=128+mottle[i]*22+grain[i]*30+noise[i]*18-pores[i]*55-voids[i]*80;return [h,h,h];},false,repeat),
    // Green channel drives roughness: darker blotches are a little smoother (worn), pores rougher.
    rough:texture(i=>{const r=220+blotch[i]*14+mottle[i]*12+(pores[i]+voids[i])*25;return [0,Math.min(255,Math.max(150,r)),0];},false,repeat),
  };
}

// Floor: near-black, very low mottling and dense light speckle, like the dark floor of the manual's renders.
export function floorSurface(base:string,seed:number,repeat=.5):SurfaceSet{
  const next=random(seed),blotch=fbm([[4,1],[7,.7]],next),grain=fbm([[110,1],[220,.9]],next);
  const speckle=dots(26000,.9,next),[R,G,B]=hex(base);
  const shade=new Float32Array(SIZE*SIZE),noise=new Float32Array(SIZE*SIZE);
  for(let i=0;i<shade.length;i++){noise[i]=next()-.5;shade[i]=1+blotch[i]*.05+grain[i]*.06+noise[i]*.07+speckle[i]*.55;}
  return {
    map:texture(i=>[R*shade[i],G*shade[i],B*shade[i]],true,repeat),
    bump:texture(i=>{const h=128+grain[i]*36+noise[i]*28+speckle[i]*40;return [h,h,h];},false,repeat),
    rough:texture(i=>{const r=212+blotch[i]*10+grain[i]*8-speckle[i]*30;return [0,Math.min(255,Math.max(150,r)),0];},false,repeat),
  };
}

export function disposeSurface(s:SurfaceSet){s.map.dispose();s.bump.dispose();s.rough.dispose();}
