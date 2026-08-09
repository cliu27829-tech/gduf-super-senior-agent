# Private resource ownership audit

Audit date: 2026-08-09 (Asia/Shanghai)

The API returns `404` for a private resource that does not belong to the current user. This avoids confirming that another user's identifier exists. Administrator access is not an implicit bypass for student-private content.

| Model | Endpoint / access path | Owner field | Read scoped? | Write scoped? | Delete scoped? | Tested? |
|---|---|---|---|---|---|---|
| Task | `/api/tasks`, item, complete, reopen, bulk | `user_id` | PASS | PASS | PASS | PASS |
| Task ICS | `/api/tasks/export/ics` | `Task.user_id` | PASS | N/A | N/A | PASS |
| Conversation | `/api/agent/conversations`, `/api/agent/chat` continuation | `user_id` | PASS | PASS | PASS | PASS |
| Message | conversation detail, note source validation | parent `Conversation.user_id` | PASS | PASS | parent cascade | PASS |
| Reminder | `/api/reminders` and task/note links | `user_id` | PASS | PASS | PASS | PASS |
| Note | `/api/notes` and source message link | `user_id` | PASS | PASS | PASS | PASS |
| KnowledgeDocument | `/api/knowledge/sources`, search, review submission | `owner_user_id` | PASS | PASS | PASS | PASS |
| KnowledgeImportJob | `/api/knowledge/jobs`, imports and reindex | `user_id` | PASS | PASS | parent/account cleanup | PASS |
| Uploaded content | knowledge file/text/url import output | `KnowledgeDocument.owner_user_id` | PASS | PASS | PASS | PASS |
| RefreshToken | refresh, logout, password/account deletion | `user_id` | PASS | PASS | PASS | PASS |

Implementation evidence:

- Shared ownership lookups live in `backend/app/services/ownership.py`.
- `Memory.conversation()` enforces ownership before loading history, so a foreign `conversation_id` cannot bypass the API detail route.
- Reminder `task_id` and `note_id`, note `source_message_id`, task `location_id`, and user `preferred_location_id` are validated before linking.
- Private knowledge is visible to the owner only. An administrator can see it only after the owner explicitly submits it for review; only a pending item can be reviewed.
- `backend/tests/test_ux_security_location.py` and `frontend/e2e/idor-isolation.spec.ts` exercise two-user identifier swapping across read, update, delete, continue, link and ICS export paths.
