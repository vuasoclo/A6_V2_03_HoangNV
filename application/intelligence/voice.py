"""Replaceable local ASR adapter; never calls a transcription or translation API."""
import io
import time
from typing import Protocol
import numpy as np
from .common import ROOT, read_json

SAMPLE_RATE=16000
MAX_SECONDS=30
MAX_BYTES=5*1024*1024

class Transcriber(Protocol):
    def transcribe(self, content: bytes) -> dict: ...

def decode_audio(content: bytes):
    if not content:raise ValueError('Bản ghi âm trống. Hãy ghi âm lại.')
    if len(content)>MAX_BYTES:raise ValueError('Bản ghi âm quá lớn (tối đa 5 MB).')
    import av
    samples=[];count=0
    try:
        with av.open(io.BytesIO(content)) as container:
            if not container.streams.audio:raise ValueError('Tệp không có âm thanh.')
            resampler=av.AudioResampler(format='fltp',layout='mono',rate=SAMPLE_RATE)
            for frame in container.decode(audio=0):
                for normalized in resampler.resample(frame):
                    array=normalized.to_ndarray().reshape(-1)
                    count+=len(array)
                    if count>MAX_SECONDS*SAMPLE_RATE:raise ValueError('Chỉ ghi âm tối đa 30 giây mỗi lần.')
                    samples.append(array)
            for normalized in resampler.resample(None):
                array=normalized.to_ndarray().reshape(-1);count+=len(array)
                if count>MAX_SECONDS*SAMPLE_RATE:raise ValueError('Chỉ ghi âm tối đa 30 giây mỗi lần.')
                samples.append(array)
    except av.error.FFmpegError as exc:
        raise ValueError('Không đọc được âm thanh. Hãy ghi âm lại.') from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Không đọc được âm thanh. Hãy ghi âm lại.') from exc
    if count<SAMPLE_RATE*0.25:raise ValueError('Bản ghi quá ngắn. Hãy nói một câu tìm kiếm.')
    audio=np.concatenate(samples).astype(np.float32)
    if not np.isfinite(audio).all():raise ValueError('Dữ liệu âm thanh không hợp lệ.')
    return audio

class PhoWhisperTranscriber:
    def __init__(self,compute_type='float32',threads=4):
        if compute_type not in {'float32','int8'}:raise ValueError('Kiểu tính toán voice không hợp lệ.')
        from faster_whisper import WhisperModel
        directory=ROOT/f'models/phowhisper-small-{compute_type}'
        if not (directory/'manifest.json').is_file():
            raise FileNotFoundError('Chưa chuẩn bị model voice local.')
        manifest=read_json(directory/'manifest.json')
        if manifest['source']!='vinai/PhoWhisper-small' or manifest['compute_type']!=compute_type:
            raise ValueError('Model voice không đúng cấu hình.')
        self.compute_type=compute_type
        self.model=WhisperModel(str(directory),device='cpu',compute_type=compute_type,
                               cpu_threads=threads,num_workers=1,local_files_only=True)

    def transcribe(self,content):
        started=time.perf_counter();audio=decode_audio(content)
        duration=len(audio)/SAMPLE_RATE
        if np.sqrt(np.mean(audio**2))<0.0001:
            return {'text':'','status':'no_speech','duration_seconds':duration,
                    'elapsed_ms':(time.perf_counter()-started)*1000,'model':'PhoWhisper-small','compute_type':self.compute_type}
        segments,info=self.model.transcribe(audio,language='vi',task='transcribe',beam_size=5,
            temperature=0,condition_on_previous_text=False,vad_filter=True,without_timestamps=True,
            vad_parameters={'min_silence_duration_ms':350,'speech_pad_ms':200})
        # Transcription is lazy: consume the generator before stopping the timer.
        segments=list(segments)
        text=' '.join(s.text.strip() for s in segments if s.text.strip()).strip()
        return {'text':text,'status':'ok' if text else 'no_speech','duration_seconds':duration,
                'elapsed_ms':(time.perf_counter()-started)*1000,'model':'PhoWhisper-small',
                'compute_type':self.compute_type,'language':'vi','segments':[
                    {'start':s.start,'end':s.end,'text':s.text.strip(),'avg_logprob':s.avg_logprob,
                     'no_speech_prob':s.no_speech_prob} for s in segments]}
