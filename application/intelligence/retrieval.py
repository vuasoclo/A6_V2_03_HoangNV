"""Dense retrieval and BM25/RRF fusion with evidence-only structured filters."""
from collections import Counter
import math
import re
import numpy as np
from .common import ROOT, fold, read_json, tokens

MODES = {"keyword_v1", "bm25", "semantic", "hybrid"}
FILTERS = {"category_id", "manufacturer", "brand", "color", "material", "max_price_usd", "min_price_usd", "max_price_vnd", "min_price_vnd", "in_stock", "size"}
STOPWORDS = set("toi can muon tim mua cho mot doi giay loai de va co voi la nhung duoc hay san pham nao please find shoes shoe the a an for with and of to in".split())
LEXICAL_EXPANSION_VERSION = "footwear-vi-en-v1"
ALIASES = {
    "chay bo": "running", "chay duong mon": "trail running", "chay dia hinh": "trail running", "di duong mon": "hiking trail", "trekking": "hiking",
    "di bo": "walking", "leo nui": "hiking", "tap luyen": "training", "gym": "training", "giay bet": "flats", "ballet": "ballet flats",
    "chong nuoc": "waterproof", "di mua": "rain waterproof", "do bam": "grip traction", "bam tot": "grip traction", "mui thep": "steel toe",
    "dem em": "cushioning", "trung tinh": "neutral", "thoang khi": "breathable", "nhe": "lightweight", "co no": "bow", "trang tri no": "bow",
    "quai dan": "hook loop velcro", "de cong": "rocker curved", "diem xoay": "pivot", "linh hoat": "flexible", "co the gap": "foldable",
    "khong can buoc day": "slip on", "phat sang": "light up led", "goc mui bang khong": "zero drop", "got mui bang khong": "zero drop",
    "giay bao ho": "work safety", "ung ngan": "ankle rain boots", "giay cao got": "pumps heels",
}


def expanded_query(text):
    value = " " + fold(text) + " "
    # Expansion assists lexical ranking; it never creates product attributes or hard filters.
    additions = [english for vietnamese, english in ALIASES.items() if " " + vietnamese + " " in value]
    return text + " " + " ".join(additions)


def query_inventory_filters(text, filters):
    value = fold(text)
    inferred = {}
    match = re.search(r"\bsize\s*(\d+(?:[.,]\d+)?)\s*(eu|us|uk)?\b", value)
    if match:
        inferred["size"] = match.group(1).replace(",", ".") + (" "+match.group(2).upper() if match.group(2) else "")
    if re.search(r"\b(?:con hang|dang con hang|co san trong kho)\b", value):
        inferred["in_stock"] = True
    if re.search(r"\b(?:het hang|khong con hang)\b", value):
        inferred["in_stock"] = False
    for key, expected in inferred.items():
        if key in filters and filters[key] != expected:
            raise ValueError("Nội dung size/tồn kho mâu thuẫn với bộ lọc.")
    return {**inferred, **filters}


def validate_filters(filters):
    if filters is None:
        return {}
    if not isinstance(filters, dict) or set(filters)-FILTERS:
        raise ValueError("Bộ lọc không hợp lệ.")
    for key, value in filters.items():
        if key in {"max_price_usd", "min_price_usd", "max_price_vnd", "min_price_vnd"}:
            if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
                raise ValueError("Giá lọc phải là số hữu hạn không âm.")
        elif key == "in_stock":
            if type(value) is not bool:
                raise ValueError("in_stock phải là boolean.")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError("Giá trị bộ lọc phải là chuỗi không rỗng.")
    if filters.get("min_price_usd", 0) > filters.get("max_price_usd", math.inf):
        raise ValueError("Giá tối thiểu lớn hơn giá tối đa.")
    if filters.get("min_price_vnd", 0) > filters.get("max_price_vnd", math.inf):
        raise ValueError("Giá VND tối thiểu lớn hơn giá tối đa.")
    return filters


