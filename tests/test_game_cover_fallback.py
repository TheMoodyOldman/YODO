"""Recap should use Steam header art when a portrait is missing, including offline demos."""
import asyncio
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from PIL import Image
from app import card_render

PORTRAIT='https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/413150/library_600x900.jpg'
HEADER=PORTRAIT.replace('library_600x900.jpg','header.jpg')
REAL_CLIENT=httpx.AsyncClient

def jpeg():
    stream=io.BytesIO();Image.new('RGB',(100,60),'green').save(stream,'JPEG');return stream.getvalue()

class CoverTests(unittest.TestCase):
    def fetch(self,handler):
        with patch.object(card_render.httpx,'AsyncClient',side_effect=lambda **kw:REAL_CLIENT(transport=httpx.MockTransport(handler),**kw)):
            return asyncio.run(card_render.fetch_images({PORTRAIT}))

    def test_missing_portrait_uses_header_under_original_key(self):
        calls=[]
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(404) if str(request.url)==PORTRAIT else httpx.Response(200,content=jpeg())
        with patch.object(card_render,'local_path',return_value=None):images=self.fetch(handler)
        self.assertIn(PORTRAIT,images);self.assertEqual(images[PORTRAIT].size,(100,60));self.assertEqual(calls,[PORTRAIT,HEADER])

    def test_valid_portrait_does_not_fetch_header(self):
        calls=[]
        def handler(request):calls.append(str(request.url));return httpx.Response(200,content=jpeg())
        with patch.object(card_render,'local_path',return_value=None):self.assertIn(PORTRAIT,self.fetch(handler))
        self.assertEqual(calls,[PORTRAIT])

    def test_offline_header_used_after_corrupt_local_portrait(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            p=Path(folder)/'portrait.jpg';p.write_bytes(b'not an image')
            h=Path(folder)/'header.jpg';h.write_bytes(jpeg())
            def local(url):return p if url==PORTRAIT else h
            def offline(request):raise AssertionError('Local fallback must not need network')
            with patch.object(card_render,'local_path',side_effect=local):images=self.fetch(offline)
            self.assertIn(PORTRAIT,images)

    def test_missing_both_remains_safe_placeholder(self):
        with patch.object(card_render,'local_path',return_value=None):self.assertEqual(self.fetch(lambda request:httpx.Response(404)),{})

if __name__=='__main__':unittest.main()
