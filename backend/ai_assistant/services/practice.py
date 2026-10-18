import hashlib


def practice_grade_cache_key(session_id, question_id, answer):
    digest = hashlib.sha256(answer.strip().encode()).hexdigest()
    return f'practice:grade:{session_id}:{question_id}:{digest}'
