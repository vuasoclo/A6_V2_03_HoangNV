"""Application facade shared by web presentation and CLI demo."""
import threading, time
from .query_service import ui_filters,validate_sort
from .ranking_service import rank_results

class SearchService:
    def __init__(self, engine, repository, image_service, speech_service, config):
        self.engine=engine;self.repository=repository;self.image=image_service;self.speech=speech_service;self.config=config
        self.search_lock=threading.Lock();self.voice_lock=threading.Lock()

    def search(self, query, filters=None, sort='relevance', top_k=20, content=None):
        filters=ui_filters(filters);validate_sort(sort)
        if not isinstance(query,str) or len(query)>500:raise ValueError('Truy vấn tối đa 500 ký tự.')
        started=time.perf_counter()
        with self.search_lock:
            result=self.image.search(content,query,filters,top_k) if content is not None else self.engine.search(query,mode='semantic',top_k=top_k,filters=filters)
        result=rank_results(result,self.repository.products,sort)
        result['elapsed_ms']=round((time.perf_counter()-started)*1000,1)
        return result

    def health(self):
        return {'status':'ready','products':len(self.repository.visible),'source_products':len(self.repository.products),
                'model':self.config['model'],'bilingual_search':self.config.get('bilingual_search',False),'device':'cpu',
                'image_search_available':self.image.available,'composed_available':self.image.composed_available,
                'voice_available':self.speech.available,'groups':self.repository.groups()}
