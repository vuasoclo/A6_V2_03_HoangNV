"""Conservative, reproducible title-based demo groups; not Amazon category labels."""
import re
from .common import digest
GROUPS=[('accessories','Phụ kiện giày',r'\b(?:insoles?|inserts?|shoelaces?|shoe laces?|shoe covers?|boot covers?|shoe trees?|shoe bags?|shoe polish|shoe cleaner|shoe rack|socks?|replacement soles?)\b'),
 ('boots','Bốt',r'\b(?:boots?|booties|bootie)\b'),
 ('slippers','Dép đi trong nhà',r'\bslippers?\b'),
 ('sandals','Sandal / dép',r'\b(?:sandals?|flip[- ]flops?|slides?)\b'),
 ('loafers','Giày lười',r'\b(?:loafers?|moccasins?|slip[- ]ons?)\b'),
 ('sneakers','Giày thể thao',r'\b(?:sneakers?|running shoes?|walking shoes?|athletic|trainers?|tennis shoes?|basketball shoes?|cross[- ]training)\b'),
 ('dress','Giày tây / giày cao gót',r'\b(?:oxfords?|brogues?|wingtips?|wing tips?|dress shoes?|pumps?|high heels?)\b'),
 ('other_shoes','Giày khác',r'\b(?:shoes?|clogs?|footwear|espadrilles?)\b')]
CATEGORIES=[{'id':'demo.'+key,'name_vi':label} for key,label,_ in GROUPS]+[{'id':'demo.unknown','name_vi':'Chưa phân loại'}]
RULE_HASH=digest(GROUPS)
def classify(name):
    for key,label,pattern in GROUPS:
        match=re.search(pattern,name,re.I)
        if match:return {'category_id':'demo.'+key,'source_field':'name','evidence':match.group(),'method':'title_rules_v1'}
    return {'category_id':'demo.unknown','source_field':'name','evidence':None,'method':'title_rules_v1'}
