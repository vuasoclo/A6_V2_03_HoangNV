"""SEARLE (ICCV 2023), pretrained B/32 textual inversion, adapted to HF CLIP.

Architecture and token replacement follow miccunifi/SEARLE, pinned in models/searle-b32.
Authors: Baldrati, Agnolucci, Bertini, Del Bimbo. CC-BY-NC-4.0; academic demo.
No runtime torch.hub execution, downloads, training or translation API.
"""
import hashlib
import time
import re
import unicodedata
import numpy as np
from .common import ROOT,read_json
from .image_search import ImageEncoder,ImageIndex,catalog_images,open_image
from .retrieval import validate_filters,matches_filters

COLORS={'den':'black','trang':'white','do':'red','xanh duong':'blue','xanh lam':'blue',
        'xanh la cay':'green','xanh la':'green','vang':'yellow','nau':'brown','tim':'purple','hong':'pink','xam':'gray','cam':'orange',
        'black':'black','white':'white','red':'red','blue':'blue','green':'green','yellow':'yellow','brown':'brown','purple':'purple','pink':'pink','gray':'gray','grey':'gray','orange':'orange'}
def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower().replace('đ','d')) if unicodedata.category(c)!='Mn')
def instruction(text):
    original=text.strip();value=fold(original)
    # Explicit finite Vietnamese templates; never claim general-purpose translation.
    color_pattern='|'.join(re.escape(k) for k in sorted(COLORS,key=len,reverse=True))
    match=re.fullmatch(r'(?:giong (?:doi|kieu|mau|anh)?\s*(?:giay)?\s*nay\s*(?:nhung|ma)?\s*|doi\s*(?:sang|thanh)?\s*|chuyen\s*(?:sang|thanh)?\s*)?(?:mau\s*)?('+color_pattern+r')',value)
    if match:return 'is '+COLORS[match.group(1)],{'method':'explicit_color_template','color':COLORS[match.group(1)]}
    # English modification is passed to the pretrained CLIP text encoder unchanged.
    if re.search(r'[à-ỹđ]',original.lower()) or any(re.search(r'\b'+k+r'\b',value) for k in ['nhung','giong','doi','mau','giay']):
        raise ValueError('CIR hiện hiểu chỉ dẫn đổi màu Việt như “giống đôi này nhưng màu đen”. Với thay đổi khác, hãy dùng tiếng Anh.')
    color_match=re.search(r'\b(?:is|but(?: is)?|in|colour|color|make it|change (?:it )?to|turn (?:it )?to)\s+(?:the colour |the color |colored |coloured )?('+color_pattern+r')\b',value)
    return original,{'method':'english_passthrough','color':COLORS[color_match.group(1)] if color_match else None}

def primary_color(product):
    value=product.get('attributes',{}).get('color')
    if not isinstance(value,str):return None
    match=re.search(r'\b(black|white|red|blue|green|yellow|brown|purple|pink|gray|grey|orange)\b',value,re.I)
    return COLORS[match.group(1).lower()] if match else None

