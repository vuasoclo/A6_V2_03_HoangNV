"""Composition root. Startup loads validated prepared indexes; never re-embeds data."""
from application.intelligence.common import ROOT,read_json
from application.intelligence.esci import create_esci_engine
from application.intelligence.image_search import ImageSearchEngine
from application.intelligence.composed import ComposedSearch
from application.intelligence.voice import PhoWhisperTranscriber
from application.image_service import ImageService
from application.speech_service import SpeechService
from application.search_service import SearchService
from data.product_repository import ProductRepository

def build_services():
    config=read_json(ROOT/'config/runtime.json')
    engine,_=create_esci_engine(config)
    repository=ProductRepository(engine)
    image_config=read_json(ROOT/'config/image.json');composed_config=read_json(ROOT/'config/composed.json');voice_config=read_json(ROOT/'config/voice.json')
    image=ImageSearchEngine(engine.products,engine.active_product_ids,image_config['model']) if image_config['enabled'] else None
    composed=ComposedSearch(engine.products,engine.active_product_ids) if image and composed_config['enabled'] else None
    voice=PhoWhisperTranscriber(voice_config['compute_type'],voice_config.get('threads',4)) if voice_config['enabled'] else None
    return SearchService(engine,repository,ImageService(engine,image,composed),SpeechService(voice),config)
