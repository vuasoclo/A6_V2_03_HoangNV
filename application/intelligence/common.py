import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data" / "processed" / "products.json"
DATABASE = ROOT / "data" / "index" / "semantic.sqlite3"


def digest(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def fold(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", value.lower().replace("đ", "d")) if not unicodedata.combining(c)).split())


def tokens(value):
    return re.findall(r"[a-z0-9]+", fold(value))


def load_catalog(path=CATALOG):
    products = read_json(path)
    if not isinstance(products, list) or not all(isinstance(p, dict) and isinstance(p.get("id"), str) and p["id"] for p in products):
        raise ValueError("Catalog phải là danh sách sản phẩm có ID hợp lệ.")
    if len({p["id"] for p in products}) != len(products):
        raise ValueError("Catalog có ID trùng.")
    return products
