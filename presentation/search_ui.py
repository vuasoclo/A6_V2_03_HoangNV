"""Thin HTTP adapter: inputs, statuses, templates and serialization only."""
from flask import Flask,request,jsonify,render_template,send_file,abort
from application.query_service import ui_filters,validate_sort
from .search_result_view import product_view,result_view

def create_app(services,testing=False):
    app=Flask(__name__);app.config.update(TESTING=testing,MAX_CONTENT_LENGTH=6*1024*1024)
    app.extensions['services']=services
    @app.before_request
    def limit_json():
        if request.path not in {'/api/voice','/api/image-search'} and (request.content_length or 0)>16384:
            return jsonify(error='Request quá lớn.'),413
    @app.get('/')
    def home():return render_template('index.html')
    @app.get('/product/<source_id>')
    def detail(source_id):
        if services.repository.get('amazon:'+source_id) is None:abort(404)
        return render_template('product.html')
    @app.get('/api/products/<source_id>')
    def product(source_id):
        product=services.repository.get('amazon:'+source_id)
        if product is None:abort(404)
        return jsonify(product_view(product))
    @app.get('/api/catalog')
    def catalog():
        if set(request.args)-{'page','sort','category_id','min_price_vnd','max_price_vnd'}:raise ValueError('Tham số không hợp lệ.')
        if any(len(request.args.getlist(k))!=1 for k in request.args):raise ValueError('Tham số trùng.')
        filters={k:float(request.args[k]) for k in ('min_price_vnd','max_price_vnd') if request.args.get(k)}
        if request.args.get('category_id'):filters['category_id']=request.args['category_id']
        page=int(request.args.get('page','1'));sort=validate_sort(request.args.get('sort','relevance'))
        if page<1 or page>10000:raise ValueError('Trang không hợp lệ.')
        products,total=services.repository.browse(ui_filters(filters),sort,page)
        return jsonify(results=[product_view(p) for p in products],total=total,page=page,page_size=24,groups=services.repository.groups())
    @app.post('/api/search')
    def search():
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict) or set(payload)-{'query','filters','sort','top_k'}:raise ValueError('JSON không hợp lệ.')
        return jsonify(result_view(services.search(payload.get('query',''),payload.get('filters'),payload.get('sort','relevance'),payload.get('top_k',20)),services.repository))
    @app.post('/api/image-search')
    def image_search():
        if not services.image.available:return jsonify(error='Tìm ảnh chưa sẵn sàng.'),503
        if set(request.files)!={'image'} or len(request.files.getlist('image'))!=1 or set(request.form)-{'query','top_k','sort','category_id','min_price_vnd','max_price_vnd'} or any(len(request.form.getlist(k))!=1 for k in request.form):raise ValueError('Chỉ gửi một ảnh và các điều kiện hợp lệ.')
        content=request.files['image'].read(5*1024*1024+1)
        if len(content)>5*1024*1024:return jsonify(error='Ảnh tối đa 5 MB.'),413
        filters={k:float(request.form[k]) for k in ('min_price_vnd','max_price_vnd') if request.form.get(k)}
        if request.form.get('category_id'):filters['category_id']=request.form['category_id']
        result=services.search(request.form.get('query',''),filters,request.form.get('sort','relevance'),int(request.form.get('top_k','20')),content)
        return jsonify(result_view(result,services.repository))
    @app.post('/api/voice')
    def voice():
        if not services.speech.available:return jsonify(error='Nhận dạng giọng nói chưa sẵn sàng.'),503
        if set(request.files)!={'audio'} or len(request.files.getlist('audio'))!=1 or request.form:raise ValueError('Gửi một bản ghi âm.')
        if not services.voice_lock.acquire(blocking=False):return jsonify(error='Đang xử lý bản ghi trước.'),429
        try:
            content=request.files['audio'].read(5*1024*1024+1)
            if len(content)>5*1024*1024:return jsonify(error='Bản ghi tối đa 5 MB.'),413
            result=services.speech.transcribe(content)
            if not result.get('text'):result['message']='Không nghe được lời nói. Hãy thử lại.'
            return jsonify(result)
        finally:services.voice_lock.release()
    @app.get('/photo/<source_id>')
    def photo(source_id):
        path=services.repository.photo(source_id)
        if path is None:abort(404)
        # Windows MIME registry may omit WebP. Catalog photo formats are verified
        # during import; do not let OS MIME guessing turn them into octet-stream.
        mime={'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.bmp':'image/bmp'}.get(path.suffix.lower())
        return send_file(path,mimetype=mime,conditional=True)
    @app.get('/health')
    def health():return jsonify(services.health())
    @app.errorhandler(ValueError)
    def bad_input(error):return jsonify(error=str(error)),400
    @app.errorhandler(404)
    def missing(error):
        if request.path.startswith('/api/') or request.path.startswith('/photo/'):return jsonify(error='Không tìm thấy sản phẩm.'),404
        return render_template('missing.html'),404
    @app.errorhandler(413)
    def too_large(error):return jsonify(error='Dữ liệu quá lớn.'),413
    return app
