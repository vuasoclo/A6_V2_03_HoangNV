"""Isolated ESCI dataset adapter; reuse the existing pretrained encoder/retrieval."""
from .common import ROOT, read_json, digest
from .encoder import HFEncoder
from data.vector_index import SQLiteIndex
from .retrieval import SearchEngine


def create_esci_engine(config, build=False):
    products = read_json(ROOT/'data/esci/products.json')
    source_catalog_hash = digest(products)
    encoder = HFEncoder(config['model'], threads=config.get('threads',4))
    raw_documents = {p['id']:p['semantic_document']['text'] for p in products}
    documents = {pid:encoder.fit_document(text)[0] for pid,text in raw_documents.items()}
    index = SQLiteIndex(ROOT/'data/esci/index.sqlite3')
    stats = index.sync(config['index_name'], products, raw_documents, encoder) if build else None
    index.validate_documents(config['index_name'], documents, encoder)
    engine = SearchEngine(products,documents,encoder,index,config['index_name'],
                          threshold=config.get('threshold'), rrf_k=config.get('rrf_k',60),
                          dense_weight=config.get('dense_weight',0.5), scope_policy=False, inventory_policy=False,
                          price_query_policy=config.get('price_query_policy',False))
    if config.get('bilingual_search',False):
        from .bilingual import load_translations,vietnamese_documents
        translations=load_translations(products)['products']
        vi_raw=vietnamese_documents(products,translations)
        vi_name=config.get('vi_index_name','e5-esci-vi-vertex')
        if build:
            vi_stats=index.sync(vi_name,products,vi_raw,encoder,language='vi')
            stats={'english':stats,'vietnamese':vi_stats}
        index.validate_documents(vi_name,vi_raw,encoder,language='vi')
        vi_ids,vi_vectors=index.load(vi_name,encoder.fingerprint,products)
        if vi_ids!=engine.ids:raise ValueError('English/Vietnamese vector IDs misaligned')
        engine.dense_views['vi']=vi_vectors
        engine.documents_vi={pid:encoder.fit_document(text)[0] for pid,text in vi_raw.items()}
        # Hybrid/BM25 have both vocabularies; pure semantic remains cosine only.
        from .retrieval import BM25
        engine.lexical=BM25(products,{pid:documents[pid]+' '+engine.documents_vi[pid] for pid in documents})
        for pid,product in engine.products.items():product['translation_vi']=translations[pid]
    image_manifest=ROOT/'data/esci/images.json'
    if image_manifest.exists():
        photos=read_json(image_manifest)
        if photos['catalog_hash']!=source_catalog_hash:
            raise ValueError('Image manifest belongs to a different catalog')
        if config.get('hide_no_source_images', False):
            if not photos.get('complete_pass') or set(photos['images']) != set(engine.products):
                raise ValueError('Visibility requires a complete image manifest')
            engine.active_product_ids -= {pid for pid, photo in photos['images'].items()
                                          if photo.get('status') == 'no_source_url'}
        for pid,p in engine.products.items():
            photo=photos['images'].get(pid,{})
            if photo.get('local_path'):
                p['images']=[{'local_path':photo['local_path'],'url':photo['download_url'],'source':photo.get('matched_source')}]
    elif config.get('hide_no_source_images', False):
        raise ValueError('Visibility requires an image manifest')
    display_manifest = ROOT/'data/esci/display.json'
    if display_manifest.exists():
        display = read_json(display_manifest)
        # Source products were augmented in memory with images above.
        if display['catalog_hash'] != digest(read_json(ROOT/'data/esci/products.json')):
            raise ValueError('Display metadata belongs to a different catalog')
        if set(display['products']) != set(engine.products):
            raise ValueError('Incomplete display metadata')
        for pid, product in engine.products.items():
            product['display'] = display['products'][pid]
    category_manifest=ROOT/'data/esci/demo_categories.json'
    if category_manifest.exists():
        from .demo_categories import RULE_HASH
        groups=read_json(category_manifest)
        if groups['catalog_hash']!=source_catalog_hash or groups['rule_hash']!=RULE_HASH or set(groups['products'])!=set(engine.products):
            raise ValueError('Demo category metadata changed. Run prepare_demo_categories.py.')
        engine.demo_categories=groups['categories']
        for pid,p in engine.products.items():
            p['demo_category']=groups['products'][pid]
            p['search_category_id']=groups['products'][pid]['category_id']
    return engine, stats