class SEARLEEncoder:
    def __init__(self):
        import torch
        from transformers import CLIPTextModelWithProjection,CLIPTokenizer
        self.torch=torch;self.vision=ImageEncoder('clip')
        self.text=CLIPTextModelWithProjection.from_pretrained(str(ROOT/'models/image-clip'),local_files_only=True,
            use_safetensors=False,attn_implementation='eager').float().eval()
        self.tokenizer=CLIPTokenizer.from_pretrained(str(ROOT/'models/image-clip'),local_files_only=True)
        folder=ROOT/'models/searle-b32';manifest=read_json(folder/'manifest.json')
        for name,sha in manifest.get('tokenizer_files',{}).items():
            if hashlib.sha256((ROOT/'models/image-clip'/name).read_bytes()).hexdigest()!=sha:raise ValueError('CIR tokenizer changed.')
        path=folder/'SEARLE_ViT-B32.pt'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['files'][path.name]['sha256']:raise ValueError('SEARLE checkpoint changed.')
        self.phi=torch.nn.Sequential(torch.nn.Linear(512,2048),torch.nn.GELU(),torch.nn.Dropout(.5),
            torch.nn.Linear(2048,2048),torch.nn.GELU(),torch.nn.Dropout(.5),torch.nn.Linear(2048,512)).eval()
        saved=torch.load(path,map_location='cpu',weights_only=True)['Phi']
        self.phi.load_state_dict({k.removeprefix('layers.'):v for k,v in saved.items()},strict=True)
        self.revision=manifest['revision'];self.checksum=manifest['files'][path.name]['sha256']
    def tokens(self,prompt):
        ids=self.tokenizer.encode(prompt,add_special_tokens=True)
        if len(ids)>77:raise ValueError('Chỉ dẫn CIR quá dài (CLIP tối đa 77 token gồm prompt).')
        return self.torch.tensor([ids+[0]*(77-len(ids))],dtype=self.torch.long)
    def text_features(self,ids,pseudo=None):
        from transformers.modeling_attn_mask_utils import _create_4d_causal_attention_mask
        model=self.text.text_model;token=model.embeddings.token_embedding(ids)
        if pseudo is not None:
            positions=(ids==259).nonzero()
            if len(positions)!=ids.shape[0]:raise ValueError('Prompt phải có đúng một token ảnh $.')
            token[positions[:,0],positions[:,1]]=pseudo
        hidden=model.embeddings(inputs_embeds=token)
        mask=_create_4d_causal_attention_mask(ids.shape,hidden.dtype,device=hidden.device)
        hidden=model.encoder(inputs_embeds=hidden,causal_attention_mask=mask).last_hidden_state
        hidden=model.final_layer_norm(hidden)
        pooled=hidden[self.torch.arange(len(ids)),ids.argmax(dim=-1)]
        return self.text.text_projection(pooled)
    def encode(self,content,caption):
        if '$' in caption:raise ValueError('Chỉ dẫn không được chứa ký hiệu $.')
        image=open_image(content);inputs=self.vision.processor(images=[image],return_tensors='pt')
        prompt='a photo of $ that '+caption;ids=self.tokens(prompt)
        with self.torch.inference_mode():
            raw=self.vision.model(**inputs).image_embeds  # Phi needs unnormalized CLIP features.
            pseudo=self.phi(raw)
            vector=self.text_features(ids,pseudo)
            vector=self.torch.nn.functional.normalize(vector,dim=-1)[0].numpy().astype(np.float32)
        return vector,prompt
    def verify_text_adapter(self):
        ids=self.tokens('a photo of a black shoe')
        with self.torch.inference_mode():
            actual=self.text_features(ids);reference=self.text(input_ids=ids).text_embeds
        error=float((actual-reference).abs().max())
        if error>1e-5:raise ValueError('HF text adaptation mismatch: '+str(error))
        dollar_ids=self.tokens('a photo of $ that is black')
        with self.torch.inference_mode():
            original=self.text.text_model.embeddings.token_embedding(dollar_ids)[dollar_ids==259]
            injected=self.text_features(dollar_ids,original)
            expected=self.text(input_ids=dollar_ids).text_embeds
        replacement_error=float((injected-expected).abs().max())
        if replacement_error>1e-5:raise ValueError('Token injection mismatch.')
        return max(error,replacement_error)

class ComposedSearch:
    def __init__(self,products,active_ids):
        self.encoder=SEARLEEncoder();self.rows=catalog_images()
        self.ids,self.vectors=ImageIndex().load(self.encoder.vision,self.rows)
        self.products=products;self.active_ids=active_ids
    def search(self,content,caption,filters=None,top_k=5,apply_color_constraint=True):
        started=time.perf_counter();filters=validate_filters(filters)
        if type(top_k) is not int or not 1<=top_k<=20:raise ValueError('Top K từ 1 đến 20.')
        if not isinstance(caption,str) or len(caption)>2000 or any(ord(c)<32 and c not in '\t\n\r' for c in caption):raise ValueError('Chỉ dẫn không hợp lệ.')
        caption,translation=instruction(caption)
        if not caption or not any(c.isalnum() for c in caption):raise ValueError('Nhập chỉ dẫn thay đổi sản phẩm.')
        vector,prompt=self.encoder.encode(content,caption)
        requested=translation['color'] if apply_color_constraint else None
        eligible=[i for i,pid in enumerate(self.ids) if pid in self.active_ids and matches_filters(self.products[pid],filters)
                  and (requested is None or primary_color(self.products[pid])==requested)]
        scores=self.vectors[eligible]@vector
        ranked=sorted(zip(eligible,scores),key=lambda p:(-float(p[1]),self.ids[p[0]]))[:top_k]
        return {'mode':'composed','model':'SEARLE-CLIP-ViT-B32','status':'ok' if ranked else 'no_match','score_is_probability':False,
            'elapsed_ms':(time.perf_counter()-started)*1000,'instruction':caption,'instruction_mapping':translation,'prompt':prompt,
            'attribute_constraints':{'primary_color':requested,'basis':'Python matches first recognized color in source attributes.color; unknown excluded'} if requested else {},
            'reason':None if ranked else 'Không có sản phẩm có ảnh phù hợp bộ lọc.',
            'results':[{'product_id':self.ids[i],'score':float(s),'cosine_score':float(s),'lexical_score':None} for i,s in ranked],
            'processing':['Lọc category, giá và màu yêu cầu nếu có','CLIP encode ảnh','SEARLE tạo token ảnh','Ghép token ảnh với chỉ dẫn thay đổi',
                          'CLIP text tạo vector CIR','Cosine với ảnh sản phẩm và chọn Top K']}
