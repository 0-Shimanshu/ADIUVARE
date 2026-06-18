# Route Verification

Verified manually against a local Flask server.

## Health

GET /

Expected:
- HTTP 200
- {"ok": true}

## Public

GET /public/

Expected:
- HTTP 200
- Route exempt from inspection

## Protected

GET /protected/

Expected:
- HTTP 200
- Verdict and score returned

## Review

POST /review/

Expected:
- HTTP 200
- Payload returned in response

## Hard Stop

POST /hard-stop/

Expected:
- Request inspected by Adiuvare
- Verdict and score returned