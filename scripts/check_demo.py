r"""Real-model HTTP smoke checks against a running assignment06 server.

Run: .venv\Scripts\python.exe scripts/check_demo.py
Saves evidence; checks plumbing/constraints, not relevance accuracy.
"""
from pathlib import Path
import io,json,time,urllib.request,urllib.error,uuid
ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:5000'

def call(path,payload=None,upload=None,fields=None):
    headers={};body=None
    if upload:
        field,name,content=upload;boundary='a06-'+uuid.uuid4().hex;chunks=[]
        for key,value in (fields or {}).items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),content,f'\r\n--{boundary}--\r\n'.encode()])
        body=b''.join(chunks);headers['Content-Type']='multipart/form-data; boundary='+boundary
    elif payload is not None:body=json.dumps(payload).encode();headers['Content-Type']='application/json'
    req=urllib.request.Request(BASE+path,data=body,headers=headers);start=time.perf_counter()
    try:
        with urllib.request.urlopen(req,timeout=90) as response:
            raw=response.read();status=response.status
            result=json.loads(raw) if 'json' in response.headers.get('Content-Type','') else raw
    except urllib.error.HTTPError as error:status=error.code;result=json.loads(error.read())
    return status,result,round((time.perf_counter()-start)*1000,1)

def main():
    checks=[]
    def check(name,condition,ms=0,detail=None):
        checks.append({'case':name,'passed':bool(condition),'elapsed_ms':ms,'detail':detail})
        print(name, 'PASS' if condition else 'FAIL',ms,'ms',flush=True)
    status,health,ms=call('/health');check('models_ready',status==200 and all(health[k] for k in ['image_search_available','composed_available','voice_available','bilingual_search']),ms,health)
    for query in ['quick drying water shoes','giày đi nước','black leather boots']:
        status,r,ms=call('/api/search',{'query':query,'top_k':5})
        check('text:'+query,status==200 and len(r['results'])==5 and [i['rank'] for i in r['results']]==list(range(1,6)),ms,[i['source_id'] for i in r.get('results',[])])
    for query in ['giày dưới 8 trăm','shoes under 800k']:
        status,r,ms=call('/api/search',{'query':query,'top_k':5})
        check('spoken_price:'+query,status==200 and r['results'] and all(i['price']<800000 for i in r['results']),ms,r.get('filters'))
    status,r,ms=call('/api/search',{'query':'water shoes','filters':{'min_price_vnd':500000,'max_price_vnd':800000,'category_id':'shoes'},'sort':'price-asc','top_k':20})
    prices=[i['price'] for i in r['results']]
    check('ui_price_group_sort',status==200 and prices==sorted(prices) and all(500000<=p<=800000 for p in prices) and all(i['group_id']=='shoes' for i in r['results']),ms)
    status,r,ms=call('/api/search',{'query':'shoes above 900k','filters':{'max_price_vnd':800000}});check('conflicting_prices',status==400,ms)
    status,r,ms=call('/api/catalog?category_id=accessories');check('catalog_accessories',status==200 and r['results'] and all(i['group_id']=='accessories' for i in r['results']),ms)
    status,content,ms=call('/photo/B07G8WM97W');check('source_photo',status==200 and isinstance(content,bytes) and len(content)>1000,ms)
    status,r,ms=call('/api/image-search',upload=('image','reference.jpg',content),fields={'top_k':5})
    check('image_self_match',status==200 and r['results'][0]['source_id']=='B07G8WM97W',ms,[i['source_id'] for i in r.get('results',[])])
    status,r,ms=call('/api/image-search',upload=('image','reference.jpg',content),fields={'top_k':5,'query':'đen','max_price_vnd':800000,'category_id':'shoes'})
    check('image_plus_black',status==200 and r['mode']=='composed' and r['results'][0]['source_id']=='B07FFRLDX9' and all(i['price']<=800000 for i in r['results']),ms,[i['source_id'] for i in r.get('results',[])])
    status,r,ms=call('/api/image-search',upload=('image','invalid.jpg',b'not an image'));check('invalid_image',status==400,ms)
    audio=ROOT/'tests/fixtures/voice.wav'
    status,r,ms=call('/api/voice',upload=('audio','sample.wav',audio.read_bytes()));check('real_voice',status==200 and bool(r.get('text')),ms,r.get('text'))
    status,r,ms=call('/api/products/B07FFRLDX9');check('detail_data',status==200 and r['price']==710000 and 'rank' not in r and 'score' not in r,ms)
    (ROOT/'screenshots').mkdir(exist_ok=True)
    (ROOT/'screenshots/runtime-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not all(c['passed'] for c in checks):raise SystemExit(1)
    print('All',len(checks),'real-runtime checks passed.')

if __name__=='__main__':main()