def matches_filters(product, filters):
    attrs = product.get("attributes", {})
    for key, expected in filters.items():
        if key == "category_id":
            actual_category=product.get('search_category_id',product['category_id'])
            if expected in {"shoes", "accessories"} and product.get("store_group"):
                if product["store_group"] != expected:
                    return False
            elif expected == "shoes":
                if not actual_category.startswith("shoes."):
                    return False
            elif actual_category != expected:
                return False
        elif key in {"max_price_usd", "min_price_usd"}:
            price = product.get("price", {})
            amount = price.get("amount")
            if price.get("currency") != "USD" or amount is None:
                return False
            if key == "max_price_usd" and amount > expected or key == "min_price_usd" and amount < expected:
                return False
        elif key in {"max_price_vnd", "min_price_vnd"}:
            price = product.get('display',{}).get('price',{})
            amount = price.get('amount')
            if price.get('currency') != 'VND' or amount is None:
                return False
            if key == 'max_price_vnd' and amount > expected or key == 'min_price_vnd' and amount < expected:
                return False
        elif key == "in_stock":
            stock = product.get("stock")
            if stock is None or ((stock > 0) != expected):
                return False
        elif key == "size":
            variants = product.get("variants", [])
            if not any(fold(str(v.get("size", ""))) == fold(expected) and (v.get("stock") or 0) > 0 for v in variants):
                return False
        else:
            actual = product.get("brand") if key == "brand" else attrs.get(key)
            if actual is None or fold(str(actual)) != fold(expected):
                return False
    return True


def scope_reason(text):
    value = " " + fold(text) + " "
    # Explicit scope terms only; no claim of a general intent classifier.
    phrases = ["dien thoai", "laptop", "may tinh", "tai nghe", "dong ho", "tui xach", "ao khoac", "quan jean", "giay tre em", "giay cho tre em", "giay em be", "dep le", "dep sandal", "iphone", "macbook", "samsung galaxy"]
    return next((p for p in phrases if " " + p + " " in value), None)


class BM25:
    def __init__(self, products, documents):
        categories = {c["id"]: c for c in read_json(ROOT / "data" / "processed" / "categories.json")}
        self.ids, self.counts, self.lengths = [], [], []
        frequency = Counter()
        for p in products:
            # Category vocabulary is explicit taxonomy translation, not inferred facts.
            text = documents[p["id"]] + " " + categories.get(p["category_id"], {}).get("name_vi", "")
            terms = [t for t in tokens(text) if t not in STOPWORDS]
            counts = Counter(terms)
            self.ids.append(p["id"])
            self.counts.append(counts)
            self.lengths.append(len(terms))
            frequency.update(counts.keys())
        self.average = sum(self.lengths)/max(1, len(products))
        self.idf = {term: math.log(1+(len(products)-df+0.5)/(df+0.5)) for term, df in frequency.items()}

    def scores(self, query):
        terms = set(t for t in tokens(query) if t not in STOPWORDS)
        result = {}
        for pid, counts, length in zip(self.ids, self.counts, self.lengths):
            score = 0.0
            for term in terms:
                tf = counts[term]
                if tf:
                    score += self.idf.get(term, 0)*tf*2.5/(tf+1.5*(0.25+0.75*length/max(1, self.average)))
            if score > 0:
                result[pid] = score
        return result


