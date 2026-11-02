#!/workspace/.venv-dy/bin/python
"""ASR（本地 faster-whisper small，离线；结果「需复核」）。
用法: asr.py <video> <out.json> [--model small] [--srt 字幕.srt]
有 --srt（成片对应的字幕文件）时直接转换，否则跑 ASR：人声带通 + 低阈值 VAD。"""
import json, subprocess, sys, os, argparse, re
ap=argparse.ArgumentParser(); ap.add_argument('video'); ap.add_argument('out'); ap.add_argument('--model',default='small'); ap.add_argument('--srt')
a=ap.parse_args()
if a.srt:
    txt=open(a.srt,encoding='utf-8-sig').read(); S=[]
    ts=lambda x: (lambda h,m,s: int(h)*3600+int(m)*60+float(s.replace(',','.')))(*x.split(':'))
    for blk in re.split(r'\n\s*\n', txt.strip()):
        L=blk.strip().splitlines()
        m=next((l for l in L if '-->' in l),None)
        if not m: continue
        A,B=[ts(x.strip()) for x in m.split('-->')]; t=''.join(L[L.index(m)+1:]).strip()
        n=max(1,len(t)); S.append(dict(a=round(A,2),b=round(B,2),text=t,words=[[ch,round(A+(B-A)*i/n,2),round(A+(B-A)*(i+1)/n,2)] for i,ch in enumerate(t)]))
    json.dump(S,open(a.out,'w'),ensure_ascii=False,indent=0); print('srt->asr',a.out,len(S)); sys.exit()
os.environ.setdefault('HF_HUB_OFFLINE','1')
from faster_whisper import WhisperModel, decode_audio
from faster_whisper.vad import get_speech_timestamps, VadOptions
wav=f"/tmp/_asr_{os.getpid()}.wav"
# 人声带通 + 动态归一，压 BGM；先 VAD 切成 ≤12s 的语音块再逐块识别（整段识别在 BGM 下会大段漏字，已实测）
subprocess.run(['ffmpeg','-v','error','-y','-i',a.video,'-af','highpass=f=120,lowpass=f=6000,dynaudnorm','-ac','1','-ar','16000',wav],check=True)
x=decode_audio(wav,16000); os.remove(wav)
m=WhisperModel(a.model,device='cpu',compute_type='int8',cpu_threads=8)
JUNK=re.compile(r'订阅|字幕by|谢谢观众|谢谢收看|请不吝|(.)\1{5,}|(..)\2{4,}|(\S{1,3}\s)\3{3,}')
def bad(segs, dur):
    t=''.join(x.text for x in segs); hz=len(re.findall(r'[\u4e00-\u9fff]',t))
    return (not t.strip()) or bool(JUNK.search(t)) or hz < 1.5*dur*0.5 or len(re.findall(r'[A-Za-z]',t)) > hz
S=[]; retried=0
for t in get_speech_timestamps(x,VadOptions(threshold=0.2,min_silence_duration_ms=300,speech_pad_ms=150,max_speech_duration_s=12)):
    off=t['start']/16000; seg=x[t['start']:t['end']]; d=len(seg)/16000
    kw=dict(language='zh',beam_size=5,condition_on_previous_text=False,vad_filter=False,word_timestamps=True)
    segs=list(m.transcribe(seg,temperature=0.0,initial_prompt='以下是普通话科普视频的逐字稿。',**kw)[0])
    if bad(segs,d):  # 幻觉/漏字：换温度、去提示词重试，取汉字最多且不含垃圾的那次
        retried+=1; cands=[segs]+[list(m.transcribe(seg,temperature=T,initial_prompt=P,**kw)[0]) for T,P in ((0.2,None),(0.4,'以下是普通话的句子。'))]
        ok=[c for c in cands if not JUNK.search(''.join(x.text for x in c))] or cands
        segs=max(ok,key=lambda c: len(re.findall(r'[\u4e00-\u9fff]',''.join(x.text for x in c))))
    for s_ in segs:
        txt=JUNK.sub('',s_.text).strip()
        if not txt: continue
        S.append(dict(a=round(off+s_.start,2),b=round(off+s_.end,2),text=txt,words=[[w.word,round(off+w.start,2),round(off+w.end,2)] for w in (s_.words or [])]))
print('retried chunks',retried)
json.dump(S,open(a.out,'w'),ensure_ascii=False,indent=0); print('asr done',a.out,len(S),sum(len(s['text']) for s in S))
