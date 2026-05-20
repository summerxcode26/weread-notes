#!/usr/bin/env python3
"""Fetch WeRead notes and regenerate data.js"""

import json
import os
import re
import time
import datetime
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib.request
import urllib.error

API_BASE = "https://i.weread.qq.com/api/agent/gateway"
SKILL_VERSION = "1.0.3"
MAX_WORKERS = 5
OUT_FILE = os.path.join(os.path.dirname(__file__), "data.js")

THEME_LABELS = {
    "health": "健康/医学",
    "philosophy": "哲学/思想",
    "yijing": "易经/国学",
    "history": "历史",
    "literature": "文学",
    "business": "商业/管理",
    "life": "生活/随笔",
    "mystery": "推理/悬疑",
    "martial": "武侠",
    "psychology": "心理学",
}

# Keywords for theme tagging
THEME_KEYWORDS = {
    "health": ["细胞", "癌", "基因", "医学", "健康", "免疫", "神经", "大脑", "身体", "疾病", "治疗", "药物", "蛋白质", "代谢", "营养"],
    "philosophy": ["哲学", "意识", "存在", "本质", "逻辑", "认知", "理性", "道德", "伦理", "自由", "价值", "真理", "形而上", "辩证", "思维"],
    "yijing": ["易经", "八卦", "卦", "阴阳", "五行", "天干", "地支", "风水", "占卜", "卦辞", "爻辞", "国学", "道家", "儒家"],
    "history": ["历史", "朝代", "皇帝", "战争", "帝国", "文明", "考古", "史书", "传记", "王朝", "革命", "民国"],
    "literature": ["诗", "词", "小说", "文学", "意象", "典故", "隐喻", "叙事", "人物", "情节", "描写", "散文", "古文"],
    "business": ["产品", "市场", "商业", "管理", "战略", "创业", "用户", "增长", "运营", "投资", "经济", "公司", "团队", "效率"],
    "life": ["生活", "感悟", "随笔", "人生", "成长", "幸福", "情感", "关系", "家庭", "时间", "习惯", "选择"],
    "mystery": ["推理", "侦探", "悬疑", "犯罪", "案件", "线索", "真相", "凶手", "密室", "谋杀"],
    "martial": ["武侠", "江湖", "武功", "剑法", "门派", "侠客", "内力", "轻功", "武林", "金庸", "古龙"],
    "psychology": ["心理", "行为", "情绪", "认知偏差", "潜意识", "动机", "焦虑", "抑郁", "人格", "压力", "治愈"],
}

# Category classification
K_THEMES = {"health", "philosophy", "yijing", "history", "business", "psychology"}
L_THEMES = {"literature", "martial", "mystery"}
R_THEMES = {"life"}

REFLECTION_WORDS = ["我觉得", "我认为", "我感", "感觉", "觉得", "想到", "联想", "启发", "印象", "感受", "体会", "想起"]
KNOWLEDGE_WORDS = ["是指", "指的是", "定义", "概念", "原理", "理论", "研究表明", "数据显示", "据统计", "如何", "方法", "步骤"]

STOP_CHARS = set("的了是在有和就也都这那个很不一到了以为他她它们我你")


def api_call(payload: dict) -> dict:
    key = os.environ.get("WEREAD_API_KEY", "")
    if not key:
        raise RuntimeError("WEREAD_API_KEY not set")
    payload["skill_version"] = SKILL_VERSION
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        API_BASE,
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_all_notebooks():
    print("  Fetching notebooks...")
    books = []
    last_sort = None
    while True:
        payload = {"api_name": "/user/notebooks", "count": 100}
        if last_sort:
            payload["lastSort"] = last_sort
        res = api_call(payload)
        items = res.get("books", [])
        if not items:
            break
        books.extend(items)
        if len(items) < 100:
            break
        last_sort = items[-1].get("sort")
        time.sleep(0.1)
    print(f"  {len(books)} books found")
    return books


