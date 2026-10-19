#!/usr/bin/env python3
"""Fetch public RSS feeds and create news.json for the static GitHub Pages site."""
from __future__ import annotations

import calendar
import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "news.json"
USER_AGENT = "TaiwanAutoDaily/1.0 (public RSS reader; contact: repository owner)"
MAX_ITEMS = 90
MAX_AGE_DAYS = 14
TIMEOUT = 18

GOOGLE_NEWS_QUERIES = [
    ("新車上市", "台灣 汽車 新車 發表 上市 when:7d"),
    ("試駕評測", "台灣 汽車 試駕 評測 實測 when:7d"),
    ("車價資訊", "台灣 汽車 車價 售價 優惠 促銷 when:7d"),
    ("品牌動態", "台灣 車廠 汽車 品牌動態 車市 when:7d"),
    ("交通法規", "台灣 汽車 交通法規 車輛 召回 when:7d"),
    ("產業新聞", "台灣 汽車產業 電動車 車市 銷量 when:7d"),
    ("專業汽車媒體", "site:u-car.com.tw 汽車 新車 試駕 when:7d"),
    ("專業汽車媒體", "site:carstuff.com.tw 汽車 新車 試駕 when:7d"),
    ("官方交通消息", "site:thb.gov.tw 汽車 交通法規 公告 when:7d"),
    ("官方交通消息", "site:freeway.gov.tw 汽車 道路 交通 公告 when:7d"),
]

# The Ministry of Transportation and Communications provides an RSS endpoint.
DIRECT_FEEDS = [
    ("交通部", "https://www.motc.gov.tw/ch/app/rss/News", "交通法規"),
]

CAR_TERMS = [
    "汽車", "新車", "車款", "車市", "車廠", "車價", "試駕", "試車", "電動車", "油電",
    "車輛", "汽車產業", "交通法規", "道路交通", "車牌", "駕照", "召回", "車展", "車主",
    "Toyota", "Honda", "Tesla", "BMW", "Mazda", "Nissan", "Hyundai", "Kia", "Lexus",
    "Mercedes", "Volkswagen", "福特", "裕隆", "和泰", "中華汽車", "Subaru", "Mitsubishi",
    "公路局", "高速公路局", "道路交通", "交通安全", "交通政策", "監理站", "國道", "汽燃費", "牌照稅", "燃料費",
]
LEGAL_TERMS = ["交通法規", "道路交通", "交通部", "公路局", "高速公路局", "監理", "駕照", "車牌", "違規", "酒駕", "行車安全", "道路封閉", "召回"]
TEST_TERMS = ["試駕", "試車", "評測", "實測", "試乘", "體驗報告"]
PRICE_TERMS = ["車價", "售價", "萬元", "預售", "降價", "漲價", "優惠", "促銷", "配備編成", "價格"]
NEW_CAR_TERMS = ["新車", "發表", "上市", "導入", "改款", "大改款", "年式", "首發", "亮相", "預接單"]
INDUSTRY_TERMS = ["汽車產業", "供應鏈", "銷量", "銷售", "電動車", "車市", "營收", "工廠", "產能", "政策"]


def clean_text(value: str, limit: int = 420) -> str:
    soup = BeautifulSoup(value or "", "html.parser")
    text = html.unescape(soup.get_text(" ", strip=True))
    text = re.sub(r"\s+", " ", text).strip()
    # Google News summaries can contain source/time boilerplate; keep the excerpt concise.
    return text[:limit].rstrip()


