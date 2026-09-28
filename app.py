from flask import Flask, render_template, request, jsonify
import download_db
import search_engine
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.template_folder = os.path.join(BASE_DIR, 'templates')

@app.route("/")
def index():
    return render_template("search.html", query="", results=[], total=0, cat="all", ai_summary=None)

@app.route("/suggest")
def suggest():
    query = request.args.get("q", "").strip()
    suggestions = search_engine.get_suggestions(query, limit=6)
    return jsonify(suggestions)

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    category = request.args.get("cat", "all")
    results = []
    ai_summary = None
    
    if query:
        try:
            # Memanggil search_engine tanpa membatasi ke 50 web
            search_data = search_engine.search(query, limit=100, category=category)
            
            if isinstance(search_data, dict):
                results = search_data.get("results", [])
                ai_summary = search_data.get("ai_summary", None)
            else:
                results = search_data
        except Exception as e:
            print(f"[SEARCH ROUTE ERROR]: {e}")

    return render_template(
        "search.html", 
        query=query, 
        results=results, 
        total=len(results), 
        cat=category, 
        ai_summary=ai_summary
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

