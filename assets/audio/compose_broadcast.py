"""Compose original non-match broadcast themes using synthesized instruments.

Requires NumPy and ffmpeg only at asset-build time. Runtime playback uses the
exported AAC files. No audio is sampled from the competition soundtrack.
"""
from pathlib import Path
import argparse
import json
import math
import subprocess
import tempfile
import wave
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
SR=44100
TAU=math.tau

def hz(midi):return 440*2**((midi-69)/12)

def envelope(t,attack=.01,release=.08):
    return np.minimum(1,t/max(attack,.001))*np.minimum(1,(t[-1]-t)/max(release,.001))

def instrument(note,length,kind):
    t=np.arange(round(length*SR))/SR;f=hz(note)
    if kind=='pad':
        left=np.zeros(len(t));right=left.copy()
        for h in range(1,7):
            amp=np.exp(-(h*f/1700)**2)/h**1.3
            left+=amp*np.sin(TAU*(f*h*.9992*t+.002*np.sin(TAU*.23*t)))
            right+=amp*np.sin(TAU*(f*h*1.0008*t+.002*np.sin(TAU*.27*t+.7)))
        env=envelope(t,.24,.45)*.22
        return np.column_stack((left*env,right*env))
    if kind=='keys':
        y=(np.sin(TAU*f*t+1.6*np.exp(-t/.14)*np.sin(TAU*2*f*t))+.2*np.sin(TAU*f*3.003*t))*np.exp(-t*3.2)*envelope(t,.007,.07)
    elif kind=='pluck':
        y=(np.sin(TAU*f*t)+.27*np.sin(TAU*2*f*t)+.10*np.sin(TAU*3.01*f*t))*np.exp(-t*7)*envelope(t,.004,.025)
    elif kind=='bass':
        y=(np.sin(TAU*f*t)+.28*np.sin(TAU*2*f*t)+.12*np.sin(TAU*3*f*t))*envelope(t,.008,.055)*np.exp(-t*.9)
    elif kind=='brass':
        y=sum(np.sin(TAU*f*h*t)*np.exp(-(f*h/1600)**2)/h for h in range(1,10))
        y=np.tanh(y*1.4)*envelope(t,.045,.14)*(.8+.2*np.exp(-t*7))
    else:
        y=(np.sin(TAU*f*t)+.15*np.sin(TAU*f*2.01*t))*(.9+.1*np.sin(TAU*4*t))*envelope(t,.045,.16)
    return np.column_stack((y,y))

def drum(kind,rng):
    duration={'kick':.28,'snare':.19,'hat':.08,'tom':.3,'ride':.26}[kind]
    t=np.arange(round(duration*SR))/SR;noise=rng.normal(0,.3,len(t))
    if kind=='kick':
        phase=TAU*(44*t+55*.03*(1-np.exp(-t/.03)))
        y=np.sin(phase)*np.exp(-t*15)+noise*np.exp(-t*180)*.12
    elif kind=='tom':
        phase=TAU*(92*t+58*.045*(1-np.exp(-t/.045)))
        y=np.sin(phase)*np.exp(-t*13)+.23*np.sin(phase*1.66)*np.exp(-t*22)
    else:
        # FFT-shaped noise is band-limited before its musical envelope.
        frequencies=np.fft.rfftfreq(len(noise),1/SR)
        if kind=='snare':shape=np.exp(-(frequencies/5000)**2)*(1-np.exp(-(frequencies/500)**2));decay=28
        elif kind=='hat':shape=(1-np.exp(-(frequencies/4500)**2))*np.exp(-(frequencies/12000)**2);decay=65
        else:shape=(1-np.exp(-(frequencies/2700)**2))*np.exp(-(frequencies/11000)**2);decay=21
        y=np.fft.irfft(np.fft.rfft(noise)*shape,n=len(noise))*np.exp(-t*decay)
        if kind=='snare':y+=.16*np.sin(TAU*175*t)*np.exp(-t*35)
    y*=np.minimum(1,t/.0015)
    return np.column_stack((y,y))

