import json,math,subprocess,sys,random,numpy as np,cv2
from PIL import Image
from pypinyin import pinyin,Style
from gsprites import *
LEAD=float(sys.argv[1]) if len(sys.argv)>1 else 0.03
OUT=sys.argv[2] if len(sys.argv)>2 else '../exports/host_a_talking_v4.mp4'
FPS=30; PAD=0.25; SRC='../exports/omni_vo_intro_6s.wav'
subprocess.run(['ffmpeg','-y','-v','error','-i',SRC,'-af','adelay=250|250,apad=pad_dur=0.5','padded.wav']); WAV='padded.wav'
dur=float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',WAV],capture_output=True,text=True).stdout)
N=int(round(dur*FPS))
au=np.frombuffer(subprocess.run(['ffmpeg','-v','error','-i',WAV,'-f','s16le','-ac','1','-ar','16000','-'],capture_output=True).stdout,np.int16)/32768
rms=np.array([np.sqrt(np.mean(au[int(i/FPS*16000):int((i+1)/FPS*16000)]**2)+1e-9) for i in range(N)])
# ---------- forced-aligned syllables (torchaudio MMS_FA, fa.py)
fa=json.load(open('chars_fa.json'))
VOW=set('aeiouv')
syl=[]
for i,(ch,rom,s0,e0,sp) in enumerate(fa):
  s0+=PAD; e0+=PAD
  # final starts at first vowel letter (skip glide y/w as initial-ish)
  letters=[c for c in rom if c in 'abcdefghijklmnopqrstuvwxyz']
  fi=next((j for j,c in enumerate(letters) if c in VOW),0)
  f0=sp[min(fi,len(sp)-1)][0]+PAD
  nxt=fa[i+1][2]+PAD if i+1<len(fa) else 1e9
  e=nxt if nxt-e0<0.16 else e0+0.07
  syl.append((ch,s0,f0,e))
def vis(ch):
  if ch=='ai_en': return None,['E','I']
  if ch=='i_en': return None,['A','I']
  ini=pinyin(ch,style=Style.INITIALS,strict=False)[0][0]; f=pinyin(ch,style=Style.FINALS,strict=False)[0][0].replace('v','u')
  if ini in('z','c','s','zh','ch','sh','r') and f=='i': seq=['E']
  elif f in('ai','uai'): seq=['A','I']
  elif f in('ao','iao'): seq=['A','O']
  elif f in('ou','iou','iu'): seq=['O','U']
  elif f=='ei': seq=['E','I']
  elif f in('uei','ui'): seq=['U','I']
  elif f in('ian','ie','ue'): seq=['I','E']
  elif f in('ua','ia'): seq=['A']
  elif f in('uan','iang','uang','an','ang'): seq=['A','N']
  elif f in('a',): seq=['A']
  elif f in('o','uo'): seq=['O']
  elif f in('ong','iong'): seq=['O','U']
  elif f in('e','er'): seq=['E']
  elif f in('en','eng'): seq=['E','N']
  elif f in('un','uen'): seq=['U','N']
  elif f in('i','in','ing'): seq=['I']
  elif f in('u','un'): seq=['U']
  else: seq=['E']
  return ini,seq
seq=['X']*N; fr=lambda t:int(round((t-LEAD)*FPS))
log=[]
for ch,s0,f0,e in syl:
  ini,v=vis(ch); log.append((ch,round(s0,2),round(f0,2),round(e,2),ini,v))
  a,b,c=fr(s0),fr(f0),fr(e)
  if ini in('b','p','m','f'):
    k='F' if ini=='f' else 'MBP'
    a0=min(a,b-2); 
    for f in range(max(0,a0),b): seq[f]=k
  else: b=a
  L=max(1,c-b)
  for f in range(max(0,b),min(N,c)):
    u=(f-b)/L; seq[f]=v[0] if (len(v)==1 or u<0.6) else v[1]
# min hold 2 frames
for _ in range(2):
  i=0
  while i<N:
    j=i
    while j<N and seq[j]==seq[i]: j+=1
    if j-i<2 and i>0: seq[i]=seq[i-1]
    i=j
LV={'X':0,'MBP':0,'F':1,'N':1,'U':1,'I':2,'O':2,'E':3,'A':4}
def runs(s):
  r=[];i=0
  while i<N:
    j=i
    while j<N and s[j]==s[i]: j+=1
    r.append([s[i],i,j]); i=j
  return r
R=runs(seq); out=list(seq); nib=0
for r0,r1 in zip(R,R[1:]):
  p,q=LV[r0[0]],LV[r1[0]]
  if abs(p-q)<2: continue
  lo,hi=sorted((p,q)); mids=[l for l in (1,3) if lo<l<hi] or [2]
  rep={1:'N',2:('I' if 'I' in (r0[0],r1[0]) or 'E' in (r0[0],r1[0]) else 'O'),3:'E'}
  ms=[rep[l] for l in mids]
  if p>q: ms=ms[::-1]
  n=min(2,len(ms) if len(ms)>1 else (2 if r1[2]-r1[1]>=5 else 1))
  ms=(ms*2)[:n] if len(ms)==1 else ms[:n]
  if r1[2]-r1[1]>=n+2:
    for k,m in enumerate(ms): out[r1[1]+k]=m; nib+=1
  elif r0[2]-r0[1]>=n+2:
    for k,m in enumerate(ms): out[r0[2]-n+k]=m; nib+=1