def entry_image(entry) -> str:
    for key in ("media_thumbnail", "media_content"):
        values = entry.get(key) or []
        for value in values:
            url = value.get("url", "")
            if url.startswith(("https://", "http://")):
                return url
    for enclosure in entry.get("enclosures", []) or []:
        url = enclosure.get("href") or enclosure.get("url") or ""
        mime = enclosure.get("type", "")
        if url.startswith(("https://", "http://")) and (mime.startswith("image/") or re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", url, re.I)):
            return url
    for field in ("summary", "description", "content"):
        value = entry.get(field)
        if isinstance(value, list):
            value = " ".join(str(part.get("value", "")) for part in value if isinstance(part, dict))
        if value:
            soup = BeautifulSoup(str(value), "html.parser")
            image = soup.find("img")
            if image:
                url = image.get("src") or image.get("data-src") or ""
                if url.startswith(("https://", "http://")):
                    return url
    return ""


def published_datetime(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    return None


def infer_category(title: str, summary: str, default: str = "品牌動態") -> str:
    text = f"{title} {summary}".lower()
    if any(term.lower() in text for term in LEGAL_TERMS):
        return "交通法規"
    if any(term.lower() in text for term in TEST_TERMS):
        return "試駕評測"
    if any(term.lower() in text for term in PRICE_TERMS):
        return "車價資訊"
    if any(term.lower() in text for term in NEW_CAR_TERMS):
        return "新車上市"
    if any(term.lower() in text for term in INDUSTRY_TERMS):
        return "產業新聞"
    return default if default in {"新車上市", "試駕評測", "車價資訊", "品牌動態", "交通法規", "產業新聞"} else "品牌動態"


def is_relevant(title: str, summary: str, forced: bool = False) -> bool:
    if forced:
        return True
    text = f"{title} {summary}".lower()
    return any(term.lower() in text for term in CAR_TERMS)


def source_name(entry, fallback: str, link: str) -> str:
    source = entry.get("source") or {}
    name = source.get("title", "") if hasattr(source, "get") else ""
    if name:
        return clean_text(name, 80)
    host = urlparse(link).netloc.lower().removeprefix("www.")
    known = {
        "u-car.com.tw": "U-CAR",
        "news.u-car.com.tw": "U-CAR",
        "carstuff.com.tw": "車勢文化",
        "motc.gov.tw": "交通部",
        "thb.gov.tw": "交通部公路局",
        "freeway.gov.tw": "交通部高速公路局",
    }
    return known.get(host, fallback or host or "新聞來源")


def build_google_url(query: str) -> str:
    params = {
        "q": query,
        "hl": "zh-TW",
        "gl": "TW",
        "ceid": "TW:zh-Hant",
    }
    return "https://news.google.com/rss/search?" + urlencode(params)


def parse_feed(url: str, fallback_source: str, default_category: str, session: requests.Session, forced: bool = False):
    items = []
    try:
        response = session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            print(f"[WARN] Feed 無法解析：{url} ({parsed.bozo_exception})", file=sys.stderr)
        for entry in parsed.entries:
            title = clean_text(entry.get("title", ""), 180)
            link = entry.get("link", "").strip()
            if not title or not link or not link.startswith(("https://", "http://")):
                continue
            summary_html = entry.get("summary", "")
            if not summary_html and entry.get("content"):
                summary_html = " ".join(str(item.get("value", "")) for item in entry.get("content", []) if isinstance(item, dict))
            summary = clean_text(summary_html, 420)
            if not is_relevant(title, summary, forced=forced):
                continue
            published = published_datetime(entry)
            if published and published < datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS):
                continue
            published_iso = published.isoformat() if published else ""
            image = entry_image(entry)
            source = source_name(entry, fallback_source, link)
            category = infer_category(title, summary, default_category)
            if not summary:
                summary = "來源未提供摘要，請點擊閱讀原文查看完整報導。"
            stable = hashlib.sha1((title.lower().strip() + "|" + link).encode("utf-8")).hexdigest()[:16]
            items.append({
                "id": stable,
                "title": title,
                "url": link,
                "source": source,
                "published_at": published_iso,
                "published_text": clean_text(entry.get("published", ""), 80),
                "summary": summary,
                "image": image,
                "category": category,
            })
    except requests.RequestException as exc:
        print(f"[WARN] 無法讀取來源 {url}: {exc}", file=sys.stderr)
    except Exception as exc:  # Keep one broken source from blocking all other sources.
        print(f"[WARN] 處理來源時發生錯誤 {url}: {exc}", file=sys.stderr)
    return items


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
    collected = []

    for fallback, url, category in DIRECT_FEEDS:
        print(f"[INFO] 讀取官方來源：{fallback}")
        collected.extend(parse_feed(url, fallback, category, session))

    for default_category, query in GOOGLE_NEWS_QUERIES:
        url = build_google_url(query)
        print(f"[INFO] 搜尋新聞：{query}")
        collected.extend(parse_feed(url, "Google 新聞彙整", default_category, session))
        time.sleep(0.25)

    # Deduplicate identical titles and links, preferring records with an image and summary.
    by_key = {}
    for item in collected:
        key = re.sub(r"\W+", "", item["title"].lower())
        if not key:
            continue
        existing = by_key.get(key)
        score = int(bool(item.get("image"))) + int(bool(item.get("summary"))) + int(bool(item.get("published_at")))
        existing_score = -1 if existing is None else int(bool(existing.get("image"))) + int(bool(existing.get("summary"))) + int(bool(existing.get("published_at")))
        if existing is None or score > existing_score:
            by_key[key] = item

    items = list(by_key.values())
    items.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    items = items[:MAX_ITEMS]

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "Asia/Taipei",
        "items_count": len(items),
        "items": items,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] 已寫入 {len(items)} 則新聞：{OUTPUT}")
    if not items:
        print("[WARN] 本次沒有取得新聞。請檢查 Actions 執行紀錄與 RSS 來源。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
