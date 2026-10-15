# UniMind Admin Phase Two

Goal: move question-bank and knowledge-catalog maintenance into the existing Directus business workspace. The student frontend and course classification remain unchanged.

Scope: question search/filter/pagination, create/edit, protected deletion, batch knowledge-point assignment; knowledge-catalog hierarchy, create/edit/move, protected leaf deletion. Existing answers, rubrics and learning records are retained. No AI generation, notifications, orders or production changes in this phase.

1. Add dedicated backoffice operations in `backend/backoffice/quizzes.py`; register both Django and Directus whitelists. Reuse model choices and the internal question serializer, validate content ownership and assessment fields. Validate tree cycles and invalidate student-tree caches after commit.
2. Add `admin-extension/src/Questions.vue` and `Knowledge.vue`, using existing dialogs, table styling, request/error handling and server-side audit. Expose ordinary form controls for options and answers; keep existing structured rubrics unless explicitly edited.
3. Add focused tests for scoped writes, invalid objective answers, cyclic moves and deletion with learning references. Run only these new checks plus extension type-check/build and Django system checks. No full regression, real-student fixtures or production writes.
4. Restart the isolated local preview and inspect the new pages on desktop/mobile. Keep the original Django admin as an operations fallback; report local delivery separately from production release.

Local delivery: the two focused tests pass, including Django system checks; extension `npm run check` and `npm run build` pass. The isolated preview at `127.0.0.1:8057` loads both sections. One existing fictional question and one fictional catalog leaf were saved through the UI; desktop lists and the 390px catalog dialog were inspected. No real student records, production services or registration defaults were changed. No deployment, commit or push was performed.
