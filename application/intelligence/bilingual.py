"""Two monolingual passage vectors per product; multilingual query encoded once."""
from .common import ROOT,read_json,digest


def load_translations(products, require_complete=True):
    source=read_json(ROOT/'data/esci/translations_vi_vertex.json')
    if source['catalog_hash']!=digest(products):
        raise ValueError('Vietnamese translations belong to a different catalog')
    if require_complete and (not source.get('complete') or set(source['products'])!={p['id'] for p in products}):
        raise ValueError('Vietnamese translations incomplete; run translate_esci_vertex.py first')
    for p in products:
        if p['id'] not in source['products']:continue
        item=source['products'][p['id']]
        # Validate against the same source-field mapping used by offline translation.
        values={'name':p['name'],'description':p['description'],'color':p.get('attributes',{}).get('color','')}
        values.update({f'feature_{i}':v for i,v in enumerate(p['features'])})
        fields={p['source_id']+'|'+k:v for k,v in values.items() if v}
        if item['source_hash']!=digest(fields):raise ValueError('Stale translation: '+p['id'])
        if len(item['features'])!=len(p['features']):raise ValueError('Translation feature alignment changed')
    return source


def vietnamese_documents(products, translations):
    docs={}
    for p in products:
        if p['id'] not in translations:continue
        t=translations[p['id']]
        parts=['Title: '+t['name']]
        if p.get('brand'):parts.append('Brand: '+p['brand'])
        if t.get('color'):parts.append('Color: '+t['color'])
        if t['description']:parts.append('Description: '+t['description'])
        parts += ['Feature: '+text for text in t['features'] if text]
        docs[p['id']]='. '.join(parts)
    return docs