class SearchEngine:
    def __init__(self, products, documents, encoder=None, index=None, index_name="e5-en", threshold=None, rrf_k=60, dense_weight=1.0, scope_policy=True, inventory_policy=True, price_query_policy=False):
        self.products = {p["id"]: p for p in products}
        self.documents, self.encoder = documents, encoder
        self.threshold, self.rrf_k, self.dense_weight = threshold, rrf_k, dense_weight
        self.scope_policy = scope_policy
        self.inventory_policy = inventory_policy
        self.price_query_policy = price_query_policy
        # Optional reversible catalog visibility; index and source data stay intact.
        self.active_product_ids = set(self.products)
        self.lexical = BM25(products, documents)
        self.ids, self.vectors = (index.load(index_name, encoder.fingerprint, products) if encoder is not None else ([], None))
        self.dense_views = {}  # Optional aligned monolingual passage snapshots; query encoded once.

    def keyword_v1_scores(self, query):
        # Original V1 matcher logic: raw whitespace tokens and substring count on name/category/color.
        words = query.lower().split()
        scores = {}
        for pid, product in self.products.items():
            category = product["category_path"][-1]
            haystack = " ".join((product["name"], category, product.get("attributes", {}).get("color", ""))).lower()
            score = sum(word in haystack for word in words)
            if score > 0:
                scores[pid] = float(score)
        return scores

    def search(self, query, *, mode="hybrid", top_k=5, filters=None, query_vector=None, apply_policy=True, candidate_ids=None):
        if not isinstance(query, str) or not query.strip() or not re.search(r"\w", query):
            raise ValueError("Hãy nhập nội dung tìm kiếm.")
        if len(query) > 2000 or any(ord(c) < 32 and c not in "\t\n\r" for c in query):
            raise ValueError("Truy vấn quá dài hoặc có ký tự điều khiển.")
        if mode not in MODES or type(top_k) is not int or not 1 <= top_k <= 50:
            raise ValueError("Mode/top_k không hợp lệ.")
        filters = validate_filters(filters)
        original_query = query.strip()
        price_clauses = []
        if self.price_query_policy and apply_policy:
            from .price_query import parse_price_query
            query, filters, price_clauses = parse_price_query(query, filters)
            filters = validate_filters(filters)
            if price_clauses:
                query_vector = None  # A supplied vector may contain the removed price clause.
        if self.inventory_policy:
            filters = query_inventory_filters(query, filters)
        eligible = {pid for pid, p in self.products.items() if matches_filters(p, filters)}
        eligible &= self.active_product_ids
        if candidate_ids is not None:
            candidates = set(candidate_ids)
            if candidates-set(self.products):
                raise ValueError('Unknown candidate IDs')
            eligible &= candidates
        base = {"mode": mode, "query": original_query, "filters": filters, "score_is_probability": False,
                "semantic_query": query.strip(), "price_clauses": price_clauses,
                "price_basis": "display_price_vnd_including_demo" if any(k.endswith('_vnd') for k in filters) else None}
        if not eligible:
            return {**base, "status": "no_match", "reason": "Không có sản phẩm có dữ liệu xác nhận phù hợp bộ lọc.", "results": []}
        if apply_policy and self.scope_policy and scope_reason(query):
            return {**base, "status": "out_of_scope", "reason": "Catalog hiện tại chỉ có giày người lớn.", "results": []}
        if not query.strip():
            ordered_ids = sorted(eligible, key=lambda pid:(self.products[pid].get('display',{}).get('price',{}).get('amount',math.inf),pid))
            results = [{"product_id":pid,"name":self.products[pid]['name'],"score":0.0,
                        "cosine_score":None,"lexical_score":None} for pid in ordered_ids[:top_k]]
            return {**base,"status":"ok","reason":None,"ranking_basis":"price_ascending","results":results}
        lexical = self.keyword_v1_scores(query) if mode == "keyword_v1" else self.lexical.scores(expanded_query(query) if mode == "hybrid" else query)
        lexical = {pid: s for pid, s in lexical.items() if pid in eligible}
        dense = {}
        if mode in {"semantic", "hybrid"}:
            if self.encoder is None:
                raise ValueError("Mode này cần pretrained encoder và index.")
            vector = self.encoder.encode([query.strip()], "query")[0] if query_vector is None else np.asarray(query_vector, dtype=np.float32)
            if vector.shape != (self.encoder.dimension,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1, atol=0.001):
                raise ValueError("Vector truy vấn không hợp lệ.")
            scores = self.vectors @ vector
            matched_languages = {pid:'en' for pid in self.ids}
            for language, passage_vectors in self.dense_views.items():
                if passage_vectors.shape != self.vectors.shape:
                    raise ValueError('Bilingual vector rows do not align')
                alternate = passage_vectors @ vector
                for position in np.flatnonzero(alternate > scores):
                    matched_languages[self.ids[position]] = language
                scores = np.maximum(scores, alternate)
            dense = {pid: float(score) for pid, score in zip(self.ids, scores) if pid in eligible}
            if apply_policy and self.threshold is not None and max(dense.values(), default=-1) < self.threshold:
                return {**base, "status": "no_match", "reason": "Độ tương đồng dưới ngưỡng thử nghiệm trên bộ dev.", "results": []}
        ordered = lambda values: sorted(values, key=lambda pid: (-values[pid], pid))
        if mode == "hybrid":
            combined = {}
            for weight, values in ((self.dense_weight, dense), (1, lexical)):
                for rank, pid in enumerate(ordered(values)[:50], 1):
                    combined[pid] = combined.get(pid, 0) + weight/(self.rrf_k + rank)
            scores = combined
        else:
            scores = dense if mode == "semantic" else lexical
        results = [{"product_id": pid, "name": self.products[pid]["name"], "score": scores[pid],
                    "cosine_score": dense.get(pid), "lexical_score": lexical.get(pid),
                    **({"matched_document_language":matched_languages[pid]} if dense else {})} for pid in ordered(scores)[:top_k]]
        return {**base, "status": "ok" if results else "no_match", "reason": None if results else "Không có kết quả.", "results": results}
