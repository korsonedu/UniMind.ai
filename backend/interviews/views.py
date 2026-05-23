import json
import logging
import time
from typing import List

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import StreamingHttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import HasPlanFeature, HasQuota
from users.views import IsMember
from users.quota import increment_quota
from quizzes.models import KnowledgePoint
from .models import InterviewSession, InterviewTurn, ResumeRecord
from .services import InterviewAIService

logger = logging.getLogger(__name__)


def _serialize_turn(turn: InterviewTurn) -> dict:
    return {
        "id": turn.id,
        "turn_number": turn.turn_number,
        "speaker": turn.speaker,
        "content_text": turn.content_text,
        "audio_url": turn.audio_url,
        "latency_ms": turn.latency_ms,
        "feedback_for_turn": turn.feedback_for_turn,
        "created_at": turn.created_at,
    }


def _serialize_session(session: InterviewSession, include_turns: bool = False) -> dict:
    data = {
        "id": session.id,
        "session_type": session.session_type,
        "interviewer_style": session.interviewer_style,
        "status": session.status,
        "radar_scores": session.radar_scores or {},
        "overall_feedback": session.overall_feedback or "",
        "started_at": session.started_at,
        "finished_at": session.finished_at,
        "websocket_path": f"/ws/interviews/{session.id}/",
    }
    if include_turns:
        turns = list(session.turns.all().order_by("turn_number", "created_at"))
        data["turns"] = [_serialize_turn(t) for t in turns]
    return data


class InterviewSessionListCreateView(APIView):
    permission_classes = [IsMember, HasPlanFeature, HasQuota]
    required_feature = 'interview.mock'
    quota_resource = 'interview'

    def get(self, request):
        sessions = InterviewSession.objects.filter(user=request.user).order_by("-started_at")[:50]
        return Response({"results": [_serialize_session(s) for s in sessions]})

    def post(self, request):
        session_type = str(request.data.get("session_type", "professional")).strip()
        interviewer_style = str(request.data.get("interviewer_style", "friendly")).strip()
        valid_types = {choice[0] for choice in InterviewSession.SESSION_TYPES}
        valid_styles = {choice[0] for choice in InterviewSession.STYLE_CHOICES}

        if session_type not in valid_types:
            return Response({"error": "无效的 session_type"}, status=400)
        if interviewer_style not in valid_styles:
            return Response({"error": "无效的 interviewer_style"}, status=400)

        # 英语口语：语音模型暂未接入，先禁用
        if session_type == 'english':
            return Response({"error": "英语口语面试正在升级语音模型，即将上线，敬请期待"}, status=400)

        # 简历深挖：必须先上传简历
        if session_type == 'resume' and not ResumeRecord.objects.filter(user=request.user).exists():
            return Response({"error": "请先在下方「简历调优」中上传并分析简历，再使用简历深挖功能"}, status=400)

        # 专业课：机构必须有知识树
        if session_type == 'professional':
            inst = request.user.institution
            if inst is None or not KnowledgePoint.objects.filter(institution=inst).exists():
                return Response({"error": "当前机构尚未设置知识结构，请联系机构管理员导入知识树后再使用专业课面试功能"}, status=400)

        session = InterviewSession.objects.create(
            user=request.user,
            session_type=session_type,
            interviewer_style=interviewer_style,
            status="ongoing",
        )

        # 生成 AI 面试官开场白
        opening = ""
        try:
            opening = InterviewAIService.generate_opening_question(session_type, interviewer_style, institution=request.user.institution)
        except Exception:
            logger.exception("opening question generation failed: session=%s", session.id)

        if opening:
            InterviewTurn.objects.create(
                session=session,
                turn_number=1,
                speaker="interviewer",
                content_text=opening,
            )

        return Response(_serialize_session(session, include_turns=True), status=201)


class InterviewSessionDetailView(APIView):
    permission_classes = [IsMember, HasPlanFeature]
    required_feature = 'interview.mock'

    def get(self, request, session_id: int):
        session = get_object_or_404(
            InterviewSession.objects.prefetch_related("turns"),
            id=session_id,
            user=request.user,
        )
        return Response(_serialize_session(session, include_turns=True))


