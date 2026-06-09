"""CLI: генерация фоновой сцены через Replicate (фаза 1).

Примеры:
  python generate_scene.py --prompt "dark gym studio, dramatic rim light, energetic mood"
  python generate_scene.py --prompt "cozy sunlit kitchen, warm morning light" --ratio 9:16 --hq
"""
import argparse

from ig_automation.scenes import RATIOS, generate_scene


def main() -> None:
    ap = argparse.ArgumentParser(description="Генерация фоновой сцены (Replicate)")
    ap.add_argument("--prompt", required=True, help="Описание сцены (англ. — лучше для моделей)")
    ap.add_argument("--ratio", default="4:5", choices=list(RATIOS))
    ap.add_argument("--hq", action="store_true", help="финальное качество (flux-1.1-pro-ultra)")
    ap.add_argument("--model", default=None, help="slug Replicate-модели (переопределить дефолт)")
    ap.add_argument("--out", default=None, help="имя файла в output/scenes/ (напр. test.png)")
    a = ap.parse_args()

    path = generate_scene(a.prompt, ratio=a.ratio, hq=a.hq, model=a.model, out_name=a.out)
    print(f"✅ сцена сохранена: {path}")


if __name__ == "__main__":
    main()
