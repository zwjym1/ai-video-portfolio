import cv2,numpy as np
from PIL import Image
base=np.array(Image.open('base.png').convert('RGB')); H,W=base.shape[:2]; X0,Y0=330,420
def load(k):
  g=np.array(Image.open(f'gpt/{k}.png').convert('RGB')).astype(np.float32)
  full=base.astype(np.float32).copy(); full[Y0:Y0+320,X0:X0+320]=g; return full
def patch(k,roi,thr=14,grow=4,feath=2.0):
  g=load(k); b=base.astype(np.float32); x0,y0,x1,y1=roi
  d=np.abs(g-b).max(2); m=np.zeros((H,W),np.uint8); m[y0:y1,x0:x1]=(d[y0:y1,x0:x1]>thr)
  m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((5,5))); m=cv2.dilate(m,np.ones((3,3)),iterations=grow)
  # colour-correct: low-freq diff on unchanged pixels
  diff=(g-b); w=((d<thr)&(m==0)).astype(np.float32)
  num=cv2.GaussianBlur(diff*w[...,None],(0,0),10); den=cv2.GaussianBlur(w,(0,0),10)[...,None]+1e-3
  g=g-num/den
  a=cv2.GaussianBlur(m.astype(np.float32),(0,0),feath)
  r=np.zeros((H,W),np.float32); r[y0:y1,x0:x1]=1; r=cv2.GaussianBlur(r,(0,0),3); a=a*r
  return np.clip(g,0,255),a[...,None]
MOUTH_ROI=(425,578,545,672)
EYE_ROI=(322,440,618,580)
import os
V3=os.environ.get('V3','1')=='1'
def pick(k): return k+'3' if V3 and os.path.exists(f'gpt/{k}3.png') else k
MOUTHS={}
for k in ['A','E','I','O','U','N','MBP','F']: MOUTHS[k]=patch(pick('m_'+k),MOUTH_ROI)
EYES={1:patch('e_half',EYE_ROI,thr=16,grow=3),2:patch(pick('e_closed'),EYE_ROI,thr=16,grow=3)}
def scale_patch(p,c,sc):
  g,a=p; M=cv2.getRotationMatrix2D(c,0,sc)
  g2=cv2.warpAffine(g,M,(W,H),flags=cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_REPLICATE); a2=cv2.warpAffine(a[...,0],M,(W,H),flags=cv2.INTER_LINEAR)
  return g2,a2[...,None]
MOUTHS['U']=scale_patch(MOUTHS['U'],(483.0,612.0),1.4)
if os.path.exists('gpt/e_q343.png'): EYES[3]=patch('e_q343',EYE_ROI,thr=16,grow=3)
def apply(img,p):
  g,a=p; return (g*a+img*(1-a)).astype(np.uint8)
def openness(k):
  g,a=MOUTHS[k]; x0,y0,x1,y1=MOUTH_ROI; s=g[y0:y1,x0:x1]; return int(((s.sum(2)<520)&(a[y0:y1,x0:x1,0]>.5)).sum())
if __name__=='__main__':
  for k in MOUTHS: print(k,openness(k))
