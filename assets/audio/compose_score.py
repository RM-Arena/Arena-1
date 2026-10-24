"""Compose the menu theme, the post-match statistics theme and the MVP theme.

Hybrid orchestral cues synthesized from scratch at asset-build time, without samples: detuned band-limited
oscillator ensembles for strings, brass and a formant-filtered choir, an additive piano, FM bells and mallets,
modelled drums and a synthetic hall. Every cue is a seamless loop: notes, filters and reverb tails that run past
the end wrap onto the start. Loudness matches the other broadcast cues (-18 LUFS, -1.5 dBTP) before AAC export.

Requires NumPy and SciPy, plus afconvert (macOS) or ffmpeg, only at asset-build time; the app loads the AAC files.
"""
from pathlib import Path
import argparse
import json
import math
import shutil
import subprocess
import tempfile
import wave
import zlib
import numpy as np
from scipy.ndimage import minimum_filter1d,uniform_filter1d
from scipy.signal import butter,fftconvolve,lfilter,resample_poly,sosfilt

ROOT=Path(__file__).resolve().parents[2]
SR=48000
TAU=math.tau

def hz(midi):return 440*2**((midi-69)/12)

def design(kind,f,order=2):
    f=(max(f[0],20),min(f[1],SR*.45)) if kind=='band' else min(f,SR*.45)
    return butter(order,f,kind,fs=SR,output='sos')
def filt(x,kind,f,order=2):return sosfilt(design(kind,f,order),x,axis=0)
def cfilt(x,kind,f,order=2):
    # Warm the filter up on the loop's tail so the seam stays continuous.
    w=min(len(x),SR);return sosfilt(design(kind,f,order),np.concatenate((x[-w:],x)),axis=0)[w:]

def envelope(n,attack,hold,release):
    t=np.arange(n)/SR;a=np.clip(t/max(attack,1e-4),0,1);a=a*a*(3-2*a)
    return a*np.where(t>hold,np.exp(-(t-hold)*4.6/max(release,1e-3)),1.)*np.clip((n/SR-t)/.004,0,1)

def saw(freq,n,phase=0.):
    """PolyBLEP sawtooth; `freq` is a scalar or one value per sample."""
    dt=np.broadcast_to(np.asarray(freq,float),(n,))/SR;p=(phase+np.cumsum(dt)-dt[0])%1.;y=2*p-1
    m=p<dt;x=p[m]/dt[m];y[m]-=x+x-x*x-1
    m=p>1-dt;x=(p[m]-1)/dt[m];y[m]-=x*x+x+x+1
    return y

def vibrato(n,rate,cents,delay,rng):
    t=np.arange(n)/SR;return cents*np.clip((t-delay)/.5,0,1)*np.sin(TAU*rate*t+rng.uniform(0,TAU))

def ensemble(f,n,rng,voices,spread,vib,delay=.3):
    """Detuned saws spread across the stereo field (cents of total detune, vibrato depth in cents)."""
    out=np.zeros((n,2))
    for v in range(voices):
        x=v/(voices-1)-.5 if voices>1 else 0.;th=(x*1.1+1)*math.pi/4
        y=saw(f*2**((x*spread+rng.normal(0,1.2)+vibrato(n,rng.uniform(4.7,5.9),vib,delay,rng))/1200),n,rng.random())
        out[:,0]+=y*math.cos(th);out[:,1]+=y*math.sin(th)
    return out*math.sqrt(2/voices)

# Instruments return stereo (n, 2) or mono (n,) arrays starting at the note onset; `seed` comes from the note key.
def strings(note,length,seed,bright=1.,attack=.3,release=.8,**_):
    rng=np.random.default_rng(seed);n=int((length+release)*SR);f=hz(note)
    y=filt(ensemble(f,n,rng,6,22,10),'low',min(1500+2.2*f,7000)*bright);y=filt(y,'high',max(45,.7*f),1)
    return y*envelope(n,attack,length,release)[:,None]

def spiccato(note,length,seed,accent=1.,**_):
    rng=np.random.default_rng(seed);n=int((length+.3)*SR);t=np.arange(n)/SR;f=hz(note)
    bite=filt(rng.normal(0,1,(n,2)),'band',(1800,6000))*(np.exp(-t/.012)*.18)[:,None]
    y=filt(ensemble(f,n,rng,3,14,0),'low',min(1400+2.5*f,6500)*(.8+.3*accent))+bite
    return y*(np.minimum(1,t/.004)*np.exp(-t/(.06+.05*accent))*np.clip(1-(t-length)/.04,0,1))[:,None]

def brass(note,length,seed,bright=1.,release=.25,**_):
    """Additive brass section: the spectrum blooms open after the attack, with a lip scoop and late vibrato."""
    rng=np.random.default_rng(seed);n=int((length+release)*SR);t=np.arange(n)/SR;f0=hz(note)
    fc=(250+2200*bright*(1-np.exp(-t/.06))*(.82+.18*np.exp(-t/.35)))*(1+.25*f0/440);out=np.zeros((n,2))
    for v in range(3):
        cents=(v-1)*7+rng.normal(0,1)-35*np.exp(-t/.035)+vibrato(n,rng.uniform(4.8,5.6),7,.45,rng)
        ph=TAU*np.cumsum(f0*2**(cents/1200))/SR+rng.random()*TAU;y=np.zeros(n)
        for h in range(1,max(1,min(36,int(SR*.42/f0)))+1):y+=np.sin(h*ph)*np.exp(-h*f0/fc)/h**.7
        th=((v-1)*.35+1)*math.pi/4;out[:,0]+=y*math.cos(th);out[:,1]+=y*math.sin(th)
    return np.tanh(out*.9)*(envelope(n,.045,length,release)*.6)[:,None]

VOWEL_AH=((710,100,1.),(1100,120,.55),(2600,170,.3),(3300,250,.16))
def choir(note,length,seed,attack=.55,release=1.1,**_):
    rng=np.random.default_rng(seed);n=int((length+release)*SR);f=hz(note)
    src=ensemble(f,n,rng,5,16,14,.25)+rng.normal(0,.05,(n,2))
    y=sum(g*filt(src,'band',(c-w/2,c+w/2),1) for c,w,g in VOWEL_AH)*3+filt(src,'low',min(4*f,900),1)*.25
    return y*envelope(n,attack,length,release)[:,None]

