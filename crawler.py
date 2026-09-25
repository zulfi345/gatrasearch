from urllib.parse import urlparse
import re

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

BAD_DOMAINS = {
    "yandex.com",
    "jagokata.com",
    "wiktionary.org",
    "kbbi.portal.id"
}


def get_domain(url):
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def normalize_domain(domain):
    return domain.lower().replace("www.", "").strip()


def looks_official(query, url, title):
    domain = normalize_domain(get_domain(url))
    q_words = re.findall(r"[a-zA-Z0-9]+", query.lower())
    title_lower = title.lower()

    official_words = ("official", "official website", "situs resmi", "website resmi", "official site")

    if any(phrase in title_lower for phrase in official_words):
        return True

    if not q_words:
        return False

    if len(q_words) == 1:
        q = q_words[0]
        domain_name = domain.split(".")[0]
        if domain_name == q:
            return True

    return False


def fetch_external_search(query, limit=60):
    if DDGS is None:
        print("duckduckgo_search belum terinstall.")
        return []

    query = query.strip()
    if not query:
        return []

    results = []
    seen = set()
    
    # Menyiapkan variasi pencarian agar menyedot puluhan hingga ratusan hasil
    search_queries = [query]
    words = query.split()

    if "indonesia" not in query.lower() and not any(x in query.lower() for x in [".com", ".org", ".net", ".id"]):
        search_queries.append(query + " Indonesia")
        search_queries.append(query + " terbaik Indonesia")

    try:
        with DDGS() as ddgs:
            for search_query in search_queries:
                try:
                    items = ddgs.text(
                        search_query,
                        region="id-id",
                        safesearch="moderate",
                        max_results=40
                    )

                    for position, item in enumerate(items):
                        url = (item.get("href") or item.get("url") or "").strip()
                        title = (item.get("title") or "").strip()
                        snippet = (item.get("body") or item.get("snippet") or "").strip()

                        if not url or not url.startswith(("http://", "https://")):
                            continue

                        domain = get_domain(url)
                        if not domain or domain in BAD_DOMAINS:
                            continue

                        normalized_url = url.split("#")[0].rstrip("/").lower()
                        if normalized_url in seen:
                            continue
                        seen.add(normalized_url)

                        official = looks_official(query, url, title)
                        engine_rank = 0 if official else (position + 1)

                        results.append({
                            "title": title,
                            "url": url,
                            "content": f"{title}\n{snippet}",
                            "engine_rank": engine_rank,
                            "external_position": position
                        })

                        if len(results) >= limit:
                            return results

                except Exception as e:
                    print("DDG query error:", search_query, repr(e))

    except Exception as e:
        print("DDGS initialization error:", repr(e))

    return results
