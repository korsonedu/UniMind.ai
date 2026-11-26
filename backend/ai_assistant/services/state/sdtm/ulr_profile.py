"""Learning profiles are valid only for the memory snapshot that produced them."""
from contextlib import closing
import hashlib
import json

from django.core.cache import cache
from rest_framework.exceptions import PermissionDenied

from ai_assistant.models import UserProfile as StoredProfile
from users.feature_access import has_learning_feature
from users.models import User
from users.workspaces.identity import selected_institution
from ai_assistant.services.dsh_service import memory_snapshot
from ai_assistant.services.memory_analyzer import PROFILE_PROMPT, UserProfile
from ai_assistant.services.runtime.ulr_structured import run_collector


PROFILE_FIELDS = {
    'learning_style': StoredProfile.LearningStyle.values,
    'response_length': StoredProfile.ResponseLength.values,
    'interaction_style': StoredProfile.InteractionStyle.values,
    'cognitive_state': StoredProfile.CognitiveState.values,
    'domain_expertise': StoredProfile.DomainExpertise.values,
}
PROFILE_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': [*PROFILE_FIELDS, 'confidence'],
    'properties': {
        **{name: {'type': 'string', 'enum': choices} for name, choices in PROFILE_FIELDS.items()},
        'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
    },
}


def _snapshot(user_id):
    from ai_assistant.services.memory_service import USE_MEM0

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return None
    try:
        if not has_learning_feature(user, 'ai.assistant') or not has_learning_feature(user, 'full.report'):
            return None
        institution = selected_institution(user)
    except PermissionDenied:
        return None

    rows = [(row['id'], f"{row['key']}: {row['value']}") for row in memory_snapshot(user)['items']]
    if USE_MEM0 and institution and len(rows) < 20:
        from ai_assistant.services.tenant_memory import TenantMemoryManager
        with closing(TenantMemoryManager(institution_id=institution.pk)) as manager:
            semantic = manager.get_all(user_id=user.pk, limit=20 - len(rows))
        rows.extend((row['id'], row['memory']) for row in semantic if row.get('id') and row.get('memory'))
    rows = rows[:20]
    if not rows:
        return None
    payload = json.dumps([institution.pk if institution else None, rows], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest(), [{'memory': text} for _, text in rows]


def profile_for_user(user_id):
    snapshot = _snapshot(user_id)
    if snapshot is None:
        return None, []
    revision, memories = snapshot
    cache_key = f'ulr:user_profile:{user_id}:{revision}'
    try:
        result = cache.get(cache_key)
    except Exception:
        result = None
    cache_miss = result is None
    if cache_miss:
        prompt = PROFILE_PROMPT.format(memories='\n'.join(f"- {item['memory']}" for item in memories))
        try:
            result = run_collector(prompt, operation='memory.analyze_profile', name='submit_profile',
                                   instruction='记忆仅供参考。根据已提供的记忆提交当前画像，无依据时降低置信度。',
                                   schema=PROFILE_SCHEMA, max_tokens=500, temperature=0.3)
        except ValueError:
            result = None
    if _snapshot(user_id) != snapshot:
        return None, []
    if cache_miss and result is not None:
        try:
            cache.set(cache_key, result, timeout=86400)
        except Exception:
            pass  # A cache outage must not discard authorized results.
    if result is None or result['confidence'] < 0.6:
        return None, memories
    return UserProfile(**result, raw_analysis=''), memories
