# Final Defect Log

| ID | Severity | Defect | Resolution / current state |
|---|---|---|---|
| FD-001 | P0 | Agent execution existed only in request memory and could not survive a location pause. | Added owner-scoped `agent_runs` and `agent_run_steps`; E2E proves the same `agent_run_id` resumes after location authorization. `PASS`. |
| FD-002 | P0 | Planner executed an entire fixed batch, so the UI could not observe each real tool boundary. | Added per-step execution and public `plan` / `tool_start` / `tool_end` / `verify` events; stream test confirms no `reasoning_content`. `PASS`. |
| FD-003 | P0 | Chat used one busy flag for model generation and geolocation, disabling the location permission action. | Split chat activity from geolocation activity; location permission and resume E2E pass. `PASS`. |
| FD-004 | P0 | Tool results were raw JSON or links instead of a unified actionable contract. | Added Action Cards and owned-run confirmation. Unknown/stale action IDs return 409. `PASS`. |
| FD-005 | P1 | Qingyuan dormitories were represented by one aggregate south-dorm record. | Replaced with official south 1–5 and north 1–8 records; legacy aggregate is inactive; seed test confirms 13 unique IDs. `PASS`. |
| FD-006 | P1 | CampusPath tables existed without auditable seed data. | Added provider-audited nodes and explicitly unverified schematic edges; only verified edges are routable. `PASS`. |
| FD-007 | P1 | Low-accuracy browser location was rejected with no way to knowingly continue. | Added disclosed continue/retry/cancel choice; backend labels accepted low-accuracy routes `approximate`. `PASS`. |
| FD-008 | External | 北饭、北教 exact entrances cannot be established from current official/provider evidence. | Coordinates stay unverified and route generation stays blocked until admin/现场 calibration. `BLOCKED_EXTERNAL`. |
| FD-009 | Diagnostic | A PowerShell smoke script changed Chinese text to question marks and produced a false signal. | Replaced by Unicode-safe HTTP smoke scripts; all recorded real-model prompts are now encoding-valid. `PASS`. |
| FD-010 | P0 | General multi-step route could append broad category matches after explicitly named stops. | Route extraction now keeps only explicit mentions, resolves overlapping aliases by longest match and preserves textual order. Regression passes. `PASS`. |
| FD-011 | P1 | A historical “清远校区食堂（正式名称待核验）” placeholder remained active. | Seed deactivates placeholder Location/Canteen; DB audit proves active Qingyuan canteens are exactly north and south. `PASS`. |
| FD-012 | P0 | Real LLM classified “我刚才说我叫什么” as knowledge search, so the answer was correct but the Run ended failed. | Conversation-recall phrases are deterministically `general_chat`; Mock and live DeepSeek both finish `completed` and remember 小明. `PASS`. |
| FD-013 | P0 | Fresh CI/Docker databases failed because the metadata-based initial migration had already created the new Agent tables before revision 09. | Revision 09 now checks table existence; a new test migrates an empty SQLite database from zero to head. `PASS`. |
| FD-014 | CI | Agent E2E unconditionally asserted live AMap DOM even when CI intentionally had no owner AMap credentials. | Core Agent assertions always run; only live-map assertions use the existing `E2E_REQUIRE_AMAP=1` gate. Local credentialed AMap E2E remains mandatory for release evidence. `PASS`. |
| FD-015 | P0 | A model could classify “提醒我复习高数” as learning guidance because both “提醒”和“高数” were present, hiding the reminder action. | Explicit reminder/note/task/notification/navigation commands now override probabilistic intent guesses; conflicting-model regression added. `PASS`. |
