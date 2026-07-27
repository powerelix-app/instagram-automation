#!/usr/bin/env python3
"""Скачивание фото карточек Ozon (референсы «по мотивам»). Умеет НЕСКОЛЬКО ссылок за
один запуск и ссылки на ПОИСК/КАТЕГОРИЮ (сам соберёт топ-N товаров из выдачи).

Использование (VPN ВЫКЛЮЧИ — нужен домашний российский IP):
    .venv/bin/python scripts/ozon_photos.py <url1> <url2> ...
    .venv/bin/python scripts/ozon_photos.py --n 8 "<ссылка на поиск>"

Опции:  --out DIR   корневая папка (default output/ozon_competitor)
        --n N       сколько товаров брать из поисковой выдачи (default 6)

Каждый товар → своя подпапка. Браузер открывается ОДИН раз (одна капча на всё).
"""
import os
import re
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def upscale(url: str) -> str:
    return re.sub(r"/wc\d+/", "/wc1920/", url)


def slug_of(url: str) -> str:
    m = re.search(r"/product/([^/?]+)", url)
    s = (m.group(1) if m else "product")[:60]
    return re.sub(r"-+\d{6,}$", "", s) or s


def wait_captcha(page):
    low = page.content()[:3000].lower()
    if "Доступ" in page.title() or "captcha" in page.url.lower() or "challenge" in low:
        try:
            page.screenshot(path="ozon_challenge.png")   # что именно показал антибот
            print("  (скриншот антибота: ozon_challenge.png)")
        except Exception:
            pass
        if sys.stdin.isatty():
            print("⚠️  Капча/антибот — реши в окне браузера, потом Enter здесь…")
            input()
        else:
            wait_s = int(os.environ.get("OZON_WAIT", "30"))
            print(f"⚠️  Капча — жду {wait_s}с…")
            time.sleep(wait_s)


def collect_image_urls(page) -> list:
    urls = page.eval_on_selector_all(
        "img",
        """els => els.flatMap(e => [e.currentSrc, e.src,
             ...(e.srcset||'').split(',').map(s=>s.trim().split(' ')[0])])"""
    ) or []
    html = page.content()
    urls += re.findall(r'https://[^"\\\\ ]*?ozone?\.ru/[^"\\\\ ]*?multimedia[^"\\\\ ]*?\.(?:jpg|jpeg|png|webp)', html)
    out, seen = [], set()
    for u in urls:
        if not u or "multimedia" not in u:
            continue
        u = upscale(u)
        key = re.sub(r"/wc\d+/", "/", u)
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out


def collect_product_links(page, n: int) -> list:
    """Со страницы поиска/категории — ссылки первых n товаров."""
    hrefs = page.eval_on_selector_all(
        'a[href*="/product/"]', "els => els.map(e => e.href)") or []
    out, seen = [], set()
    for h in hrefs:
        m = re.search(r"(https://www\.ozon\.ru/product/[^/?#]+/)", h)
        if not m:
            continue
        u = m.group(1)
        if u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= n:
            break
    return out


def scroll(page, times=6):
    for _ in range(times):
        page.mouse.wheel(0, 1200)
        time.sleep(0.7)
    time.sleep(1.5)


def download_product(page, url: str, root: Path) -> int:
    print(f"\n→ товар: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    wait_captcha(page)
    scroll(page)
    urls = collect_image_urls(page)
    outdir = root / slug_of(url)
    outdir.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, u in enumerate(urls, 1):
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=30)
            if r.ok and len(r.content) > 5000:
                ext = ".png" if ".png" in u else ".jpg"
                (outdir / f"ozon_{i:02d}{ext}").write_bytes(r.content)
                n += 1
        except Exception as e:
            print(f"  ✗ {i}: {e}")
    print(f"  ✓ скачано {n} фото → {outdir}")
    return n


def main():
    args = sys.argv[1:]
    root, n_search, urls = Path("output/ozon_competitor"), 6, []
    i = 0
    while i < len(args):
        if args[i] == "--out":
            root = Path(args[i + 1]); i += 2
        elif args[i] == "--n":
            n_search = int(args[i + 1]); i += 2
        else:
            urls.append(args[i]); i += 1
    if not urls:
        print(__doc__)
        sys.exit(1)

    headless = os.environ.get("OZON_HEADLESS", "0") == "1"
    total = 0
    with sync_playwright() as p:
        # НАСТОЯЩИЙ Google Chrome с постоянным профилем — отпечаток реального браузера,
        # антибот Ozon пропускает (плейрайтовский Chromium он режет даже на домашнем IP).
        # Профиль персистентный: капчу/куки достаточно пройти один раз.
        profile = str(Path.home() / ".ozon_chrome_profile")
        common = dict(headless=headless, locale="ru-RU", timezone_id="Europe/Moscow",
                      viewport={"width": 1400, "height": 1000},
                      args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                            "--disable-dev-shm-usage"])
        try:
            ctx = p.chromium.launch_persistent_context(profile, channel="chrome", **common)
            print("→ браузер: настоящий Google Chrome")
        except Exception as e:
            print(f"→ Chrome не найден ({e}) — fallback на Chromium")
            ctx = p.chromium.launch_persistent_context(profile, **common)
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()

        product_urls = []
        for u in urls:
            if "/product/" in u:
                product_urls.append(u)
            else:  # поиск / категория → собрать товары из выдачи
                print(f"→ поисковая выдача: {u}")
                page.goto(u, wait_until="domcontentloaded", timeout=60000)
                wait_captcha(page)
                scroll(page, 8)
                found = collect_product_links(page, n_search)
                print(f"  найдено товаров: {len(found)}")
                product_urls += found

        # дедуп, сохраняя порядок
        seen = set()
        product_urls = [u for u in product_urls if not (u in seen or seen.add(u))]
        print(f"\nВсего товаров к скачиванию: {len(product_urls)}")
        for u in product_urls:
            total += download_product(page, u, root)
        ctx.close()

    print(f"\n=== ИТОГО: {total} фото, папки в {root} ===")


if __name__ == "__main__":
    main()