THEMES={
 'lobby':dict(bpm=86,bars=16,key=52,chords=[(0,[0,3,7,14]),(3,[0,4,7,11]),(-2,[0,4,7,14]),(5,[0,3,7,12])],style='lounge',seed=101),
 'hangar':dict(bpm=100,bars=16,key=45,chords=[(0,[0,3,7,14]),(5,[0,4,7,12]),(7,[0,3,7,14]),(3,[0,4,7,11])],style='mechanical',seed=202),
 'self-check':dict(bpm=118,bars=16,key=50,chords=[(0,[0,3,7,12]),(-2,[0,4,7,12]),(-5,[0,4,7,11]),(-7,[0,4,7,12])],style='tension',seed=303),
 'victory':dict(bpm=126,bars=8,key=48,chords=[(0,[0,4,7,12]),(5,[0,4,7,12]),(9,[0,3,7,12]),(7,[0,4,7,14])],style='anthem',seed=404),
 'results':dict(bpm=82,bars=16,key=53,chords=[(0,[0,4,7,11]),(7,[0,4,7,14]),(9,[0,3,7,12]),(5,[0,4,7,11])],style='reflection',seed=505),
 'mvp':dict(bpm=110,bars=12,key=49,chords=[(0,[0,3,7,12]),(-4,[0,4,7,11]),(3,[0,4,7,14]),(-2,[0,4,7,12])],style='spotlight',seed=606),
}

