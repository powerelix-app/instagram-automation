"""Reels №5-UGC «Блогер-обзор» (коллаген) — формат «живой UGC».

Цель: выглядеть как реальный блогер с телефона, а НЕ как нейросеть/реклама.
Что дало реализм (выводы 2026-06-25):
  • Кадр — UGC-СЕЛФИ (телефон, домашняя ванная, держит банку, casual, без студийного
    глянца), а не глянцевый студийный портрет. gpt-image-2: input=[ai_model, банка] +
    «UGC-style selfie shot on phone, candid, amateur, talking to camera».
  • Движение — ЭНЕРГИЧНОЕ (Grok: «talks energetically like a vlogger, lively expression,
    eyebrow raise, gestures»), НЕ «minimal calm» (то давало сонность).
  • Липсинк — latentsync на зацикленном (бумеранг) клипе под взрослый голос
    MiniMax **Wise_Woman** (не «girl» — та звучала по-детски).
  • Оверлеи — МИНИМАЛЬНЫЕ UGC-сабтитры (белый текст на тёмной капсуле), без брендовых
    плашек/вордмарка (они «палят» рекламу).

ВАЖНО: latentsync отдаёт 720×1280 — перед наложением 1080×1920 сабтитров видео надо
отскейлить до 1080×1920 (иначе плашки уходят за кадр).

Пайплайн (шаги генерации — внешние, см. историю): portrait → ugc_base(Grok) →
ugc_loop(boomerang) → ugc_lipsync(latentsync). Этот скрипт делает финальную сборку
(скейл + сабтитры) из output/reels05/ugc/ugc_lipsync.mp4.
"""
import subprocess

from PIL import Image, ImageDraw

from ig_automation.brand_overlay import _font, INTER_XB

W, H = 1080, 1920
U = "output/reels05/ugc"
LS = f"{U}/ugc_lipsync.mp4"
OUT = "output/reels05/reels05_ugc.mp4"
HOOK = "Крем не вернёт упругость"
END = "Коллаген Пауэрликс — в профиле"


def caption(path, text):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = _font(INTER_XB, 58)
    tw = d.textlength(text, font=f)
    x = (W - tw) / 2
    y = 1380
    pad = 26
    d.rounded_rectangle([x - pad, y - pad, x + tw + pad, y + 58 + pad], radius=28, fill=(0, 0, 0, 140))
    d.text((x + 2, y + 2), text, font=f, fill=(0, 0, 0, 180))
    d.text((x, y), text, font=f, fill=(255, 255, 255, 255))
    ov.save(path)
    return path


def build():
    ch = caption(f"{U}/cap_hook.png", HOOK)
    ce = caption(f"{U}/cap_end.png", END)
    # latentsync = 720×1280 → скейл до 1080×1920, потом UGC-сабтитры по таймингу
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[bg];"
          f"[bg][1:v]overlay=0:0:enable='between(t,0.3,3.0)'[a];"
          f"[a][2:v]overlay=0:0:enable='gte(t,9.8)'[v]")
    subprocess.run(["ffmpeg", "-y", "-i", LS, "-i", ch, "-i", ce, "-filter_complex", fc,
                    "-map", "[v]", "-map", "0:a", "-c:a", "aac", "-b:a", "160k",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", OUT], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", OUT], capture_output=True, text=True).stdout.strip()
    print(f"OK {OUT} ({float(d):.1f}s)")


if __name__ == "__main__":
    build()
