import os, time, requests
for line in open('.env'):
    k=line.split('=',1)[0]
    if k in ('REPLICATE_API_TOKEN','ELEVENLABS_API_KEY'): os.environ[k]=line.strip().split('=',1)[1]
RT=os.environ['REPLICATE_API_TOKEN']; EL=os.environ.get('ELEVENLABS_API_KEY')
BASE='Несколько капель {w1} в воду — и ты даёшь телу силу зелени. Очищение, крепкий иммунитет, чистая кожа. Пауэрликс {w2} — обновление каждый день.'
# MiniMax
def minimax(text, out):
    h={'Authorization':f'Bearer {RT}','Content-Type':'application/json'}
    ver=requests.get('https://api.replicate.com/v1/models/minimax/speech-02-hd',headers=h,timeout=30).json()['latest_version']['id']
    p=requests.post('https://api.replicate.com/v1/predictions',headers=h,json={'version':ver,'input':{'text':text,'voice_id':'Wise_Woman','language_boost':'Russian','emotion':'fluent','speed':1.05}},timeout=60).json()
    url=p['urls']['get']
    for _ in range(80):
        time.sleep(3); s=requests.get(url,headers=h,timeout=30).json()
        if s['status']=='succeeded':
            o=s['output']; o=o if isinstance(o,str) else o[0]; open(out,'wb').write(requests.get(o,timeout=60).content); print('OK',out,flush=True); return
        if s['status']=='failed': print('FAIL',out,flush=True); return
minimax(BASE.format(w1='хлорофилла',w2='Хлорофилл'), 'output/reels05/hf/vo_opts/A_minimax_plain.mp3')
minimax(BASE.format(w1='хларафи́лла',w2='Хларафи́лл'), 'output/reels05/hf/vo_opts/B_minimax_phon.mp3')
# ElevenLabs (Lily)
if EL:
    h={'xi-api-key':EL,'Content-Type':'application/json'}
    body={'text':BASE.format(w1='хлорофилла',w2='Хлорофилл'),'model_id':'eleven_multilingual_v2','voice_settings':{'stability':0.45,'similarity_boost':0.8,'speed':1.05}}
    r=requests.post('https://api.elevenlabs.io/v1/text-to-speech/pFZP5JQG7iQjIQuC4Bku',headers=h,json=body,timeout=120)
    if r.status_code==200: open('output/reels05/hf/vo_opts/C_eleven_lily.mp3','wb').write(r.content); print('OK C_eleven',flush=True)
    else: print('EL ERR',r.status_code,r.text[:80],flush=True)