def warm_pad(note,length,seed,attack=.8,release=1.5,**_):
    rng=np.random.default_rng(seed);n=int((length+release)*SR);f=hz(note)
    return filt(ensemble(f,n,rng,7,26,4,.2),'low',min(900+f,2400))*envelope(n,attack,length,release)[:,None]

def piano(note,length,seed,vel=.7,**_):
    """Additive piano: stretched partials, hammer-position comb, two-stage decay, beating unisons, damper."""
    rng=np.random.default_rng(seed);f0=hz(note);ring=min(length,5.)+.4;n=int(ring*SR);t=np.arange(n)/SR
    key=min(max((note-21)/87,0),1);B=.0002*2**((note-60)/14);y=np.zeros(n)
    for k in range(1,40):
        fk=k*f0*math.sqrt(1+B*k*k)
        if fk>14000:break
        a=k**-1.05*math.exp(-k*f0/(900+5200*vel))*(.35+.65*abs(math.sin(math.pi*k*.13)))
        env=.7*np.exp(-t*(1+.22*k)/(1.1-.8*key))+.3*np.exp(-t*(1+.1*k)/(5.5-4*key))
        y+=a*env*np.sin(TAU*fk*t+rng.random()*TAU)
        if k<=6:y+=a*.6*env*np.sin(TAU*fk*(1+.0007*rng.uniform(.5,1))*t+rng.random()*TAU)
    y+=filt(rng.normal(0,1,n)*np.exp(-t/.003),'low',1800+3500*vel)*.05*vel
    return y*np.minimum(1,t/.0015)*np.where(t>length,np.exp(-(t-length)/.09),1)*np.clip((ring-t)/.01,0,1)*(.35+.65*vel)

def bell(note,length,seed,index=1.6,decay=1.4,**_):
    f=hz(note);n=int((length+decay*2.5)*SR);t=np.arange(n)/SR
    y=np.sin(TAU*f*t+index*np.exp(-t/.18)*np.sin(TAU*3.5*f*t))*np.exp(-t/decay)+.3*np.sin(TAU*2*f*t)*np.exp(-t/(decay*.35))
    return y*np.minimum(1,t/.0015)*np.clip((n/SR-t)/.02,0,1)

def mallet(note,length,seed,**_):
    f=hz(note);n=int((length+1.5)*SR);t=np.arange(n)/SR
    y=np.sin(TAU*f*t)*np.exp(-t/(.9*(440/f)**.3))+.35*np.sin(TAU*4*f*t)*np.exp(-t/.06)+.12*np.sin(TAU*10*f*t)*np.exp(-t/.015)
    return y*np.minimum(1,t/.001)*np.where(t>length+.6,np.exp(-(t-length-.6)/.2),1)*np.clip((n/SR-t)/.02,0,1)

def synth_pluck(note,length,seed,cut=2000.,**_):
    rng=np.random.default_rng(seed);n=int((length+.25)*SR);t=np.arange(n)/SR;f=hz(note)
    y=.5*saw(f*1.004,n,rng.random())+.5*saw(f*.996,n,rng.random())+.35*(saw(f,n,0.)-saw(f,n,.5))
    return filt(y,'low',cut)*np.minimum(1,t/.002)*np.exp(-t/.17)*np.clip(1-(t-length)/.05,0,1)*.5

def synth_bass(note,length,seed,tone=1.,**_):
    rng=np.random.default_rng(seed);n=int((length+.08)*SR);t=np.arange(n)/SR;f=hz(note)
    y=np.tanh((np.sin(TAU*f*t)*.9+filt(saw(f,n,rng.random()),'low',min(f*6*tone+120,1800))*.5)*1.3)
    return y*np.minimum(1,t/.004)*(.8+.2*np.exp(-t/.15))*np.clip(1-(t-length)/.06,0,1)

def kick(seed,punch=1.,**_):
    rng=np.random.default_rng(seed);n=int(.6*SR);t=np.arange(n)/SR
    body=np.sin(TAU*np.cumsum(44+105*np.exp(-t/.032)+250*np.exp(-t/.004))/SR)*np.exp(-t/.26)
    click=filt(rng.normal(0,1,n)*np.exp(-t/.002),'band',(1200,9000))*.3*punch
    return (np.tanh(1.7*body)*.8+click)*np.minimum(1,t/.0005)*np.clip((n/SR-t)/.01,0,1)

def snare(seed,tone=1.,**_):
    rng=np.random.default_rng(seed);n=int(.5*SR);t=np.arange(n)/SR
    body=.55*np.sin(TAU*np.cumsum(180+30*np.exp(-t/.01))/SR)*np.exp(-t/.055)+.3*np.sin(TAU*330*t+1.3)*np.exp(-t/.035)
    wires=filt(rng.normal(0,1,n),'band',(1500,10000))*np.exp(-t/.14)*.5*tone
    clap=sum(filt(rng.normal(0,1,n),'band',(900,4200))*np.where(t>=d,np.exp(-np.maximum(t-d,0)/.007),0) for d in (0.,.008,.017))*.35
    return (body+wires+clap)*np.minimum(1,t/.0006)*np.clip((n/SR-t)/.01,0,1)

def hat(seed,open_=False,**_):
    rng=np.random.default_rng(seed);n=int((.5 if open_ else .12)*SR);t=np.arange(n)/SR
    metal=sum(np.sign(np.sin(TAU*205.3*r*t+rng.random()*TAU)) for r in (2,3,4.16,5.43,6.79,8.21))/6
    return filt(metal*.6+rng.normal(0,.5,n),'band',(6500,16000))*np.exp(-t/(.18 if open_ else .03))*np.minimum(1,t/.0005)

def shaker(seed,**_):
    rng=np.random.default_rng(seed);n=int(.14*SR);t=np.arange(n)/SR
    return filt(rng.normal(0,1,n),'band',(4200,11000))*(t/.012)*np.exp(1-t/.012)

def taiko(seed,pitch=62.,decay=.5,**_):
    rng=np.random.default_rng(seed);n=int(decay*3.2*SR);t=np.arange(n)/SR
    ph=TAU*np.cumsum(pitch+55*np.exp(-t/.045))/SR
    y=np.sin(ph)*np.exp(-t/decay)+.35*np.sin(ph*1.58+.4)*np.exp(-t/(decay*.45))+filt(rng.normal(0,1,n),'low',1400)*np.exp(-t/.025)*.6
    return np.tanh(y*1.3)*np.minimum(1,t/.0008)*np.clip((n/SR-t)/.02,0,1)

