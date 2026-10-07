import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from application.intelligence.image_search import open_image,ImageSearchEngine,ImageIndex,MAX_IMAGE_BYTES
import application.intelligence.image_search as image_module
import hashlib
from contextlib import closing

def picture(color='red',fmt='PNG',size=(64,64)):
    output=io.BytesIO();Image.new('RGB',size,color).save(output,format=fmt);return output.getvalue()

class ImageInputTests(unittest.TestCase):
    def test_bad_empty_tiny_animated_oversized(self):
        for content in [b'',b'not image',picture(size=(4,4)),picture(fmt='GIF'),b'x'*(MAX_IMAGE_BYTES+1)]:
            with self.assertRaises(ValueError):open_image(content)
    def test_transparency_is_composited_and_exif_rotation(self):
        output=io.BytesIO();Image.new('RGBA',(32,64),(255,0,0,0)).save(output,format='PNG')
        image=open_image(output.getvalue());self.assertEqual(image.getpixel((0,0)),(255,255,255))
        original=Image.new('RGB',(32,64),'red');exif=original.getexif();exif[274]=6
        output=io.BytesIO();original.save(output,format='JPEG',exif=exif)
        self.assertEqual(open_image(output.getvalue()).size,(64,32))

class ImageRankingTests(unittest.TestCase):
    def setUp(self):
        self.engine=object.__new__(ImageSearchEngine)
        class Encoder:
            alias='dino'
            def encode(self,images):return np.asarray([[1,0]],dtype=np.float32)
        self.engine.encoder=Encoder();self.engine.ids=['A','B','C'];self.engine.vectors=np.asarray([[1,0],[.8,.6],[1,0]],dtype=np.float32)
        self.engine.active_ids={'A','B'}
        self.engine.products={'A':{'display':{'price':{'amount':900000,'currency':'VND'}}},'B':{'display':{'price':{'amount':400000,'currency':'VND'}}},'C':{}}
    def test_visibility_and_price_before_topk(self):
        result=self.engine.search(picture());self.assertEqual([r['product_id'] for r in result['results']],['A','B'])
        result=self.engine.search(picture(),max_price_vnd=500000)
        self.assertEqual([r['product_id'] for r in result['results']],['B'])
        self.assertEqual(self.engine.search(picture(),max_price_vnd=100000)['results'],[])
    def test_invalid_price_and_topk(self):
        for maximum in [-1,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):self.engine.search(picture(),max_price_vnd=maximum)
        for k in [0,True,21]:
            with self.assertRaises(ValueError):self.engine.search(picture(),top_k=k)