class InterviewTextTurnView(APIView):
    permission_classes = [IsMember, HasPlanFeature]
    required_feature = 'interview.mock'

    def post(self, request, session_id: int):
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        if session.status != "ongoing":
            return Response({"error": "当前会话已结束，无法继续提问"}, status=400)

        user_text = str(request.data.get("text", "")).strip()
        if not user_text:
            return Response({"error": "text 不能为空"}, status=400)

        last_turn = session.turns.order_by("-turn_number", "-created_at").first()
        next_turn_number = int(last_turn.turn_number + 1) if last_turn else 1

        turn_started = time.monotonic()
        candidate_feedback = ""
        try:
            candidate_feedback = InterviewAIService.annotate_candidate_turn(
                session_type=session.session_type,
                answer_text=user_text,
            ) or ""
        except Exception:
            logger.exception("interview turn feedback failed: session=%s", session.id)

        candidate_turn = InterviewTurn.objects.create(
            session=session,
            turn_number=next_turn_number,
            speaker="candidate",
            content_text=user_text,
            feedback_for_turn=candidate_feedback,
        )

        history_messages: List[dict] = []
        for turn in session.turns.order_by("turn_number", "created_at"):
            role = "assistant" if turn.speaker == "interviewer" else "user"
            history_messages.append({"role": role, "content": turn.content_text})

        ai_reply = "已收到你的回答。请继续展开你刚才提到的核心逻辑。"
        try:
            generated = InterviewAIService.generate_interview_reply(
                session_type=session.session_type,
                style=session.interviewer_style,
                chat_history=history_messages,
                institution=session.user.institution,
            )
            if generated:
                ai_reply = generated
        except Exception as exc:  # noqa: BLE001
            logger.exception("interview text turn ai generation failed: session=%s err=%s", session.id, exc)

        latency_ms = int((time.monotonic() - turn_started) * 1000)
        interviewer_turn = InterviewTurn.objects.create(
            session=session,
            turn_number=next_turn_number + 1,
            speaker="interviewer",
            content_text=ai_reply,
            latency_ms=latency_ms,
        )

        # 计入 AI 调用总次数
        if request.user.institution:
            increment_quota(request.user.institution, 'ai_call_total')

        return Response(
            {
                "session_id": session.id,
                "candidate_turn": _serialize_turn(candidate_turn),
                "interviewer_turn": _serialize_turn(interviewer_turn),
                "reply": ai_reply,
            }
        )


class InterviewReplyStreamView(APIView):
    """SSE 流式返回面试官追问，前端逐 token 渲染。"""
    permission_classes = [IsMember, HasPlanFeature]
    required_feature = 'interview.mock'

    def post(self, request, session_id: int):
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        if session.status != "ongoing":
            return Response({"error": "当前会话已结束"}, status=400)

        user_text = str(request.data.get("text", "")).strip()
        if not user_text:
            return Response({"error": "text 不能为空"}, status=400)

        last_turn = session.turns.order_by("-turn_number", "-created_at").first()
        next_turn_number = int(last_turn.turn_number + 1) if last_turn else 1

        # 保存 candidate turn（annotation 跳过，流式场景不做逐句反馈）
        candidate_turn = InterviewTurn.objects.create(
            session=session,
            turn_number=next_turn_number,
            speaker="candidate",
            content_text=user_text,
        )

        history_messages: List[dict] = []
        for turn in session.turns.order_by("turn_number", "created_at"):
            role = "assistant" if turn.speaker == "interviewer" else "user"
            history_messages.append({"role": role, "content": turn.content_text})

        def generate():
            collected: list[str] = []
            try:
                for token in InterviewAIService.generate_interview_reply_stream(
                    session_type=session.session_type,
                    style=session.interviewer_style,
                    chat_history=history_messages,
                    institution=session.user.institution,
                ):
                    if token is None:
                        break
                    collected.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"
            except Exception:
                logger.exception("interview stream failed: session=%s", session.id)
            finally:
                reply_text = "".join(collected).strip() or "已收到你的回答。请继续展开你刚才提到的核心逻辑。"
                InterviewTurn.objects.create(
                    session=session,
                    turn_number=next_turn_number + 1,
                    speaker="interviewer",
                    content_text=reply_text,
                    latency_ms=0,
                )
                yield f"data: {json.dumps({'done': True})}\n\n"
                # 计入 AI 调用总次数
                if collected and session.user.institution:
                    increment_quota(session.user.institution, 'ai_call_total')

        return StreamingHttpResponse(
            generate(),
            content_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )


