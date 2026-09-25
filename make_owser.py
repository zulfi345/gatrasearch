import zipfile

files = {
"README.md": """# Browser & Search Engine Sendiri (Owser)

Project ini berisi:
- `search_engine.py` — search engine sendiri (SQLite FTS5, tanpa API pihak ketiga)
- `crawler.py` — crawler sendiri (requests + BeautifulSoup, tanpa API pihak ketiga)
- `main.py` — GUI browser (PyQt6 + QWebEngine, mesin render Chromium via Qt)
- `requirements.txt` — daftar dependensi Python
- `README.md` — panduan penggunaan

## Cara Pakai di VNC
export DISPLAY=:1
python3 main.py
""",

"requirements.txt": """PyQt6
PyQt6-WebEngine
requests
beautifulsoup4
lxml
""",

"search_engine.py": """import sqlite3
import re

DB_NAME = "index.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            url, title, content, tokenize='unicode61'
        )
    ''')
    conn.commit()
    conn.close()

def add_or_update_page(url, title, content):
    if not url or not content:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pages_fts WHERE url = ?", (url,))
    cursor.execute("INSERT INTO pages_fts (url, title, content) VALUES (?, ?, ?)", (url, title, content))
    conn.commit()
    conn.close()

def search(query, limit=20):
    if not query.strip():
        return []
    conn = get_connection()
    cursor = conn.cursor()
    safe_query = re.sub(r'[^\\w\\s]', '', query).strip()
    if not safe_query:
        conn.close()
        return []
    words = safe_query.split()
    fts_query = " OR ".join([f'"{word}" OR {word}*' for word in words])
    results = []
    try:
        cursor.execute('''
            SELECT url, title, snippet(pages_fts, 2, '<b>', '</b>', '...', 15) AS snippet, bm25(pages_fts) AS score
            FROM pages_fts
            WHERE pages_fts MATCH ?
            ORDER BY score
            LIMIT ?
        ''', (fts_query, limit))
        results = cursor.fetchall()
    except sqlite3.OperationalError:
        cursor.execute('''
            SELECT url, title, substr(content, 1, 150) AS snippet, 0 AS score
            FROM pages_fts
            WHERE title LIKE ? OR content LIKE ?
            LIMIT ?
        ''', (f"%{safe_query}%", f"%{safe_query}%", limit))
        results = cursor.fetchall()
    conn.close()
    return [{"url": r[0], "title": r[1] or r[0], "snippet": r[2]} for r in results]
""",

"crawler.py": """import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import search_engine

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 MyBrowser/1.0"
}

def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.netloc) and parsed.scheme in ['http', 'https']

def crawl(start_url, max_pages=15, status_callback=None):
    search_engine.init_db()
    visited = set()
    queue = [start_url]
    crawled_count = 0

    while queue and crawled_count < max_pages:
        current_url = queue.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        if status_callback:
            status_callback(f"Proses Indexing ({crawled_count + 1}/{max_pages}): {current_url}")

        try:
            response = requests.get(current_url, headers=HEADERS, timeout=7)
            if response.status_code != 200 or 'text/html' not in response.headers.get('Content-Type', ''):
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            for element in soup(["script", "style", "noscript", "header", "footer", "nav"]):
                element.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else current_url
            text = soup.get_text(separator=' ')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = ' '.join(chunk for chunk in chunks if chunk)

            search_engine.add_or_update_page(current_url, title, clean_text)
            crawled_count += 1

            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                full_url = urljoin(current_url, href).split('#')[0]
                if is_valid_url(full_url) and full_url not in visited and full_url not in queue:
                    queue.append(full_url)

        except Exception as e:
            if status_callback:
                status_callback(f"Gagal ({current_url}): {str(e)}")
            continue

    if status_callback:
        status_callback(f"Selesai! {crawled_count} halaman berhasil di-index.")
    return crawled_count
""",

"main.py": """import sys
from PyQt6.QtCore import QUrl, QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QLabel, QProgressBar, QMessageBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

import search_engine
import crawler

class CrawlThread(QThread):
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, start_url, max_pages=15):
        super().__init__()
        self.start_url = start_url
        self.max_pages = max_pages

    def run(self):
        count = crawler.crawl(
            self.start_url, 
            max_pages=self.max_pages, 
            status_callback=self.status_signal.emit
        )
        self.finished_signal.emit(count)

class SearchEngineBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Browser & Search Engine Mandiri (Owser)")
        self.resize(1100, 700)
        search_engine.init_db()
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        top_layout = QHBoxLayout()
        self.btn_back = QPushButton("◀")
        self.btn_forward = QPushButton("▶")
        self.btn_reload = QPushButton("🔄")
        
        self.btn_back.clicked.connect(lambda: self.web_view.back())
        self.btn_forward.clicked.connect(lambda: self.web_view.forward())
        self.btn_reload.clicked.connect(lambda: self.web_view.reload())
        
        top_layout.addWidget(self.btn_back)
        top_layout.addWidget(self.btn_forward)
        top_layout.addWidget(self.btn_reload)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ketik kata kunci pencarian ATAU URL lengkap (https://...)...")
        self.input_box.returnPressed.connect(self.handle_search_or_go)
        top_layout.addWidget(self.input_box)

        self.btn_search = QPushButton("🔍 Cari")
        self.btn_search.clicked.connect(self.handle_search_or_go)
        top_layout.addWidget(self.btn_search)

        self.btn_crawl = QPushButton("🌐 Index URL")
        self.btn_crawl.clicked.connect(self.start_crawling)
        top_layout.addWidget(self.btn_crawl)

        main_layout.addLayout(top_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Siap. Masukkan query pencarian atau URL untuk diawali crawling.")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        main_layout.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_results = QLabel("<b>Hasil Pencarian Lokal (Database FTS):</b>")
        left_layout.addWidget(lbl_results)

        self.result_list = QListWidget()
        self.result_list.itemClicked.connect(self.on_result_clicked)
        left_layout.addWidget(self.result_list)
        
        splitter.addWidget(left_widget)

        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl("about:blank"))
        self.web_view.loadProgress.connect(self.progress_bar.setValue)
        self.web_view.urlChanged.connect(self.on_url_changed)
        splitter.addWidget(self.web_view)

        splitter.setSizes([350, 750])
        main_layout.addWidget(splitter)

    def handle_search_or_go(self):
        text = self.input_box.text().strip()
        if not text:
            return

        if text.startswith("http://") or text.startswith("https://"):
            self.web_view.setUrl(QUrl(text))
        else:
            self.perform_search(text)

    def perform_search(self, query):
        self.result_list.clear()
        results = search_engine.search(query)
        
        if not results:
            self.status_label.setText(f"Tidak ada hasil untuk query: '{query}'. Lakukan Index URL terlebih dahulu.")
            item = QListWidgetItem("Tidak ada hasil ditemukan di Database FTS.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.result_list.addItem(item)
            return

        self.status_label.setText(f"Ditemukan {len(results)} hasil untuk: '{query}'")
        for res in results:
            title = res['title']
            url = res['url']
            snippet = res['snippet'].replace('\\n', ' ')
            
            item_text = f"🌐 {title}\\n🔗 {url}\\n📄 {snippet}\\n"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, url)
            self.result_list.addItem(item)

    def on_result_clicked(self, item):
        url = item.data(Qt.ItemDataRole.UserRole)
        if url:
            self.input_box.setText(url)
            self.web_view.setUrl(QUrl(url))

    def on_url_changed(self, qurl):
        url_str = qurl.toString()
        if url_str != "about:blank":
            self.input_box.setText(url_str)

    def start_crawling(self):
        url = self.input_box.text().strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            QMessageBox.warning(self, "Peringatan", "Masukkan URL lengkap yang valid (contoh: https://example.com) untuk di-crawl!")
            return

        self.btn_crawl.setEnabled(False)
        self.btn_search.setEnabled(False)
        self.status_label.setText(f"Memulai crawling: {url}...")
        
        self.crawl_thread = CrawlThread(url, max_pages=15)
        self.crawl_thread.status_signal.connect(self.status_label.setText)
        self.crawl_thread.finished_signal.connect(self.on_crawl_finished)
        self.crawl_thread.start()

    def on_crawl_finished(self, count):
        self.btn_crawl.setEnabled(True)
        self.btn_search.setEnabled(True)
        QMessageBox.information(self, "Selesai", f"Proses crawl selesai! {count} halaman telah berhasil ditambahkan ke Database FTS.")

def main():
    app = QApplication(sys.argv)
    window = SearchEngineBrowser()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
"""
}

with zipfile.ZipFile("Owser.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for fname, content in files.items():
        z.writestr(fname, content)

print("SUKSES: Owser.zip berhasil dibuat!")
