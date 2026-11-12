from __future__ import annotations
import asyncio,time,httpx
from backend.config import settings
from backend.paypal.errors import PayPalTransportError,PayPalAPIError
class PayPalAuth:
    def __init__(self): self.token=None; self.exp=0; self.lock=asyncio.Lock()
    async def access_token(self):
        if self.token and time.time()<self.exp-30:return self.token
        async with self.lock:
            if self.token and time.time()<self.exp-30:return self.token
            try:
                async with httpx.AsyncClient(timeout=15) as c: r=await c.post(settings.paypal_base_url+'/v1/oauth2/token',data={'grant_type':'client_credentials'},auth=(settings.paypal_client_id,settings.paypal_client_secret),headers={'Accept':'application/json'})
            except httpx.HTTPError as e: raise PayPalTransportError(str(e)) from e
            if r.status_code>=400: raise PayPalAPIError('PayPal OAuth failed',r.status_code, r.json() if 'json' in r.headers.get('content-type','') else {'text':r.text})
            d=r.json(); self.token=d['access_token']; self.exp=time.time()+int(d.get('expires_in',300)); return self.token
paypal_auth=PayPalAuth()