def fetch_book_notes(book_entry):
    book_id = book_entry["bookId"]
    book = book_entry.get("book", {})
    title = book.get("title", "")
    author = book.get("author", "")
    notes = []

    # Highlights
    try:
        res = api_call({"api_name": "/book/bookmarklist", "bookId": book_id})
        for item in res.get("updated", []):
            text = item.get("markText", "").strip()
            if not text:
                continue
            notes.append({
                "id": item.get("bookmarkId", 0),
                "type": "highlight",
                "bookId": book_id,
                "title": title,
                "author": author,
                "text": text,
                "thought": "",
                "chapterTitle": item.get("chapterTitle", ""),
                "createTime": item.get("createTime", 0),
                "likeCount": item.get("likeCount", 0),
            })
        time.sleep(0.08)
    except Exception as e:
        print(f"  [warn] highlights {book_id}: {e}")

    # Thoughts / reviews
    try:
        res = api_call({"api_name": "/review/list/mine", "bookId": book_id, "listType": 11, "count": 100})
        for item in res.get("reviews", []):
            rv = item.get("review", {})
            text = rv.get("abstract", "").strip()
            thought = rv.get("content", "").strip()
            chapter = rv.get("chapterTitle", "")
            if not thought and not text:
                continue
            notes.append({
                "id": rv.get("reviewId", rv.get("createTime", 0)),
                "type": "thought",
                "bookId": book_id,
                "title": title,
                "author": author,
                "text": text,
                "thought": thought,
                "chapterTitle": chapter,
                "createTime": rv.get("createTime", 0),
                "likeCount": rv.get("likeCount", 0),
            })
        time.sleep(0.08)
    except Exception as e:
        print(f"  [warn] thoughts {book_id}: {e}")

    return notes


def classify_note(note: dict) -> tuple:
    """Return (category, themes) where category is k/l/r/u."""
    combined = (note.get("text", "") + " " + note.get("thought", "")).lower()

    matched_themes = []
    for theme, kws in THEME_KEYWORDS.items():
        if any(kw in combined for kw in kws):
            matched_themes.append(theme)

    # Determine category
    cat = "u"
    if matched_themes:
        if any(t in K_THEMES for t in matched_themes):
            cat = "k"
        elif any(t in L_THEMES for t in matched_themes):
            cat = "l"
        elif any(t in R_THEMES for t in matched_themes):
            cat = "r"

    # Override with text analysis if still untagged
    if cat == "u":
        thought = note.get("thought", "")
        if thought and any(w in thought for w in REFLECTION_WORDS):
            cat = "r"
        elif any(w in combined for w in KNOWLEDGE_WORDS):
            cat = "k"

    return cat, matched_themes[:3]  # cap to 3 themes


def extract_keywords(notes: list) -> dict:
    """Extract top Chinese bigrams/trigrams per category."""
    stop = STOP_CHARS | set(" \t\n\r.,!?，。！？、；：""''（）【】《》")

    def score_text(text):
        words = Counter()
        for n in (2, 3):
            for i in range(len(text) - n + 1):
                w = text[i:i+n]
                if any(c in stop for c in w):
                    continue
                if not all('一' <= c <= '鿿' for c in w):
                    continue
                words[w] += 1
        return words

    buckets = {"all": Counter(), "k": Counter(), "l": Counter(), "r": Counter()}
    for n in notes:
        combined = (n.get("tx", "") + " " + n.get("th", "")).strip()
        if not combined:
            continue
        wc = score_text(combined)
        buckets["all"].update(wc)
        cat = n.get("cat", "u")
        if cat in buckets:
            buckets[cat].update(wc)

    return {k: v.most_common(200) for k, v in buckets.items()}


def compact_note(n: dict, cat: str, themes: list) -> dict:
    ts = n.get("createTime", 0)
    dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "2020-01-01"
    yr = int(dt[:4])
    text = n.get("text", "")
    thought = n.get("thought", "")
    ln = len(text) + len(thought)

    c = {
        "id": n["id"],
        "tp": "h" if n["type"] == "highlight" else "t",
        "bk": n["title"],
        "au": n["author"],
        "tx": text,
        "dt": dt,
        "yr": yr,
        "ln": ln,
        "cat": cat,
    }
    if thought:
        c["th"] = thought
    chapter = n.get("chapterTitle", "")
    if chapter:
        c["ch"] = chapter
    if themes:
        c["tg"] = themes
    lk = n.get("likeCount", 0)
    if lk:
        c["lk"] = lk
    return c


