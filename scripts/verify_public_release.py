from __future__ import annotations
import argparse, hashlib, json, tempfile, zipfile, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from submission.submission import scan_text_for_secrets

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('zip');a=ap.parse_args();zp=Path(a.zip).resolve()
    errors=[]
    with zipfile.ZipFile(zp) as z:
        names=z.namelist()
        if 'PUBLIC_RELEASE_MANIFEST.json' not in names:
            errors.append('PUBLIC_RELEASE_MANIFEST.json missing')
            manifest={}
        else:
            manifest=json.loads(z.read('PUBLIC_RELEASE_MANIFEST.json'))['files']
        for rel,dig in manifest.items():
            if rel not in names: errors.append(f'missing: {rel}'); continue
            data=z.read(rel)
            if sha(data)!=dig: errors.append(f'hash mismatch: {rel}')
            if len(data)<=2_000_000:
                try:text=data.decode('utf-8')
                except Exception:text=''
                if text and scan_text_for_secrets(text): errors.append(f'secret-like content: {rel}')
        forbidden=[]
        for n in names:
            parts=set(Path(n).parts);base=Path(n).name
            if parts & {'.git','.data','__pycache__','.pytest_cache','.ruff_cache','node_modules','dist','.venv','venv','.omp'}: forbidden.append(n)
            if any(part.startswith('pytest-cache-files-') for part in Path(n).parts): forbidden.append(n)
            if n.startswith(('research/.tmp/','research/.baseline/')): forbidden.append(n)
            if n.startswith('study_runs/') and base!='.gitignore': forbidden.append(n)
            if n.startswith('uploads/') or n.startswith('private_uploads/'): forbidden.append(n)
            if base=='.env' or (base.startswith('.env.') and not base.endswith('.example')): forbidden.append(n)
        if forbidden: errors.append('forbidden entries: '+', '.join(sorted(set(forbidden))[:20]))
    print(json.dumps({'status':'PASS' if not errors else 'FAIL','zip_sha256':sha(zp.read_bytes()),'manifest_entries':len(manifest),'errors':errors},indent=2));return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(main())
