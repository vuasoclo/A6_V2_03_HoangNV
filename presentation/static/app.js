/* Presentation only; actual retrieval runs behind the application API. */
const $=id=>document.getElementById(id),money=n=>new Intl.NumberFormat('vi-VN').format(n)+' ₫';
let state={query:'',category:'',min:'',max:'',sort:'relevance'};
try{state={...state,...JSON.parse(sessionStorage.getItem('buoc-store-search')||'{}')};}catch{}
const params=new URLSearchParams(location.search);
if(params.has('category'))state={...state,category:params.get('category'),query:'',min:'',max:''};
if(params.has('similar'))state={query:'',category:'',min:'',max:'',sort:'relevance'};
if(!['','shoes','accessories'].includes(state.category))state.category='';
let attachment=null,attachmentUrl=null,attachmentPending=false,page=1,total=0,current=[],requestId=0,controller=null;
const groupNames={shoes:'Giày',accessories:'Phụ kiện'};
function node(tag,value,cls){const el=document.createElement(tag);if(value!=null)el.textContent=value;if(cls)el.className=cls;return el;}
function persist(){try{sessionStorage.setItem('buoc-store-search',JSON.stringify(state));}catch{}}
function imageStore(action,value){return new Promise((resolve,reject)=>{const req=indexedDB.open('buoc-store-images',1);req.onupgradeneeded=()=>req.result.createObjectStore('attachments');req.onerror=()=>reject(req.error);req.onsuccess=()=>{const db=req.result,tx=db.transaction('attachments',action==='get'?'readonly':'readwrite'),store=tx.objectStore('attachments');const op=action==='get'?store.get('current'):action==='put'?store.put(value,'current'):store.delete('current');let result;op.onsuccess=()=>result=op.result;tx.oncomplete=()=>{db.close();resolve(result);};tx.onerror=()=>{db.close();reject(tx.error);};};});}
function filters(){const f={};if(state.category)f.category_id=state.category;if(state.min!=='')f.min_price_vnd=Number(state.min);if(state.max!=='')f.max_price_vnd=Number(state.max);return f;}
function chip(label,action){const wrap=node('span',null,'chip'),button=node('button','×');button.type='button';button.setAttribute('aria-label','Bỏ '+label);button.onclick=action;wrap.append(node('span',label),button);$('chips').append(wrap);}
function showChips(){
  $('chips').replaceChildren();
  if(state.category)chip(groupNames[state.category],()=>{state.category='';document.querySelector('[name="category"][value=""]').checked=true;load();});
  if(state.min!==''||state.max!=='')chip((state.min!==''?money(Number(state.min)):'0 ₫')+' – '+(state.max!==''?money(Number(state.max)):'Không giới hạn'),()=>{state.min=state.max='';$('min-price').value=$('max-price').value='';load();});
}
function showCards(products,append=false){
  if(!append)$('results').replaceChildren();
  for(const p of products){
    const card=node('article',null,'product-card'),link=node('a',null,'product-link');link.href='/product/'+encodeURIComponent(p.source_id);
    link.onclick=()=>{persist();sessionStorage.setItem('buoc-store-position',String(scrollY));sessionStorage.setItem('buoc-store-page',String(page));};
    const visual=node('div',null,'product-image');
    if(p.image){const img=document.createElement('img');img.src=p.image;img.alt=p.name;img.loading='lazy';img.onerror=()=>{img.remove();visual.append(node('span','Chưa có ảnh','image-placeholder'));};visual.append(img);}
    else visual.append(node('span','Chưa có ảnh','image-placeholder'));
    link.append(visual,node('p',p.brand,'brand-name'),node('h3',p.name),node('p',p.color,'product-meta'),node('p',money(p.price),'product-price'));
    if(p.rank)link.append(node('p','Rank #'+p.rank+(Number.isFinite(p.cosine_score)?' · Cosine '+p.cosine_score.toFixed(4):''),'product-rank'));
    card.append(link);$('results').append(card);
  }
  $('empty').hidden=current.length>0;
}
async function load(append=false){
  const id=++requestId;controller?.abort();controller=new AbortController();
  if(!append){page=1;current=[];}
  persist();showChips();$('error').hidden=true;$('results').setAttribute('aria-busy','true');$('search-button').disabled=true;$('load-more').disabled=true;
  $('result-count').textContent='Đang tìm sản phẩm…';$('result-title').textContent=state.query?'Kết quả cho “'+state.query+'”':attachment?'Sản phẩm tương tự ảnh':groupNames[state.category]||'Tất cả sản phẩm';
  try{
    let response;const options={signal:controller.signal};
    if(attachment){const body=new FormData();body.append('image',attachment,'reference');body.append('query',state.query);body.append('sort',state.sort);body.append('top_k','20');for(const [key,value] of Object.entries(filters()))body.append(key,String(value));response=await fetch('/api/image-search',{...options,method:'POST',body});}
    else if(state.query)response=await fetch('/api/search',{...options,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:state.query,filters:filters(),sort:state.sort,top_k:20})});
    else response=await fetch('/api/catalog?'+new URLSearchParams({page,sort:state.sort,...filters()}),options);
    const data=await response.json();if(id!==requestId)return;if(!response.ok)throw new Error(data.error||'Không tìm được sản phẩm. Hãy thử lại.');
    current=append?[...current,...data.results]:data.results;total=data.total??current.length;showCards(data.results,append);
    $('result-count').textContent=(state.query||attachment)?current.length+' kết quả':current.length+' / '+total+' sản phẩm';$('load-more').hidden=Boolean(state.query||attachment||current.length>=total);
  }catch(error){if(error.name==='AbortError'||id!==requestId)return;current=[];showCards([]);$('empty').hidden=true;$('load-more').hidden=true;$('error').textContent=error.message;$('error').hidden=false;$('result-count').textContent='Chưa tải được kết quả';}
  finally{if(id===requestId){$('results').setAttribute('aria-busy','false');$('search-button').disabled=false;$('load-more').disabled=false;}}
}
function drawGroups(groups){
  $('categories').replaceChildren();
  for(const group of [{id:'',name:'Tất cả sản phẩm',count:groups.reduce((n,g)=>n+g.count,0)},...groups]){const label=node('label',null,'category-choice'),input=document.createElement('input');input.type='radio';input.name='category';input.value=group.id;input.checked=state.category===group.id;label.append(input,node('span',group.name),node('small',group.count));$('categories').append(label);input.onchange=()=>{state.category=group.id;load();};}
}
$('query').value=state.query;$('min-price').value=state.min;$('max-price').value=state.max;$('sort').value=state.sort;
$('search-form').onsubmit=e=>{e.preventDefault();if(attachmentPending||$('voice').getAttribute('aria-pressed')==='true'){$('input-help').textContent='Chờ đọc ảnh hoặc dừng ghi âm trước khi tìm.';return;}state.query=$('query').value.trim();load();};
$('sort').onchange=()=>{state.sort=$('sort').value;load();};
for(const button of document.querySelectorAll('[data-query]'))button.onclick=()=>{$('query').value=button.dataset.query;$('search-form').requestSubmit();document.querySelector('.search-panel').scrollIntoView({block:'start',behavior:'smooth'});};
$('apply-price').onclick=()=>{const min=$('min-price').value,max=$('max-price').value;if(!$('min-price').validity.valid||!$('max-price').validity.valid||(min!==''&&max!==''&&Number(min)>Number(max))){$('error').textContent='Giá từ phải không âm và không lớn hơn giá đến.';$('error').hidden=false;return;}state.min=min;state.max=max;load();};
function clearFilters(){state.category='';state.min=state.max='';$('min-price').value=$('max-price').value='';document.querySelector('[name="category"][value=""]').checked=true;}
$('clear-filters').onclick=()=>{clearFilters();load();};$('reset').onclick=async()=>{state.query='';$('query').value='';clearFilters();await removeImage();load();};
$('load-more').onclick=()=>{page++;load(true);};
$('toggle-filters').onclick=()=>{const open=$('filters').classList.toggle('expanded');$('toggle-filters').setAttribute('aria-expanded',String(open));if(open)$('filters').scrollIntoView({block:'start'});};
function showImage(file){attachment=file;if(attachmentUrl)URL.revokeObjectURL(attachmentUrl);attachmentUrl=URL.createObjectURL(file);$('preview').src=attachmentUrl;$('attachment').hidden=false;$('query').placeholder='Thêm chỉ dẫn cho ảnh, ví dụ: màu đen';$('input-help').textContent='Ví dụ: “giống đôi này nhưng màu đen”';}
async function attach(file){
  if(!file)return false;
  if(file.size>5*1024*1024){$('input-help').textContent='Ảnh quá lớn. Chọn ảnh tối đa 5 MB.';return false;}
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){$('input-help').textContent='Định dạng ảnh không được hỗ trợ. Chọn JPG, PNG hoặc WebP.';return false;}
  attachmentPending=true;
  try{const image=new Image(),url=URL.createObjectURL(file);try{image.src=url;await image.decode();if(image.width*image.height>16000000||Math.min(image.width,image.height)<16)throw new Error('Ảnh phải từ 16 pixel mỗi chiều và không quá 16 triệu pixel.');}finally{URL.revokeObjectURL(url);}showImage(file);try{await imageStore('put',file);}catch{$('input-help').textContent='Ảnh đã sẵn sàng; trình duyệt không lưu được ảnh khi quay lại.';}return true;}
  catch(error){$('input-help').textContent=error.message||'Không đọc được ảnh.';return false;}finally{attachmentPending=false;}
}
async function removeImage(){if(attachmentUrl)URL.revokeObjectURL(attachmentUrl);attachment=null;attachmentUrl=null;$('file').value='';$('attachment').hidden=true;$('query').placeholder='Ví dụ: giày đi nước màu đen dưới 800k';$('input-help').textContent='';try{await imageStore('delete');}catch{}}
$('add-image').onclick=()=>$('file').click();$('file').onchange=()=>attach($('file').files[0]);
$('query').addEventListener('paste',event=>{const file=Array.from(event.clipboardData.items).find(item=>item.type.startsWith('image/'))?.getAsFile();if(file){event.preventDefault();attach(file);}});$('remove-image').onclick=async()=>{await removeImage();load();};
(async()=>{
  try{const response=await fetch('/health');if(!response.ok)throw new Error('Chưa kết nối được hệ thống tìm kiếm.');const data=await response.json();drawGroups(data.groups);$('voice').disabled=!data.voice_available;$('add-image').disabled=!data.image_search_available;
    if(params.has('similar')){
      await removeImage();persist();sessionStorage.removeItem('buoc-store-position');sessionStorage.removeItem('buoc-store-page');
      // Refresh previously cached octet-stream headers as well as image bytes.
      const photo=await fetch('/photo/'+encodeURIComponent(params.get('similar')),{cache:'reload'});
      if(!photo.ok)throw new Error('Không tải được ảnh sản phẩm để tìm tương tự.');
      const blob=await photo.blob();
      if(!await attach(new File([blob],'product-reference',{type:blob.type})))throw new Error($('input-help').textContent||'Không đọc được ảnh sản phẩm.');
      history.replaceState(null,'','/');
    }else if(params.has('category'))await imageStore('delete');else{try{const file=await imageStore('get');if(file)showImage(file);}catch{}}
    await load();if(!params.has('category')&&!params.has('similar')){const oldPage=Math.min(30,Number(sessionStorage.getItem('buoc-store-page')||1));if(!state.query&&!attachment)while(page<oldPage&&current.length<total){page++;await load(true);}const y=Number(sessionStorage.getItem('buoc-store-position')||0);if(y)requestAnimationFrame(()=>scrollTo(0,y));}
  }catch(error){$('error').textContent=error.message;$('error').hidden=false;}
})();
