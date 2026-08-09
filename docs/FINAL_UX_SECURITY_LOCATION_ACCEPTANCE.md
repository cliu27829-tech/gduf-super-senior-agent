# Final UX, security and current-location acceptance

Audit date: 2026-08-09 (Asia/Shanghai)

Statuses are intentionally limited to `PASS`, `FAIL`, and `BLOCKED_EXTERNAL`.

| Module | Status | Evidence / remaining external dependency |
|---|---|---|
| Login UI | PASS | Brand/value layout, no security implementation advertising, show/hide password, clear errors. |
| Register UI | PASS | Campus selection, grouped profile fields, live password requirements and mobile layout. |
| Global Design System | PASS | `tokens.css`, `base.css`, `components.css`, `responsive.css`; project brand red and warm neutral surfaces. |
| Home | PASS | Existing sourced product promise retained and rendered in browser tests. |
| Dashboard | PASS | Today schedule, next reminder, quick actions, notes and verified common-location shortcuts. |
| Chat | PASS | Real streaming model, multi-turn memory, no mock success, location request/resume and deduplicated tool cards. |
| Map | PASS | Configured AMap JS base map, verified POIs, current-position marker/circle and real browser route fallback. |
| Current Location | PASS | Explicit bottom-sheet consent, `getCurrentPosition`, accuracy bands, session memory only and manual fallback. |
| Route From Current Position | BLOCKED_EXTERNAL | Route endpoint and verified Qingyuan-library live flow pass. North Teaching still lacks a source that proves an exact entrance coordinate; no coordinate is fabricated. Backend AMap WebService key is also not configured, so the browser AMap SDK is the active real-route provider. |
| Canteens | PASS | North/South canteen facts and West-food-street lead are represented with verification status; no realtime menu claim. |
| Notifications | PASS | Parse, user confirmation, task persistence and linked reminder flow pass. |
| Tasks | PASS | CRUD, bulk actions, ICS, verified `location_id` link and “from here” navigation pass. |
| Reminders | PASS | Preview, explicit save, due watcher, location link and owner isolation pass. |
| Processes | PASS | Sourced process display and confirmed task conversion pass in real MVP E2E. |
| Profile | PASS | Campus/preference editing, notes, reminders and user-facing data controls use the shared visual system. |
| Admin | PASS | Role gate, dashboard, source review rules, user response filtering and backend admin tests pass. |
| Mobile | BLOCKED_EXTERNAL | 390×844, 393×852 and 412×915 responsive tests pass locally. Public-phone GPS still requires an authenticated HTTPS deployment/domain. |
| Password Security | PASS | Database proof confirms Argon2id hash; plaintext is absent; change-password and deletion flows pass. |
| Cookie Security | PASS | Access/refresh cookies are HttpOnly with explicit SameSite/path; production requires Secure cookies and strong secrets. |
| User Isolation | PASS | Shared owner lookups, linked-resource validation and private-knowledge owner-review gate pass. |
| IDOR | PASS | Backend two-user matrix and Playwright browser/API identifier swapping pass with `404`. |
| Privacy | PASS | GPS is not stored in DB, chat messages or tool logs; private uploads remain owner-only until explicit review submission. |
| Accessibility | PASS | Semantic labels, dialogs, live status/error regions, visible focus ring, skip link and 44px primary controls. |
| Build | PASS | Python compile, backend tests, TypeScript, ESLint, Vitest and Vite production build pass. |
| E2E | PASS | Real-model MVP, AMap, current-location, two-user IDOR, mobile and knowledge-route tests pass locally. |

## External blockers

1. North Teaching exact entrance: official school pages verify the North Teaching Building name, while AMap search returns nearby named buildings but no result proving which point is the North Teaching entrance. It remains `needs_verification` and is excluded from direct navigation.
2. Public HTTPS: the code, permissions policy and production headers are ready, but no deploy authorization/domain was available in this workspace. LAN `http://192.168.x.x` must not be presented as phone-GPS support.
3. AMap WebService: `AMAP_WEBSERVICE_KEY` is absent. `VITE_AMAP_JS_KEY` plus the server-side security proxy is configured and the browser JS walking route passed; the backend route endpoint returns a clear configuration error rather than an estimated route.

## Verification commands

```text
python -m compileall backend
pytest -q
npm run typecheck
npm run lint
npm run test
npm run build
E2E_REQUIRE_AMAP=1 npm run test:e2e
```

## Final local results

- Python compile: PASS.
- Backend: 101 tests passed; one upstream Starlette/httpx deprecation warning.
- Frontend: TypeScript PASS, ESLint PASS, 29 Vitest tests passed, production build PASS.
- Browser: all five enabled Playwright scenarios passed; the live admin-review scenario remains conditionally skipped when its external test precondition is absent.
- AMap: the live walking-route scenario passed in 12.4 seconds. One earlier full-suite attempt encountered an intermittent third-party SDK JSON parse error after the map assertions; the isolated rerun passed without a code change.
- Security scan: configured local secret values had zero matches outside ignored environment files; generic `sk-` patterns had zero matches.
