import sqlite3
import re
import math
from urllib.parse import urlparse, unquote
from collections import Counter

DB_NAME = "index.db"

STOP_WORDS = {
    "yang", "dan", "atau", "di", "ke", "dari", "dengan",
    "untuk", "pada", "dalam", "ini", "itu", "adalah",
    "sebagai", "oleh", "sebuah", "para", "akan", "sudah",
    "telah", "bisa", "dapat", "lebih", "juga", "tidak",
    "apa", "siapa", "bagaimana", "kenapa", "mengapa",
    "dimana", "di mana", "kapan", "kah", "nya"
}

NOISE_DOMAINS = {
    "jagokata.com",
    "wiktionary.org",
    "kbbi.portal.id",
    "yandex.com"
}

QUESTION_WORDS = {
    "apa", "siapa", "bagaimana", "kenapa", "mengapa",
    "dimana", "di", "mana", "kapan", "berapa"
}


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            url,
            title,
            content,
            tokenize='unicode61 remove_diacritics 2'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pages_meta (
            url TEXT PRIMARY KEY,
            clicks INTEGER DEFAULT 0,
            engine_rank REAL DEFAULT 20,
            last_crawled DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pages_meta_clicks
        ON pages_meta(clicks)
    """)

    conn.commit()
    conn.close()


def normalize_text(text):
    if not text:
        return ""

    text = unquote(str(text))
    text = text.lower()
    text = re.sub(r"https?://", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text):
    text = normalize_text(text)
    if not text:
        return []
    return [x for x in text.split() if len(x) > 1]


def query_tokens(query):
    words = tokenize(query)
    core = [w for w in words if w not in STOP_WORDS]
    return core if core else words


def is_question(query):
    words = set(tokenize(query))
    return bool(words & QUESTION_WORDS)


def get_domain(url):
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def clean_url(url):
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return ""
    return url


def add_or_update_page(url, title, content, engine_rank=20):
    url = clean_url(url)
    if not url:
        return

    if not title:
        title = url

    content = str(content or "")[:50000]
    title = str(title)[:1000]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM pages_fts WHERE url = ?", (url,))
    cur.execute("""
        INSERT INTO pages_fts (url, title, content)
        VALUES (?, ?, ?)
    """, (url, title, content))

    cur.execute("""
        INSERT INTO pages_meta (url, clicks, engine_rank, last_crawled)
        VALUES (?, 0, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(url) DO UPDATE SET
            engine_rank = excluded.engine_rank,
            last_crawled = CURRENT_TIMESTAMP
    """, (url, float(engine_rank)))

    conn.commit()
    conn.close()


def increment_click(url):
    if not url:
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE pages_meta
        SET clicks = MIN(clicks + 1, 100000)
        WHERE url = ?
    """, (url,))
    conn.commit()
    conn.close()


def build_fts_query(query):
    words = query_tokens(query)
    if not words:
        return ""

    parts = []
    for word in words[:12]:
        safe = word.replace('"', '""')
        parts.append(f'("{safe}" OR "{safe}"*)')

    return " AND ".join(parts)


def calculate_text_score(query, title, content, url, bm25_score, engine_rank, clicks):
    q_words = query_tokens(query)
    if not q_words:
        return 0.0

    title_norm = normalize_text(title)
    content_norm = normalize_text(content)
    url_norm = normalize_text(url)

    title_words = tokenize(title)
    content_words = tokenize(content)

    title_counter = Counter(title_words)
    content_counter = Counter(content_words)

    score = 0.0

    # 1. BM25 Quality Score
    bm25_quality = abs(bm25_score)
    score += min(bm25_quality * 3.0, 35.0)

    # 2. Exact query phrase
    q_norm = normalize_text(query)
    if q_norm and q_norm in title_norm:
        score += 40
    if q_norm and q_norm in content_norm:
        score += 15

    # 3. Title matching
    matched_title = 0
    for word in q_words:
        if word in title_counter:
            matched_title += 1
            score += 12
            score += min(title_counter[word] * 2, 6)

    title_coverage = matched_title / len(q_words)
    score += title_coverage * 30

    # 4. Content matching
    matched_content = 0
    for word in q_words:
        if word in content_counter:
            matched_content += 1
            freq = content_counter[word]
            score += min(math.log2(freq + 1) * 3, 10)

    content_coverage = matched_content / len(q_words)
    score += content_coverage * 20

    # 5. URL & Domain matching
    url_words = tokenize(url_norm)
    for word in q_words:
        if word in url_words:
            score += 8

    domain = get_domain(url)
    domain_clean = domain.replace(".", " ")
    for word in q_words:
        if word in domain_clean:
            score += 10

    # 6. REGIONAL & GEO BOOSTING (Jombang / Jatim / Indonesia / Domain .id)
    if domain.endswith(".id") or ".id/" in url:
        score += 20.0
    if any(loc in title_norm or loc in content_norm for loc in ["jombang", "jawa timur", "jatim"]):
        score += 25.0
    elif "indonesia" in title_norm or "indonesia" in content_norm:
        score += 12.0

    # 7. Search-engine rank
    if engine_rank == 0:
        score += 20.0
    else:
        score += max(0, 12 - float(engine_rank) * 0.4)

    # 8. Click popularity
    if clicks > 0:
        score += min(math.log2(clicks + 1) * 2, 10)

    # 9. Penalti noise
    if domain in NOISE_DOMAINS:
        score -= 30

    # 10. Pertanyaan
    if is_question(query):
        answer_words = ["pengertian", "adalah", "definisi", "sejarah", "jawaban", "penjelasan", "profil", "biografi"]
        if any(x in title_norm for x in answer_words):
            score += 6

    return score


def deduplicate_results(results):
    seen = set()
    output = []
    for item in results:
        parsed = urlparse(item["url"])
        normalized = (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/").lower())
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(item)
    return output


def diversify_domains(results, limit):
    selected = []
    remaining = []
    domain_count = {}

    for item in results:
        domain = item["domain"]
        count = domain_count.get(domain, 0)

        if count < 2:
            selected.append(item)
            domain_count[domain] = count + 1
        else:
            remaining.append(item)

        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for item in remaining:
            if item not in selected:
                selected.append(item)
                if len(selected) >= limit:
                    break

    return selected


def make_snippet(query, title, content, length=260):
    if not content:
        return title[:length]

    text = re.sub(r"\s+", " ", content).strip()
    if len(text) <= length:
        return text

    words = query_tokens(query)
    lower = text.lower()
    best_pos = 0

    for word in words:
        pos = lower.find(word.lower())
        if pos >= 0:
            best_pos = pos
            break

    start = max(0, best_pos - 80)
    end = min(len(text), start + length)
    snippet = text[start:end]

    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."

    return snippet


def search_local(query, limit=50):
    query = query.strip()
    if not query:
        return []

    fts_query = build_fts_query(query)
    if not fts_query:
        return []

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                f.url, f.title, f.content,
                bm25(pages_fts, 1.0, 12.0, 2.0) AS bm,
                COALESCE(m.clicks, 0) AS clicks,
                COALESCE(m.engine_rank, 20) AS engine_rank
            FROM pages_fts AS f
            LEFT JOIN pages_meta AS m ON f.url = m.url
            WHERE pages_fts MATCH ?
            ORDER BY bm ASC
            LIMIT 300
        """, (fts_query,))
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        print("FTS error:", e)
        conn.close()
        return []

    conn.close()

    scored = []
    for row in rows:
        url = row["url"]
        title = row["title"] or url
        content = row["content"] or ""
        bm = float(row["bm"] or 0)
        clicks = int(row["clicks"] or 0)
        engine_rank = float(row["engine_rank"] or 20)

        score = calculate_text_score(
            query=query,
            title=title,
            content=content,
            url=url,
            bm25_score=bm,
            engine_rank=engine_rank,
            clicks=clicks
        )

        domain = get_domain(url)
        scored.append({
            "url": url,
            "title": title,
            "content": content,
            "score": score,
            "clicks": clicks,
            "engine_rank": engine_rank,
            "domain": domain
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    scored = deduplicate_results(scored)
    scored = diversify_domains(scored, limit)

    formatted = []
    for item in scored:
        snippet = make_snippet(query, item["title"], item["content"])
        domain = item["domain"]
        is_official = (item["engine_rank"] == 0)
        favicon = f"https://www.google.com/s2/favicons?domain={domain}&sz=32"

        formatted.append({
            "url": item["url"],
            "title": item["title"],
            "snippet": snippet,
            "clicks": item["clicks"],
            "engine_rank": item["engine_rank"],
            "domain": domain,
            "favicon": favicon,
            "is_official": is_official,
            "score": round(item["score"], 2)
        })

    return formatted


def search(query, limit=50):
    results = search_local(query, limit)

    # PERBAIKAN UTAMA: Jika hasil lokal kurang dari 20, paksa crawler untuk mencari lebih banyak ke internet
    if len(results) < 20:
        try:
            import crawler
            external = crawler.fetch_external_search(query, limit=60)
            for item in external:
                add_or_update_page(
                    url=item["url"],
                    title=item["title"],
                    content=item["content"],
                    engine_rank=item.get("engine_rank", 20)
                )
            results = search_local(query, limit)
        except Exception as e:
            print("External search error:", repr(e))

    return results