TIMPANI=((1.,1.,1.6),(1.504,.6,1.1),(1.742,.42,.85),(2.,.32,.75),(2.245,.2,.6),(2.494,.12,.5))
def timpani(note,seed,length=2.6,**_):
    rng=np.random.default_rng(seed);n=int(length*SR);t=np.arange(n)/SR;ph=TAU*np.cumsum(hz(note)*(1+.012*np.exp(-t/.04)))/SR
    y=sum(a*np.sin(r*ph+rng.random()*TAU)*np.exp(-t/d) for r,a,d in TIMPANI)+filt(rng.normal(0,1,n),'low',600)*np.exp(-t/.018)*.6
    return y*np.minimum(1,t/.001)*np.clip((length-t)/.05,0,1)

def crash(seed,length=3.2,**_):
    rng=np.random.default_rng(seed);n=int(length*SR);t=np.arange(n)/SR;y=filt(rng.normal(0,1,(n,2)),'high',3000)*.6
    for f,d,p in zip(rng.uniform(2500,11000,48),rng.uniform(.4,2.2,48),rng.random(48)):
        s=np.sin(TAU*f*t+rng.random()*TAU)*np.exp(-t/d)*.05;y[:,0]+=s*(1-p);y[:,1]+=s*p
    return y*((.5*np.exp(-t/.22)+.5*np.exp(-t/1.5))*np.minimum(1,t/.0015)*np.clip((length-t)/.05,0,1))[:,None]

def swell(seed,length=2.,**_):
    """Reversed cymbal that peaks at the end of `length`."""
    rng=np.random.default_rng(seed);n=int(length*SR);t=np.arange(n)/SR
    y=filt(rng.normal(0,1,(n,2)),'band',(2500,14000))*((t/length)**3)[:,None]
    return y*np.clip((length-t)/.006,0,1)[:,None]

def boom(seed,**_):
    rng=np.random.default_rng(seed);n=int(2.6*SR);t=np.arange(n)/SR
    y=np.sin(TAU*np.cumsum(34+70*np.exp(-t/.09))/SR)*np.exp(-t/1.)+filt(rng.normal(0,1,n),'low',180)*np.exp(-t/.25)*.6
    return np.tanh(y*1.4)*np.minimum(1,t/.001)*np.clip((n/SR-t)/.05,0,1)

def riser(length,seed,top=7000.,**_):
    """Noise whose band climbs from 400 Hz to `top` (overlap-added windows) while it grows."""
    rng=np.random.default_rng(seed);n=int(length*SR);t=np.arange(n)/SR;noise=rng.normal(0,1,(n,2));out=np.zeros((n,2))
    blocks=48;size=n//blocks
    for b in range(blocks):
        c=400*(top/400)**(b/(blocks-1));i0=max(0,(b-1)*size);i1=min(n,(b+1)*size)
        out[i0:i1]+=filt(noise[i0:i1],'band',(c*.6,c*1.6),1)*np.hanning(i1-i0)[:,None]
    return out*((t/length)**2.2*np.clip((length-t)/.01,0,1))[:,None]

def hall(rt,seed,predelay=.02,damp=.45):
    """Stereo impulse response: decorrelated noise decaying faster in the treble, plus sparse early reflections."""
    rng=np.random.default_rng(seed);n=int(min(rt*1.5,5.)*SR);t=np.arange(n)/SR;noise=rng.normal(0,1,(n,2))
    low=filt(noise,'low',500);high=filt(noise,'high',4000)
    ir=low*np.exp(-6.9*t/(rt*1.2))[:,None]+(noise-low-high)*np.exp(-6.9*t/rt)[:,None]+high*np.exp(-6.9*t/(rt*damp))[:,None]
    ir*=np.minimum(1,t/.025)[:,None]
    for _ in range(14):
        d=rng.uniform(.004,.07);ir[int(d*SR),rng.integers(0,2)]+=rng.uniform(.3,1)*(1-d/.08)*3*rng.choice((-1,1))
    ir=np.vstack((np.zeros((int(predelay*SR),2)),ir))
    return ir/np.sqrt(np.sum(ir**2)/2)

def circular(y,n):
    out=y[:n].copy();tail=y[n:]
    while len(tail):k=min(len(tail),n);out[:k]+=tail[:k];tail=tail[k:]
    return out

def reverb(x,ir):
    l=x[:,0]*.7+x[:,1]*.3;r=x[:,1]*.7+x[:,0]*.3
    return np.column_stack((circular(fftconvolve(l,ir[:,0]),len(x)),circular(fftconvolve(r,ir[:,1]),len(x))))

def loudness(x):
    """Integrated loudness (ITU-R BS.1770-4 K-weighting at 48 kHz, 400 ms blocks, absolute and relative gates)."""
    y=lfilter([1.53512485958697,-2.69169618940638,1.19839281085285],[1,-1.69065929318241,.73248077421585],x,axis=0)
    y=lfilter([1.,-2.,1.],[1,-1.99004745483398,.99007225036621],y,axis=0)
    c=np.concatenate(([0.],np.cumsum((y**2).sum(1))));block,hop=int(.4*SR),int(.1*SR)
    power=np.array([(c[i+block]-c[i])/block for i in range(0,len(y)-block+1,hop)]);lufs=-.691+10*np.log10(np.maximum(power,1e-12))
    rel=-.691+10*np.log10(power[lufs>-70].mean())-10
    return -.691+10*np.log10(power[(lufs>-70)&(lufs>rel)].mean())

def biquad(kind,f0,db,q=.707):
    A=10**(db/40);w=TAU*f0/SR;cw=math.cos(w);alpha=math.sin(w)/(2*q);sa=2*math.sqrt(A)*alpha
    if kind=='peak':b,a=[1+alpha*A,-2*cw,1-alpha*A],[1+alpha/A,-2*cw,1-alpha/A]
    elif kind=='low':b,a=[A*((A+1)-(A-1)*cw+sa),2*A*((A-1)-(A+1)*cw),A*((A+1)-(A-1)*cw-sa)],[(A+1)+(A-1)*cw+sa,-2*((A-1)+(A+1)*cw),(A+1)+(A-1)*cw-sa]
    else:b,a=[A*((A+1)+(A-1)*cw+sa),-2*A*((A-1)+(A+1)*cw),A*((A+1)+(A-1)*cw-sa)],[(A+1)-(A-1)*cw+sa,2*((A-1)-(A+1)*cw),(A+1)-(A-1)*cw-sa]
    return np.array(b)/a[0],np.array(a)/a[0]