class InterviewFinishView(APIView):
    permission_classes = [IsMember, HasPlanFeature]
    required_feature = 'interview.mock'

    def post(self, request, session_id: int):
        session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
        if session.status == "completed":
            return Response(_serialize_session(session, include_turns=True))

        session.status = "analyzing"
        session.save(update_fields=["status"])

        chat_history = []
        turns = list(session.turns.order_by("turn_number", "created_at"))
        for turn in turns:
            role = "interviewer" if turn.speaker == "interviewer" else "candidate"
            chat_history.append({"role": role, "content": turn.content_text})

        radar_scores = {}
        overall_feedback = ""
        try:
            report = InterviewAIService.generate_post_interview_radar(chat_history) or {}
            radar_scores = report.get("radar_scores") if isinstance(report.get("radar_scores"), dict) else {}
            overall_feedback = str(report.get("overall_feedback") or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.exception("interview finish radar generation failed: session=%s err=%s", session.id, exc)

        session.status = "completed"
        session.finished_at = timezone.now()
        session.radar_scores = radar_scores
        session.overall_feedback = overall_feedback
        session.save(update_fields=["status", "finished_at", "radar_scores", "overall_feedback"])

        return Response(_serialize_session(session, include_turns=True))


class ResumeTuneView(APIView):
    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTS = {'.pdf', '.docx', '.txt'}

    permission_classes = [IsMember, HasPlanFeature]
    required_feature = 'interview.mock'

    def get(self, request):
        """列出当前用户的简历调优记录"""
        records = ResumeRecord.objects.filter(user=request.user).order_by("-created_at")[:20]
        results = []
        for r in records:
            results.append({
                "id": r.id,
                "score": r.optimized_content.get("score") if isinstance(r.optimized_content, dict) else None,
                "diagnostics": r.optimized_content.get("diagnostics") if isinstance(r.optimized_content, dict) else "",
                "optimized_content": r.optimized_content if isinstance(r.optimized_content, dict) else {},
                "predicted_questions": r.predicted_questions if isinstance(r.predicted_questions, list) else [],
                "parsed_content": r.parsed_content[:500],
                "created_at": r.created_at,
            })
        return Response({"results": results})

    def post(self, request):
        resume_text = str(request.data.get("resume_text", "")).strip()
        resume_file = request.FILES.get("file")
        if resume_file is not None:
            if resume_file.size > self.MAX_SIZE:
                return Response({'error': f'文件大小不能超过 {self.MAX_SIZE // (1024*1024)}MB'}, status=400)
            file_ext = '.' + str(resume_file.name).rsplit('.', 1)[-1].lower() if '.' in str(resume_file.name) else ''
            if file_ext not in self.ALLOWED_EXTS:
                return Response({'error': '仅支持 PDF / DOCX / TXT 格式'}, status=400)
        if not resume_text and resume_file is not None:
            parsed = ""
            name = str(getattr(resume_file, "name", "")).lower()
            try:
                if name.endswith(".pdf"):
                    from pypdf import PdfReader
                    reader = PdfReader(resume_file)
                    parsed = "\n".join((page.extract_text() or "") for page in reader.pages)
                elif name.endswith(".docx"):
                    from docx import Document
                    doc = Document(resume_file)
                    parsed = "\n".join(p.text for p in doc.paragraphs)
                else:
                    parsed = resume_file.read().decode("utf-8", errors="ignore")
            except Exception:
                logger.exception("resume parse failed")
                parsed = ""
            resume_text = parsed.strip()
        if not resume_text:
            return Response({"error": "resume_text 不能为空，或上传文件解析失败。"}, status=400)

        try:
            payload = InterviewAIService.tune_resume(resume_text) or {}
        except Exception as exc:  # noqa: BLE001
            logger.exception("resume tune failed: err=%s", exc)
            payload = {}

        optimized = payload.get("optimized_content") if isinstance(payload, dict) else {}
        if isinstance(optimized, dict):
            optimized["score"] = payload.get("score") if isinstance(payload, dict) else None
            optimized["diagnostics"] = payload.get("diagnostics") if isinstance(payload, dict) else ""

        record = ResumeRecord.objects.create(
            user=request.user,
            parsed_content=resume_text,
            optimized_content=optimized,
            predicted_questions=payload.get("predicted_questions") if isinstance(payload, dict) else [],
        )
        if resume_file is not None:
            record.original_file = resume_file
            record.save(update_fields=["original_file", "updated_at"])

        return Response({"record_id": record.id, "result": payload})