seq=out
ov=np.array([LV[k] for k in seq],float)
for off in (-2,-1,0,1,2):
  print('offset',off,'corr %.3f'%np.corrcoef(np.roll(ov,off)[3:-3],rms[3:-3])[0,1])
json.dump({'syl':log,'frames':seq},open('timeline_v2.json','w'),ensure_ascii=False)
print(nib,'inbetween frames')
if '--score' in sys.argv: sys.exit()
# ---------- stress -> nods + brow raises
pk=[]
phr=[[]]
for k,(ch,s0,f0,e) in enumerate(syl):
  if k and s0-syl[k-1][3]>0.12: phr.append([])
  a,b=fr(s0),max(fr(s0)+1,fr(e)); phr[-1].append((rms[a:b].max(),s0))
stress=[max(p)[1] for p in phr if p]; print('stress',stress)
def ease(x): x=min(1,max(0,x)); return 0.5-0.5*math.cos(math.pi*x)
def bump(t,c,up,hold,down):
  u=t-c
  if u<-up or u>hold+down: return 0
  if u<0: return ease((u+up)/up)
  if u<hold: return 1
  return 1-ease((u-hold)/down)
head_dy=lambda t: max([1.5*bump(t,n+0.12,0.12,0.04,0.35) for n in stress]+[0])
brow=lambda t: max([bump(t,n,0.1,0.25,0.3) for k,n in enumerate(stress) if k%2==0]+[0])
breath_dy=lambda t:-1.3*(0.5-0.5*math.cos(2*math.pi*0.25*t))
# ---------- blinks: random 2.5-5s, 20% double
rng=random.Random(7); blinks={}; t=rng.uniform(1.0,1.6)
while t<dur-0.3:
  f=int(t*FPS)
  for k,l in enumerate([1,3,2,2,3,1,1]): blinks[f+k]=l
  if rng.random()<0.25:
    for k,l in enumerate([1,3,2,3,1]): blinks[f+8+k]=l
  t+=rng.uniform(2.5,5.0)
