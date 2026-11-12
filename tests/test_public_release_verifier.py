import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def test_public_release_round_trip(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();(repo/'README.md').write_text('CaseGraph')
    (repo/'.env.example').write_text('OPENAI_API_KEY=your_key')
    (repo/'.env').write_text('OPENAI_API_KEY=do-not-package')
    out=tmp_path/'public.zip'
    made=subprocess.run([sys.executable,str(ROOT/'scripts/build_public_release.py'),'--repo',str(repo),'--output',str(out)],capture_output=True,text=True)
    assert made.returncode==0,made.stdout+made.stderr
    check=subprocess.run([sys.executable,str(ROOT/'scripts/verify_public_release.py'),str(out)],capture_output=True,text=True)
    assert check.returncode==0,check.stdout+check.stderr
    data=json.loads(check.stdout);assert data['status']=='PASS';assert data['manifest_entries']==2