def compose(config):
    beat=60/config['bpm'];bar=beat*4;seconds=bar*config['bars'];n=round(seconds*SR)
    mix=np.zeros((n,2));rng=np.random.default_rng(config['seed']);cache={}
    def add(y,at,gain=1,pan=0):
        data=y*gain*np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)])
        start=round(at*SR)%n;count=min(len(data),n-start);mix[start:start+count]+=data[:count]
        if count<len(data):mix[:len(data)-count]+=data[count:]
    def note(midi,length,kind,at,gain,pan=0):
        key=(midi,round(length,4),kind)
        if key not in cache:cache[key]=instrument(midi,length,kind)
        add(cache[key],at,gain,pan)
    style=config['style']
    motif=[0,7,12,14,7,3,12,7] if style in ('lounge','reflection') else [0,7,12,7,3,10,14,12]
    for i in range(config['bars']):
        root,intervals=config['chords'][(i//2)%4];root+=config['key'];at=i*bar
        for j,step in enumerate(intervals):note(root+step,bar*1.2,'pad',at,.30 if style in ('lounge','reflection') else .23,(j-1.5)*.32)
        bass_gain=.26 if style in ('lounge','reflection') else .32
        bass_pattern=[0,2,3.5] if style in ('lounge','reflection') else [0,1.5,2,2.75,3.5]
        for b in bass_pattern:note(root-12,.48*beat,'bass',at+b*beat,bass_gain)
        for j in range(8):
            pitch=root+12+intervals[(j+i)%len(intervals)]
            kind='keys' if style in ('lounge','reflection') else 'pluck'
            note(pitch,1.5*beat,kind,at+j*.5*beat,.12 if kind=='keys' else .15,(-1 if j%2 else 1)*.32)
        if style in ('anthem','spotlight'):
            third=intervals[1]
            phrase=[7,12,12+third,14,12,7,9,12] if style=='anthem' else [7,12,12+third,14,7,third,0,7]
            for j,b in enumerate([0,.75,1.5,2.5]):
                pitch=root+12+phrase[(i*4+j)%len(phrase)]
                note(pitch,.8*beat,'brass' if style=='anthem' else 'lead',at+b*beat,.19 if style=='anthem' else .21,0)
        elif style=='tension':
            for j,b in enumerate([.25,1.25,2.25,3.25]):note(root+24+intervals[(j+i)%4],.45*beat,'pluck',at+b*beat,.12,(j-1.5)*.25)
        else:
            for j,b in enumerate([.5,2.5]):note(root+24+motif[(i*2+j)%8],1.4*beat,'keys',at+b*beat,.12,-.12 if j else .12)
        if style!='reflection':
            for b in ([0,2] if style=='lounge' else [0,1.75,2,3.5]):add(drum('kick',rng),at+b*beat,.27 if style=='lounge' else .40)
            for b in [1,3]:add(drum('snare',rng),at+b*beat,.23 if style=='lounge' else .42,.07)
            for j in range(8):add(drum('hat',rng),at+j*.5*beat,.13 if style=='lounge' else .20,(1 if j%2 else -1)*.24)
        else:
            for b in [0,2]:add(drum('kick',rng),at+b*beat,.18)
            for b in [1,3]:add(drum('snare',rng),at+b*beat,.13)
            for j in range(4):add(drum('hat',rng),at+(j+.5)*beat,.10,.3)
        if i%4==3:
            for j in range(4):add(drum('tom',rng),at+(3+j*.25)*beat,.20,(-.4+j*.26))
        if i%4==0:add(drum('ride',rng),at,.19,.35)
    # Stereo taps add depth while wrapping their tails across the loop boundary.
    dry=mix.copy()
    for delay,gain,swap in [(.19,.08,True),(.31,.055,False),(.47,.035,True)]:
        tail=np.roll(dry,round(delay*SR),axis=0);mix+=tail[:,::-1] *gain if swap else tail*gain
    mix=np.tanh(mix*.9)
    fade=min(round(.004*SR),n//4);mix[:fade]*=np.linspace(0,1,fade)[:,None];mix[-fade:]*=np.linspace(1,0,fade)[:,None]
    return mix

def countdown():
    n=SR*5;t=np.arange(n)/SR;rng=np.random.default_rng(707)
    pad=sum(np.sin(TAU*hz(p)*t)*(1+.18*np.sin(TAU*.5*t)) for p in (38,45,50,57))*.09
    noise=rng.normal(0,.14,n);freq=np.fft.rfftfreq(n,1/SR)
    noise=np.fft.irfft(np.fft.rfft(noise)*(1-np.exp(-(freq/1800)**2))*np.exp(-(freq/7500)**2),n=n)
    y=pad*(.35+.65*(t/5)**1.6)+noise*(t/5)**2*.5
    result=np.column_stack((y,y))
    for at in np.arange(0,4.7,.5):
        d=drum('tom',rng)*(.22+.18*at/5);a=int(at*SR);result[a:a+len(d)]+=d[:min(len(d),n-a)]
    for at in np.arange(2.5,4.85,.125):
        d=drum('snare',rng)*(.15+.15*(at-2.5)/2.5);a=int(at*SR);count=min(len(d),n-a);result[a:a+count]+=d[:count]
    result=np.tanh(result);result[:220]*=np.linspace(0,1,220)[:,None];result[-660:]*=np.linspace(1,0,660)[:,None]
    return result

def export(name,pcm,out):
    peak=float(np.max(np.abs(pcm)));pcm=pcm/max(peak,.001)*.82
    with tempfile.TemporaryDirectory(prefix='rmuc-music-') as directory:
        wav=Path(directory)/'source.wav'
        with wave.open(str(wav),'wb') as f:
            f.setparams((2,2,SR,len(pcm),'NONE','not compressed'));f.writeframes(np.round(pcm*32767).astype('<i2').tobytes())
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),'-af','loudnorm=I=-18:TP=-1.5:LRA=7','-ar',str(SR),'-c:a','aac','-b:a','160k','-movflags','+faststart','-metadata','title=RMUC '+name,str(out/(name+'.m4a'))],check=True)
    return {'seconds':round(len(pcm)/SR,3),'peak_before_mastering':round(peak,5)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'frontend/public/assets/audio');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    info={}
    for name,config in THEMES.items():
        info[name]={**config,**export(name,compose(config),args.output)};print('Composed',name,info[name]['seconds'],flush=True)
    info['countdown']=export('countdown',countdown(),args.output)
    (args.output/'broadcast-themes.json').write_text(json.dumps(info,indent=2)+'\n')
