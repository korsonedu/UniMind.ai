from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsMember

from .models import KnowledgePoint, UserKnowledgeState


def _mastery_to_color(mastery_score: float) -> str:
    if mastery_score >= 0.8:
        return "#10b981"  # green
    if mastery_score >= 0.6:
        return "#84cc16"  # lime
    if mastery_score >= 0.4:
        return "#f59e0b"  # amber
    return "#ef4444"  # red


def _mastery_to_state(mastery_score: float) -> str:
    if mastery_score >= 0.8:
        return "mastered"
    if mastery_score >= 0.6:
        return "stable"
    if mastery_score >= 0.4:
        return "learning"
    return "weak"


class UserHeatmapView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        all_kps = list(
            KnowledgePoint.objects.all().values("id", "name", "parent_id", "level", "code")
        )
        score_map = {
            row["knowledge_point_id"]: float(row["mastery_score"] or 0.0)
            for row in UserKnowledgeState.objects.filter(user=request.user).values(
                "knowledge_point_id", "mastery_score"
            )
        }

        nodes = []
        weak_count = 0
        mastered_count = 0
        total = len(all_kps)
        weak_map = {}

        for kp in all_kps:
            mastery_score = score_map.get(kp["id"], 0.0)
            color = _mastery_to_color(mastery_score)
            state = _mastery_to_state(mastery_score)
            if state == "weak":
                weak_count += 1
                weak_map[kp["id"]] = {
                    "id": kp["id"],
                    "name": kp["name"],
                    "score": round(mastery_score, 4),
                    "parent_id": kp["parent_id"],
                }
            if state == "mastered":
                mastered_count += 1
            nodes.append(
                {
                    "id": kp["id"],
                    "name": kp["name"],
                    "code": kp["code"],
                    "parent": kp["parent_id"],
                    "level": kp["level"],
                    "mastery_score": round(mastery_score, 4),
                    "color": color,
                    "state": state,
                    "weight": round(1.0 - mastery_score, 4),
                }
            )

        bottlenecks = []
        for _, item in weak_map.items():
            parent_id = item.get("parent_id")
            if not parent_id or parent_id not in weak_map:
                continue
            bottlenecks.append(
                {
                    "knowledge_point_id": item["id"],
                    "knowledge_point_name": item["name"],
                    "knowledge_point_score": item["score"],
                    "parent_id": parent_id,
                    "parent_name": weak_map[parent_id]["name"],
                    "parent_score": weak_map[parent_id]["score"],
                }
            )

        return Response(
            {
                "nodes": nodes,
                "summary": {
                    "total_nodes": total,
                    "mastered_nodes": mastered_count,
                    "weak_nodes": weak_count,
                    "mastered_ratio": round((mastered_count / total), 4) if total else 0.0,
                },
                "bottlenecks": bottlenecks[:8],
            }
        )
