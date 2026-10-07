import numpy as np

class FakeEncoder:
    fingerprint,dimension='test-model-v1',4
    config={'model':'test'}
    def __init__(self):self.encoded=[]
    def fit_document(self,text):return text,{'omitted_segments':0,'encoded_tokens':len(text.split())}
    def encode(self,texts,role='passage'):
        self.encoded.extend(texts)
        vectors=[]
        for text in texts:
            vector=np.asarray([1+text.count('running'),1+text.count('leather'),1+text.count('waterproof'),1+text.count('pivot')],dtype=np.float32)
            vectors.append(vector/np.linalg.norm(vector))
        return np.stack(vectors) if vectors else np.empty((0,4),dtype=np.float32)

def product(pid='A',category='running',price=30,material='leather'):
    return {'id':'amazon:'+pid,'source_id':pid,'name':'Example '+category+' shoe','category_id':'shoes.'+category,
            'category_path':['fashion','shoes',category],'brand':None,'attributes':{'material':material,'manufacturer':'Factory'},
            'price':{'amount':price,'currency':'USD','kind':'historical_source'},'stock':None,'variants':[],
            'images':[],'features':['Useful source feature'],'semantic_document':{'text':'running leather waterproof'}}
