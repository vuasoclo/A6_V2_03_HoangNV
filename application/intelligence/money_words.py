"""Configured written variants of Vietnamese/English money, no dialect inference."""
from decimal import Decimal
import re
import unicodedata

VI_DIGITS={'khong':0,'mot':1,'hai':2,'ba':3,'bon':4,'tu':4,'nam':5,'lam':5,'nham':5,'sau':6,'bay':7,'tam':8,'chin':9}
EN_DIGITS={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,
           'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,
           'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
SCALES={'trieu':1000000,'tr':1000000,'million':1000000,'m':1000000,
        'nghin':1000,'ngan':1000,'nghen':1000,'k':1000,'thousand':1000,
        'vnd':1,'dong':1,'d':1,'₫':1}
WORDS=set(VI_DIGITS)|set(EN_DIGITS)|set(SCALES)|{'tram','chuc','muoi','linh','le','hundred','ruoi','half'}
TOKEN=r'(?:\d+(?:[.,]\d+)*|(?:'+ '|'.join(sorted((re.escape(w) for w in WORDS),key=len,reverse=True))+r')(?![a-z]))'
RUN=re.compile(rf'(?<!\w)(?!tu\b){TOKEN}(?:\s*{TOKEN})*',re.I)


def small_number(words):
    if not words:return Decimal(1)
    if words==['half']:return Decimal('0.5')
    if len(words)==1 and re.fullmatch(r'\d+(?:[.,]\d+)*',words[0]):
        s=words[0]
        if re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+',s):s=s.replace(',','').replace('.','')
        elif s.count(',')+s.count('.')>1:raise ValueError('Số tiền không rõ dấu phân cách.')
        return Decimal(s.replace(',','.'))
    english=any(w in EN_DIGITS or w=='hundred' for w in words)
    total=0;pending=None;last_scale=None
    for w in words:
        if w in ('linh','le'):continue
        if w in ('ruoi','half'):
            if last_scale not in (10,100):raise ValueError('Cách dùng rưỡi/half chưa rõ đơn vị.')
            total+=Decimal(last_scale)/2;continue
        digits=EN_DIGITS if english else VI_DIGITS
        if w in digits or re.fullmatch(r'\d+',w):
            n=digits[w] if w in digits else int(w)
            if pending is not None:
                if english and pending>=20 and pending%10==0 and n<10:
                    pending+=n
                else:raise ValueError('Cách đọc số tiền chưa rõ. Hãy nhập chữ số hoặc số đầy đủ.')
            else:pending=n
        elif w in ('tram','hundred','muoi','chuc'):
            scale=100 if w in ('tram','hundred') else 10
            n=pending if pending is not None else 1
            if n>9:raise ValueError('Cách đọc hàng chục/trăm không hợp lệ.')
            total+=n*scale;pending=None;last_scale=scale
        else:raise ValueError('Cách đọc số tiền chưa hỗ trợ.')
    return Decimal(total+(pending if pending is not None else 0))


def spoken_amount(text):
    words=re.findall(r'\d+(?:[.,]\d+)*|[a-z]+|₫',text)
    total=Decimal(0);group=[];last_scale=None;has_money=False
    for w in words:
        if w in SCALES:
            scale=SCALES[w]
            # Final VND/dong after k/million is a currency marker, not another term.
            if scale==1 and last_scale is not None and not group:continue
            if last_scale is not None and scale>=last_scale:
                raise ValueError('Thứ tự đơn vị tiền chưa rõ. Hãy nhập 1,5 triệu hoặc 1500000 VND.')
            total+=small_number(group)*scale;group=[];last_scale=scale;has_money=True
        elif w in ('ruoi','half') and last_scale is not None and not group:
            total+=Decimal(last_scale)/2
        else:group.append(w)
    if not has_money:return None
    if group:raise ValueError('Số tiền thiếu đơn vị ở phần cuối. Ví dụ: một triệu hai trăm nghìn.')
    if total!=total.to_integral_value() or not 0<=total<=10**12:
        raise ValueError('Số tiền VND ngoài khoảng hỗ trợ.')
    return int(total)


def normalize_money_query(original):
    """Return folded parse text plus per-character spans in the original query."""
    value='';mapping=[];assumptions=[]
    for i,ch in enumerate(original):
        chars=''.join(c for c in unicodedata.normalize('NFD',ch.lower().replace('đ','d')) if not unicodedata.combining(c))
        value+=chars;mapping.extend([(i,i+1)]*len(chars))

    def replace(matches):
        nonlocal value,mapping
        for match,replacement in reversed(matches):
            start,end=match.span();span=(mapping[start][0],mapping[end-1][1])
            value=value[:start]+replacement+value[end:]
            mapping=mapping[:start]+[span]*len(replacement)+mapping[end:]

    aliases=[(r'\b(?:hong|khong|khum|ko|k)\s+(?:qua|vuot qua)\b','at most'),
             (r'\b(?:hong|khong|ko)\s+(?:mac hon|dat hon)\b','at most'),
             (r'\b(?:hong|khum|ko|k)\s+duoi\b','at least'),
             (r'\b(?:chua toi|chua den|khong toi|hong toi|re hon|thap hon|be hon|nho hon)\b','under'),
             (r'\b(?:cao hon|lon hon|dat hon)\b','above')]
    for pattern,replacement in aliases:replace([(m,replacement) for m in re.finditer(pattern,value)])
    replace([(m,'half ') for m in re.finditer(r'\bhalf\s+a\s+(?=million|thousand)',value)])
    replace([(m,str(EN_DIGITS[m.group(1)]+Decimal('0.5'))+' ') for m in re.finditer(r'\b(one|two|three|four|five|six|seven|eight|nine)\s+and\s+a\s+half\s+(?=million|thousand)',value)])
    replace([(m,'at most ') for m in re.finditer(r'\b(?:ngan sach|budget)\s+(?=\d|mot\b|hai\b|ba\b|bon\b|nam\b|sau\b|bay\b|tam\b|chin\b|one\b|two\b|three\b|four\b|five\b|six\b|seven\b|eight\b|nine\b)',value)])
    # English "hundred and fifty"; the range connector after thousand stays intact.
    replace([(m,'hundred ') for m in re.finditer(r'\bhundred\s+and\s+',value)])
    has_context=bool(re.search(r'\b(?:gia|price|budget|duoi|tren|under|above|below|over|tu|from|between|toi da|toi thieu|at most|at least)\b|[<>]',value))
    suffix=bool(re.search(r'\b(?:do lai|tro xuong|tro len)\b',value))
    if has_context or suffix:
        replacements=[]
        for match in RUN.finditer(value):
            text=match.group().strip()
            prefix=value[:match.start()]
            nearby=re.search(r'(?:\b(?:duoi|tren|under|over|above|below|tu|from|between|den|toi|to|and|at most|at least|toi da|toi thieu|it nhat|khong qua|khong duoi|less than|more than|no more than|no less than|not under|not over|gia|price|budget)|[<>]=?)\s*$',prefix)
            follows_suffix=re.match(r'\s+(?:do lai|tro xuong|tro len)\b',value[match.end():])
            if not (nearby or follows_suffix):continue
            # A number alone is not a money amount: preserve model/size/year.
            word_tokens=re.findall(r'[a-z]+|₫',text)
            if not any(w in SCALES for w in word_tokens):
                if (nearby or follows_suffix) and any(w in ('tram','chuc') for w in word_tokens):
                    amount=small_number(re.findall(r'\d+(?:[.,]\d+)*|[a-z]+',text))*1000
                    if amount!=amount.to_integral_value() or not 0<=amount<=10**12:
                        raise ValueError('Số tiền ngoài khoảng hỗ trợ.')
                    span=(mapping[match.start()][0],mapping[match.end()-1][1])
                    assumptions.append({'span':span,'text':original[span[0]:span[1]],
                                        'amount_vnd':int(amount),'rule':'colloquial_hundreds_tens_in_thousands',
                                        'note':'Trong điều kiện giá, trăm/chục không ghi đơn vị được hiểu theo nghìn đồng.'})
                    replacements.append((match,str(int(amount))+' vnd'))
                continue
            # Keep numeric shorthand for range inheritance (300 to 500k).
            if not follows_suffix and re.fullmatch(r'\d+(?:[.,]\d+)*\s*(?:'+ '|'.join(SCALES)+r')(?:\s*(?:vnd|dong|d|₫))?',text):continue
            amount=spoken_amount(text)
            if amount is not None:replacements.append((match,str(amount)+' vnd'))
        replace(replacements)
    pattern=rf'(?<!\w)(?:tu\s+)?(\d+\s+vnd)\s+(do lai|tro xuong|tro len)\b'
    replace([(m,('at least ' if m.group(2)=='tro len' else 'at most ')+m.group(1)) for m in re.finditer(pattern,value)])
    return value,mapping,assumptions
