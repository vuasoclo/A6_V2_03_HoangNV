import tempfile
from pathlib import Path
import unittest
from application.intelligence.price_query import parse_price_query
from data.vector_index import SQLiteIndex
from application.intelligence.retrieval import SearchEngine
from fixtures import FakeEncoder,product


class PriceQueryTests(unittest.TestCase):
    def test_spoken_and_regional_variants(self):
        cases=[
            ('giày dưới 8 trăm k',None,799999),
            ('giày dưới 8 trăm',None,799999),
            ('giày dưới tám trăm',None,799999),
            ('giày tám trăm đổ lại',None,800000),
            ('giày dưới năm chục',None,49999),
            ('giày dưới tám trăm nghìn',None,799999),
            ('giày hông quá tám trăm ngàn',None,800000),
            ('giày hổng mắc hơn tám trăm ngàn',None,800000),
            ('giày dưới tám trăm nghèn',None,799999),
            ('giày dưới 800 nghèn',None,799999),
            ('giày ko quá tám trăm ngàn',None,800000),
            ('giày khum quá tám trăm ngàn',None,800000),
            ('giày chưa tới một triệu rưỡi',None,1499999),
            ('giày dưới triệu rưỡi',None,1499999),
            ('giày dưới 1 triệu 500 nghìn',None,1499999),
            ('giày dưới một trăm rưỡi nghìn',None,149999),
            ('giày dưới hai chục ngàn',None,19999),
            ('giày dưới hai trăm linh năm ngàn',None,204999),
            ('giày dưới hai trăm lẻ năm ngàn',None,204999),
            ('giày dưới hai mươi tư ngàn',None,23999),
            ('giày dưới hai mươi lăm ngàn',None,24999),
            ('giày dưới hai mươi nhăm ngàn',None,24999),
            ('giày 800k đổ lại',None,800000),
            ('giày một triệu trở xuống',None,1000000),
            ('giày từ 800k trở lên',800000,None),
            ('giày ngân sách tám trăm nghìn',None,800000),
            ('giày từ ba trăm ngàn tới một triệu hai trăm ngàn',300000,1200000),
            ('shoes under eight hundred thousand VND',None,799999),
            ('shoes under one hundred and fifty thousand VND',None,149999),
            ('shoes under half a million VND',None,499999),
            ('shoes under one and a half million VND',None,1499999),
            ('shoes budget five hundred thousand VND',None,500000),
            ('shoes between three hundred thousand and eight hundred thousand VND',300000,800000),
        ]
        for query,minimum,maximum in cases:
            with self.subTest(query=query):
                cleaned,filters,clauses=parse_price_query(query,{})
                self.assertEqual(filters.get('min_price_vnd'),minimum)
                self.assertEqual(filters.get('max_price_vnd'),maximum)
                self.assertEqual(cleaned,'shoes' if query.startswith('shoes') else 'giày')
                self.assertTrue(all(c['text'] in query for c in clauses))

    def test_ambiguous_price_is_not_ignored(self):
        for query in ['giày dưới một triệu hai','giày tầm tám trăm ngàn',
                      'shoes between three hundred and eight hundred thousand VND','shoes under 800kxyz']:
            with self.subTest(query=query),self.assertRaises(ValueError):parse_price_query(query,{})
        self.assertEqual(parse_price_query('Nike size 10 M under 500k',{})[0],'Nike size 10 M')
        self.assertEqual(parse_price_query('black and white shoes under 500k',{})[0],'black and white shoes')
        self.assertEqual(parse_price_query('shoes for kids under 5 years',{}),('shoes for kids under 5 years',{},[]))
        _,_,clauses=parse_price_query('giày dưới 8 trăm',{})
        self.assertEqual(clauses[0]['assumptions'][0]['amount_vnd'],800000)

    def test_vietnamese_and_english_units(self):
        for query,minimum,maximum in [
            ('giày dưới 500k',None,499999),
            ('shoes under 500,000 VND',None,499999),
            ('giày không quá 1,5 triệu',None,1500000),
            ('shoes at least 1.2m VND',1200000,None),
            ('shoes above 1.000.000 đồng',1000001,None),
            ('giày từ 300 nghìn đến 1 triệu',300000,1000000),
            ('shoes between 300 and 500k',300000,500000),
            ('shoes from 300000 VND to 1 million VND',300000,1000000),
            ('giày không dưới 500 ngàn',500000,None),
            ('shoes no more than 500 thousand',None,500000),
        ]:
            with self.subTest(query=query):
                cleaned,filters,clauses=parse_price_query(query,{})
                self.assertEqual(filters.get('min_price_vnd'),minimum)
                self.assertEqual(filters.get('max_price_vnd'),maximum)
                self.assertTrue(clauses)
                self.assertNotIn('500',cleaned)

    def test_non_price_numbers_remain(self):
        for query in ['Nike Kyrie 6 size 10 US','shoes from 2019 to 2020','model under 10']:
            self.assertEqual(parse_price_query(query,{}),(query,{},[]))

    def test_contradictions_and_unsupported_currency(self):
        for query in ['shoes under 300k and above 500k','giày từ 1 triệu đến 500k',
                      'shoes under twenty dollars','shoes under $20','giày dưới -500k',
                      'shoes not below 500k','giày dưới 0 đồng',
                      'shoes under 300k or above 500k']:
            with self.subTest(query=query),self.assertRaises(ValueError):
                parse_price_query(query,{})
        with self.assertRaises(ValueError):
            parse_price_query('shoes above 500k',{'max_price_vnd':400000})
        _,filters,_=parse_price_query('shoes under 500k',{'max_price_vnd':300000})
        self.assertEqual(filters['max_price_vnd'],300000)

    def test_filter_before_ranking_and_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            products=[product('A'),product('B'),product('C'),product('D')]
            for p,amount in zip(products,[499999,500000,700000,None]):
                if amount is not None:
                    p['display']={'price':{'amount':amount,'currency':'VND','kind':'synthetic_demo'}}
            docs={p['id']:'running mesh' for p in products}
            encoder=FakeEncoder();index=SQLiteIndex(Path(folder)/'index.sqlite3')
            index.sync('test',products,docs,encoder)
            engine=SearchEngine(products,docs,encoder,index,'test',scope_policy=False,
                                inventory_policy=False,price_query_policy=True)
            for mode in ['semantic','hybrid','bm25','keyword_v1']:
                result=engine.search('running under 500k',mode=mode)
                self.assertEqual([i['product_id'] for i in result['results']],['amazon:A'])
                self.assertEqual(result['semantic_query'],'running')
            self.assertEqual([i['product_id'] for i in engine.search('running at most 500k')['results']],['amazon:A','amazon:B'])
            only_price=engine.search('từ 500k đến 800k')
            self.assertEqual([i['product_id'] for i in only_price['results']],['amazon:B','amazon:C'])
            self.assertEqual(only_price['ranking_basis'],'price_ascending')
            self.assertEqual(engine.search('running under 10k')['status'],'no_match')
            self.assertEqual(engine.search('running',mode='semantic',apply_policy=False)['results'][0]['product_id'],'amazon:A')


if __name__=='__main__':unittest.main()
