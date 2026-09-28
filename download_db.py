import os
import requests

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.db")

HF_URL = "https://huggingface.co/datasets/zulfitjahnu/gatrasearch-db/resolve/main/index.db"

print("[DB] Mengecek index.db...")

if os.path.exists(DB_PATH):
    print("[DB] index.db sudah ada.")
else:
    print("[DB] Download index.db dari Hugging Face...")

    r = requests.get(HF_URL, stream=True, timeout=120)
    r.raise_for_status()

    with open(DB_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    print("[DB] index.db berhasil di-download.")
