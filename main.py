import sys
import requests
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QLabel, QProgressBar, QMessageBox, QTextBrowser
)

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

class FetchPageThread(QThread):
    """Thread terpisah untuk mengambil isi Web HTML secara asynchronous tanpa Chromium."""
    fetched_signal = pyqtSignal(str, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MyBrowser/1.0"}
            resp = requests.get(self.url, headers=headers, timeout=10)
            if resp.status_code == 200:
                self.fetched_signal.emit(self.url, resp.text)
            else:
                self.fetched_signal.emit(self.url, f"<h3 style='color:red;'>Error {resp.status_code} saat memuat halaman</h3>")
        except Exception as e:
            self.fetched_signal.emit(self.url, f"<h3 style='color:red;'>Gagal memuat URL: {str(e)}</h3>")

class SearchEngineBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Browser & Search Engine Mandiri (Owser - Lite Edition)")
        self.resize(1100, 700)
        search_engine.init_db()
        self.history = []
        self.current_history_idx = -1
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        top_layout = QHBoxLayout()
        self.btn_back = QPushButton("◀")
        self.btn_forward = QPushButton("▶")
        self.btn_reload = QPushButton("🔄")
        
        self.btn_back.clicked.connect(self.go_back)
        self.btn_forward.clicked.connect(self.go_forward)
        self.btn_reload.clicked.connect(self.reload_page)
        
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

        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_results = QLabel("<b>Hasil Pencarian Lokal (Rating BM25 + Klik):</b>")
        left_layout.addWidget(lbl_results)

        self.result_list = QListWidget()
        self.result_list.itemClicked.connect(self.on_result_clicked)
        left_layout.addWidget(self.result_list)
        
        splitter.addWidget(left_widget)

        # Pengganti Chromium: QTextBrowser Native Qt (100% Ringan & Bebas Crash)
        self.web_view = QTextBrowser()
        self.web_view.setOpenExternalLinks(False)
        self.web_view.anchorClicked.connect(self.on_link_clicked)
        splitter.addWidget(self.web_view)

        splitter.setSizes([350, 750])
        main_layout.addWidget(splitter)

    def handle_search_or_go(self):
        text = self.input_box.text().strip()
        if not text:
            return

        if text.startswith("http://") or text.startswith("https://"):
            self.load_url(text)
        else:
            self.perform_search(text)

    def load_url(self, url):
        self.progress_bar.setValue(30)
        self.status_label.setText(f"Memuat: {url}...")
        self.fetch_thread = FetchPageThread(url)
        self.fetch_thread.fetched_signal.connect(self.on_page_fetched)
        self.fetch_thread.start()

    def on_page_fetched(self, url, html):
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Selesai memuat: {url}")
        self.input_box.setText(url)
        self.web_view.setHtml(html)
        
        if not self.history or self.history[self.current_history_idx] != url:
            self.history = self.history[:self.current_history_idx + 1]
            self.history.append(url)
            self.current_history_idx = len(self.history) - 1

    def on_link_clicked(self, qurl):
        url = qurl.toString()
        self.load_url(url)

    def go_back(self):
        if self.current_history_idx > 0:
            self.current_history_idx -= 1
            self.load_url(self.history[self.current_history_idx])

    def go_forward(self):
        if self.current_history_idx < len(self.history) - 1:
            self.current_history_idx += 1
            self.load_url(self.history[self.current_history_idx])

    def reload_page(self):
        if self.current_history_idx >= 0 and self.current_history_idx < len(self.history):
            self.load_url(self.history[self.current_history_idx])

    def perform_search(self, query):
        self.result_list.clear()
        results = search_engine.search(query)
        
        if not results:
            self.status_label.setText(f"Tidak ada hasil untuk query: '{query}'. Lakukan Index URL terlebih dahulu.")
            item = QListWidgetItem("Tidak ada hasil ditemukan di Database FTS.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.result_list.addItem(item)
            return

        self.status_label.setText(f"Ditemukan {len(results)} hasil untuk: '{query}'")
        for res in results:
            title = res['title']
            url = res['url']
            snippet = res['snippet'].replace('\n', ' ')
            clicks = res['clicks']
            
            item_text = f"🌐 {title} ⭐ [Rating Klik: {clicks}]\n🔗 {url}\n📄 {snippet}\n"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, url)
            self.result_list.addItem(item)

    def on_result_clicked(self, item):
        url = item.data(Qt.UserRole)
        if url:
            search_engine.increment_click(url)
            self.load_url(url)

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
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
