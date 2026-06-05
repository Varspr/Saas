"""Фаза 1а — получение фото одежды по ссылке.

Логика fetch_image():
  1. Если ссылка — прямая картинка (по content-type/расширению) → качаем.
  2. Иначе это страница товара → достаём главное фото:
       а) og:image / twitter:image из мета-тегов (быстро, httpx + BS4);
       б) доменные CSS-селекторы (DOMAIN_SELECTORS);
       в) если сайт рендерится через JS (WB/Ozon/Lamoda/Zara — SPA) →
          Playwright headless как резерв.
  3. Любое фото нормализуем: RGB, вписываем в 1024×1024.

Сохранённый файл — вход для сегментации.
"""
from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image

# Главное фото товара для популярных магазинов (приоритет из плана).
# SPA-сайты часто кладут картинку в og:image, поэтому селекторы — резерв.
DOMAIN_SELECTORS: dict[str, str] = {
    "wildberries.ru": "img.photo-zoom__preview, .slide__content img",
    "ozon.ru": "div[data-widget='webGallery'] img",
    "lamoda.ru": ".product-gallery__main img, img.gallery__img",
    "zara.com": "img.media-image__image, picture.media-image img",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".avif")


def fetch_image(url: str, dest: Path) -> Path:
    url = str(url)

    # 1. Прямая картинка
    if _looks_like_image_url(url):
        data = _http_get_bytes(url)
        return _normalize_to_png(data, dest)

    # 2. Страница товара: пробуем мета-теги и доменные селекторы
    try:
        html = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=20).text
        img_url = _extract_product_image(html, url)
        if img_url:
            return _normalize_to_png(_http_get_bytes(img_url), dest)
    except Exception:
        pass  # перейдём к Playwright

    # 3. JS-сайт: Playwright headless
    img_url = _scrape_with_playwright(url)
    if not img_url:
        raise RuntimeError(f"Не удалось найти фото товара по ссылке: {url}")
    return _normalize_to_png(_http_get_bytes(img_url), dest)


# ── helpers ───────────────────────────────────────────────────────────────

def _looks_like_image_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith(_IMG_EXT):
        return True
    try:
        head = httpx.head(url, headers=_HEADERS, follow_redirects=True, timeout=10)
        return head.headers.get("content-type", "").startswith("image/")
    except Exception:
        return False


def _http_get_bytes(url: str) -> bytes:
    resp = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp.content


def _extract_product_image(html: str, base_url: str) -> str | None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # og:image / twitter:image — самый надёжный путь для магазинов
    for prop in ("og:image", "og:image:secure_url", "twitter:image"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if tag and tag.get("content"):
            return urljoin(base_url, tag["content"])

    # Доменные селекторы
    host = urlparse(base_url).netloc.replace("www.", "")
    for domain, selector in DOMAIN_SELECTORS.items():
        if domain in host:
            el = soup.select_one(selector)
            if el and el.get("src"):
                return urljoin(base_url, el["src"])
    return None


def _scrape_with_playwright(url: str) -> str | None:
    """Резерв для SPA-сайтов: дожидаемся рендера и берём og:image/первое крупное фото."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            page.goto(url, wait_until="networkidle", timeout=30000)

            og = page.locator("meta[property='og:image']").first
            if og.count():
                content = og.get_attribute("content")
                if content:
                    return urljoin(url, content)

            host = urlparse(url).netloc.replace("www.", "")
            for domain, selector in DOMAIN_SELECTORS.items():
                if domain in host:
                    el = page.locator(selector).first
                    if el.count():
                        src = el.get_attribute("src")
                        if src:
                            return urljoin(url, src)
            return None
        finally:
            browser.close()


def _normalize_to_png(data: bytes, dest: Path, size: int = 1024) -> Path:
    """RGB, вписать в квадрат size×size на белом фоне."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "PNG")
    return dest
