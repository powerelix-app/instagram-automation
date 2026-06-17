"""Сэмплы: генерим свежие сцены (Replicate, лицо бренда) и накладываем эталонный стиль
обложки (brand_overlay) — чтобы посмотреть, как ляжет текст на разном фоне."""
from pathlib import Path

from PIL import Image, ImageDraw

from ig_automation import scenes
from ig_automation.services import brand
from ig_automation.brand_overlay import (
    W, H, M, _font, _cover, _scrim, _spaced,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, _hex,
)

ACCENT = _hex("#00C29B")
OUT = Path("output/overlay_styles")
OUT.mkdir(parents=True, exist_ok=True)

NOTEXT = ("БЕЗ ТЕКСТА в кадре: никаких букв, слов, надписей, логотипов, этикеток с текстом; "
          "no text, no letters, no words, no captions, no labels, no logo anywhere; "
          "оставь чистое пространство для текста потом")
FACE = "молодая привлекательная девушка — то же лицо что на референсе, естественный свет, "\
       "чистая современная эстетика здоровья и энергии"


def _wrap(d, text, font, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def cover(photo, hook, sub, tag, out):
    img = _scrim(_cover(Image.open(photo)), top=140, bottom=660)
    d = ImageDraw.Draw(img)
    _spaced(d, (M, 60), "POWERELIX", _font(MONT_BLACK, 52), WHITE, 3)
    fh, fs, ft = _font(MONT_BLACK, 104), _font(INTER_SB, 42), _font(INTER_MED, 28)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    subl = _wrap(d, sub, fs, W - 2 * M)
    HEAD_LH, SUB_LH = 110, 54
    # Якорим снизу вверх с явными зазорами (тег ↔ подзаголовок ↔ акцент ↔ заголовок).
    tag_y = H - 84
    sub_bottom = tag_y - 48                       # гарантированный зазор до «СОХРАНИ»
    sub_top = sub_bottom - len(subl) * SUB_LH
    accent_y = sub_top - 30
    head_bottom = accent_y - 22
    y = head_bottom - len(lines) * HEAD_LH
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += HEAD_LH
    d.rectangle([M, accent_y, M + 110, accent_y + 8], fill=ACCENT)
    y = sub_top
    for ln in subl:
        d.text((M, y), ln, font=fs, fill=WHITE); y += SUB_LH
    _spaced(d, (M, tag_y), tag, ft, ACCENT, 4)
    img.save(out)
    return out


def gen(out_name, prompt):
    p = OUT / out_name
    if p.exists():                                # переиспользуем уже сгенеренную сцену
        return p
    scene = scenes.generate_branded(f"{prompt}. {FACE}. {NOTEXT}",
                                    refs=[brand.model_ref()], ratio="4:5", out_name=out_name)
    Image.open(scene).convert("RGB").save(p)
    return p


if __name__ == "__main__":
    from ig_automation.db import base as _db
    _db.init()
    a = gen("_scene_energy.png",
            "профессиональная чистая лайфстайл-фотография: девушка со здоровым сиянием держит "
            "стакан зелёного смузи у светлого окна на современной кухне, утренний свет, бодрость")
    cover(a, "Энергия с самого утра",
          "Хлорофилл — зелёная перезагрузка дня", "СОХРАНИ  →", OUT / "S1_energy.png")
    print("ok energy")

    b = gen("_scene_evening.png",
            "профессиональная лайфстайл-фотография: девушка спокойно отдыхает на диване в тёплом "
            "вечернем свете лампы, уютно, расслабленное умиротворённое настроение, мягкий полумрак")
    cover(b, "Засыпай без тревог",
          "Магний + B6 для спокойных нервов", "СОХРАНИ  →", OUT / "S2_evening.png")
    print("ok evening")

    # контроль длинного подзаголовка (где был наезд на «СОХРАНИ»)
    cover("/tmp/post1_check.png", "Магний для спокойных нервов",
          "Поддержка нервной системы и лёгкое засыпание", "СОХРАНИ  →", OUT / "S3_longsub.png")
    print("ok longsub")
