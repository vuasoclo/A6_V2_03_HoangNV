"""Read-only visible catalog and validated original product photo paths."""
from collections import Counter
import re
from application.intelligence.common import ROOT
from application.intelligence.retrieval import matches_filters, validate_filters

class ProductRepository:
    def __init__(self, engine):
        self.products=engine.products
        self.visible=set(engine.active_product_ids)
        for product in self.products.values():
            category=product.get('search_category_id','')
            # Water footwear is also marketed as "aqua socks"; it is still footwear.
            water_footwear=re.search(r'\b(?:water(?:\s+sports?)?|aqua|beach|barefoot|swim(?:ming)?)\s+shoes?\b',product['name'],re.I)
            accessory=category=='demo.accessories' or re.search(r'\b(?:tights|stockings|gloves|shoe care|shoe storage)\b',product['name'],re.I)
            product['store_group']='accessories' if accessory and not water_footwear else 'shoes'

    def get(self, product_id):
        return self.products.get(product_id) if product_id in self.visible else None

    def groups(self):
        counts=Counter(self.products[pid]['store_group'] for pid in self.visible)
        return [{'id':key,'name':name,'count':counts[key]} for key,name in [('shoes','Giày'),('accessories','Phụ kiện')]]

    def browse(self, filters, sort, page, page_size=24):
        validate_filters(filters)
        products=[self.products[pid] for pid in sorted(self.visible) if matches_filters(self.products[pid],filters)]
        if sort in {'price-asc','price-desc'}:
            products.sort(key=lambda p:p['display']['price']['amount'],reverse=sort=='price-desc')
        else:
            products.sort(key=lambda p:(not any(i.get('local_path') for i in p['images']),p['source_id']))
        return products[(page-1)*page_size:page*page_size],len(products)

    def photo(self, source_id):
        product=self.get('amazon:'+source_id)
        if not product:return None
        image=next((i for i in product['images'] if i.get('local_path')),None)
        if not image:return None
        path=(ROOT/image['local_path']).resolve()
        return path if path.is_relative_to((ROOT/'data/images').resolve()) and path.is_file() else None
