import re
import math
import time
import json
import sqlite3
import os
import threading
import concurrent.futures
import requests
from urllib.parse import urlparse, unquote, quote
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "index.db")

STOP_WORDS = {"yang", "dan", "atau", "di", "ke", "dari", "dengan", "untuk", "pada", "dalam", "ini", "itu", "adalah", "sebagai", "oleh", "sebuah", "para", "akan", "sudah", "telah", "bisa", "dapat", "lebih", "juga", "tidak", "apa", "siapa", "bagaimana", "kenapa", "mengapa", "dimana", "di mana", "kapan", "kah", "nya", "sekarang", "terbaru"}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

BIG_DOMAINS = {
    "google.com", "microsoft.com", "apple.com", "amazon.com", "meta.com", "ibm.com", "oracle.com",
    "intel.com", "nvidia.com", "cloudflare.com", "github.com", "wikipedia.org",
    "bbc.com", "reuters.com", "bloomberg.com", "nytimes.com", "theguardian.com", "aljazeera.com",
    "detik.com", "kompas.com", "tempo.co", "cnnindonesia.com", "antaranews.com", "liputan6.com",
    "cnbcindonesia.com", "kumparan.com",
    "who.int", "un.org", "worldbank.org", "imf.org", "nature.com", "science.org", "arxiv.org"
}

def normalize_text(text):
    if not text: return ""
    text = unquote(str(text)).lower()
    text = re.sub(r"https?://", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()

def tokenize(text):
    return [x for x in normalize_text(text).split() if len(x) > 1] if text else []

def query_tokens(query):
    words = tokenize(query)
    core = [w for w in words if w not in STOP_WORDS]
    return core if core else words

def get_domain(url):
    try:
        domain = urlparse(url).netloc.lower()
        return domain[4:] if domain.startswith("www.") else domain
    except: return ""

def domain_authority_bonus(domain):
    if domain.endswith(".go.id") or domain.endswith(".ac.id"):
        return 20.0
    if any(domain == d or domain.endswith("." + d) for d in BIG_DOMAINS):
        return 15.0
    return 0.0

def make_clean_snippet(query, title, content, length=180):
    if not content: return title[:length] if title else ""
    text = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '', content)
    text = re.sub(r'\d{2}:\d{2}', '', text)
    text = re.sub(r"\s+", " ", text).strip()

    q_words = query_tokens(query)
    lower = text.lower()
    best_pos = -1
    for word in q_words:
        pos = lower.find(word)
        if pos >= 0:
            best_pos = pos
            break

    if best_pos >= 0:
        start = max(0, best_pos - 30)
        end = min(len(text), start + length)
        snippet = text[start:end]
        return ("..." if start > 0 else "") + snippet + ("..." if end < len(text) else "")
    return text[:length] + "..." if len(text) > length else text

def get_suggestions(query, limit=6):
    if not query or len(query) < 2: return []
    try:
        url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=3).json()
        if len(resp) > 1:
            return resp[1][:limit]
    except: pass
    return []

# ============================================================
# PEMANGGIL WEB (PARALEL DDG, BING, DATABASE)
# ============================================================
def fetch_duckduckgo_web(query, limit=100, retries=2, delay=1.0):
    results = []
    for attempt in range(retries):
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                for r in ddgs.text(query, region="id-id", max_results=limit):
                    results.append({"url": r.get("href", ""), "title": r.get("title", ""), "content": r.get("body", "")})
            if results:
                return results
        except Exception as e:
            print(f"[DUCKDUCKGO ERROR] percobaan {attempt+1}/{retries}:", e)
            time.sleep(delay)
    return results

def fetch_bing_web(query, limit=100, retries=2, delay=1.0):
    results = []
    per_page = 10
    max_pages = math.ceil(limit / per_page)
    for page in range(max_pages):
        first = page * per_page + 1
        page_ok = False
        for attempt in range(retries):
            try:
                url = f"https://www.bing.com/search?q={quote(query)}&first={first}&setlang=id&cc=ID"
                resp = requests.get(url, headers=HEADERS, timeout=6)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                page_items = []
                for li in soup.select("li.b_algo"):
                    h2 = li.find("h2")
                    if not h2 or not h2.find("a"):
                        continue
                    link_tag = h2.find("a")
                    href = link_tag.get("href", "")
                    title = link_tag.get_text(strip=True)
                    snippet_tag = li.select_one(".b_caption p") or li.select_one(".b_lineclamp3") or li.select_one(".b_lineclamp2")
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                    if href:
                        page_items.append({"url": href, "title": title, "content": snippet})
                if page_items:
                    results.extend(page_items)
                    page_ok = True
                break
            except Exception as e:
                print(f"[BING ERROR] halaman {page+1}, percobaan {attempt+1}/{retries}:", e)
                time.sleep(delay)
        if not page_ok:
            break
        if len(results) >= limit:
            break
        time.sleep(0.3)
    return results[:limit]

