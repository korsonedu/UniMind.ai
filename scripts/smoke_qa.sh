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

user, _ = User.objects.get_or_create(
    username="smoke_member",
    defaults={"is_member": True, "email": "smoke@example.com"},
)
if not user.is_member:
    user.is_member = True
    user.save(update_fields=["is_member"])

client = APIClient()
client.force_authenticate(user=user)

for path in ('/api/qa/questions/', '/api/study/messages/'):
    for response in (client.get(path, HTTP_HOST='localhost'),
                     client.post(path, {'content': 'smoke test'}, format='json', HTTP_HOST='localhost')):
        assert response.status_code == 404, f"{path} expected 404, got {response.status_code}"

print('[OK] Retired community endpoints return 404')
PY
