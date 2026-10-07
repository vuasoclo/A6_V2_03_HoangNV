"""Late score fusion of aligned product IDs, never addition of incompatible vectors."""
import time
import math
import numpy as np
from .retrieval import validate_filters
from .price_query import parse_price_query

def scaled(scores):
    low=min(scores.values());high=max(scores.values())
    return {pid:(value-low)/(high-low) if high-low>1e-8 else .5 for pid,value in scores.items()}

class MultimodalSearch:
    def __init__(self,text_engine,image_engine,composed_engine=None):
        self.text=text_engine;self.image=image_engine;self.composed=composed_engine
    def search(self,content,query='',filters=None,image_weight=.5,top_k=5):
        started=time.perf_counter()
        if not isinstance(query,str) or len(query)>2000 or any(ord(c)<32 and c not in '\t\n\r' for c in query):raise ValueError('Truy vấn không hợp lệ.')
        if type(image_weight) not in {int,float} or not math.isfinite(image_weight) or not 0<=image_weight<=1:raise ValueError('Trọng số ảnh phải từ 0 đến 1.')
        if type(top_k) is not int or not 1<=top_k<=20:raise ValueError('Top K phải từ 1 đến 20.')
        filters=validate_filters(filters)
        cleaned,filters,clauses=parse_price_query(query,filters) if query.strip() else ('',filters,[])
        filters=validate_filters(filters)
        if cleaned.strip() and self.composed is not None:
            result=self.composed.search(content,cleaned,filters=filters,top_k=top_k)
            result.update(query=query,semantic_query=cleaned,filters=filters,price_clauses=clauses,
                elapsed_ms=(time.perf_counter()-started)*1000,
                price_basis='display_vnd_including_demo' if any(k.endswith('_vnd') for k in filters) else None)
            return result
        if not cleaned.strip():
            result=self.image.search(content,top_k=top_k,filters=filters)
        else:
            if not any(c.isalnum() for c in cleaned):raise ValueError('Hãy nhập nhu cầu tìm kiếm bằng chữ.')
            image_scores=self.image.scores(content,filters)
            vector=self.text.encoder.encode([cleaned.strip()],'query')[0]
            scores=self.text.vectors@vector
            for view in self.text.dense_views.values():scores=np.maximum(scores,view@vector)
            text_scores={pid:float(score) for pid,score in zip(self.text.ids,scores) if pid in image_scores and pid in self.text.active_product_ids}
            image_scores={pid:image_scores[pid] for pid in text_scores}
            if text_scores:
                t=scaled(text_scores);i=scaled(image_scores)
                fused={pid:(1-image_weight)*t[pid]+image_weight*i[pid] for pid in t}
                ids=sorted(fused,key=lambda pid:(-fused[pid],pid))[:top_k]
                results=[{'product_id':pid,'score':fused[pid],'cosine_score':text_scores[pid],'lexical_score':None,
                          'text_cosine_score':text_scores[pid],'image_cosine_score':image_scores[pid],
                          'text_normalized_score':t[pid],'image_normalized_score':i[pid]} for pid in ids]
            else:results=[]
            result={'mode':'multimodal','status':'ok' if results else 'no_match','results':results,
                    'reason':None if results else 'Không có sản phẩm có ảnh phù hợp bộ lọc.',
                    'fusion':{'method':'weighted_minmax_scores','image_weight':image_weight,'text_weight':1-image_weight,
                              'normalization':'min-max over the same eligible image catalog; constant signal = 0.5'},
                    'score_is_probability':False}
        result.update(query=query,semantic_query=cleaned,filters=filters,price_clauses=clauses,
                      elapsed_ms=(time.perf_counter()-started)*1000,
                      price_basis='display_vnd_including_demo' if any(k.endswith('_vnd') for k in filters) else None)
        result['processing']=['Đọc và chuẩn hóa ảnh','Lọc category và giá trước xếp hạng',
                              'Encode ảnh bằng SigLIP2']+(['Encode chữ bằng E5 Việt/Anh','Chuẩn hóa hai điểm và fusion','Chọn Top K'] if cleaned.strip() else ['Cosine ảnh và chọn Top K'])
        return result
