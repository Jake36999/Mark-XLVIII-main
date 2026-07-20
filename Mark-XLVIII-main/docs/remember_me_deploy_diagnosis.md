# Remember Me Deployment Diagnosis

Date checked: 2026-07-20

## Current Finding

Remember Me is not a clean runtime dependency for MARK XLVIII right now.

- MARK XLVIII dashboard binds local ports `8000` and `8001`.
- Remember Me `D:\remember_me\project-Mnemosyne-main\.env` has `BACKEND_PORT=8000`.
- Mark's old `remember_api_url` pointed at `http://127.0.0.1:8000`, which hits Mark's dashboard instead of Remember Me.
- `docker ps` and `docker compose ps` showed no Remember Me containers running.

## Runtime Decision

Mark-native vault memory is authoritative. Remember Me is optional and disabled by default.

If Remember Me is launched later, use non-conflicting ports such as:

- `BACKEND_PORT=8010`
- `FRONTEND_PORT=3010`
- `WEB_PORT=8088`

Only enable Mark's Remember Me sync after the backend responds correctly at `/remember/debug/state`.
