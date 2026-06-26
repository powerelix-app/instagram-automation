import os, time
from io import BytesIO
from PIL import Image
for line in open('.env'):
    if line.startswith('REPLICATE_API_TOKEN='): os.environ['REPLICATE_API_TOKEN']=line.strip().split('=',1)[1]
    if line.startswith('OPENAI_API_KEY='): os.environ['OPENAI_API_KEY']=line.strip().split('=',1)[1]
from ig_automation.scenes import _call_replicate_gptimage, _fit
B='output/scenes/bottle_ref.jpg'
GREEN='deep emerald-green (dark forest-emerald, like concentrated liquid chlorophyll)'
GLASS='a tall smooth straight-sided clear drinking glass'
shots=[
 ('anchor_bottle', 'Vertical product photo: the POWERELIX chlorophyll bottle from the reference, keep label IDENTICAL, pulled back, frosted with fine condensation water droplets all over it, clean white marble counter, soft natural daylight, fresh premium, photoreal', [B]),
 ('anchor_drink', f'Vertical photo: a young woman drinks {GLASS} filled with {GREEN} chlorophyll water, profile medium close-up, bright airy kitchen with indoor plants, soft natural morning light, healthy refreshed, photoreal', []),
 ('anchor_life', f'Vertical photo: a young woman holds {GLASS} filled with {GREEN} chlorophyll water, walking in a bright modern home with large windows and plants, fresh energized, warm natural light, photoreal', []),
]
for name,prompt,refs in shots:
    done=False
    for a in range(4):
        try:
            c=_call_replicate_gptimage(prompt,refs,aspect_ratio='2:3')
            _fit(Image.open(BytesIO(c)).convert('RGB'),'9:16').save(f'output/reels05/hf/{name}.png')
            print('OK',name,flush=True); done=True; break
        except Exception as e:
            print('ERR',name,a,str(e)[:90],flush=True); time.sleep(10)
    if not done: print('GIVEUP',name,flush=True)
