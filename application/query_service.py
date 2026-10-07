"""UI contract: two coarse product groups and prices in VND."""
from .intelligence.retrieval import validate_filters

def ui_filters(filters=None):
    value=validate_filters(filters)
    if set(value)-{'category_id','min_price_vnd','max_price_vnd'}:
        raise ValueError('Chỉ hỗ trợ nhóm sản phẩm và khoảng giá.')
    if value.get('category_id') not in {None,'shoes','accessories'}:
        raise ValueError('Nhóm sản phẩm không hợp lệ.')
    return value

def validate_sort(sort):
    if sort not in {'relevance','price-asc','price-desc'}:
        raise ValueError('Thứ tự sắp xếp không hợp lệ.')
    return sort
