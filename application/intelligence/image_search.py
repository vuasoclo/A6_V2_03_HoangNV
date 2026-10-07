"""Independent image encoders and image index; never changes semantic text vectors."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import time
import warnings
from contextlib import closing
import numpy as np
from PIL import Image,ImageOps,UnidentifiedImageError
from .common import ROOT,read_json,digest

MAX_IMAGE_BYTES=5*1024*1024
MAX_PIXELS=16_000_000
ALIASES={'dino':'DINOv2-small','siglip':'SigLIP2-base','clip':'CLIP-ViT-B32'}

def open_image(content):
    if not content:raise ValueError('Ảnh trống. Hãy chọn hoặc paste một ảnh.')
    if len(content)>MAX_IMAGE_BYTES:raise ValueError('Ảnh quá lớn (tối đa 5 MB).')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as original:
                if original.format not in {'JPEG','PNG','WEBP','BMP'}:
                    raise ValueError('Dùng ảnh JPG, PNG, WebP hoặc BMP; không hỗ trợ SVG/GIF/ảnh động.')
                if getattr(original,'n_frames',1)>1:raise ValueError('Chỉ dùng một ảnh tĩnh.')
                if original.width*original.height>MAX_PIXELS:raise ValueError('Ảnh vượt quá 16 triệu pixel.')
                if min(original.size)<16:raise ValueError('Ảnh quá nhỏ (mỗi chiều tối thiểu 16 pixel).')
                original.load();image=ImageOps.exif_transpose(original)
                if 'A' in image.getbands() or 'transparency' in image.info:
                    rgba=image.convert('RGBA');canvas=Image.new('RGBA',rgba.size,'white')
                    canvas.alpha_composite(rgba);return canvas.convert('RGB')
                return image.convert('RGB')
    except ValueError:raise
    except (OSError,UnidentifiedImageError,Image.DecompressionBombWarning,Image.DecompressionBombError) as exc:
        raise ValueError('Không đọc được ảnh. Hãy chọn lại file ảnh hợp lệ.') from exc

class ImageEncoder:
    def __init__(self,alias='dino',threads=4,batch_size=8):
        if alias not in ALIASES:raise ValueError('Model ảnh chưa đăng ký.')
        import torch
        from transformers import AutoImageProcessor,Dinov2Model,SiglipVisionModel,CLIPVisionModelWithProjection
        path=ROOT/f'models/image-{alias}';manifest=read_json(path/'manifest.json')
        # Validate the pinned files once at load time.
        for name,info in manifest['files'].items():
            if name=='README.md':continue
            file=path/name;checksum=hashlib.sha256()
            with file.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):checksum.update(block)
            if file.stat().st_size!=info['bytes'] or checksum.hexdigest()!=info['sha256']:
                raise ValueError('File model ảnh đã thay đổi: '+name)
        torch.set_num_threads(threads)
        self.processor=AutoImageProcessor.from_pretrained(str(path),local_files_only=True,trust_remote_code=False,use_fast=False)
        cls={'dino':Dinov2Model,'siglip':SiglipVisionModel,'clip':CLIPVisionModelWithProjection}[alias]
        self.model=cls.from_pretrained(str(path),local_files_only=True,trust_remote_code=False,
                                      use_safetensors=manifest['weights'].endswith('.safetensors')).to('cpu').float().eval()
        self.torch=torch;self.alias=alias;self.batch_size=batch_size
        self.dimension={'dino':384,'siglip':768,'clip':512}[alias]
        self.config={'alias':alias,'repo':manifest['repo'],'revision':manifest['revision'],
                     'files':manifest['files'],'pooling':{'dino':'cls','siglip':'pooler','clip':'projected'}[alias],
                     'dtype':'float32','normalization':'l2','processor':self.processor.to_dict()}
        self.fingerprint=digest(self.config)

    def encode(self,images):
        vectors=[]
        for start in range(0,len(images),self.batch_size):
            inputs=self.processor(images=images[start:start+self.batch_size],return_tensors='pt')
            with self.torch.inference_mode():
                output=self.model(**inputs)
                vector=output.last_hidden_state[:,0] if self.alias=='dino' else output.pooler_output if self.alias=='siglip' else output.image_embeds
                vector=self.torch.nn.functional.normalize(vector,p=2,dim=-1)
            vectors.append(vector.cpu().numpy().astype(np.float32))
        return np.concatenate(vectors) if vectors else np.empty((0,self.dimension),dtype=np.float32)

from data.image_index import ImageIndex
from data.image_storage import catalog_images

class ImageSearchEngine:
    def __init__(self,products,active_ids,alias='dino'):
        self.encoder=ImageEncoder(alias);self.rows=catalog_images()
        self.ids,self.vectors=ImageIndex().load(self.encoder,self.rows)
        self.products=products;self.active_ids=set(active_ids)
    def scores(self,content,filters=None):
        from .retrieval import validate_filters,matches_filters
        filters=validate_filters(filters)
        image=open_image(content)
        indices=[i for i,pid in enumerate(self.ids) if pid in self.active_ids and matches_filters(self.products[pid],filters)]
        if not indices:return {}
        vector=self.encoder.encode([image])[0];scores=self.vectors[indices]@vector
        return {self.ids[i]:float(score) for i,score in zip(indices,scores)}
    def search(self,content,top_k=5,max_price_vnd=None,filters=None):
        if type(top_k) is not int or not 1<=top_k<=20:raise ValueError('Top K phải từ 1 đến 20.')
        if max_price_vnd is not None and (type(max_price_vnd) not in {int,float} or not np.isfinite(max_price_vnd) or not 0<=max_price_vnd<=10**12):raise ValueError('Giá tối đa không hợp lệ.')
        started=time.perf_counter();filters=dict(filters or {})
        if max_price_vnd is not None:filters['max_price_vnd']=min(filters.get('max_price_vnd',max_price_vnd),max_price_vnd)
        scores=self.scores(content,filters)
        ranked=sorted(scores,key=lambda pid:(-scores[pid],pid))[:top_k]
        return {'mode':'image','model':ALIASES[self.encoder.alias],'status':'ok' if ranked else 'no_match',
                'elapsed_ms':(time.perf_counter()-started)*1000,'score_is_probability':False,
                'results':[{'product_id':pid,'score':scores[pid],'cosine_score':scores[pid],'image_cosine_score':scores[pid],'lexical_score':None} for pid in ranked],
                'reason':None if ranked else 'Không có sản phẩm có ảnh phù hợp bộ lọc giá.',
                'filters':filters,'price_basis':'display_vnd_including_demo' if any(k.endswith('_vnd') for k in filters) else None}
