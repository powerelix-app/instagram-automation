"""Сравнение генераторов сочных фонов: nano-banana vs gpt-image vs flux-ultra.

Один и тот же «премиум-продуктовый» промпт (эталон — WB-карточки хлорофилла:
изумруд, всплеск воды, мята, мокрый камень, драматичный свет) гоняем тремя
моделями и кладём результаты рядом, чтобы выбрать победителя до того, как
перегенерировать всю карусель.
"""
import os
import traceback

from PIL import Image, ImageDraw, ImageFont

from ig_automation.scenes import generate_scene

PROMPT = (
    "premium product photography backdrop, deep emerald and dark green gradient "
    "background, fresh vibrant mint leaves, dynamic water splash frozen mid-air, "
    "glistening water droplets, wet black stone podium, dramatic rim lighting, "
    "high contrast, richly saturated vivid colors, cinematic studio lighting, "
    "glossy reflections, lush fresh and alive, empty space in lower center for a "
    "product, ultra detailed, commercial advertising quality"
)

MODELS = [
    ("nanobanana", "google/nano-banana"),
    ("gptimage", "openai/gpt-image-1"),
    ("fluxultra", "black-forest-labs/flux-1.1-pro-ultra"),
]

os.makedirs("output/scenes", exist_ok=True)
results = []
for label, mdl in MODELS:
    out = f"output/scenes/cmp_{label}.png"
    try:
        generate_scene(PROMPT, ratio="4:5", model=mdl, out_name=f"cmp_{label}.png")
        results.append((label, out))
        print(f"OK  {label:12} → {out}")
    except Exception as e:
        print(f"FAIL {label:12}: {e}")
        traceback.print_exc()

# контактный лист бок о бок
if results:
    tw, th = 540, 675
    sheet = Image.new("RGB", (tw * len(results), th + 50), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.truetype(str(__import__("pathlib").Path.home()
                               / "Library/Fonts/Inter-ExtraBold.otf"), 30)
    except Exception:
        f = ImageFont.load_default()
    for i, (label, path) in enumerate(results):
        im = Image.open(path).resize((tw, th))
        sheet.paste(im, (i * tw, 50))
        d.text((i * tw + 16, 12), label, font=f, fill=(20, 20, 20))
    sheet.save("output/scenes/_compare_sheet.jpg", quality=85)
    print("сравнение:", "output/scenes/_compare_sheet.jpg")