def fetch_database_web(query, limit=100):
    results = []
    try:
        q_words = query_tokens(query)
        if not q_words:
            return results
        match_query = " OR ".join(f'"{w}"' for w in q_words)

        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA journal_mode = WAL")
        cur = conn.cursor()
        cur.execute("""
            SELECT url, title, content FROM pages_fts
            WHERE pages_fts MATCH ?
            LIMIT ?
        """, (match_query, limit))
        for url, title, content in cur.fetchall():
            body = content.split("\n", 1)[1] if content and "\n" in content else (content or "")
            results.append({"url": url, "title": title, "content": body})
        conn.close()
    except Exception as e:
        print("[DATABASE SEARCH ERROR]:", e)
    return results

def fetch_ai_summary(query):
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            answer = ddgs.chat(query)
            return answer.strip() if answer else None
    except Exception as e:
        print("[AI SUMMARY ERROR]:", e)
        return None

# ============================================================
# PEMANGGIL GAMBAR (MURNI LIVE DARI DUCKDUCKGO DAN BING)
# ============================================================
def fetch_duckduckgo_images(query, limit=100, retries=2, delay=1.0):
    images = []
    for attempt in range(retries):
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                for r in ddgs.images(query, region="id-id", max_results=limit):
                    img_url = r.get("image", "")
                    if img_url:
                        images.append({
                            "image_url": img_url, 
                            "title": r.get("title", query.title()), 
                            "domain": get_domain(r.get("url", img_url)), 
                            "source_url": r.get("url", img_url)
                        })
            if images:
                return images
        except Exception as e:
            print(f"[DDG IMAGE ERROR] percobaan {attempt+1}/{retries}:", e)
            time.sleep(delay)
    return images

def fetch_bing_images(query, limit=100, retries=2, delay=1.0):
    images = []
    for attempt in range(retries):
        try:
            url = f"https://www.bing.com/images/search?q={quote(query)}&FORM=HDRSC2"
            resp = requests.get(url, headers=HEADERS, timeout=6)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select("a.iusc"):
                    m_data = a.get("m")
                    if m_data:
                        try:
                            data = json.loads(m_data)
                            img_url = data.get("murl")
                            src_url = data.get("purl") or data.get("hosturl") or img_url
                            title = data.get("t") or query.title()
                            if img_url:
                                images.append({
                                    "image_url": img_url,
                                    "title": title,
                                    "domain": get_domain(src_url),
                                    "source_url": src_url
                                })
                        except Exception:
                            continue
            if images:
                return images[:limit]
        except Exception as e:
            print(f"[BING IMAGE ERROR] percobaan {attempt+1}/{retries}:", e)
            time.sleep(delay)
    return images[:limit]

# ============================================================
# PENYIMPANAN BACKGROUND & ALGORITMA RANKING
# ============================================================
def _fetch_full_page(url, timeout=5):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
            return None, None
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else url
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return title, text[:3000]
    except Exception:
        return None, None

def _save_new_items_background(items):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        cur = conn.cursor()
        cur.execute("SELECT url FROM pages_meta")
        existing = {row[0] for row in cur.fetchall()}

        saved = 0
        for item in items:
            url = item.get("url", "")
            if not url or url in existing:
                continue

            title = item.get("title", "") or url
            content = item.get("content", "") or ""

            if len(content.split()) < 30:
                full_title, full_content = _fetch_full_page(url)
                if full_content:
                    title = full_title or title
                    content = full_content

            if len(content.split()) < 20:
                continue

            domain = get_domain(url)
            cur.execute("INSERT OR REPLACE INTO pages_meta (url, domain, engine_rank) VALUES (?, ?, 1.0)", (url, domain))
            cur.execute("DELETE FROM pages_fts WHERE url = ?", (url,))
            cur.execute("INSERT INTO pages_fts (url, title, content) VALUES (?, ?, ?)", (url, title, f"{title}\n{content}"))
            saved += 1

        conn.commit()
        conn.close()
        if saved:
            print(f"[BACKGROUND SAVE] {saved} URL baru ditambahkan ke index.db")
    except Exception as e:
        print("[BACKGROUND SAVE ERROR]:", e)

