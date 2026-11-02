from faster_whisper import WhisperModel
import json,subprocess,numpy as np
a=np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i","exports/omni_vo_intro_6s.wav","-f","s16le","-ac","1","-ar","16000","-"],capture_output=True).stdout,np.int16).astype(np.float32)/32768
m=WhisperModel("small",device="cpu",compute_type="int8")
segs,_=m.transcribe(a,language="zh",word_timestamps=True,initial_prompt="以下是普通话的句子。")
out=[[w.word,w.start,w.end] for s in segs for w in s.words]
json.dump(out,open("work/words.json","w"),ensure_ascii=False);print(out)
