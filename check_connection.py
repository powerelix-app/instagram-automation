#!/usr/bin/env python3
"""Проверка связи с Instagram API: печатает профиль аккаунта POWERELIX."""
from __future__ import annotations

import json

from ig_automation.instagram import get_profile


def main() -> None:
    print("Запрашиваю профиль через Instagram API…")
    profile = get_profile()
    print(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
