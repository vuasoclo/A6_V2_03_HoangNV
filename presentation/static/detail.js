const $=id=>document.getElementById(id),sourceId=decodeURIComponent(location.pathname.split('/').pop());
(async()=>{
  try{
    const response=await fetch('/api/products/'+encodeURIComponent(sourceId)),p=await response.json();if(!response.ok)throw new Error(p.error);
    document.title=p.name+' — BƯỚC';$('category-name').textContent=p.group;
    if(p.image){$('product-photo').src=p.image;$('product-photo').alt=p.name;}else{$('product-photo').hidden=true;document.querySelector('.photo-caption').textContent='Chưa có ảnh sản phẩm';}
    $('product-brand').textContent=p.brand;$('product-name').textContent=p.name;$('product-lead').textContent=p.features[0]||'';$('product-lead').hidden=!p.features.length;
    $('product-price').textContent=new Intl.NumberFormat('vi-VN').format(p.price)+' ₫';$('product-color').textContent=p.color;document.querySelector('.color-info').hidden=!p.color;$('description').textContent=p.description;$('description').hidden=!p.description;
    for(const [label,value] of [['Nhóm sản phẩm',p.group],['Thương hiệu',p.brand],['Dòng sản phẩm',p.model],['Đối tượng',p.audience],['Chất liệu',p.material],['Công dụng',p.uses]]){if(!value)continue;const row=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;row.append(dt,dd);$('specs').append(row);}
    for(const feature of p.features){const li=document.createElement('li');li.textContent=feature;$('features').append(li);}
    $('similar').href='/?similar='+encodeURIComponent(p.source_id);$('similar').firstChild.textContent='Sản phẩm tương tự ';
    $('similar').hidden=!p.image;
  }catch(error){$('detail').hidden=true;document.querySelector('.detail-sections').hidden=true;$('category-name').textContent=error.message||'Không tải được sản phẩm';}
})();
