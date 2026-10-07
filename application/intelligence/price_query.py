"""Deterministic VND comparisons; keep numerical constraints out of embeddings."""
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from .money_words import normalize_money_query

NUMBER = r'\d+(?:[.,]\d+)*'
UNIT = r'(?:trieu|million|nghin|ngan|nghen|thousand|vnd|dong|tr|k|m|d|₫)'
AMOUNT = rf'({NUMBER})\s*({UNIT})?(?:\s*(?:vnd|dong|d|₫))?(?![\w.,])'
RANGE = re.compile(rf'\b(?:tu|from|between)\s+{AMOUNT}\s*(?:den|toi|to|and|[-–])\s*{AMOUNT}', re.I)
COMPARISON = re.compile(rf'(?<!\w)(khong qua|khong vuot qua|toi da|it hon hoac bang|up to|at most|no more than|not over|less than or equal to|<=|duoi|it hon|under|below|less than|<|khong duoi|toi thieu|it nhat|at least|no less than|not under|>=|tren|hon|above|over|more than|>|tu|from)\s*{AMOUNT}', re.I)


def amount_vnd(number, unit):
    text = number
    if re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', text):
        text = text.replace(',','').replace('.','')
    elif text.count('.')+text.count(',') > 1:
        raise ValueError('Số tiền không rõ định dạng. Ví dụ: 500000 VND hoặc 1,5 triệu.')
    else:
        text = text.replace(',','.')
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError('Số tiền không hợp lệ.')
    unit = (unit or 'vnd').lower()
    scale = 1000000 if unit in ('trieu','tr','million','m') else 1000 if unit in ('k','nghin','ngan','nghen','thousand') else 1
    value *= scale
    if value != value.to_integral_value() or not 0 <= value <= 10**12:
        raise ValueError('Giá VND phải là số nguyên không âm, tối đa 1.000 tỷ.')
    return int(value)


