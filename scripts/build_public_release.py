from __future__ import annotations
import argparse, hashlib, json, zipfile, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from submission.submission import safe_public_file, scan_text_for_secrets

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',default='.'); ap.add_argument('--output',required=True); args=ap.parse_args()
    repo=Path(args.repo).resolve(); out=Path(args.output).resolve()
    if repo in out.parents or out.parent==repo:
        # output inside repo is allowed only because we explicitly skip it below
        pass
    files=[]; rejected=[]; secret_hits=[]
    for p in sorted(repo.rglob('*')):
        if not p.is_file() or p.resolve()==out: continue
        ok,reason=safe_public_file(p,repo)
        if not ok:
            rejected.append({'path':p.relative_to(repo).as_posix(),'reason':reason}); continue
        if p.stat().st_size<=2_000_000:
            try:text=p.read_text(encoding='utf-8')
            except Exception:text=''
            if text and scan_text_for_secrets(text): secret_hits.append(p.relative_to(repo).as_posix())
        files.append(p)
    if secret_hits:
        print(json.dumps({'status':'FAIL','secret_like_files':secret_hits},indent=2)); return 1
    manifest={}
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            rel=p.relative_to(repo).as_posix(); data=p.read_bytes(); manifest[rel]=sha(data); z.writestr(rel,data)
        manifest_bytes=(json.dumps({'schema_version':1,'files':manifest},indent=2,sort_keys=True)+'\n').encode()
        z.writestr('PUBLIC_RELEASE_MANIFEST.json',manifest_bytes)
    print(json.dumps({'status':'PASS','output':str(out),'files':len(files),'excluded':len(rejected),'sha256':sha(out.read_bytes())},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
