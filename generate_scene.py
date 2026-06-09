"""CLI: генерация сцены (Replicate) + опц. бренд-оверлей (фазы 1–2).

Примеры:
  # просто сцена
  python generate_scene.py --prompt "dark gym studio, dramatic rim light"

  # сцена + лайфстайл-обложка (каркас band) с заголовком
  python generate_scene.py --prompt "cozy sunlit kitchen, warm light" \
      --overlay band --title "Утро начинается с заботы"

  # сцена + врезка реальной банки (продукт 2 = Магний) + каркас block
  python generate_scene.py --prompt "calm dark bedroom, soft moonlight" \
      --overlay block --product 2
"""
import argparse

from ig_automation.brand_overlay import render_hero
from ig_automation.scenes import RATIOS, generate_scene


def main() -> None:
    ap = argparse.ArgumentParser(description="Генерация сцены (Replicate) + бренд-оверлей")
    ap.add_argument("--prompt", required=True, help="Описание сцены (англ. — лучше для моделей)")
    ap.add_argument("--ratio", default="4:5", choices=list(RATIOS))
    ap.add_argument("--hq", action="store_true", help="финальное качество (flux-1.1-pro-ultra)")
    ap.add_argument("--model", default=None, help="slug Replicate-модели (переопределить дефолт)")
    ap.add_argument("--out", default=None, help="имя файла сцены в output/scenes/")
    # оверлей (фаза 2)
    ap.add_argument("--overlay", default="none", choices=["none", "block", "band", "anchor"],
                    help="наложить бренд-каркас на сцену")
    ap.add_argument("--title", default="", help="заголовок (пусто = без заголовка)")
    ap.add_argument("--subtitle", default="", help="подзаголовок в фирменных { }")
    ap.add_argument("--product", default=None, help="id продукта: врезать банку + акцент/подпись")
    a = ap.parse_args()

    scene = generate_scene(a.prompt, ratio=a.ratio, hq=a.hq, model=a.model, out_name=a.out)
    print(f"✅ сцена: {scene}")

    if a.overlay != "none" or a.product:
        style = a.overlay if a.overlay != "none" else "block"
        card = scene.with_name(scene.stem + f"_{style}.png")
        render_hero(style, title=a.title, out_path=card, bg_path=scene,
                    subtitle=a.subtitle, product_id=a.product)
        print(f"✅ карточка: {card}")


if __name__ == "__main__":
    main()
