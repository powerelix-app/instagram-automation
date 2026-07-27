#!/usr/bin/env python3
"""Скачивание всех фото карточки товара с Ozon (для референса «по мотивам»).

Использование:
    .venv/bin/python scripts/ozon_photos.py "<ozon_product_url>" [папка_вывода]

Ozon режет ботов на самой странице, поэтому открываем реальным браузером (Playwright,
headed) — с твоего Мака (резидентный IP) проходит. Если всплывёт капча — реши её в окне,
скрипт подождёт. Собираем все URL картинок галереи, апскейлим (wc1000→wc1920) и качаем.
"""
import re
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def upscale(url: str) -> str:
    """Ozon-URL с /wcNNN/ → крупнее (wc1920). Оставляем как есть, если размера нет."""
    return re.sub(r"/wc\d+/", "/wc1920/", url)


def collect_image_urls(page) -> list[str]:
    """Все URL картинок товара со страницы: из <img src/srcset> + из JSON-стейта."""
    urls = page.eval_on_selector_all(
        "img",
        """els => els.flatMap(e => [e.currentSrc, e.src,
             ...(e.srcset||'').split(',').map(s=>s.trim().split(' ')[0])])"""
    ) or []
    # + вытащить из сырого HTML (Ozon кладёт ссылки в JSON-стейт)
    html = page.content()
    urls += re.findall(r'https://[^"\\\\ ]*?ozone?\.ru/[^"\\\\ ]*?multimedia[^"\\\\ ]*?\.(?:jpg|jpeg|png|webp)', html)
    # только мультимедиа-картинки товара, крупные, без иконок
    out, seen = [], set()
    for u in urls:
        if not u or "multimedia" not in u:
            continue
        u = upscale(u)
        # ключ = id картинки без размера (дедуп разных размеров)
        key = re.sub(r"/wc\d+/", "/", u)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: ozon_photos.py <url> [outdir]"); sys.exit(1)
    url = sys.argv[1]
    outdir = Path(sys.argv[2] if len(sys.argv) > 2 else "output/ozon_competitor")
    outdir.mkdir(parents=True, exist_ok=True)

    import os
    headless = os.environ.get("OZON_HEADLESS", "0") == "1"   # =1 на сервере (нет дисплея)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                  "--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=UA, locale="ru-RU", timezone_id="Europe/Moscow",
                                  viewport={"width": 1400, "height": 1000})
        # прячем webdriver-флаг (антибот его читает)
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()
        print("→ открываю карточку…")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # прокрутка, чтобы галерея и ниже-контент подгрузились (ленивые картинки)
        for _ in range(6):
            page.mouse.wheel(0, 1200); time.sleep(0.8)
        time.sleep(2)
        # если капча/заглушка — дать время решить вручную
        if "Доступ" in page.title() or "captcha" in page.url.lower() or "challenge" in page.content()[:2000].lower():
            if sys.stdin.isatty():
                print("⚠️  Похоже на антибот/капчу. Реши в открытом окне, потом Enter здесь…")
                input()
            else:
                print("⚠️  Антибот/капча — жду 30с на ручное решение в окне…")
                time.sleep(30)
        urls = collect_image_urls(page)
        print(f"→ найдено картинок: {len(urls)}")
        browser.close()

    n = 0
    for i, u in enumerate(urls, 1):
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=30)
            if r.ok and len(r.content) > 5000:
                ext = ".jpg" if "png" not in u else ".png"
                (outdir / f"ozon_{i:02d}{ext}").write_bytes(r.content)
                n += 1
                print(f"  ✓ {i:02d} — {len(r.content)//1024} КБ")
        except Exception as e:
            print(f"  ✗ {i}: {e}")
    print(f"\nГотово: {n} фото → {outdir}")


if __name__ == "__main__":
    main()
