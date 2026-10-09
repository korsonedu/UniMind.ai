#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

cd "$BACKEND_DIR"

if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python3 manage.py shell <<'PY'
from rest_framework.test import APIClient
from users.models import User
from faq_system.models import Question

user, _ = User.objects.get_or_create(
    username="smoke_member",
    defaults={"is_member": True, "email": "smoke@example.com"},
)
if not user.is_member:
    user.is_member = True
    user.save(update_fields=["is_member"])

client = APIClient()
client.force_authenticate(user=user)

r = client.get('/api/qa/questions/?filter=all&search=', HTTP_HOST='localhost')
assert r.status_code == 200, f"GET /api/qa/questions expected 200, got {r.status_code}"

payload = {"content": "smoke test question"}
r2 = client.post('/api/qa/questions/', payload, format='multipart', HTTP_HOST='localhost')
assert r2.status_code == 201, f"POST /api/qa/questions expected 201, got {r2.status_code}"

qid = r2.data.get('id')
if qid:
    Question.objects.filter(id=qid).delete()

print('[OK] QA smoke passed')
PY
