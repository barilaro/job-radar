#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Job Radar — шукає 3D / VFX / animation вакансії на кількох англомовних
remote-бордах і надсилає нові знахідки тобі в Telegram.

Працює на GitHub Actions за розкладом. Нічого не треба запускати вручну.
Жодних сторонніх бібліотек — тільки стандартна бібліотека Python.

Що легко правити (дивись нижче блок CONFIG):
  - STRONG_KEYWORDS  — слова, які ЗАВЖДИ пропускають вакансію
  - SOFT_KEYWORDS    — "шумні" слова, пропускають лише якщо немає веб-слів
  - WEBDEV_NOISE     — слова, через які "шумну" вакансію відкидаємо
  - MAX_PER_RUN      — скільки максимум вакансій слати за один запуск
"""

import json
import os
import re
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

# ========================= CONFIG =========================

# Сильні слова: якщо є в назві/тегах — вакансія точно твоя.
STRONG_KEYWORDS = [
    "3d artist", "3d model", "3d generalist", "3d animation",
    "character artist", "character model", "character design",
    "zbrush", "maya", "blender", "cinema 4d", "c4d", "houdini",
    "vfx", "cgi", "cg artist", "cg generalist", "generalist 3d",
    "sculpt", "substance painter", "marvelous designer", "motionbuilder",
    "redshift", "unreal engine", "look dev", "lookdev",
    "rigging", "rigger", "nuke", "compositing", "texturing",
    "motion design", "motion graphic", "animator",
]

# Шумні слова: цікаві, але можуть зловити веб-розробку.
# Пропускаємо вакансію по них ТІЛЬКИ якщо в назві немає слів із WEBDEV_NOISE.
SOFT_KEYWORDS = [
    "3d", "animation", "render", "rendering", "generalist", "modeler",
]

# Якщо в назві є щось із цього — "шумну" вакансію відкидаємо.
WEBDEV_NOISE = [
    "react", "vue", "angular", "frontend", "front-end", "front end",
    "css", "javascript", "typescript", "web developer", "wordpress",
    "node", "php", "fullstack", "full-stack", "full stack", "backend",
]

MAX_PER_RUN = 25          # щоб не завалило повідомленнями
SEEN_FILE = "seen.json"   # тут бот пам'ятає, що вже надсилав
TIMEOUT = 25              # секунд на запит до сайту

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

USER_AGENT = "Mozilla/5.0 (compatible; JobRadar/1.0; +https://github.com)"

# ========================= helpers =========================


def http_get(url):
    """Проста GET-функція. Повертає bytes або None, якщо не вдалося."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except Exception as e:  # одне джерело впало — решта працює далі
        print(f"[warn] не вдалося відкрити {url}: {e}")
        return None


def matches(text):
    """Чи підходить вакансія за ключовими словами."""
    t = (text or "").lower()
    for kw in STRONG_KEYWORDS:
        if kw in t:
            return True
    has_webdev = any(n in t for n in WEBDEV_NOISE)
    if not has_webdev:
        for kw in SOFT_KEYWORDS:
            # для коротких слів типу "3d" шукаємо як окреме слово
            if len(kw) <= 3:
                if re.search(r"\b" + re.escape(kw) + r"\b", t):
                    return True
            elif kw in t:
                return True
    return False


# ========================= sources =========================


def from_remoteok():
    """RemoteOK — публічний JSON за адресою /api."""
    jobs = []
    raw = http_get("https://remoteok.com/api")
    if not raw:
        return jobs
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        print(f"[warn] RemoteOK: поганий JSON: {e}")
        return jobs
    for item in data:
        if not isinstance(item, dict) or "url" not in item:
            continue  # перший елемент — службовий
        title = item.get("position") or item.get("title") or ""
        company = item.get("company") or ""
        tags = " ".join(item.get("tags", []) or [])
        location = item.get("location") or "Remote"
        haystack = f"{title} {company} {tags}"
        if matches(haystack):
            jobs.append({
                "id": item.get("url"),
                "title": title.strip(),
                "company": company.strip(),
                "location": location.strip(),
                "url": item.get("url"),
                "source": "RemoteOK",
            })
    return jobs


