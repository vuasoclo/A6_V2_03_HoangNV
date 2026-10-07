import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from application.intelligence.composed import instruction,primary_color,ComposedSearch
from application.intelligence.multimodal import MultimodalSearch

class InstructionTests(unittest.TestCase):
    def test_vietnamese_colors_and_relative_template(self):
        for text in ['đen','den','màu đen','đổi sang đen','giống đôi này nhưng màu đen','giống ảnh này nhưng màu đen']:
            self.assertEqual(instruction(text)[0],'is black')
            self.assertEqual(instruction(text)[1]['color'],'black')
        self.assertEqual(instruction('same shape but black')[1]['color'],'black')
        self.assertEqual(instruction('is black instead of blue')[1]['color'],'black')
        self.assertIsNone(instruction('is not black')[1]['color'])
        with self.assertRaises(ValueError):instruction('giống đôi này nhưng có dây buộc')
    def test_source_primary_color_not_description_keyword(self):
        self.assertEqual(primary_color({'attributes':{'color':'Black/Dots'}}),'black')
        self.assertEqual(primary_color({'attributes':{'color':'Blue/Black'}}),'blue')
        self.assertIsNone(primary_color({'attributes':{},'description':'black shoes'}))

class ComposedRankingTests(unittest.TestCase):
    def setUp(self):
        self.engine=object.__new__(ComposedSearch)
        self.engine.encoder=SimpleNamespace(encode=lambda content,caption:(np.asarray([1,0],dtype=np.float32),'a photo of $ that '+caption))
        self.engine.ids=['reference','target','unknown'];self.engine.vectors=np.asarray([[1,0],[.9,.1],[.8,.2]],dtype=np.float32)
        self.engine.active_ids=set(self.engine.ids)
        self.engine.products={'reference':{'category_id':'esci.candidates','attributes':{'color':'Orange/Blue'}},
            'target':{'category_id':'esci.candidates','search_category_id':'demo.loafers','attributes':{'color':'Black/Dots'},'display':{'price':{'amount':710000,'currency':'VND'}}},
            'unknown':{'category_id':'esci.candidates','attributes':{}}}
    def test_model_ranks_but_explicit_color_enforces_metadata(self):
        result=self.engine.search(b'photo','den')
        self.assertEqual([r['product_id'] for r in result['results']],['target'])
        self.assertEqual(self.engine.search(b'photo','is black',apply_color_constraint=False)['results'][0]['product_id'],'reference')
        self.assertEqual(self.engine.search(b'photo','den',filters={'max_price_vnd':700000})['results'],[])
        self.assertEqual(self.engine.search(b'photo','den',filters={'category_id':'demo.sneakers'})['results'],[])
    def test_dispatch_does_not_call_e5_or_siglip_when_composed(self):
        image=SimpleNamespace(search=lambda *a,**k:{'mode':'image','results':[]})
        route=MultimodalSearch(SimpleNamespace(),image,self.engine)
        result=route.search(b'photo','đen dưới 800k')
        self.assertEqual(result['mode'],'composed')
        self.assertTrue(result['price_clauses']);self.assertEqual(result['results'][0]['product_id'],'target')
        self.assertEqual(route.search(b'photo','dưới 800k')['mode'],'image')
    def test_invalid_inputs(self):
        for query in [None,'\x00','!','']:
            with self.assertRaises(ValueError):self.engine.search(b'photo',query)
        with self.assertRaises(ValueError):self.engine.search(b'photo','black',top_k=True)
