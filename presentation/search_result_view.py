"""Vietnamese storefront projection; keep English source and indexed documents intact."""
MATERIALS={'Leather':'Da','Suede':'Da lộn','Mesh':'Lưới','Synthetic':'Tổng hợp','Fabric':'Vải','Rubber':'Cao su','Eva':'EVA','Canvas':'Vải canvas','Textile':'Vải dệt','Cotton':'Cotton','Nylon':'Nylon','Polyester':'Polyester'}

def product_view(product):
    translated=product.get('translation_vi') or {}
    fields=product.get('display',{}).get('fields',{})
    def values(key):return ', '.join(str(item['value']) for item in fields.get(key,[]) if item.get('value'))
    color=translated.get('color') or values('color') or product.get('attributes',{}).get('color') or ''
    brand=values('brand') or product.get('brand') or product.get('attributes',{}).get('manufacturer') or ''
    material=', '.join(MATERIALS.get(item['value'],item['value']) for item in fields.get('materials',[]))
    return {'id':product['id'],'source_id':product['source_id'],'name':translated.get('name') or product['name'],
            'name_en':product['name'],'brand':brand,'color':color,'price':product['display']['price']['amount'],
            'group':'Phụ kiện' if product['store_group']=='accessories' else 'Giày','group_id':product['store_group'],
            'description':translated.get('description') or product.get('description',''),
            'features':translated.get('features') or product.get('features',[]),'material':material,
            'audience':values('audience'),'model':values('model'),'uses':values('uses'),
            'image':'/photo/'+product['source_id'] if any(i.get('local_path') for i in product['images']) else None}

def result_view(result, repository):
    return {**result,'results':[{**item,**product_view(repository.get(item['product_id']))} for item in result['results']]}