def calculate_relevance_scores_bm25(query, items):
    q_words = query_tokens(query)
    if not q_words or not items:
        return [0.0] * len(items)
    phrase = " ".join(q_words)

    docs_tokens, docs_len = [], []
    for item in items:
        title_tokens = tokenize(item.get("title", ""))
        content_tokens = tokenize(item.get("content", ""))
        combined = title_tokens * 2 + content_tokens
        docs_tokens.append(combined)
        docs_len.append(len(combined) if combined else 1)

    avg_doc_len = sum(docs_len) / len(docs_len)
    total_docs = len(items)

    doc_freq_map = {}
    for term in set(q_words):
        doc_freq_map[term] = sum(1 for tokens in docs_tokens if term in tokens)

    scores = []
    for idx, item in enumerate(items):
        tokens = docs_tokens[idx]
        doc_len = docs_len[idx]
        title_norm = normalize_text(item.get("title", ""))
        content_norm = normalize_text(item.get("content", ""))
        url = item.get("url", "")

        bm25_total = 0.0
        for term in q_words:
            tf = tokens.count(term)
            df = doc_freq_map.get(term, 0)
            idf = math.log(((total_docs - df + 0.5) / (df + 0.5)) + 1)
            num = tf * 2.5
            den = tf + 1.5 * (1 - 0.75 + 0.75 * (doc_len / max(avg_doc_len, 1)))
            bm25_total += idf * (num / den)

        score = bm25_total * 10
        if phrase in title_norm: score += 25.0
        elif phrase in content_norm: score += 10.0

        title_words = title_norm.split()
        if title_words and title_words[0] in q_words: score += 8.0

        url_norm = normalize_text(url)
        matched_in_url = sum(1 for w in q_words if w in url_norm)
        if matched_in_url: score += (matched_in_url / len(q_words)) * 10.0

        scores.append(score)
    return scores

# ============================================================
# FUNGSI UTAMA SEARCH (DEFAULT LIMIT 100)
# ============================================================
def search(query, limit=100, category='all', mode='bm25', include_ai_summary=True):
    query = query.strip()
    if not query:
        return {"results": [], "ai_summary": None}

    # KATEGORI GAMBAR: HANYA DUCKDUCKGO DAN BING
    if category == 'images':
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_ddg = executor.submit(fetch_duckduckgo_images, query, limit=limit)
            f_bing = executor.submit(fetch_bing_images, query, limit=limit)
            ddg_imgs = f_ddg.result() or []
            bing_imgs = f_bing.result() or []

        seen_imgs = set()
        combined_imgs = []
        for img in ddg_imgs + bing_imgs:
            iurl = img.get("image_url")
            if iurl and iurl not in seen_imgs:
                seen_imgs.add(iurl)
                combined_imgs.append(img)

        return {"results": combined_imgs[:limit], "ai_summary": None}

    clean_q = " ".join([w for w in query.split() if w.lower() not in STOP_WORDS]) or query

    # EKSEKUSI PARALEL (WEB DDG, WEB BING, DATABASE, AI CHAT)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_ddg = executor.submit(fetch_duckduckgo_web, clean_q, limit)
        future_bing = executor.submit(fetch_bing_web, clean_q, limit)
        future_db = executor.submit(fetch_database_web, clean_q, limit)
        future_ai = executor.submit(fetch_ai_summary, query) if include_ai_summary else None

        ddg_res = future_ddg.result()
        bing_res = future_bing.result()
        db_res = future_db.result()
        ai_summary = future_ai.result() if future_ai else None

    source_map = {}
    for item in ddg_res: source_map.setdefault(item["url"], set()).add("duckduckgo")
    for item in bing_res: source_map.setdefault(item["url"], set()).add("bing")
    for item in db_res: source_map.setdefault(item["url"], set()).add("database")

    seen = {}
    for item in ddg_res + bing_res + db_res:
        url = item.get("url", "")
        if not url: continue
        domain = get_domain(url)
        if category == 'edu' and not domain.endswith('.ac.id'): continue
        if url not in seen or len(item.get("content", "")) > len(seen[url].get("content", "")):
            seen[url] = item

    deduped = list(seen.values())
    if not deduped:
        return {"results": [], "ai_summary": ai_summary}

    scores = calculate_relevance_scores_bm25(query, deduped)

    results = []
    for item, score in zip(deduped, scores):
        url = item["url"]
        domain = get_domain(url)
        final_score = score + domain_authority_bonus(domain)
        results.append({
            "url": url,
            "title": item["title"],
            "snippet": make_clean_snippet(query, item["title"], item["content"]),
            "domain": domain,
            "is_official": (domain.endswith('.go.id') or domain.endswith('.ac.id')),
            "score": round(final_score, 1),
            "source": "+".join(sorted(source_map.get(url, []))),
            "mode": mode,
            "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    final_results = results[:limit]

    # SIMPAN DATA BARU DI LATAR BELAKANG
    new_candidates = [it for it in deduped if "database" not in source_map.get(it["url"], set())]
    if new_candidates:
        threading.Thread(target=_save_new_items_background, args=(new_candidates,), daemon=True).start()

    return {"results": final_results, "ai_summary": ai_summary}
