from flask import (
    Flask,
    request,
    render_template_string,
    redirect,
    abort
)
from urllib.parse import urlparse
import search_engine

app = Flask(__name__)
search_engine.init_db()

GATRA_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% if query %}{{ query }} - GATRA Search{% else %}GATRA Search{% endif %}</title>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", Roboto, Arial, sans-serif; background: #0f172a; color: #cbd5e1; font-size: 14px; }
.header { display: flex; align-items: center; padding: 12px 20px; border-bottom: 1px solid #1e293b; background: #0f172a; position: sticky; top: 0; z-index: 100; }
.logo-box { text-decoration: none; margin-right: 24px; display: flex; flex-direction: column; }
.logo-text { font-size: 24px; font-weight: 900; letter-spacing: 1.5px; color: #38bdf8; line-height: 1; }
.logo-text span { color: #f59e0b; }
.logo-tagline { font-size: 7.5px; font-weight: 700; color: #94a3b8; letter-spacing: 1.2px; margin-top: 3px; }
.search-form { flex: 1; max-width: 680px; }
.search-input-wrapper { display: flex; align-items: center; background: #1e293b; border: 1px solid #334155; border-radius: 24px; padding: 8px 16px; transition: all 0.2s; }
.search-input-wrapper:focus-within { border-color: #38bdf8; box-shadow: 0 0 12px rgba(56,189,248,0.25); }
.search-input { flex: 1; background: transparent; border: none; outline: none; color: #f8fafc; font-size: 15px; }

.container { max-width: 680px; margin-left: 160px; padding: 16px; }
@media (max-width: 900px) { .container { margin-left: 0; max-width: 100%; } }

.stats { color: #64748b; font-size: 12.5px; margin-bottom: 16px; }

/* Featured Box Jawaban Cepat */
.featured-box { background: #1e293b; border: 2px solid #38bdf8; border-radius: 12px; padding: 16px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(56,189,248,0.15); }
.featured-label { font-size: 11px; font-weight: bold; color: #38bdf8; letter-spacing: 1px; margin-bottom: 6px; }
.featured-text { font-size: 14.5px; color: #f8fafc; line-height: 1.5; margin-bottom: 8px; }
.featured-source { font-size: 11.5px; color: #94a3b8; text-decoration: none; }
.featured-source:hover { text-decoration: underline; color: #38bdf8; }

.result-card { margin-bottom: 16px; background: #1e293b; padding: 16px; border-radius: 12px; border: 1px solid #334155; }
.result-card.official { border-color: #38bdf8; }
.site-info { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; text-decoration: none; }
.favicon { width: 22px; height: 22px; border-radius: 50%; background: #0f172a; padding: 2px; }
.site-title-box { display: flex; flex-direction: column; min-width: 0; }
.site-name { font-size: 13px; color: #cbd5e1; font-weight: 500; }
.site-url { font-size: 11.5px; color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 500px; }
.result-title { font-size: 18px; color: #38bdf8; text-decoration: none; font-weight: 600; line-height: 1.3; display: inline-block; margin-bottom: 6px; }
.result-title:hover { text-decoration: underline; }
.result-snippet { font-size: 13.5px; color: #94a3b8; line-height: 1.55; margin-top: 8px; }

.badges { display: inline-flex; gap: 6px; margin-left: 8px; vertical-align: middle; }
.badge { font-size: 10px; padding: 2px 7px; border-radius: 6px; font-weight: 600; }
.badge-official { background: #0284c7; color: white; }
.badge-rank { background: #334155; color: #94a3b8; }
.badge-score { background: #0f172a; color: #f59e0b; border: 1px solid #334155; }

.hero { text-align: center; margin-top: 90px; }
.hero-title { font-size: 56px; font-weight: 900; letter-spacing: 3px; color: #38bdf8; line-height: 1; }
.hero-title span { color: #f59e0b; }
.hero-tagline { font-size: 13px; font-weight: 800; color: #94a3b8; letter-spacing: 3px; margin-top: 8px; }
.hero-desc { color: #64748b; font-size: 13px; margin-top: 16px; }
.empty { margin-top: 30px; color: #64748b; }
</style>
</head>

<body>
<div class="header">
    <a href="/" class="logo-box">
        <div class="logo-text">GATR<span>A</span></div>
        <div class="logo-tagline">UNTUK INDONESIA MAJU</div>
    </a>
    <form action="/search" method="get" class="search-form">
        <div class="search-input-wrapper">
            <input type="text" name="q" class="search-input" value="{{ query }}" placeholder="Cari dengan GATRA..." required autocomplete="off">
        </div>
    </form>
</div>

<div class="container">
{% if query %}
    <div class="stats">Ditemukan <b>{{ results|length }}</b> hasil untuk "<b>{{ query }}</b>"</div>

    {% if results and ('siapa' in query.lower() or 'apa' in query.lower() or 'berapa' in query.lower()) %}
        <div class="featured-box">
            <div class="featured-label">💡 RINGKASAN JAWABAN CEPAT</div>
            <div class="featured-text">{{ results[0].snippet }}</div>
            <a href="/open?url={{ results[0].url|urlencode }}" class="featured-source">Sumber: {{ results[0].title }} ({{ results[0].domain }})</a>
        </div>
    {% endif %}

    {% for res in results %}
        <div class="result-card {{ 'official' if res.is_official else '' }}">
            <a href="/open?url={{ res.url|urlencode }}" class="site-info">
                <img src="{{ res.favicon }}" class="favicon" loading="lazy" onerror="this.style.display='none'">
                <div class="site-title-box">
                    <span class="site-name">{{ res.domain }}</span>
                    <span class="site-url">{{ res.url }}</span>
                </div>
            </a>
            <a href="/open?url={{ res.url|urlencode }}" class="result-title">{{ res.title }}</a>

            <span class="badges">
                {% if res.is_official %}
                    <span class="badge badge-official">SITUS RESMI</span>
                {% endif %}
                <span class="badge badge-rank">Rank {{ loop.index }}</span>
                <span class="badge badge-score">{{ res.score }}</span>
            </span>

            <div class="result-snippet">{{ res.snippet }}</div>
        </div>
    {% endfor %}

    {% if not results %}
        <div class="empty">Tidak ditemukan hasil untuk <b>{{ query }}</b>.</div>
    {% endif %}
{% else %}
    <div class="hero">
        <div class="hero-title">GATR<span>A</span></div>
        <div class="hero-tagline">UNTUK INDONESIA MAJU</div>
        <div class="hero-desc">Mesin pencari mandiri dengan pencarian lokal, ranking relevansi, dan pencarian web.</div>
    </div>
{% endif %}
</div>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(GATRA_TEMPLATE, query="", results=[])

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect("/")
    query = query[:300]
    results = search_engine.search(query, limit=50)
    return render_template_string(GATRA_TEMPLATE, query=query, results=results)

@app.route("/open")
def open_url():
    url = request.args.get("url", "").strip()
    if not url:
        return redirect("/")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        abort(400)

    search_engine.increment_click(url)
    return redirect(url)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
