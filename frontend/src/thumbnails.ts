import * as THREE from 'three';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';
import type {TeamId} from './types';
import {LED_COLORS,cloneForTeam} from './teamMaterials';
import {fitCustomModel,isCustomAsset} from './customModels';

// Studio renders of the robot GLBs for broadcast cards and the MVP screen, from one shared offscreen renderer.
const SIZES={card:[360,240],showcase:[1100,900]} as const;
export type ImageSize=keyof typeof SIZES;
const images=new Map<string,Promise<string>>(),models=new Map<string,Promise<THREE.Object3D>>(),loader=new GLTFLoader();
let renderer:THREE.WebGLRenderer|null=null,queue:Promise<unknown>=Promise.resolve();

const model=(url:string)=>{let m=models.get(url);if(!m){m=loader.loadAsync(url).then(g=>isCustomAsset(url)?fitCustomModel(g.scene,url):g.scene);models.set(url,m);}return m;};

async function render(url:string,team:TeamId,size:ImageSize){
  const [w,h]=SIZES[size],source=await model(url);
  if(!renderer){renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,preserveDrawingBuffer:true});renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;renderer.outputColorSpace=THREE.SRGBColorSpace;}
  renderer.setPixelRatio(1);renderer.setSize(w,h,false);renderer.setClearColor(0x000000,0);
  const scene=new THREE.Scene(),robot=cloneForTeam(source,team);scene.add(robot);
  scene.add(new THREE.HemisphereLight('#dfe9f2','#1a1d22',2.1));
  const key=new THREE.DirectionalLight('#ffffff',3.2);key.position.set(3,5,4);scene.add(key);
  const rim=new THREE.DirectionalLight(LED_COLORS[team],4);rim.position.set(-4,2.5,-3);scene.add(rim);
  const box=new THREE.Box3().setFromObject(robot),center=box.getCenter(new THREE.Vector3()),extent=box.getSize(new THREE.Vector3());
  const camera=new THREE.PerspectiveCamera(26,w/h,.01,50),radius=Math.max(extent.x,extent.y*1.15,extent.z)*.62;
  const distance=radius/Math.sin(THREE.MathUtils.degToRad(13))*(size==='card'?1.02:.94);
  camera.position.copy(center).add(new THREE.Vector3(.95,.55,.85).normalize().multiplyScalar(distance));camera.lookAt(center.x,center.y-extent.y*.04,center.z);
  renderer.render(scene,camera);
  const png=renderer.domElement.toDataURL('image/png');
  robot.traverse(o=>{if(o instanceof THREE.Mesh)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose());});
  return png;
}

export function robotImage(url:string,team:TeamId,size:ImageSize='card'){
  const key=`${url}|${team}|${size}`;let image=images.get(key);
  if(!image){
    image=queue.then(()=>render(url,team,size));queue=image.catch(()=>undefined);images.set(key,image);image.catch(()=>images.delete(key));
  }
  return image;
}
