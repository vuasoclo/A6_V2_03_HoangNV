"""Replaceable local image and composed retrieval adapters."""
from .intelligence.multimodal import MultimodalSearch

class ImageService:
    def __init__(self, text_engine, image_engine, composed_engine):
        self.engine=MultimodalSearch(text_engine,image_engine,composed_engine)
        self.available=image_engine is not None
        self.composed_available=composed_engine is not None

    def search(self, content, query, filters, top_k):
        return self.engine.search(content,query=query,filters=filters,top_k=top_k)
