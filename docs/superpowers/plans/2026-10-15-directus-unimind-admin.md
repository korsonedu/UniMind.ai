# Directus UniMind Admin Implementation Plan

> Execution: inline, as explicitly requested by the user. No additional approval checkpoint before implementation. No commit or production deployment in this run.

**Goal:** Add a Directus business module for course/module management and student/service grants, backed by authenticated Django operations.

**Architecture:** A Directus bundle contains a Vue module and an authenticated endpoint proxy. The proxy signs a fixed set of JSON operations; Django authenticates an explicit two-operator mapping, executes existing business services, and records separate audit identities. Media uploads go directly to OSS or through a size-limited small-file endpoint.

**Tech Stack:** Directus 12.4.1-compatible extension SDK, Vue 3, TypeScript, Django/DRF, existing Redis and OSS services.

**Spec:** `docs/superpowers/specs/2026-10-15-directus-unimind-admin-design.md`

## Constraints

- Preserve the user's change in `backend/courses/access.py` exactly.
- Do not touch the website repository, its database, accounts, or production Directus. Local port 8055 is an SSH tunnel, not an isolated development instance.
- Keep operator secrets on the server, require two explicit identity mappings, reject replayed or forged requests, and keep learning-side authentication unchanged.
- No automatic user creation or privilege elevation in request handling.
- Focused checks only: authentication boundary, module ownership, grant idempotency, builds and one isolated local workflow.

## Review Focus

- Signed identity, operation and payload cannot be substituted or replayed.
- Both operators receive equal access but produce different audit users.
- Bulk classification cannot partly move courses or cross content ownership.
- Repeated grant requests cannot create extra service time.
- Large video files cannot pass through Directus memory; completed upload keys cannot be substituted.

## Tasks

### 1. Backend Authentication and Operations

Files: `backend/backoffice/{authentication,views,urls,common,courses,people,uploads}.py`, `backend/school_system/{settings,urls}.py`, and a nullable unique request UUID on `LearningGrant` with a new migration.

- [x] Add explicit server settings for bridge secret, two-operator map and content institution.
- [x] Authenticate HMAC requests using operator, method, path, timestamp, nonce and SHA-256 body digest; reject invalid identities and cache failures.
- [x] Add a fixed operation dispatcher and transactional audit writes to `SecurityAuditLog`.
- [x] Implement management-only course/module queries, validated saves, protected deletion and atomic assignment.
- [x] Implement student lookup/detail, existing product validation, idempotent grants and revocation without changing course visibility.
- [x] Add three focused test cases for authentication/replay, ownership and grant idempotency; run only these tests and Django checks.

Contract: `POST /api/backoffice/operations/<operation>/` accepts a JSON object and returns a JSON result. Read operations do not mutate records. Write operations validate a request UUID and record actor, target and result without sensitive request bodies.

### 2. Media Control

Files: `backend/backoffice/uploads.py`, `admin-extension/src/upload.ts`.

- [x] Reuse existing file validation and OSS bucket construction.
- [x] Bind an upload to operator, course, content institution and intended field using expiring signed state.
- [x] Return short-lived part URLs and a signed ticket; validate completed object identity, file header and actual size before attachment.
- [x] Attach only to the corresponding course and field; use the same bounded OSS flow for small files and support cancellation.

### 3. Directus Bundle and Business UI

Files: `admin-extension/package.json`, `src/{module,endpoint}/index.ts`, `src/bridge.ts`, `src/{ModuleRoot,Workspace,Courses,People}.vue`, `src/{api,types,upload}.ts`, `src/style.css`.

- [x] Build an API/module bundle using the Directus SDK and Vue.
- [x] Require Directus administrator accountability plus the configured operator allowlist; never accept browser-supplied target URLs or authentication headers.
- [x] Build quiet table-based interfaces with search, paging, classification, dialogs, errors and submission states.
- [x] Expose only implemented navigation: courses/modules, students/services, audit.
- [x] Add course editing with media progress and protected delete; add products, grant confirmation and revocation confirmation.
- [x] Type-check and build extension output, without including it in the learning frontend.

### 4. Isolated Preview and Delivery

Files: `admin-extension/README.md`, `.env.example`, local preview configuration and fixtures.

- [x] Use a separate preview database and separate Directus port if a local runtime is available; never use the SSH tunnel on 8055.
- [x] Keep fixture names and accounts explicitly confined to the preview database.
- [x] Verify one course classification and one grant workflow in the isolated preview; report runtime limits accurately if unavailable.
- [x] Document operator mapping, private server variables, extension mounting and rollback.
- [x] Run one final fresh-context code review and address important issues; leave existing user edits intact.

## Execution Record

- Start: existing main checkout is reused per the user's direct execution request. Existing uncommitted course-access change is outside ownership and remains untouched.
- Start: production account identifiers are not yet supplied. Implement fail-closed configuration and isolate preview identities; do not claim production account integration.
- Implementation: use one OSS direct-upload path for all supported media, including small files, to avoid a second buffered upload API. No production OSS calls were made.
- Verification: three focused Django tests pass, migration dry-run reports no changes, Vue type check and extension build pass. Directus 12.4.1 loads the bundle in an isolated container on 8057; dedicated Django runs on 8002 with its own SQLite database.
- Preview: one course was assigned to a module and one service was granted through the actual UI. AI usage updated from 0/100 to 0/200. A second isolated operator saved a module with its own mapped Django identity.
- Review: fixed missing post-commit video processing, stale transcript/outline handling, and cleanup of failed completed OSS objects. Read-only re-review found no remaining blocking issue in those fixes.
- Delivery boundary: no real administrator accounts configured, no production extension mounted, no commit/push/deployment performed. The user's course-access edit remains unchanged.
