# Adiuvare Flask Demo

This is a maintained Flask example showing how to use Adiuvare inside a real
Flask app. It is intended as a practical reference for users who want to
understand how to attach Adiuvare to Flask, configure route-level policies, and
verify behavior end-to-end.

The central Flask integration documentation links here.

## What this demo covers

| Route         | Method | Purpose                  | Expected behavior                                  |
| ------------- | ------ | ------------------------ | -------------------------------------------------- |
| `/`           | GET    | Health check             | Exempt, basic liveness check                       |
| `/public/`    | GET    | Public route             | Exempt from Adiuvare inspection                    |
| `/protected/` | GET    | Protected route          | Inspected and allowed, verdict + score in response |
| `/review/`    | POST   | Payload review route     | JSON body read and scored, result in response      |
| `/hard-stop/` | POST   | Suspicious payload route | Demonstrates flagged malicious-looking input       |

## Setup

```bash
cd examples/multi-framework-demo/flask_demo
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
cd examples/multi-framework-demo/flask_demo
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Start the server

```bash
python app.py
```