def fetch_shelf_reviews():
    """Fetch star ratings from shelf."""
    reviews = []
    try:
        res = api_call({"api_name": "/shelf/sync", "synckey": 0, "teenmode": 0})
        for book in res.get("books", []):
            b = book.get("book", {})
            bid = b.get("bookId", "")
            title = b.get("title", "")
            author = b.get("author", "")
            rating = book.get("finishedStar", 0) or book.get("star", 0)
            if rating and title:
                reviews.append({"bk": title, "au": author, "st": rating, "dt": ""})
    except Exception as e:
        print(f"  [warn] shelf: {e}")
    return reviews


def generate_data_js(compact_notes: list, books_raw: list, reviews: list):
    today = datetime.date.today().isoformat()

    # Books list
    book_counts = Counter()
    book_authors = {}
    for n in compact_notes:
        bk = n["bk"]
        book_counts[bk] += 1
        book_authors[bk] = n["au"]
    wr_books = [{"title": bk, "author": book_authors[bk], "count": cnt}
                for bk, cnt in book_counts.most_common(300)]

    # Authors list
    author_data = defaultdict(lambda: {"count": 0, "books": set()})
    for n in compact_notes:
        au = n["au"]
        author_data[au]["count"] += 1
        author_data[au]["books"].add(n["bk"])
    wr_authors = sorted(
        [{"author": au, "count": d["count"], "books": len(d["books"])}
         for au, d in author_data.items()],
        key=lambda x: -x["count"]
    )[:100]

    # Year stats
    year_stats = Counter(n["yr"] for n in compact_notes)
    wr_year = dict(sorted(year_stats.items()))

    # Theme stats
    theme_stats = Counter()
    for n in compact_notes:
        for t in (n.get("tg") or []):
            theme_stats[t] += 1
    wr_theme = dict(theme_stats.most_common())

    # Cat stats
    cat_stats = Counter(n["cat"] for n in compact_notes)
    wr_cat = dict(cat_stats)

    # Top thoughts by length
    thoughts = [n for n in compact_notes if n["tp"] == "t" and n.get("th")]
    thoughts.sort(key=lambda x: x["ln"], reverse=True)
    wr_top_thoughts = [
        {"bk": n["bk"], "au": n["au"], "th": n["th"], "dt": n["dt"],
         "tx": n["tx"], "ln": n["ln"]}
        for n in thoughts[:30]
    ]

    # Keywords
    wr_keywords = extract_keywords(compact_notes)

    lines = [
        f"// Auto-generated {today}",
        f"window.WR_NOTES={json.dumps(compact_notes, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_BOOKS={json.dumps(wr_books, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_AUTHORS={json.dumps(wr_authors, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_THEME_LABELS={json.dumps(THEME_LABELS, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_YEAR_STATS={json.dumps(wr_year, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_THEME_STATS={json.dumps(wr_theme, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_TOP_THOUGHTS={json.dumps(wr_top_thoughts, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_REVIEWS={json.dumps(reviews, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_KEYWORDS={json.dumps(wr_keywords, ensure_ascii=False, separators=(',',':'))};",
        f"window.WR_CAT_STATS={json.dumps(wr_cat, ensure_ascii=False, separators=(',',':'))};",
    ]

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    size_kb = os.path.getsize(OUT_FILE) // 1024
    print(f"  data.js written: {len(compact_notes)} notes, {size_kb} KB")
    return len(compact_notes)


def run(progress_callback=None):
    """Run full pipeline. Returns note count."""
    def log(msg):
        print(msg)
        if progress_callback:
            progress_callback(msg)

    log("Fetching notebooks...")
    books = fetch_all_notebooks()

    log(f"Fetching notes from {len(books)} books (parallel)...")
    all_raw = []
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_book_notes, b): b for b in books}
        for future in as_completed(futures):
            try:
                notes = future.result()
                all_raw.extend(notes)
            except Exception as e:
                log(f"  [error] {e}")
            completed += 1
            if completed % 50 == 0:
                log(f"  {completed}/{len(books)} books done, {len(all_raw)} notes so far")

    log(f"Processing {len(all_raw)} notes...")
    compact_notes = []
    for n in all_raw:
        cat, themes = classify_note(n)
        compact_notes.append(compact_note(n, cat, themes))

    log("Fetching shelf reviews...")
    reviews = fetch_shelf_reviews()

    log("Generating data.js...")
    count = generate_data_js(compact_notes, books, reviews)
    log(f"Done. {count} notes written to data.js")
    return count


if __name__ == "__main__":
    run()
