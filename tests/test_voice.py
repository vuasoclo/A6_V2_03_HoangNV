import io
from pathlib import Path
import sys
import threading
import unittest
import wave
from types import SimpleNamespace
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from application.intelligence.voice import decode_audio, PhoWhisperTranscriber,MAX_BYTES

def wav(seconds=1,rate=16000,channels=1):
    output=io.BytesIO()
    with wave.open(output,'wb') as stream:
        stream.setnchannels(channels);stream.setsampwidth(2);stream.setframerate(rate)
        stream.writeframes(np.zeros(int(seconds*rate)*channels,dtype='<i2').tobytes())
    return output.getvalue()

class AudioTests(unittest.TestCase):
    def test_empty_invalid_too_short_and_oversized(self):
        for content in [b'',b'not audio',wav(.1),b'x'*(MAX_BYTES+1)]:
            with self.assertRaises(ValueError):decode_audio(content)
    def test_resample_stereo_and_duration_bound(self):
        audio=decode_audio(wav(1,48000,2))
        self.assertEqual(audio.dtype,np.float32)
        self.assertEqual(len(audio),16000)
        with self.assertRaises(ValueError):decode_audio(wav(31))
    def test_decoder_error_is_readable(self):
        with self.assertRaisesRegex(ValueError,'Không đọc được âm thanh'):
            decode_audio(b'broken')
    def test_silence_does_not_invoke_model(self):
        asr=object.__new__(PhoWhisperTranscriber);asr.compute_type='float32'
        class Forbidden:
            def transcribe(self,*args,**kwargs):raise AssertionError('Silence reached model')
        asr.model=Forbidden()
        result=asr.transcribe(wav())
        self.assertEqual(result['status'],'no_speech');self.assertEqual(result['text'],'')

