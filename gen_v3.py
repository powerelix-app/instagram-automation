import os, time
from io import BytesIO
from PIL import Image
for line in open('.env'):
    if line.startswith('REPLICATE_API_TOKEN='): os.environ['REPLICATE_API_TOKEN']=line.strip().split('=',1)[1]
    if line.startswith('OPENAI_API_KEY='): os.environ['OPENAI_API_KEY']=line.strip().split('=',1)[1]
from ig_automation.scenes import _call_replicate_gptimage, _fit
B='output/scenes/bottle_ref.jpg'; MODEL='assets/brand/ai_model.png'
GREEN='deep emerald-green (dark forest-emerald, concentrated liquid chlorophyll)'
GLASS='a tall smooth straight-sided clear drinking glass'
shots=[
 ('glass2', f'Vertical product photo: ONLY {GLASS} filled with {GREEN} chlorophyll water, alone on a clean white marble counter, NOTHING else in frame — no jars, no powder, no bowls, plain minimal background, fine condensation droplets on the glass, soft daylight, photoreal', []),
 ('drink2', f'Vertical photo: the young woman from the reference (auburn wavy hair, freckles) drinks {GLASS} of {GREEN} chlorophyll water, profile medium close-up, bright airy kitchen with plants, soft morning light, healthy, keep her face identical to reference, photoreal', [MODEL]),
 ('life2', f'Vertical photo: the young woman from the reference (auburn wavy hair, freckles) holds {GLASS} of {GREEN} chlorophyll water, walking in a bright modern home with plants, fresh energized, warm light, keep her face identical to reference, photoreal', [MODEL]),
 ('pour2', f'Vertical product photo: the POWERELIX chlorophyll bottle from the reference tilted, pouring {GREEN} liquid into {GLASS} on clean white marble. The bottle label is PERFECTLY FLAT, fully intact, crisp and readable — NOT peeling, NOT wrinkled. Keep label identical to reference. soft daylight, photoreal', [B]),
]
for name,prompt,refs in shots:
    for a in range(4):
        try:
            c=_call_replicate_gptimage(prompt,refs,aspect_ratio='2:3')
            _fit(Image.open(BytesIO(c)).convert('RGB'),'9:16').save(f'output/reels05/hf/anchor_{name}.png'); print('OK',name,flush=True); break
        except Exception as e: print('ERR',name,a,str(e)[:70],flush=True); time.sleep(10)