def tone(x,bands):
    """Master EQ: (kind, Hz, dB[, Q]) shelves and peaks, warmed up on the loop's tail like `cfilt`."""
    w=min(len(x),SR);y=np.concatenate((x[-w:],x))
    for band in bands:b,a=biquad(*band);y=lfilter(b,a,y,axis=0)
    return y[w:]

def true_peak(x):return 20*math.log10(float(np.max(np.abs(resample_poly(x,4,1,axis=0)))))

def limit(x,ceiling,release=.12,block=32):
    """Look-ahead peak limiter run on the loop with its tail prepended, so the gain is continuous at the seam."""
    w=SR;ext=np.concatenate((x[-w:],x));nb=len(ext)//block+1;peak=np.zeros(nb*block);peak[:len(ext)]=np.max(np.abs(ext),axis=1)
    need=minimum_filter1d(np.minimum(1,ceiling/np.maximum(peak.reshape(nb,block).max(1),1e-9)),9)
    g=np.empty(nb);cur=1.;coef=1-math.exp(-block/(release*SR))
    for i,v in enumerate(need):cur=v if v<cur else cur+(v-cur)*coef;g[i]=cur
    gain=uniform_filter1d(np.repeat(g,block)[:len(ext)],block*4)
    return np.clip(ext*gain[:,None],-ceiling,ceiling)[w:]

def master(x,eq=(),target=-18.,peak=-1.5):
    x=tone(cfilt(x,'high',28),eq);x=x*10**((target-loudness(x))/20);ceiling=peak-.5
    for _ in range(6):
        y=limit(x,10**(ceiling/20));level,tp=loudness(y),true_peak(y)
        if tp>peak:ceiling-=tp-peak+.05
        elif abs(level-target)>.1:x=x*10**((target-level)/20)
        else:break
    return y,{'lufs':round(float(level),2),'true_peak_dbtp':round(tp,2)}

class Score:
    def __init__(self,bpm,bars,seed):
        self.beat=60/bpm;self.bar=4*self.beat;self.n=int(round(bars*self.bar*SR));self.bus={};self.cache={};self.kicks=[]
        self.rng=np.random.default_rng(seed)
    def t(self,bar,beat=0.):return bar*self.bar+beat*self.beat
    def put(self,bus,at,sig,gain=1.,pan=0.):
        if sig.ndim==1:th=(pan+1)*math.pi/4;sig=np.column_stack((sig*math.cos(th),sig*math.sin(th)))*math.sqrt(2)
        elif pan:sig=sig*np.array([min(1,1-pan),min(1,1+pan)])
        sig=sig*gain;out=self.bus.setdefault(bus,np.zeros((self.n,2)));i=int(round(at*SR))%self.n
        while len(sig):k=min(len(sig),self.n-i);out[i:i+k]+=sig[:k];sig=sig[k:];i=0
    def play(self,bus,at,fn,*args,gain=1.,pan=0.,jitter=0.,**kw):
        """Render (cached by its arguments) and place one note or hit; notes past the end wrap to the start."""
        key=(fn.__name__,)+tuple(round(a,4) if isinstance(a,float) else a for a in args)+tuple(sorted(kw.items()))
        if key not in self.cache:self.cache[key]=fn(*args,seed=zlib.crc32(repr(key).encode()),**kw)
        self.put(bus,at+(self.rng.normal(0,jitter) if jitter else 0),self.cache[key],gain,pan)
    def hit(self,bus,at,fn,gain=1.,pan=0.,**kw):self.play(bus,at,fn,gain=gain,pan=pan,variant=int(self.rng.integers(0,4)),**kw)
    def kick(self,at,gain=1.,duck=1.):self.hit('drums',at,kick,gain);self.kicks.append((at,duck*gain))
    def mix(self,buses,verbs):
        n=self.n;dry=np.zeros((n,2));sends={k:np.zeros((n,2)) for k in verbs}
        imp=np.zeros(n)
        for at,w in self.kicks:imp[int(round(at*SR))%n]+=w
        kt=np.arange(int(.45*SR))/SR;duck=np.clip(circular(fftconvolve(imp,(1-np.exp(-kt/.006))*np.exp(-kt/.12)),n),0,1)
        levels={}
        for name,cfg in buses.items():
            if name not in self.bus:continue
            x=self.bus[name]*cfg.get('gain',1.)
            if 'hp' in cfg:x=cfilt(x,'high',cfg['hp'])
            if 'lp' in cfg:x=cfilt(x,'low',cfg['lp'])
            if 'duck' in cfg:x=x*(1-cfg['duck']*duck)[:,None]
            dry+=x;levels[name]=round(10*math.log10(np.mean(x**2)+1e-12),1)
            for k,amount in cfg.get('send',{}).items():sends[k]+=x*amount
        for k,(rt,predelay,damp,seed) in verbs.items():dry+=cfilt(reverb(sends[k],hall(rt,seed,predelay,damp)),'high',120)
        return dry,levels

CHORDS={'Dm':(62,3),'C':(60,4),'Bb':(58,4),'A':(57,4),'F':(65,4),'Am':(57,3),'Gm':(55,3)}
def bass_of(root):return root-24 if root-24>=33 else root-12
def spans(plan):
    out=[]
    for i,(part,name) in enumerate(plan):
        if out and tuple(out[-1][2:])==(part,name) and out[-1][0]+out[-1][1]==i:out[-1][1]+=1
        else:out.append([i,1,part,name])
    return out

# Arena theme: D minor, 110 BPM, 40 bars. Intro, verse, chorus, bridge with a build, chorus, outro that thins back
# to the intro's filtered arpeggio so the loop closes on itself.
ARENA_PARTS=[('intro',['Dm']*4),('verse',['Dm','Dm','C','C','Bb','Bb','A','A']),('chorus',['Dm','Bb','F','C']*2),
             ('bridge',['Bb','C','Am','Dm','Gm','Bb','C','A']),('chorus2',['Dm','Bb','F','C','Dm','Bb','F','A']),('outro',['Dm','Bb','Dm','Dm'])]
