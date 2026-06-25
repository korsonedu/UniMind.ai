"""
Knowledge tree traversal helpers.

Replaces N+1 recursive queries with a single bulk fetch + in-memory BFS.
"""

from quizzes.models import KnowledgePoint


def get_descendant_kp_ids(sub_ids):
    """
    Given SUB-level KnowledgePoint IDs, return all descendant KP-level node IDs.

    Fetches all non-root tree nodes in a single query, then performs BFS
    in-memory to collect all kp-level descendants.

    Args:
        sub_ids: Iterable of SUB-level KnowledgePoint IDs.

    Returns:
        List of KP-level KnowledgePoint IDs that are descendants of any of
        the given sub_ids.
    """
    if not sub_ids:
        return []

    # Single query: fetch all non-root nodes (ch, sec, kp) at once
    nodes = KnowledgePoint.objects.exclude(level='sub').values_list(
        'id', 'parent_id', 'level'
    )

    # Build parent_id -> [(child_id, level)] adjacency map in memory
    children_map = {}
    for child_id, parent_id, level in nodes:
        children_map.setdefault(parent_id, []).append((child_id, level))

    # BFS from the given sub-level IDs, collecting kp-level descendants
    kp_ids = []
    queue = list(sub_ids)
    while queue:
        parent_id = queue.pop()
        for child_id, child_level in children_map.get(parent_id, []):
            if child_level == 'kp':
                kp_ids.append(child_id)
            else:
                queue.append(child_id)

    return kp_ids
