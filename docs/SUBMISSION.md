# Submission tooling

The `submission/` package and related scripts provide claim linting, public-release sanitization, demo-video duration checks, and final submission diagnostics.

Useful commands:

```bash
python scripts/submission_lint.py
python scripts/submission_doctor.py --repo .
python scripts/check_demo_video.py final_demo.mp4
python scripts/build_public_release.py --repo . --output casegraph_public_release.zip
python scripts/verify_public_release.py casegraph_public_release.zip
```

Public claims must reflect actual completed gates. Do not promote pending live validation or user-study metrics into final submission copy.
