"""Keep semantic ranks intact when the user sorts the returned shortlist by price."""
def rank_results(result, products, sort='relevance'):
    for rank,item in enumerate(result['results'],1):
        item['rank']=rank if result.get('ranking_basis')!='price_ascending' else None
    if sort in {'price-asc','price-desc'}:
        result['results'].sort(key=lambda item:products[item['product_id']]['display']['price']['amount'],reverse=sort=='price-desc')
    return result
