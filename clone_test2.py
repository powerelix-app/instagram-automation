import os, time, base64, requests
from ig_automation import config
RT=config.REPLICATE_API_TOKEN
h={'Authorization':f'Bearer {RT}'}; hj={**h,'Content-Type':'application/json'}
b=open('/tmp/oksana_30.mp3','rb').read()
data_uri='data:audio/mpeg;base64,'+base64.b64encode(b).decode()
print('data uri kb:', len(data_uri)//1024, flush=True)
vc=requests.get('https://api.replicate.com/v1/models/minimax/voice-cloning',headers=h,timeout=30).json()['latest_version']['id']
p=requests.post('https://api.replicate.com/v1/predictions',headers=hj,json={'version':vc,'input':{'voice_file':data_uri,'model':'speech-02-hd','need_noise_reduction':True,'need_volume_normalization':True}},timeout=120).json()
if 'urls' not in p: print('SUBMIT ERR',str(p)[:200],flush=True); raise SystemExit
url=p['urls']['get']; voice_id=None
for _ in range(150):
    time.sleep(4); s=requests.get(url,headers=h,timeout=30).json()
    if s['status']=='succeeded':
        o=s['output']; print('clone out:',str(o)[:200],flush=True)
        voice_id=o if isinstance(o,str) else (o.get('voice_id') or o.get('id') if isinstance(o,dict) else None); break
    if s['status']=='failed': print('CLONE FAIL',str(s.get('error'))[:200],flush=True); raise SystemExit
print('voice_id:',voice_id,flush=True)
tts=requests.get('https://api.replicate.com/v1/models/minimax/speech-02-hd',headers=h,timeout=30).json()['latest_version']['id']
TEXT='Несколько капель хлорофилла в воду — и ты даёшь телу силу зелени. Очищение, крепкий иммунитет, чистая кожа. Пауэрэликс хлорофилл — обновление каждый день.'
p2=requests.post('https://api.replicate.com/v1/predictions',headers=hj,json={'version':tts,'input':{'text':TEXT,'voice_id':voice_id,'language_boost':'Russian','emotion':'neutral'}},timeout=60).json()
url2=p2['urls']['get']
for _ in range(80):
    time.sleep(3); s2=requests.get(url2,headers=h,timeout=30).json()
    if s2['status']=='succeeded':
        out=s2['output']; out=out if isinstance(out,str) else out[0]
        open('output/reels05/hf/vo_opts/Z_clone_oksana.mp3','wb').write(requests.get(out,timeout=60).content); print('CLONE VO OK',flush=True); break
    if s2['status']=='failed': print('SYNTH FAIL',str(s2.get('error'))[:150],flush=True); break
