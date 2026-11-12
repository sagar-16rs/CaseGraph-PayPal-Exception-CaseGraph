import json, subprocess, sys, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def test_default_doctor_passes_on_validation_contract_mock(tmp_path):
    (tmp_path/'docs').mkdir(); (tmp_path/'docs/VALIDATION_PROTOCOL.md').write_text('protocol')
    (tmp_path/'validation').mkdir()
    (tmp_path/'README_SUBMISSION.md').write_text('CaseGraph')
    out=subprocess.run([sys.executable,str(ROOT/'scripts/submission_doctor.py'),'--repo',str(tmp_path)],capture_output=True,text=True)
    assert out.returncode==0, out.stdout+out.stderr
    data=json.loads(out.stdout); assert data['status']=='PASS'; assert data['checks']['open_source_license'] is False

def test_submission_ready_fails_until_urls_and_license_are_real(tmp_path):
    (tmp_path/'docs').mkdir(); (tmp_path/'docs/VALIDATION_PROTOCOL.md').write_text('protocol')
    (tmp_path/'validation').mkdir()
    (tmp_path/'README.md').write_text('CaseGraph')
    out=subprocess.run([sys.executable,str(ROOT/'scripts/submission_doctor.py'),'--repo',str(tmp_path),'--submission-ready'],capture_output=True,text=True)
    assert out.returncode==1
