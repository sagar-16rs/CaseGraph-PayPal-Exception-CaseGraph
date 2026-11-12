from __future__ import annotations
import json, hashlib
from typing import Any

def canonical_json_bytes(value:Any)->bytes:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode()
def content_hash(value:Any)->str: return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
