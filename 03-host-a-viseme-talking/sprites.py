import math,numpy as np,cv2
from PIL import Image,ImageDraw,ImageFilter
base=np.array(Image.open('base.png').convert('RGB')); H,W=base.shape[:2]
def inpaint(img,m,r=5): return cv2.inpaint(img,(m>0).astype(np.uint8)*255,r,cv2.INPAINT_TELEA)
def feather(dst,src,m,s=1.2):
  k=cv2.GaussianBlur(m.astype(np.float32),(0,0),s)[...,None]; return (src*k+dst*(1-k)).astype(np.uint8)
# ---------- mouth erase: original smile line ~ (451,614)-(514,603)
reg=base[596:624,444:522].astype(int); skin=np.array([255,236,231])
mm=np.zeros((H,W),np.uint8); mm[596:624,444:522]=(np.abs(reg-skin).sum(2)>18)
mm=cv2.dilate(mm,np.ones((3,3)),iterations=2)
nomouth=inpaint(base,mm); nomouth=feather(base,cv2.GaussianBlur(nomouth,(0,0),1.0),cv2.dilate(mm,np.ones((3,3))),1.0)
MC=(483,611); ANG=7.0; S=8
# w, top height, bottom height, corner roundness exp (<=0.5 = rounded), teeth(frac), tongue
SH={'A':(36,7,19,0.42,0.0,1.0),'E':(42,5,10,0.55,0.38,0.5),'I':(46,3.2,5.0,0.62,0.55,0),
    'O':(24,10,13,0.40,0,0.8),'U':(15,4.5,5.5,0.40,0,0),'N':(32,2.0,4.0,0.60,0,0)}
LINE=(105,52,60); IN0=(122,40,52); IN1=(170,70,80); TONG=(236,138,146); TEETH=(255,253,252)
def mouth_img(P):
  w,ht,hb,p,teeth,tg=P; R=40; sz=2*R*S
  im=Image.new('RGBA',(sz,sz),(0,0,0,0)); d=ImageDraw.Draw(im)
  u=np.linspace(-1,1,121); g=np.clip(1-u**2,0,1)
  lift=-1.6*u**2  # soft smile: corners slightly up
  top=[(R+w/2*x, R-ht*gg**p+l) for x,gg,l in zip(u,g,lift)]
  bot=[(R+w/2*x, R+hb*gg**p+l) for x,gg,l in zip(u,g,lift)][::-1]
  sc=lambda L:[(x*S,y*S) for x,y in L]
  mask=Image.new('L',(sz,sz),0); ImageDraw.Draw(mask).polygon(sc(top+bot),fill=255)
  yy=np.arange(sz)/S; t=np.clip((yy-(R-ht))/max(1,ht+hb),0,1)[:,None,None]
  inner=np.zeros((sz,sz,4),np.uint8); inner[...,:3]=(np.array(IN0)+(np.array(IN1)-np.array(IN0))*t).astype(np.uint8); inner[...,3]=255
  inner=Image.fromarray(inner); di=ImageDraw.Draw(inner)
  if tg>0:
    tw=w*0.28*tg+2; ty=R+hb*0.35
    di.ellipse([(R-tw)*S,ty*S,(R+tw)*S,(R+hb+tw*0.8)*S],fill=TONG+(255,))
  if teeth>0:
    yb=R-ht+(ht+hb)*teeth
    di.rectangle([0,0,sz,yb*S],fill=TEETH+(255,))
  im.paste(inner,(0,0),mask)
  # outline: upper slightly thicker, all rounded
  d.line(sc(top),fill=LINE+(255,),width=int(1.5*S),joint='curve')
  d.line(sc(bot),fill=LINE+(235,),width=int(1.1*S),joint='curve')
  for (x,y) in (top[0],top[-1]): d.ellipse([(x-0.75)*S,(y-0.75)*S,(x+0.75)*S,(y+0.75)*S],fill=LINE+(255,))
  if ht+hb>9:  # soft lower-lip shade
    lw=w*0.18; ly=R+hb+3.0
    d.arc([(R-lw)*S,(ly-2)*S,(R+lw)*S,(ly+1.5)*S],25,155,fill=(238,170,170,150),width=int(1.0*S))
  im=im.filter(ImageFilter.GaussianBlur(S*0.25)).resize((2*R,2*R),Image.LANCZOS).rotate(ANG,resample=Image.BICUBIC)
  return im,R
CLOSED=(56,0.4,0.9,0.6,0,0)
def comp_mouth(img,P):
  out=Image.fromarray(img).convert('RGBA'); m,R=mouth_img(P); out.alpha_composite(m,(MC[0]-R,MC[1]-R)); return np.array(out.convert('RGB'))
