def legacy_subject(points, point_id):
    seen = set()
    subject = ''
    while point_id and point_id not in seen:
        seen.add(point_id)
        point = points.get(point_id)
        if not point:
            break
        if point.get('subject'):
            return point['subject'].strip()
        subject = point['name']
        point_id = point['parent_id']
    return subject