ARENA_MELODY=[[(0,.5,69),(.5,1,74),(1.5,.5,76),(2,1.5,77),(3.5,.5,76)],[(0,1.5,74),(1.5,.5,72),(2,1,70),(3,1,74)],
              [(0,1.5,72),(1.5,.5,69),(2,.5,72),(2.5,.5,74),(3,1,77)],[(0,2,76),(2,1,74),(3,1,72)],
              [(0,.5,69),(.5,1,74),(1.5,.5,76),(2,1,77),(3,1,79)],[(0,1.5,74),(1.5,.5,77),(2,1,79),(3,1,77)],
              [(0,2,81),(2,1,79),(3,1,77)],[(0,3.5,76)]]
ARENA_CADENCE=[(0,2,76),(2,2,73)]
ARENA_BRIDGE=[(74,77),(76,79),(76,72),(74,69),(70,74),(77,74),(76,79),(76,73)]
VERSE_HORNS={'Dm':(57,62),'C':(55,64),'Bb':(53,62),'A':(52,61)}
ARENA_MIX=dict(strings=dict(gain=.24,hp=55,send=dict(hall=.35),duck=.2),spiccato=dict(gain=1.,hp=90,send=dict(hall=.22),duck=.15),
               brass=dict(gain=.75,hp=70,send=dict(hall=.32)),choir=dict(gain=.3,hp=140,send=dict(hall=.5),duck=.15),
               piano=dict(gain=.62,send=dict(hall=.3)),bell=dict(gain=.22,hp=300,send=dict(hall=.45)),
               arp=dict(gain=1.4,hp=180,send=dict(hall=.18),duck=.35),bass=dict(gain=.5,lp=3000,duck=.4),
               drums=dict(gain=.62,hp=30,send=dict(room=.18,hall=.05)),perc=dict(gain=.55,hp=25,send=dict(hall=.28)),
               fx=dict(gain=.3,hp=150,send=dict(hall=.3)))
VERBS=dict(hall=(2.6,.022,.45,5),room=(.9,.008,.4,6))

def arp_cut(i):
    if i<4:return 700+1700*i/4
    if i<12:return 2600
    if 24<=i<28:return 1200+1800*(i-24)/4
    if i>=36:return 3000-2300*(i-36)/4
    return 3400 if i<20 or i>=28 else None

def arena_theme():
    plan=[(p,c) for p,cs in ARENA_PARTS for c in cs];s=Score(110,len(plan),2027);B=s.beat
    for start,span,part,name in spans(plan):
        root,third=CHORDS[name];at=s.t(start);L=span*s.bar
        bright,gain,attack={'intro':(.65,.55,.9),'verse':(.8,.6,.35),'chorus':(1.,.7,.3),'bridge':(.65,.45,.5),'chorus2':(1.05,.75,.3),'outro':(.65,.55,.6)}[part]
        for p in (root-12,root,root+third,root+7):s.play('strings',at,strings,p,L,bright=bright,attack=attack,gain=gain)
        if part in ('chorus','chorus2'):
            for p in (root+12,root+12+third,root+19):s.play('strings',at,strings,p,L,bright=1.1,gain=.28)
        if part in ('chorus','chorus2','bridge'):
            for p in (root,root+third,root+7)+((root+12,) if part=='chorus2' else ()):s.play('choir',at,choir,p,L,gain=.55 if part=='chorus2' else .45)
        if part=='verse':
            for p in VERSE_HORNS[name]:s.play('brass',at,brass,p,L-.1,bright=.55,gain=.42)
    for i,(part,name) in enumerate(plan):
        root,third=CHORDS[name];at=s.t(i);low=bass_of(root);arp=(0,7,12,7,12+third,7,12,19)
        cut=arp_cut(i)
        if cut:
            for k in range(16):
                c=cut if i>=4 and i<36 else (700+1700*(i*16+k)/64 if i<4 else 3000-2300*((i-36)*16+k)/64)
                level={'intro':.5,'verse':.45,'outro':.45,'bridge':.25}.get(part,.28)
                s.play('arp',at+k*B/4,synth_pluck,root+arp[k%8],B*.22,cut=float(round(c/50)*50),gain=level,pan=(.25 if k%2 else -.25))
        if part=='verse':
            for k,step in enumerate((0,0,7,0,12,0,7,0)):s.play('spiccato',at+k*B/2,spiccato,root-12+step,B*.4,accent=1. if k%2==0 else .6,gain=.55,jitter=.004)
        if part in ('chorus','chorus2'):
            for k,step in enumerate((0,0,12,0,7,0,12,0,0,0,12,0,7,12,7,0)):
                s.play('spiccato',at+k*B/4,spiccato,root-12+step,B*.22,accent=1. if k%4==0 else .55,gain=.5,jitter=.003)
        # Bass
        if part=='intro' and i>=2:s.play('bass',at,synth_bass,low,s.bar*.95,gain=.4)
        if part=='verse':
            for k in range(8):s.play('bass',at+k*B/2,synth_bass,low,B*.42,gain=.55 if k==0 else .45)
        if part in ('chorus','chorus2'):
            for k in range(8):s.play('bass',at+k*B/2,synth_bass,low+(12 if k==6 else 0),B*.42,gain=.6 if k%2==0 else .48)
        if part=='bridge':
            for k in (0,2):s.play('bass',at+k*B,synth_bass,low,B*1.9,gain=.5)
        if part=='outro' and i==36:s.play('bass',at,synth_bass,low,s.bar*1.9,gain=.5)
        # Melody and bridge piano
        if part in ('chorus','chorus2'):
            bar=i-(12 if part=='chorus' else 28);phrase=ARENA_CADENCE if part=='chorus2' and bar==7 else ARENA_MELODY[bar]
            for b,l,p in phrase:
                s.play('brass',at+b*B,brass,p,l*B*.96,bright=1.,gain=1.,jitter=.004)
                s.play('brass',at+b*B,brass,p-12,l*B*.96,bright=.65,gain=.5,jitter=.004)
                if part=='chorus2':s.play('strings',at+b*B,strings,p,l*B,bright=1.15,attack=.06,release=.35,gain=.55)
        if i==36:
            s.play('brass',at,brass,74,s.bar*1.6,bright=.9,gain=.9);s.play('brass',at,brass,62,s.bar*1.6,bright=.6,gain=.5)
        if part=='bridge':
            for k,step in enumerate((0,7,12,12+third,19,12+third,12,7)):
                p=root-12+step;s.play('piano',at+k*B/2,piano,p,B*1.5,vel=.42,gain=.6,pan=(p-64)/40,jitter=.006)
            for k,p in enumerate(ARENA_BRIDGE[i-20]):
                s.play('piano',at+k*2*B,piano,p,B*1.9,vel=.75,pan=.1,jitter=.004);s.play('bell',at+k*2*B,bell,p+12,B*1.5,gain=.5,pan=.2)
            s.play('piano',at,piano,low+12,s.bar*.95,vel=.5,gain=.7,pan=-.3)
        # Drums
        if part=='intro' and i>=2:
            for b in (0,2):s.kick(at+b*B,.55,.6)
        if part=='verse':
            for b in ((0,2) if i<8 else (0,1.5,2)):s.kick(at+b*B,.8)
            if i>=8:
                for b in (1,3):s.hit('drums',at+b*B,snare,.5)
            for k in range(8):s.hit('drums',at+k*B/2,hat,.3 if k%2 else .18,pan=.2)
            for k in range(16):s.hit('drums',at+k*B/4,shaker,.12 if k%2 else .07,pan=-.3)
            if i==11:
                for k in range(4):s.hit('drums',at+(3+k/4)*B,snare,.3+.1*k)
        if part in ('chorus','chorus2'):
            for b in (0,1.5,2)+((3.75,) if i%4==3 else ()):s.kick(at+b*B,.9)
            for b in (1,3):s.hit('drums',at+b*B,snare,.62)
            for k in range(16):s.hit('drums',at+k*B/4,hat,(.3,.12,.2,.12)[k%4],pan=.2)
            for k in range(16):s.hit('drums',at+k*B/4,shaker,.1 if k%2 else .06,pan=-.3)
            s.hit('perc',at,taiko,.55,pan=-.15);s.hit('perc',at+2.5*B,taiko,.4,pan=.15)
            s.play('perc',at,timpani,low+12,gain=.4)
        if part=='bridge':
            for b in (0,2.5):s.kick(at+b*B,.7,.6)
            s.hit('drums',at+2*B,snare,.55)
            for k in range(8):s.hit('drums',at+k*B/2,hat,.2 if k%2 else .12,pan=.2)
            if i>=22:s.hit('perc',at,taiko,.4,pan=-.15);s.hit('perc',at+1.5*B,taiko,.3,pan=.15)
        if i==26:
            for k in range(16):s.hit('drums',at+k*B/4,snare,.12+.25*k/16,pan=-.05)
        if i==27:
            for k in range(28):s.hit('drums',at+k*B/8,snare,.3+.5*k/28,pan=-.05)
            for k in range(28):s.play('perc',at+k*B/8,timpani,45,length=.6,gain=.12+.3*k/28)
            for k,p in enumerate((110,95,80,65)):s.hit('perc',at+(3+k/4)*B,taiko,.45,pitch=float(p),decay=.3,pan=.4-.25*k)
        for bar,g in ((0,.4),(36,.6),(37,.4)):
            if i==bar:s.hit('perc',at,taiko,g)
        for bar,g in ((4,.45),(12,.6),(16,.4),(28,.65),(32,.4),(36,.55)):
            if i==bar:s.hit('perc',at,crash,g)
        for bar,g in ((0,.25),(12,.5),(28,.6),(36,.55)):
            if i==bar:s.hit('perc',at,boom,g)
        if i==36:s.play('perc',at,timpani,50,gain=.5)
    s.play('fx',s.t(3),riser,s.bar,gain=.35);s.play('fx',s.t(11),riser,s.bar,gain=.3);s.play('fx',s.t(26),riser,2*s.bar,gain=.5)
    for end,length,g in ((4,s.bar,.3),(12,s.bar,.4),(28,2*s.bar,.5)):s.hit('perc',s.t(end)-length,swell,g,length=round(length,4))
    return s,s.mix(ARENA_MIX,VERBS)