# ---------- eyes
px_=base.astype(int); ns_=(np.abs(px_-np.array([255,236,231])).sum(2)>45).astype(np.uint8)
def auto_eye(box,c,xr):
  x0,y0,x1,y1=box; b=np.zeros_like(ns_); b[y0:y1,xr[0]:xr[1]]=ns_[y0:y1,xr[0]:xr[1]]
  n,lab=cv2.connectedComponents(b); m=(lab==lab[c[1],c[0]]).astype(np.uint8)
  hull=cv2.convexHull(np.argwhere(m)[:,::-1].astype(np.int32)); h=np.zeros_like(m); cv2.fillPoly(h,[hull],1)
  core=cv2.dilate(h,np.ones((3,3)),iterations=2)
  return core,m
EYES=[dict(box=(325,478,440,575),c=(385,525),xr=(336,427),lash_x=(342,424)),
      dict(box=(500,455,615,550),c=(560,500),xr=(509,601),lash_x=(513,599))]
emask=[];lashm=[]
for e in EYES:
  core,m=auto_eye(e['box'],e['c'],e['xr']); emask.append(core)
  p=base.astype(int); lash=(p.sum(2)<330)&((p[...,2]-p[...,0])<30)&(m>0); lashm.append(lash)
LASH=np.array([48,26,34])
_src=base.copy(); _ring=cv2.dilate(emask[0]|emask[1],np.ones((9,9)))>0
_bad=_ring&(np.abs(base.astype(int)-np.array([255,236,231])).sum(2)>30); _src[_bad]=cv2.GaussianBlur(base,(0,0),1)[_bad]*0+np.array([254,235,230],np.uint8)
skinfill=inpaint(_src,emask[0]|emask[1],9)
skinfill=feather(skinfill,cv2.GaussianBlur(skinfill,(0,0),2.5),cv2.dilate(emask[0]|emask[1],np.ones((5,5))),2)
def blink(img,level):
  if level==0: return img
  out=img.copy()
  for e,m,lm in zip(EYES,emask,lashm):
    ys,xs=np.nonzero(m); y0,y1=ys.min(),ys.max(); hgt=y1-y0
    if level==1:
      dy=int(round(hgt*0.42))
      band=np.zeros_like(lm)
      for x in range(xs.min(),xs.max()+1):
        c=np.nonzero(lm[:,x])[0]
        if len(c):
          k=0
          while k+1<len(c) and c[k+1]-c[k]<=2: k+=1
          if c[0]<y0+hgt*0.6: band[c[0]:min(c[k]+1,y0+int(hgt*0.5),c[0]+10),x]=True  # only upper lash
      band=(cv2.dilate(band.astype(np.uint8),np.ones((3,3)))&m)>0
      cover=np.zeros_like(m); cx=[];cb=[]
      for x in range(xs.min(),xs.max()+1):
        c=np.nonzero(band[:,x])[0]
        if len(c): cx.append(x); cb.append(c.max())
      allx=np.arange(xs.min(),xs.max()+1); bb=np.interp(allx,cx,cb)
      bb=np.convolve(np.pad(bb,3,mode='edge'),np.ones(7)/7,'valid')
      for x,b in zip(allx,bb): cover[y0:int(b)+dy+1,x]=1
      cover&=m
      sh=np.zeros_like(img); shm=np.zeros_like(m)
      sh[dy:]=base[:-dy]; shm[dy:]=band[:-dy]
      layer=skinfill.copy(); keep=shm>0; layer[keep]=sh[keep]
      out=feather(out,layer,cover|shm,0.9)
    else:
      out=feather(out,skinfill,m,1.0)
      x0,x1=e['lash_x']; pil=Image.fromarray(out).convert('RGBA'); lay=Image.new('RGBA',(W*4,H*4),(0,0,0,0)); d=ImageDraw.Draw(lay)
      yc=y0+hgt*0.62; sag=hgt*0.16
      outer=-1 if x0<480 else 1  # outer corner side (left eye: left)
      P=[]
      for t in np.linspace(0,1,60):
        x=x0+(x1-x0)*t; y=yc+sag*math.sin(math.pi*t)
        P.append((x,y))
      for i in range(len(P)-1):
        t=i/(len(P)-1); tt=t if outer<0 else 1-t   # thicker at outer side
        wdt=1.5+3.0*math.sin(math.pi*min(1,t*1.05))*(0.6+0.4*(1-tt))
        d.line([(P[i][0]*4,P[i][1]*4),(P[i+1][0]*4,P[i+1][1]*4)],fill=tuple(LASH)+(255,),width=max(1,int(wdt*4)))
      ox,oy=P[0] if outer<0 else P[-1]
      d.line([(ox*4,oy*4),((ox+outer*4)*4,(oy+3.5)*4)],fill=tuple(LASH)+(255,),width=int(2.2*4))
      lay=lay.filter(ImageFilter.GaussianBlur(2)).resize((W,H),Image.LANCZOS); pil.alpha_composite(lay); out=np.array(pil.convert('RGB'))
  return out
