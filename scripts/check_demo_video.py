from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('video',nargs='?'); ap.add_argument('--seconds',type=float); a=ap.parse_args()
    seconds=a.seconds
    if seconds is None:
        if not a.video: ap.error('video path or --seconds required')
        cmd=['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(Path(a.video))]
        try: seconds=float(subprocess.check_output(cmd,text=True).strip())
        except Exception as exc:
            print(json.dumps({'status':'FAIL','error':f'ffprobe failed: {exc}'},indent=2)); return 1
    status='PASS' if seconds<180 else 'FAIL'
    print(json.dumps({'status':status,'duration_seconds':seconds,'margin_seconds':180-seconds},indent=2)); return 0 if status=='PASS' else 1
if __name__=='__main__': raise SystemExit(main())