# Results theme: E-flat major, 90 BPM, 32 bars of an 8-bar progression. Piano ostinato and pad, then a light beat
# and mallet melody, strings take the melody, and the last bars thin back to the opening texture.
RESULTS_CHORDS=[(39,(67,70,74,75)),(38,(65,70,74,77)),(36,(63,67,70,74)),(44,(63,67,72,75)),
                (43,(67,70,75,79)),(44,(68,70,72,75)),(41,(63,68,72,75)),(46,(63,65,70,75))]
RESULTS_RESOLVE=(62,65,70,74)
RESULTS_MELODY=[[(0,1,70),(1,1,67),(2,.5,70),(2.5,1.5,72)],[(0,2,74),(2,2,70)],[(0,1,75),(1,.5,74),(1.5,1.5,72),(3,1,67)],
                [(0,3,72),(3,1,70)],[(0,1,70),(1,1,67),(2,.5,70),(2.5,1.5,75)],[(0,1,75),(1,1,77),(2,1,75),(3,1,72)],
                [(0,1,68),(1,1,72),(2,2,75)],[(0,2,75),(2,2,74)]]
RESULTS_MIX=dict(piano=dict(gain=.7,send=dict(hall=.28)),pad=dict(gain=.32,hp=90,send=dict(hall=.3),duck=.15),
                 strings=dict(gain=.4,hp=70,send=dict(hall=.35)),mallet=dict(gain=.6,hp=150,send=dict(hall=.35)),
                 bell=dict(gain=.16,hp=400,send=dict(hall=.5)),choir=dict(gain=.22,hp=160,send=dict(hall=.55)),
                 bass=dict(gain=.48,lp=2000,duck=.25),drums=dict(gain=.58,hp=35,send=dict(room=.2,hall=.06)))