def parse_price_query(query, filters):
    original = unicodedata.normalize('NFC',query)
    folded, mapping, assumptions = normalize_money_query(original)
    if re.search(r'\b(?:tam|khoang|co|quanh|around|about|approximately)\s+(?:\d|mot\b|hai\b|ba\b|bon\b|nam\b|sau\b|bay\b|tam\b|chin\b|one\b|two\b|three\b|four\b|five\b|six\b|seven\b|eight\b|nine\b)',folded) and re.search(r'\b(?:nghin|ngan|nghen|trieu|thousand|million|vnd)\b|\d\s*[km]\b',folded):
        raise ValueError('Giá khoảng/tầm chưa có cận rõ. Hãy dùng dưới, tối đa hoặc từ ... đến ...')
    if re.search(r'\b(?:duoi|tren|under|over|below|above|gia|price)\s*-\s*\d',folded):
        raise ValueError('Giá không thể âm.')
    conditions = list(RANGE.finditer(folded))
    conditions += [m for m in COMPARISON.finditer(folded) if not any(m.start()<r.end() and m.end()>r.start() for r in conditions)]
    # Explicit foreign-currency comparisons are not silently interpreted as VND.
    if re.search(r'\b(?:under|below|over|above|between|from|duoi|tren|gia|price|budget)\b',folded) and re.search(r'\$|\b(?:usd|dollars?|eur|euros?)\b',folded):
        raise ValueError('Bộ lọc này dùng VND. Hãy nhập ví dụ: under 500k VND hoặc dưới 500 nghìn.')
    bounds = dict(filters)
    clauses = []
    for match in sorted(conditions,key=lambda m:m.start()):
        if match.re is RANGE:
            n1,u1,n2,u2 = match.groups()
            if not (u1 or u2 or re.search(r'\b(?:gia|price|budget)\b',folded)):
                continue
            minimum, maximum = amount_vnd(n1,u1 or u2), amount_vnd(n2,u2 or u1)
            if minimum > maximum:
                raise ValueError('Khoảng giá có cận dưới lớn hơn cận trên.')
            new = {'min_price_vnd':minimum,'max_price_vnd':maximum}
        else:
            op,number,unit = match.groups()
            if not unit and not re.search(r'\b(?:gia|price|budget)\b',folded):
                continue
            # Do not accidentally invert an unrecognized negative expression.
            if re.search(r'\b(?:not|khong)\s*$',folded[:match.start()]):
                raise ValueError('Điều kiện giá phủ định chưa rõ. Hãy dùng tối đa / tối thiểu.')
            value = amount_vnd(number,unit)
            if op in ('duoi','it hon','under','below','less than','<'):
                new={'max_price_vnd':value-1}
            elif op in ('tren','hon','above','over','more than','>'):
                new={'min_price_vnd':value+1}
            elif op in ('khong duoi','toi thieu','it nhat','at least','no less than','not under','>=','tu','from'):
                new={'min_price_vnd':value}
            else:
                new={'max_price_vnd':value}
        for key,value in new.items():
            if key.startswith('min_'):
                bounds[key]=max(bounds.get(key,0),value)
            else:
                bounds[key]=min(bounds.get(key,10**12),value)
        span=(mapping[match.start()][0],mapping[match.end()-1][1])
        clauses.append({'text':original[span[0]:span[1]],'bounds':new,'span':span,
                        'assumptions':[{k:v for k,v in assumption.items() if k!='span'} for assumption in assumptions
                                       if span[0]<=assumption['span'][0] and assumption['span'][1]<=span[1]]})
        if re.match(rf'\s+{NUMBER}\s*{UNIT}\b',folded[match.end():]):
            raise ValueError('Số tiền chưa được đọc đầy đủ. Hãy nhập chữ số và đơn vị.')
    if len(clauses)>1 and re.search(r'\b(?:hoac|or)\b',folded):
        raise ValueError('Chưa hỗ trợ nhiều khoảng giá nối bằng hoặc/or. Hãy nhập một khoảng giá.')
    # Fail closed for recognizable but unreadable monetary constraints.
    covered=[m.span() for m in conditions if any((mapping[m.start()][0],mapping[m.end()-1][1])==c['span'] for c in clauses)]
    price_intent=re.compile(r'\b(?:duoi|tren|under|over|below|above|at most|at least|toi da|toi thieu|khong qua|khong duoi)\s+(?:\d[\d.,]*|(?:mot|hai|ba|bon|nam|sau|bay|tam|chin|one|two|three|four|five|six|seven|eight|nine|ten)\b)')
    for intent in price_intent.finditer(folded):
        if not any(start<=intent.start()<end for start,end in covered):
            tail=folded[intent.start():intent.start()+100]
            if re.search(r'\b(?:years?|months?|tuoi|size|us|eu|uk)\b',tail) and not re.search(r'\b(?:vnd|dong|nghin|ngan|trieu|million|thousand)\b',tail):
                continue
            if re.search(r'\b(?:tram|hundred|nghin|ngan|nghen|trieu|thousand|million|gia|price|budget)\b',tail) or not re.match(r'(?:under|over|below|above)\s+\d+\s*$',tail):
                raise ValueError('Chưa hiểu rõ điều kiện giá. Hãy ghi số tiền kèm đơn vị, ví dụ 800k hoặc tám trăm nghìn.')
    for intent in re.finditer(r'\b(?:tu|from|between)\s+(?:\d|mot\b|hai\b|ba\b|bon\b|nam\b|sau\b|bay\b|tam\b|chin\b|one\b|two\b|three\b|four\b|five\b|six\b|seven\b|eight\b|nine\b)',folded):
        if not any(start<=intent.start()<end for start,end in covered) and re.search(r'\b(?:nghin|ngan|nghen|trieu|thousand|million|vnd)\b|\d\s*[km]\b',folded[intent.start():intent.start()+150]):
            raise ValueError('Chưa hiểu đầy đủ khoảng giá. Hãy ghi đơn vị cho cả hai đầu khoảng.')
    if bounds.get('min_price_vnd',0)>bounds.get('max_price_vnd',10**12):
        raise ValueError('Các điều kiện giá mâu thuẫn hoặc không có khoảng giá khả dụng.')
    cleaned=original
    for clause in reversed(clauses):
        start,end=clause['span'];cleaned=cleaned[:start]+' '+cleaned[end:]
    cleaned=re.sub(r'\s+',' ',cleaned).strip(' ,.;:-')
    if clauses:
        edge_words=r'(?:giá|gia|price|budget|and|và|va)'
        for _ in range(3):
            cleaned=re.sub(rf'^{edge_words}\b\s*|\s*\b{edge_words}$','',cleaned,flags=re.I).strip()
        cleaned=re.sub(r'\s+',' ',cleaned).strip(' ,.;:-')
    return cleaned,bounds,[{k:v for k,v in clause.items() if k!='span'} for clause in clauses]
