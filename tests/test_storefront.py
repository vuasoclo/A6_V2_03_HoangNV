import io,threading,unittest
from types import SimpleNamespace
from application.search_service import SearchService
from application.image_service import ImageService
from application.speech_service import SpeechService
from data.product_repository import ProductRepository
from main import create_app
from fixtures import product
from unittest.mock import patch
from application.intelligence.common import ROOT

class StorefrontTests(unittest.TestCase):
    def setUp(self):
        a,b=product('A'),product('B');b['search_category_id']='demo.accessories'
        for p,price in [(a,500000),(b,800000)]:p['display']={'price':{'amount':price,'currency':'VND','kind':'synthetic_demo'},'fields':{}}
        self.engine=SimpleNamespace(products={p['id']:p for p in [a,b]},active_product_ids={a['id'],b['id']})
        self.engine.search=lambda query,**kw:{'mode':'semantic','results':[{'product_id':'amazon:A','score':.8},{'product_id':'amazon:B','score':.6}]}
        self.repo=ProductRepository(self.engine)
        self.services=SearchService(self.engine,self.repo,ImageService(self.engine,None,None),SpeechService(None),{'model':'test'})
        self.client=create_app(self.services,testing=True).test_client()
    def test_rank_and_price_order(self):
        r=self.client.post('/api/search',json={'query':'walking shoes','sort':'price-desc'}).json
        self.assertEqual([p['rank'] for p in r['results']],[2,1])
        self.assertEqual(r['results'][0]['price'],800000)
    def test_coarse_groups_and_pagination(self):
        data=self.client.get('/api/catalog?category_id=accessories').json
        self.assertEqual(data['total'],1);self.assertEqual(data['results'][0]['source_id'],'B')
        self.assertEqual(self.client.get('/api/catalog?page=2').json['results'],[])
    def test_water_shoes_marketed_as_aqua_socks_are_footwear(self):
        p=self.engine.products['amazon:B'];p['name']='Quick Dry Water Shoes Barefoot Aqua Socks'
        ProductRepository(self.engine)
        self.assertEqual(p['store_group'],'shoes')
    def test_validations(self):
        for body in [{'query':[]},{'query':'x','filters':{'category_id':'bogus'}},{'query':'x','sort':'bogus'},{'query':'x','extra':1},{'query':'x','filters':{'max_price_vnd':-1}}]:
            self.assertEqual(self.client.post('/api/search',json=body).status_code,400)
        for url in ['/api/catalog?page=0','/api/catalog?min_price_vnd=nan','/api/catalog?min_price_vnd=900000&max_price_vnd=100','/api/catalog?page=1&page=2']:
            self.assertEqual(self.client.get(url).status_code,400)
    def test_hidden_and_unknown_product(self):
        self.assertEqual(self.client.get('/product/A').status_code,200)
        self.assertEqual(self.client.get('/api/products/X').status_code,404)
        self.repo.visible.remove('amazon:A')
        self.assertEqual(self.client.get('/api/products/A').status_code,404)
        self.assertEqual(self.client.get('/photo/A').status_code,404)
    def test_ui_has_no_points_or_toggle(self):
        home=self.client.get('/').text;detail=self.client.get('/product/A').text
        for marker in ['show-scores','search-details','mock-data.js']:self.assertNotIn(marker,home)
        for marker in ['context-score','detail-context','Rank #']:self.assertNotIn(marker,detail)
        self.assertIn('discover-link',detail)
    def test_voice_status_and_lock(self):
        self.assertEqual(self.client.post('/api/voice').status_code,503)
        self.services.speech=SpeechService(SimpleNamespace(transcribe=lambda content:{'text':'giày màu đen'}))
        self.assertEqual(self.client.post('/api/voice',data={'audio':(io.BytesIO(b'a'),'audio')}).json['text'],'giày màu đen')
        self.services.voice_lock.acquire()
        try:self.assertEqual(self.client.post('/api/voice',data={'audio':(io.BytesIO(b'a'),'audio')}).status_code,429)
        finally:self.services.voice_lock.release()
        self.assertEqual(self.client.post('/api/voice',data={'audio':[(io.BytesIO(b'a'),'a'),(io.BytesIO(b'b'),'b')]}).status_code,400)
    def test_large_payload_and_photo_traversal(self):
        self.assertEqual(self.client.post('/api/search',data='x'*17000,content_type='application/json').status_code,413)
        self.assertEqual(self.client.get('/photo/..').status_code,404)
    def test_webp_mime_without_windows_registry_entry(self):
        path=ROOT/'data/images/B0007XTKKG.webp'
        with patch.object(self.repo,'photo',return_value=path),patch('mimetypes.guess_type',return_value=(None,None)):
            response=self.client.get('/photo/B0007XTKKG')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content_type,'image/webp')
            self.assertEqual(response.data,path.read_bytes())
            response.close()

if __name__=='__main__':unittest.main()