def results_theme():
    s=Score(90,32,1506);B=s.beat
    for i in range(32):
        low,voicing=RESULTS_CHORDS[i%8];at=s.t(i);section=i//8;last=i%8==7
        halves=((0,2,voicing),(2,2,RESULTS_RESOLVE)) if last else ((0,4,voicing),)
        for b,l,notes in halves:
            for p in notes:s.play('pad',at+b*B,warm_pad,p,l*B,gain=.5)
            if section==2:
                for p in notes[:3]:s.play('strings',at+b*B,strings,p-12,l*B,bright=.6,attack=.6,gain=.4)
            if section==3 and i<30:
                for p in notes[1:]:s.play('choir',at+b*B,choir,p,l*B,gain=.4)
        for k,idx in enumerate((0,1,2,1,3,1,2,1)):
            notes=RESULTS_RESOLVE if last and k>=4 else voicing;p=notes[idx]
            s.play('piano',at+k*B/2,piano,p,B*1.2,vel=.38+(.08 if k%4==0 else 0),gain=.75,pan=(p-66)/30,jitter=.006)
        s.play('piano',at,piano,low+12,B*3.8,vel=.5,pan=-.35);s.play('piano',at+2*B,piano,low+19,B*1.8,vel=.38,gain=.7,pan=-.25)
        if section==2:
            for k in range(8):s.play('bass',at+k*B/2,synth_bass,low+(12 if k in (3,7) else 0),B*.4,tone=.7,gain=.5)
        else:s.play('bass',at,synth_bass,low,s.bar*.96,tone=.6,gain=.55)
        melody=RESULTS_MELODY[i%8]
        if section in (1,3):
            for b,l,p in melody:
                s.play('mallet',at+b*B,mallet,p,l*B,gain=.8,pan=.15,jitter=.004);s.play('bell',at+b*B,bell,p+12,l*B,index=.8,gain=.5,pan=.3)
        if section==2:
            for b,l,p in melody:s.play('strings',at+b*B,strings,p,l*B,bright=.9,attack=.12,release=.5,gain=.6)
        drums=section>=1 and i<30
        if drums:
            for b in ((0,2.5) if section!=2 else (0,1.5,2.5)):s.kick(at+b*B,.6)
            for b in (1,3):s.hit('drums',at+b*B,snare,.28,tone=.5)
            for k in range(16):s.hit('drums',at+k*B/4,shaker,.11 if k%2 else .06,pan=-.35)
            if section==2:s.hit('drums',at+3.5*B,hat,.12,open_=True,pan=.25)
        if section==0 and i>=4 or i>=30:
            for k in range(8):s.hit('drums',at+k*B/2,hat,.09 if k%2 else .05,pan=.25)
        elif drums:
            for k in range(8):s.hit('drums',at+k*B/2,hat,.16 if k%2 else .09,pan=.25)
    return s,s.mix(RESULTS_MIX,dict(hall=(2.2,.02,.5,7),room=(.8,.006,.4,8)))

# MVP theme: B-flat major, 96 BPM, 20 bars. An impact chord, an ostinato over a pedal, the fanfare (with the Lydian
# C major), a climax on the tonic, and a two-bar build that lands back on the opening impact.
MVP_BARS=[('Bb',34,(58,62,65,70)),('Bb',34,(58,62,65)),('C/Bb',34,(60,64,67)),('Gm/Bb',34,(62,67,70)),('Eb/Bb',34,(63,67,70)),
          ('Bb',34,(58,62,65,70)),('F/A',33,(60,65,69)),('Gm',31,(62,67,70)),('Eb',39,(63,67,70)),('Bb/D',38,(62,65,70)),
          ('Eb',39,(63,67,70)),('C',36,(60,64,67)),('F',41,(60,65,69)),('Eb',39,(63,67,70)),('F',41,(60,65,69)),
          ('Gm',43,(62,67,70)),('Eb',39,(63,67,70)),('Bb',34,(58,62,65,70)),('Eb',39,(63,67,70)),('Fsus',41,(60,65,70))]
MVP_ROOTS={'Bb':46,'C':36,'Gm':43,'Eb':39,'F':41,'Fsus':41}
# Bars whose harmony changes halfway: (beat, beats, chord, bass, voicing).
MVP_SPLIT={16:((0,2,'Eb',39,(63,67,70)),(2,2,'F',41,(60,65,69))),19:((0,2,'Fsus',41,(60,65,70)),(2,2,'F',41,(60,65,69)))}
MVP_MELODY={5:[(0,1,65),(1,.5,70),(1.5,.5,72),(2,2,74)],6:[(0,1.5,72),(1.5,.5,70),(2,2,72)],7:[(0,1,74),(1,.5,70),(1.5,.5,74),(2,2,79)],
            8:[(0,2,77),(2,1,75),(3,1,74)],9:[(0,1,65),(1,.5,70),(1.5,.5,72),(2,2,74)],10:[(0,1.5,79),(1.5,.5,77),(2,2,75)],
            11:[(0,1.5,76),(1.5,.5,74),(2,2,79)],12:[(0,2,81),(2,2,77)],13:[(0,1,75),(1,1,79),(2,1.5,82),(3.5,.5,79)],
            14:[(0,2,81),(2,1,77),(3,1,72)],15:[(0,1.5,74),(1.5,.5,77),(2,2,79)],16:[(0,2,79),(2,2,81)],17:[(0,4,82)]}
MVP_MIX=dict(strings=dict(gain=.3,hp=50,send=dict(hall=.35)),spiccato=dict(gain=1.,hp=80,send=dict(hall=.25)),
             brass=dict(gain=.7,hp=60,send=dict(hall=.34)),choir=dict(gain=.34,hp=140,send=dict(hall=.55)),
             bell=dict(gain=.2,hp=400,send=dict(hall=.5)),bass=dict(gain=.42,lp=1500,duck=.15),
             drums=dict(gain=.5,hp=30,send=dict(room=.2,hall=.08)),perc=dict(gain=.6,hp=25,send=dict(hall=.3)),
             fx=dict(gain=.3,hp=150,send=dict(hall=.3)))

