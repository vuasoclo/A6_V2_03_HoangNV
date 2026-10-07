"""Speech becomes editable text; it does not auto-submit a purchase/search."""
class SpeechService:
    def __init__(self, transcriber):self.transcriber=transcriber
    @property
    def available(self):return self.transcriber is not None
    def transcribe(self, content):return self.transcriber.transcribe(content)
