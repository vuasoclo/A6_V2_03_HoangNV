/* One button: record, stop, transcribe locally, then let the user review/search. */
(() => {
  const button=document.getElementById('voice');
  const input=document.getElementById('query');
  const feedback=document.getElementById('input-help');
  const searchButton=document.getElementById('search-button');
  if (!button || button.disabled) return;
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    button.disabled=true;
    button.title='Trình duyệt cần hỗ trợ ghi âm và chạy trên localhost hoặc HTTPS.';
    return;
  }
  let recorder=null,stream=null,timer=null,state='idle',chunks=[],cancelled=false;
  const release=() => {
    clearTimeout(timer); timer=null;
    stream?.getTracks().forEach(track=>track.stop()); stream=null;
  };
  const reset=() => {
    release(); state='idle'; recorder=null;chunks=[];
    button.disabled=false;document.getElementById('voice-label').textContent='Nói để nhập';
    button.setAttribute('aria-pressed','false');button.setAttribute('aria-label','Ghi âm truy vấn');
    searchButton.disabled=false;
  };
  async function transcribe(blob) {
    if (cancelled) {reset();return;}
    state='processing';button.disabled=true;document.getElementById('voice-label').textContent='Đang xử lý';
    feedback.textContent='Đang nhận dạng giọng nói…';
    const controller=new AbortController();
    const deadline=setTimeout(()=>controller.abort(),60000);
    try {
      if (!blob.size) throw new Error('Bản ghi âm trống. Hãy thử lại.');
      const body=new FormData();body.append('audio',blob,'recording');
      const response=await fetch('/api/voice',{method:'POST',body,signal:controller.signal});
      const data=await response.json();
      if (!response.ok) throw new Error(data.error || 'Không nhận dạng được âm thanh.');
      if (!data.text) {feedback.textContent=data.message || 'Không nghe được lời nói. Hãy thử lại.';return;}
      if (data.text.length>input.maxLength) throw new Error('Câu nhận dạng quá dài. Hãy nói ngắn hơn.');
      input.value=data.text;input.focus();
      feedback.textContent=`Đã nghe: “${data.text}”. Kiểm tra câu rồi bấm Tìm kiếm.`;
    } catch(error) {
      feedback.textContent=error.name==='AbortError'?'Nhận dạng mất quá lâu. Hãy thử một câu ngắn hơn.':error.message;
    } finally {clearTimeout(deadline);reset();}
  }
  button.addEventListener('click',async()=> {
    if (state==='recording') {
      state='stopping';button.disabled=true;
      if (recorder?.state==='recording') recorder.stop();
      return;
    }
    if (state!=='idle') return;
    if (searchButton.disabled) {feedback.textContent='Hãy chờ tìm kiếm hiện tại hoàn tất rồi ghi âm.';return;}
    state='requesting';cancelled=false;button.disabled=true;searchButton.disabled=true;
    feedback.textContent='Đang mở micro…';
    try {
      stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
      if (cancelled) {reset();return;}
      const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
      recorder=new MediaRecorder(stream,mime?{mimeType:mime}:{});chunks=[];
      recorder.addEventListener('dataavailable',event=>{if(event.data.size)chunks.push(event.data);});
      recorder.addEventListener('stop',()=>{
        const blob=new Blob(chunks,{type:recorder.mimeType});release();void transcribe(blob);
      },{once:true});
      recorder.addEventListener('error',()=>{
        cancelled=true;feedback.textContent='Ghi âm bị gián đoạn. Hãy thử lại.';
        if(recorder?.state==='recording')recorder.stop();else reset();
      });
      recorder.start();state='recording';button.disabled=false;document.getElementById('voice-label').textContent='Dừng nhập';
      button.setAttribute('aria-pressed','true');button.setAttribute('aria-label','Dừng ghi âm');
      feedback.textContent='Đang ghi âm. Bấm Dừng nhập để dừng (tối đa 25 giây).';
      timer=setTimeout(()=>{if(state==='recording'){state='stopping';button.disabled=true;recorder.stop();}},25000);
    } catch(error) {
      feedback.textContent=error.name==='NotAllowedError'?'Micro chưa được cấp quyền. Cho phép micro để ghi âm.':
        error.name==='NotFoundError'?'Không tìm thấy micro.': 'Không mở được micro. Hãy thử lại.';
      reset();
    }
  });
  window.addEventListener('pagehide',()=>{
    cancelled=true;
    if(recorder?.state==='recording')recorder.stop();
    release();
  });
})();
