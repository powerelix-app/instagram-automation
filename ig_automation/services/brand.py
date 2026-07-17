"""Бренд-ассеты: лицо AI-модели, логотип, банки товаров — для брендированной генерации.

Банка конкретного товара передаётся в Grok как мультиреференс (лицо + банка) →
на картинке настоящий продукт с читаемой этикеткой, а не абстрактный «POWERELIX».
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import List, Optional

from .. import config
from ..db.base import session_scope
from ..db.models import BrandAsset

log = logging.getLogger(__name__)

BRAND_DIR = config.MEDIA_DIR / "brand"
DEFAULT_MODEL = config.ROOT / "assets" / "brand" / "ai_model.png"
_ALLOWED = {".png", ".jpg", ".jpeg", ".webp"}


def _abs(web_path: str) -> Path:
    return config.MEDIA_DIR / web_path.replace("/media/", "", 1)


def add_asset(kind: str, file_bytes: bytes, filename: str, product: str = "", label: str = "") -> int:
    if kind not in ("model", "logo", "product"):
        raise ValueError("kind должен быть model|logo|product")
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED:
        raise ValueError("формат не поддерживается (нужен PNG/JPG/WEBP)")
    if not file_bytes:
        raise ValueError("пустой файл")
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{kind}_{hashlib.md5(file_bytes).hexdigest()[:12]}{ext}"
    (BRAND_DIR / name).write_bytes(file_bytes)
    with session_scope() as s:
        a = BrandAsset(kind=kind, product=product.strip(), label=label.strip(),
                       path=f"/media/brand/{name}", active=True)
        s.add(a)
        s.flush()
        return a.id


def list_assets() -> List[BrandAsset]:
    with session_scope() as s:
        return s.query(BrandAsset).order_by(BrandAsset.kind, BrandAsset.id.desc()).all()


def delete_asset(asset_id: int) -> None:
    with session_scope() as s:
        a = s.get(BrandAsset, asset_id)
        if not a:
            return
        try:
            _abs(a.path).unlink()
        except OSError:
            pass
        s.delete(a)


def list_models() -> list:
    """Ростер лиц бренда: дефолт + assets/brand/models/*.png (ключ = имя файла)."""
    out = [{"key": "", "name": "Основная (рыжая)", "path": str(model_ref())}]
    mdir = config.ROOT / "assets" / "brand" / "models"
    names = {"cand_blonde": "Блондинка", "cand_brunette": "Брюнетка",
             "sport_blonde": "Спорт-блонд", "sport_caramel": "Спорт-карамель",
             "sport_yoga": "Йога", "man_athletic": "Мужчина-атлет",
             "man_casual": "Мужчина-кэжуал", "man_mature": "Мужчина 40+"}
    if mdir.exists():
        for f in sorted(mdir.glob("*.png")):
            if f.stem.startswith("_"):
                continue
            out.append({"key": f.stem, "name": names.get(f.stem, f.stem), "path": str(f)})
    return out


def model_by_key(key: str) -> Path:
    """Лицо по ключу ростера; пусто/не найдено -> основная модель."""
    if key:
        f = config.ROOT / "assets" / "brand" / "models" / f"{key}.png"
        if f.exists():
            return f
    return model_ref()


def model_ref() -> Path:
    """Активное лицо модели (последнее загруженное) или дефолтный ai_model.png."""
    with session_scope() as s:
        a = (
            s.query(BrandAsset)
            .filter(BrandAsset.kind == "model", BrandAsset.active.is_(True))
            .order_by(BrandAsset.id.desc())
            .first()
        )
        if a:
            p = _abs(a.path)
            if p.exists():
                return p
    return DEFAULT_MODEL


def logo_ref() -> Optional[Path]:
    """Путь к последнему загруженному логотипу (для оверлея на сгенерированный визуал)."""
    with session_scope() as s:
        a = (
            s.query(BrandAsset).filter(BrandAsset.kind == "logo")
            .order_by(BrandAsset.id.desc()).first()
        )
        if a:
            p = _abs(a.path)
            if p.exists():
                return p
    return None


def product_ref(product_name: str) -> Optional[Path]:
    """Банка товара по подстроке (asset.product входит в название из поста, или наоборот)."""
    if not product_name or product_name.strip() in ("", "—"):
        return None
    pn = product_name.lower()
    with session_scope() as s:
        for a in s.query(BrandAsset).filter(BrandAsset.kind == "product").all():
            key = (a.product or "").lower().strip()
            if key and (key in pn or pn in key):
                p = _abs(a.path)
                if p.exists():
                    return p
    return None
