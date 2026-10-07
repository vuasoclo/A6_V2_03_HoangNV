"""SQLite vector snapshots: incremental encoding and transactional publication."""
import json
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager
import numpy as np
from application.intelligence.common import DATABASE, digest


class SQLiteIndex:
    def __init__(self, path=DATABASE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS index_sets (
                    name TEXT PRIMARY KEY, generation TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    dimension INTEGER NOT NULL, catalog_hash TEXT NOT NULL, document_language TEXT NOT NULL,
                    config_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vectors (
                    name TEXT NOT NULL, generation TEXT NOT NULL, product_id TEXT NOT NULL,
                    document_hash TEXT NOT NULL, document TEXT NOT NULL, vector BLOB NOT NULL,
                    token_json TEXT NOT NULL, PRIMARY KEY(name, generation, product_id));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout=20000")
            with db:
                yield db
        finally:
            db.close()

    def metadata(self, name):
        with self.connect() as db:
            row = db.execute("SELECT generation,fingerprint,dimension,catalog_hash,document_language,config_json FROM index_sets WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        return dict(zip(("generation", "fingerprint", "dimension", "catalog_hash", "document_language", "config_json"), row))

    def sync(self, name, products, documents, encoder, language="en"):
        started = time.perf_counter()
        ids = [p["id"] for p in products]
        if len(set(ids)) != len(ids) or set(documents) != set(ids):
            raise ValueError("Catalog/document IDs không khớp hoặc bị trùng.")
        before = self.metadata(name)
        old = {}
        previous_ids = set()
        if before:
            with self.connect() as db:
                previous_rows = list(db.execute("SELECT product_id,document_hash,document,vector,token_json FROM vectors WHERE name=? AND generation=?", (name, before["generation"])))
            previous_ids = {r[0] for r in previous_rows}
            if before["fingerprint"] == encoder.fingerprint:
                old = {r[0]: r[1:] for r in previous_rows}
        rows, changed = {}, []
        for pid in ids:
            text, info = encoder.fit_document(documents[pid])
            document_hash = digest({"text": text, "encoder": encoder.fingerprint, "language": language})
            if pid in old and old[pid][0] == document_hash:
                vector = np.frombuffer(old[pid][2], dtype="<f4")
                if vector.shape != (encoder.dimension,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1, atol=0.001):
                    raise ValueError("Vector cache hỏng; không tái sử dụng.")
                rows[pid] = old[pid]
            else:
                changed.append((pid, document_hash, text, info))
        encoded = encoder.encode([c[2] for c in changed], "passage")
        if encoded.shape != (len(changed), encoder.dimension) or not np.isfinite(encoded).all():
            raise ValueError("Vector mới sai kích thước hoặc chứa NaN.")
        for c, vector in zip(changed, encoded):
            if not np.isclose(np.linalg.norm(vector), 1, atol=0.001):
                raise ValueError("Vector phải được chuẩn hóa L2.")
            rows[c[0]] = (c[1], c[2], vector.astype("<f4").tobytes(), json.dumps(c[3]))
        catalog_hash = digest(products)
        no_op = before and not changed and set(old) == set(ids) and before["catalog_hash"] == catalog_hash and before["document_language"] == language
        if not no_op:
            generation = uuid.uuid4().hex
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT generation FROM index_sets WHERE name=?", (name,)).fetchone()
                if (current[0] if current else None) != (before["generation"] if before else None):
                    raise ValueError("Index vừa được tiến trình khác cập nhật; hãy chạy lại.")
                db.executemany("INSERT INTO vectors VALUES (?,?,?,?,?,?,?)", [(name, generation, pid, *rows[pid]) for pid in ids])
                config = json.dumps(getattr(encoder, "config", {}))
                db.execute("INSERT OR REPLACE INTO index_sets VALUES (?,?,?,?,?,?,?)", (name, generation, encoder.fingerprint, encoder.dimension, catalog_hash, language, config))
                db.execute("DELETE FROM vectors WHERE name=? AND generation<>?", (name, generation))
        return {"name": name, "products": len(ids), "encoded": len(changed), "reused": len(ids)-len(changed),
                "added": len(set(ids)-previous_ids), "updated": sum(c[0] in previous_ids for c in changed),
                "removed": len(previous_ids-set(ids)), "no_op": bool(no_op), "index_seconds": time.perf_counter()-started,
                "vector_bytes": len(ids)*encoder.dimension*4, "token_budget_omissions": sum(json.loads(r[3])["omitted_segments"] > 0 for r in rows.values())}

    def validate_documents(self, name, documents, encoder, language="en"):
        with self.connect() as db:
            stored = dict(db.execute("SELECT product_id,document_hash FROM vectors WHERE name=? AND generation=(SELECT generation FROM index_sets WHERE name=?)", (name, name)))
        expected = {pid: digest({"text": encoder.fit_document(text)[0], "encoder": encoder.fingerprint, "language": language})
                    for pid, text in documents.items()}
        if stored != expected:
            raise ValueError("Document policy changed or index missing; rebuild the selected index.")

    def load(self, name, fingerprint, products):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT generation,fingerprint,dimension,catalog_hash FROM index_sets WHERE name=?", (name,)).fetchone()
            if not row:
                raise ValueError("Chưa có index; chạy build_index.py trước.")
            if row[1] != fingerprint:
                raise ValueError("Model/tokenizer khác phiên bản index; cần lập lại index.")
            if row[3] != digest(products):
                raise ValueError("Catalog đã đổi; chạy build_index.py để đồng bộ.")
            records = db.execute("SELECT product_id,vector FROM vectors WHERE name=? AND generation=? ORDER BY product_id", (name, row[0])).fetchall()
        ids = [r[0] for r in records]
        if set(ids) != {p["id"] for p in products}:
            raise ValueError("Index thiếu/thừa sản phẩm.")
        vectors = np.stack([np.frombuffer(r[1], dtype="<f4") for r in records]) if records else np.empty((0, row[2]), dtype=np.float32)
        if vectors.shape != (len(ids), row[2]) or not np.isfinite(vectors).all():
            raise ValueError("Index hỏng.")
        if len(ids) and not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=0.001):
            raise ValueError("Vector index chưa chuẩn hóa.")
        return ids, vectors.copy()