def mvp_theme():
    s=Score(96,20,606);B=s.beat
    for i,(name,low,notes) in enumerate(MVP_BARS):
        at=s.t(i);full=5<=i<=17
        if i==0:
            for p in notes+(74,):s.play('brass',at,brass,p,B*1.5,bright=1.2,gain=.55)
            for p in (46,34):s.play('brass',at,brass,p,B*1.5,bright=.8,gain=.45)
            for p in notes:s.play('strings',at,strings,p,B*3,bright=1.,attack=.03,gain=.7);s.play('choir',at,choir,p,B*3.5,attack=.08,gain=.6)
            s.play('strings',at+3*B,strings,46,B,bright=.6,attack=.4,gain=.5)
            s.hit('perc',at,crash,.7);s.hit('perc',at,boom,.6);s.hit('perc',at,taiko,.7);s.play('perc',at,timpani,46,gain=.6);s.kick(at,.8,0)
            continue
        if i<5:
            for p in ((62,65),(64,67),(62,67),(63,67))[i-1]:s.play('brass',at,brass,p,s.bar*.97,bright=.6,gain=.42)
            for k in range(8):
                p=46 if k%2==0 else notes[(0,1,2,1)[k//2]]
                s.play('spiccato',at+k*B/2,spiccato,p,B*.4,accent=1. if k%2==0 else .7,gain=.6,jitter=.003)
            for k,p in enumerate(notes+(notes[1],)):s.play('bell',at+k*B,bell,p+24,B,gain=.5,pan=-.3+.2*k)
            s.play('perc',at,timpani,46,gain=.38)
        parts=MVP_SPLIT.get(i,((0,4,name.split('/')[0],low,notes),))
        for b,l,chord,bass,voicing in parts:
            s.play('strings',at+b*B,strings,bass+12,l*B,bright=.6,attack=.25,gain=.55);s.play('bass',at+b*B,synth_bass,bass,l*B*.96,tone=.5,gain=.5)
            if full or i>=18:
                for p in voicing:
                    s.play('strings',at+b*B,strings,p,l*B,bright=1. if full else .9,attack=.2 if full else .4,gain=.6 if full else .55)
                    s.play('choir',at+b*B,choir,p,l*B,attack=.55 if full else .8,gain=.5 if full else .4)
                # The ostinato follows the chord root, not the bass of an inversion.
                for k in range(int(l*2)):
                    s.play('spiccato',at+(b+k/2)*B,spiccato,MVP_ROOTS[chord]+12+(0,12,7,12)[k%4],B*.4,
                           accent=(1. if k%2==0 else .65) if full else .8,gain=.5 if full else .45,jitter=.003)
        if full:
            for b,l,p in MVP_MELODY.get(i,()):
                s.play('brass',at+b*B,brass,p,l*B*.96,bright=1.3,gain=.9,jitter=.004)
                s.play('brass',at+b*B,brass,p-12,l*B*.96,bright=.8,gain=.6,jitter=.004)
            s.hit('perc',at,taiko,.55,pan=-.15);s.hit('perc',at+2*B,taiko,.45,pan=.15);s.hit('perc',at+3.5*B,taiko,.3)
            s.kick(at,.6,0);s.kick(at+2*B,.5,0)
            for b in (1,3):s.hit('drums',at+b*B,snare,.4,tone=1.2)
            for k in (1,3,5,7):s.hit('drums',at+(k/4+2)*B,snare,.07,tone=1.2)
            root=MVP_ROOTS[parts[0][2]];s.play('perc',at,timpani,root if root>=40 else root+12,gain=.38)
            if i==11:
                for k,p in enumerate((72,76,79,84)):s.play('bell',at+k*B,bell,p,B,gain=.6,pan=.3)
        for bar,g in ((5,.55),(9,.4),(13,.5),(17,.65)):
            if i==bar:s.hit('perc',at,crash,g)
        if i==17:s.hit('perc',at,boom,.5)
        if i==18:
            for k in range(16):s.hit('drums',at+k*B/4,snare,.12+.22*k/16,tone=1.2)
        if i==19:
            for k in range(30):s.hit('drums',at+k*B/8,snare,.3+.5*k/30,tone=1.2)
            for k in range(30):s.play('perc',at+k*B/8,timpani,41,length=.6,gain=.1+.3*k/30)
            for k,p in enumerate((53,55,57,58,60,62,64,65,67,69,70,72,74,76,77,79)):s.play('spiccato',at+k*B/4,spiccato,p,B*.22,accent=.6+.4*k/15,gain=.55)
            for p in (65,69):s.play('brass',at+2*B,brass,p,B*1.9,bright=.9,gain=.4)
            for p in (65,70):s.play('brass',at,brass,p,B*1.9,bright=.7,gain=.35)
    s.play('fx',s.t(18),riser,2*s.bar,gain=.45);s.hit('perc',s.t(18),swell,.5,length=round(2*s.bar,4))
    return s,s.mix(MVP_MIX,VERBS)

THEMES={'arena-theme':(arena_theme,dict(style='hybrid-orchestral',key='D minor',bpm=110,bars=40),
                       (('low',80,2.),('peak',650,-2.5,.9),('high',6000,3.))),
        'results-summary':(results_theme,dict(style='piano-ostinato',key='E-flat major',bpm=90,bars=32),
                           (('peak',480,-4.5,.9),('high',4000,5.))),
        'mvp-fanfare':(mvp_theme,dict(style='fanfare',key='B-flat major',bpm=96,bars=20),
                       (('low',80,3.),('peak',900,-3.,.8),('high',6000,3.)))}

def export(name,pcm,out,preview=None):
    rng=np.random.default_rng(1);dither=(rng.random(pcm.shape)-rng.random(pcm.shape))/32768
    data=np.clip(np.round((pcm+dither)*32767),-32768,32767).astype('<i2')
    with tempfile.TemporaryDirectory(prefix='arena-score-') as directory:
        wav=Path(directory)/'source.wav'
        with wave.open(str(wav),'wb') as f:f.setparams((2,2,SR,len(pcm),'NONE','not compressed'));f.writeframes(data.tobytes())
        if preview:shutil.copy(wav,Path(preview)/(name+'.wav'))
        target=out/(name+'.m4a')
        if shutil.which('ffmpeg'):subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),'-c:a','aac','-b:a','192k','-movflags','+faststart','-metadata','title=Arena-1 '+name,str(target)],check=True)
        else:subprocess.run(['afconvert','-f','m4af','-d','aac','-b','192000','-q','127','-s','2',str(wav),str(target)],check=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'frontend/public/assets/audio')
    parser.add_argument('--only',nargs='*',choices=list(THEMES));parser.add_argument('--preview',type=Path,help='also keep the 16-bit WAV masters here')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    meta=args.output/'broadcast-themes.json';info=json.loads(meta.read_text()) if meta.exists() else {}
    for name,(compose,config,eq) in THEMES.items():
        if args.only and name not in args.only:continue
        score,(mix,levels)=compose();pcm,stats=master(mix,eq)
        export(name,pcm,args.output,args.preview)
        info[name]={**config,'seconds':round(len(pcm)/SR,3),**stats,'bus_rms_db':levels};print('Composed',name,info[name],flush=True)
    meta.write_text(json.dumps(info,indent=2)+'\n')