def from_remotive():
    """Remotive — публічний JSON з пошуком."""
    jobs = []
    for query in ("3d", "vfx", "animation"):
        url = "https://remotive.com/api/remote-jobs?" + urllib.parse.urlencode(
            {"search": query})
        raw = http_get(url)
        if not raw:
            continue
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except Exception as e:
            print(f"[warn] Remotive '{query}': поганий JSON: {e}")
            continue
        for item in data.get("jobs", []):
            title = item.get("title") or ""
            company = item.get("company_name") or ""
            tags = " ".join(item.get("tags", []) or [])
            location = item.get("candidate_required_location") or "Remote"
            haystack = f"{title} {company} {tags}"
            if matches(haystack):
                jobs.append({
                    "id": item.get("url"),
                    "title": title.strip(),
                    "company": company.strip(),
                    "location": location.strip(),
                    "url": item.get("url"),
                    "source": "Remotive",
                })
    return jobs


def from_weworkremotely():
    """We Work Remotely — RSS-стрічки."""
    jobs = []
    feeds = [
        "https://weworkremotely.com/categories/remote-design-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    ]
    for feed_url in feeds:
        raw = http_get(feed_url)
        if not raw:
            continue
        try:
            root = ET.fromstring(raw)
        except Exception as e:
            print(f"[warn] WWR RSS: не розпарсив: {e}")
            continue
        for item in root.iter("item"):
            title_full = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not link:
                continue
            # у WWR назва у форматі "Компанія: Посада"
            if ": " in title_full:
                company, title = title_full.split(": ", 1)
            else:
                company, title = "", title_full
            if matches(title_full):
                jobs.append({
                    "id": link,
                    "title": title.strip(),
                    "company": company.strip(),
                    "location": "Remote",
                    "url": link,
                    "source": "We Work Remotely",
                })
    return jobs


SOURCES = [from_remoteok, from_remotive, from_weworkremotely]


# ========================= telegram =========================


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[error] немає TELEGRAM_TOKEN або TELEGRAM_CHAT_ID у секретах")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"[error] Telegram не прийняв повідомлення: {e}")
        return False


def format_job(job):
    lines = [f"🎯 {job['title']}"]
    if job["company"]:
        lines.append(f"🏢 {job['company']}")
    if job.get("location"):
        lines.append(f"📍 {job['location']}")
    lines.append(f"🔗 {job['url']}")
    lines.append(f"— {job['source']}")
    return "\n".join(lines)


# ========================= main =========================


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return None  # None = найперший запуск
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=0)


def main():
    # 1. зібрати все з усіх джерел
    all_jobs = {}
    for source in SOURCES:
        for job in source():
            if job.get("id"):
                all_jobs[job["id"]] = job
    print(f"[info] знайдено відповідних вакансій усього: {len(all_jobs)}")

    seen = load_seen()

    # 2. найперший запуск — нічого не спамимо, тільки запам'ятовуємо
    if seen is None:
        save_seen(set(all_jobs.keys()))
        send_telegram(
            "✅ Радар вакансій запущено!\n"
            f"Стежу за {len(SOURCES)} джерелами. "
            "Нові 3D/VFX/animation вакансії приходитимуть сюди."
        )
        print("[info] перший запуск: база створена, нічого не слав")
        return

    # 3. звичайний запуск — знайти нові
    new_jobs = [j for jid, j in all_jobs.items() if jid not in seen]
    print(f"[info] нових вакансій: {len(new_jobs)}")

    sent = 0
    for job in new_jobs[:MAX_PER_RUN]:
        if send_telegram(format_job(job)):
            sent += 1
        seen.add(job["id"])

    # навіть якщо не всі влізли в ліміт — позначимо решту як бачені,
    # щоб не копилися; наступного разу прийдуть зовсім свіжі
    for job in new_jobs:
        seen.add(job["id"])

    save_seen(seen)
    print(f"[info] надіслано: {sent}")


if __name__ == "__main__":
    main()