print('blinks',sorted(set(f//1 for f in blinks if blinks[f]==2)))
# ---------- saccades: small iris shifts
sac=[]; t=0.9
while t<dur:
  dx=rng.choice([-1.6,-1.0,1.0,1.6,0]); hold=rng.uniform(0.6,1.3); sac.append((t,dx)); t+=hold
def sac_dx(t):
  x=0
  for i,(t0,dx) in enumerate(sac):
    if t>=t0:
      prev=sac[i-1][1] if i else 0; x=prev+(dx-prev)*ease((t-t0)/0.07)
  return x
# iris mask
import sprites as SP
px=base.astype(int); hull=(SP.emask[0]|SP.emask[1])>0
iris=hull&((px[...,2]-px[...,0])>35)
lash=hull&(px.sum(2)<330)&((px[...,2]-px[...,0])<30)
im_=cv2.dilate(iris.astype(np.uint8),np.ones((5,5)))>0
im_&=hull&~cv2.dilate(lash.astype(np.uint8),np.ones((3,3))).astype(bool)
IRM=cv2.GaussianBlur(im_.astype(np.float32),(0,0),0.8)[...,None]
yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
def saccade(img,dx):
  if abs(dx)<0.05: return img
  sh=cv2.remap(img,xx-dx,yy,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
  return (sh*IRM+img*(1-IRM)).astype(np.uint8)
# ---------- warp fields
yv=np.arange(H,dtype=np.float32); xv=np.arange(W,dtype=np.float32)
ss=lambda a:a*a*(3-2*a)
wb=ss(np.clip((1600-yv)/(1600-900),0,1))[:,None]*np.ones((1,W),np.float32)
wh=ss(np.clip((760-yv)/(760-690),0,1))[:,None]*np.ones((1,W),np.float32)
# jaw: below mouth to chin tip (681), fade to 0 by 696; horizontal within face
jy=np.where(yv<612,0,np.where(yv<681,ss(np.clip((yv-612)/69,0,1)),ss(np.clip((696-yv)/15,0,1))))
jx=np.exp(-((xv-488)/62)**2*1.0)
JAW=(jy[:,None]*jx[None,:]).astype(np.float32)
BROW=np.zeros((H,W),np.float32)
for cx,cy in ((392,484),(540,463)):
  BROW+=np.exp(-((xx-cx)/28)**2-((yy-cy)/6.0)**2)
BROW=np.clip(BROW,0,1)
JL={'X':0,'MBP':0,'F':0.15,'N':0.2,'U':0.25,'I':0.35,'O':0.6,'E':0.7,'A':1.0}
jaw_t=np.array([JL[k] for k in seq],float)
for i in range(1,N): jaw_t[i]=jaw_t[i-1]+(jaw_t[i]-jaw_t[i-1])*0.65  # soften
cache={}
def face(m,b):
  k=(m,b)
  if k not in cache:
    img=base.copy()
    if b: img=apply(img,EYES[b])
    if m!='X': img=apply(img,MOUTHS[m])
    cache[k]=img
  return cache[k]
xw=[1.0]*N; xprev=list(seq)
for i in range(1,N):
  if seq[i]!=seq[i-1]:
    L=1
    while i+L<N and seq[i+L]==seq[i]: L+=1
    ws=[0.5] if L<3 else [0.4,0.75]
    for k,wv in enumerate(ws): xw[i+k]=wv; xprev[i+k]=seq[i-1]
# ---- whole-body motion (bottom-anchored)
BOTY=1672.0
LEANW=np.clip((BOTY-yv)/BOTY,0,1)[:,None]*np.ones((1,W),np.float32)
SHO=np.exp(-((yv-840)/70)**2)[:,None]*np.ones((1,W),np.float32)
ST=3.05
def settle(t): return bump(t,ST,0.18,0.05,0.6)
def lean_deg(t): return 0.22*math.sin(2*math.pi*t/3.6)+0.12*ease((t-ST)/0.5)
def head_dx(t): return 1.4*math.sin(2*math.pi*t/3.6-0.7)
DIS=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST); DIS.setFinestScale(0)
MX0,MY0,MX1,MY1=415,570,555,680
_mc={}
def morph(A,B,w):
  a=A[MY0:MY1,MX0:MX1]; bb=B[MY0:MY1,MX0:MX1]
  k=(id(A),id(B))
  if k not in _mc:
    ga=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY); gb=cv2.cvtColor(bb,cv2.COLOR_RGB2GRAY)
    _mc[k]=(DIS.calc(ga,gb,None),DIS.calc(gb,ga,None))
  fab,fba=_mc[k]; h,wd=a.shape[:2]; gy,gx=np.mgrid[0:h,0:wd].astype(np.float32)
  wa=cv2.remap(a,gx-fba[...,0]*w*-1*-1+0,gy,cv2.INTER_LINEAR) if False else cv2.remap(a,gx+fba[...,0]*w,gy+fba[...,1]*w,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
  wb_=cv2.remap(bb,gx+fab[...,0]*(1-w),gy+fab[...,1]*(1-w),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
  out=B.copy(); out[MY0:MY1,MX0:MX1]=(wa.astype(np.float32)*(1-w)+wb_.astype(np.float32)*w).astype(np.uint8)
  # feather ROI edge (content identical outside mouth anyway)
  return out
# ---- Aning-style talk bob (measured: T=12.5f, head dy 0..+23px@1080p down dips x4/loop, dx 0..11.7px; scaled x1.67 by head size)
T_LOOP=12.5/30; AY=33.0; AX=17.0; HEADY=500.0
WB=np.clip((BOTY-yv)/(BOTY-HEADY),0,1)[:,None]*np.ones((1,W),np.float32)
spk=np.zeros(N)
for ch,s0,f0,e in syl:
  spk[max(0,int((s0-0.05)*FPS)):min(N,int((e+0.30)*FPS))]=1
g=np.zeros(N); onset=np.zeros(N); t_on=0
for i in range(N):
  if spk[i] and (i==0 or g[i-1]<0.02): t_on=i/FPS
  onset[i]=t_on
  k=0.45 if spk[i] else 0.16   # attack ~3f, release ~0.3s
  g[i]=(g[i-1] if i else 0)+(spk[i]-(g[i-1] if i else 0))*k
def bob(f):
  th=2*math.pi*(f/FPS-onset[f])/T_LOOP
  return AX*g[f]*(1-math.cos(th))/2, AY*g[f]*abs(math.sin(th))
OW,OH=1080,1920; import os,glob
[os.remove(p) for p in glob.glob('v/*.png')]
for f in range(N):
  t=f/FPS; b=blinks.get(f,0); img=face(seq[f],b)
  w=xw[f]
  if w<1: img=(face(xprev[f],b).astype(np.float32)*(1-w)+img.astype(np.float32)*w).astype(np.uint8)
  if not b: img=saccade(img,sac_dx(t))
  bx,by_=bob(f)
  dx=bx*WB
  dy=by_*WB+breath_dy(t)*wb*(1-g[f])+0.9*breath_dy(t)*SHO+2.0*jaw_t[f]*JAW-1.6*brow(t)*BROW
  out=cv2.remap(img,(xx-dx).astype(np.float32),(yy-dy).astype(np.float32),cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
  out=cv2.resize(out,(OW,OH),interpolation=cv2.INTER_LANCZOS4)
  cv2.imwrite(f'v/{f:04d}.png',cv2.cvtColor(out,cv2.COLOR_RGB2BGR))
subprocess.run(['ffmpeg','-y','-v','error','-framerate','30','-i','v/%04d.png','-i',WAV,'-c:v','libx264','-crf','15','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-shortest',OUT])
json.dump({'blinks':blinks,'sac':sac,'stress':stress},open('motion_v2.json','w'))
