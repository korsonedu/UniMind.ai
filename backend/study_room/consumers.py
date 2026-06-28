"""
自习室 WebSocket Consumer — 服务器端持有 timer 权威状态，路由切换不断开。
"""

import json
import logging
import asyncio
import time

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from . import session_manager as sm

logger = logging.getLogger(__name__)

TICK_INTERVAL = 10  # 每 10 秒推送一次 timer.tick
IDLE_WARNING_AFTER = 300  # 5 分钟无心跳触发 idle_warning
IDLE_WARNING_COOLDOWN = 300  # idle_warning 冷却时间，避免重复推送
COACH_MILESTONES = [25, 50, 90, 120]  # 累计分钟里程碑


class StudyRoomConsumer(AsyncWebsocketConsumer):
    """自习室 WebSocket，处理 session 生命周期 + timer 同步 + 督学事件。"""

    async def connect(self):
        self.user = self.scope.get('user')
        logger.info("StudyRoom WS connect: user=%s", self.user)

        if not (self.user and self.user.is_authenticated):
            logger.warning("StudyRoom WS rejected: no auth")
            await self.close(code=4001)
            return

        self.user_id = self.user.id
        self._cancelled = asyncio.Event()
        # 防止 timer.expired / milestone 重复推送
        self._timer_expired_sent = False
        self._milestones_sent: set[int] = set()
        self._last_idle_warning_at: float = 0.0
        await self.accept()
        logger.info("StudyRoom WS accepted: user=%s", self.user_id)

        # 发送当前会话状态同步
        session = sm.get_session(self.user_id)
        if session:
            now = time.time()
            timer_end = session.get('timer_end_ts')
            if timer_end and session['status'] == 'active':
                session['time_left'] = max(0, int(timer_end - now))
            elif session['status'] == 'paused':
                session['time_left'] = session.get('remaining_seconds', 0)
            else:
                session['time_left'] = 0
            await self.send(text_data=json.dumps({
                'type': 'session.sync',
                'session': session,
            }, ensure_ascii=False))

        # 启动后台任务
        self._tick_task = asyncio.create_task(self._tick_loop())
        self._idle_task = asyncio.create_task(self._idle_monitor())

    async def disconnect(self, code):
        user_id = getattr(self, 'user_id', None)
        if user_id is None:
            logger.info("StudyRoom WS disconnect before auth: code=%s", code)
            return
        logger.info("StudyRoom WS disconnect: user=%s, code=%s", user_id, code)
        self._cancelled.set()

        if hasattr(self, '_tick_task'):
            self._tick_task.cancel()
        if hasattr(self, '_idle_task'):
            self._idle_task.cancel()

        # 保存快照供重连
        session = sm.get_session(user_id)
        if session:
            now = time.time()
            timer_end = session.get('timer_end_ts')
            if timer_end and session['status'] == 'active':
                session['remaining_seconds'] = max(0, int(timer_end - now))
            sm._save_snapshot(user_id, session)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps(
                {'type': 'error', 'message': 'Invalid JSON'}, ensure_ascii=False))
            return

        msg_type = data.get('type', '')
        logger.info("StudyRoom WS received: user=%s, type=%s", self.user_id, msg_type)

        if msg_type == 'session.start':
            await self._handle_start(data)
        elif msg_type == 'session.pause':
            await self._handle_pause()
        elif msg_type == 'session.resume':
            await self._handle_resume()
        elif msg_type == 'session.end':
            await self._handle_end()
        elif msg_type == 'ping':
            sm.update_heartbeat(self.user_id)
            await self.send(text_data=json.dumps({'type': 'pong'}))
        else:
            await self.send(text_data=json.dumps(
                {'type': 'error', 'message': f'Unknown message type: {msg_type}'},
                ensure_ascii=False))

    # ── Handlers ──

    async def _handle_start(self, data: dict):
        task_name = data.get('task_name', '专注学习')
        duration = int(data.get('duration', 25))
        # 结束上一个会话的 DB 记录（避免孤儿）
        await self._finalize_previous_db_session()
        # 重置防护标志
        self._timer_expired_sent = False
        self._milestones_sent.clear()
        session = sm.start_session(self.user_id, task_name, duration)
        await self.send(text_data=json.dumps({
            'type': 'session.sync',
            'session': {**session, 'time_left': duration * 60},
        }, ensure_ascii=False))
        await self._save_session_record('active', task_name, duration)

    async def _handle_pause(self):
        session = sm.pause_session(self.user_id)
        if session:
            await self.send(text_data=json.dumps({
                'type': 'session.sync',
                'session': session,
            }, ensure_ascii=False))

    async def _handle_resume(self):
        session = sm.resume_session(self.user_id)
        if session:
            now = time.time()
            timer_end = session.get('timer_end_ts')
            time_left = max(0, int(timer_end - now)) if timer_end else 0
            await self.send(text_data=json.dumps({
                'type': 'session.sync',
                'session': {**session, 'time_left': time_left},
            }, ensure_ascii=False))
            await self._update_session_record('active')

    async def _handle_end(self):
        result = sm.end_session(self.user_id)
        if result:
            await self.send(text_data=json.dumps({
                'type': 'session.ended',
                'summary': result,
            }, ensure_ascii=False))
            await self._finalize_session_record(result)

    # ── Background loops ──

    async def _tick_loop(self):
        """每 TICK_INTERVAL 推送一次倒计时。"""
        while not self._cancelled.is_set():
            try:
                await asyncio.sleep(TICK_INTERVAL)
                if self._cancelled.is_set():
                    break

                session = sm.get_session(self.user_id)
                if not session or session['status'] != 'active':
                    continue

                now = time.time()
                timer_end = session.get('timer_end_ts')
                if not timer_end:
                    continue

                time_left = max(0, int(timer_end - now))
                await self.send(text_data=json.dumps({
                    'type': 'timer.tick',
                    'time_left': time_left,
                }, ensure_ascii=False))

                # Timer 到期 — 只发一次
                if time_left <= 0 and not self._timer_expired_sent:
                    self._timer_expired_sent = True
                    total_focus = session.get('total_focus', 0)
                    duration_secs = session.get('duration', 25) * 60
                    # 焦点时间 = 已累积 + 本次完整时长
                    accumulated_focus = total_focus + duration_secs
                    await self.send(text_data=json.dumps({
                        'type': 'timer.expired',
                        'task_name': session.get('task_name', ''),
                        'duration': session.get('duration', 25),
                        'total_focus': accumulated_focus,
                    }, ensure_ascii=False))

                    # 检查里程碑（每个只发一次）
                    total_minutes = accumulated_focus // 60
                    for milestone in COACH_MILESTONES:
                        if total_minutes >= milestone and milestone not in self._milestones_sent:
                            self._milestones_sent.add(milestone)
                            await self.send(text_data=json.dumps({
                                'type': 'coach.event',
                                'event': 'milestone',
                                'total_minutes': total_minutes,
                                'milestone': milestone,
                            }, ensure_ascii=False))

            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("StudyRoom tick loop error", exc_info=True)

    async def _idle_monitor(self):
        """检测空闲状态：5 分钟无心跳触发 idle_warning（冷却期内不重复）。"""
        while not self._cancelled.is_set():
            try:
                await asyncio.sleep(30)
                if self._cancelled.is_set():
                    break

                session = sm.get_session(self.user_id)
                if not session or session['status'] != 'active':
                    continue

                now = time.time()
                last_hb = session.get('heartbeat_ts', 0)
                if last_hb and (now - last_hb) > IDLE_WARNING_AFTER:
                    # 冷却期内不重复推送
                    if now - self._last_idle_warning_at < IDLE_WARNING_COOLDOWN:
                        continue
                    self._last_idle_warning_at = now
                    await self.send(text_data=json.dumps({
                        'type': 'coach.event',
                        'event': 'idle_warning',
                        'idle_seconds': int(now - last_hb),
                    }, ensure_ascii=False))
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("StudyRoom idle monitor error", exc_info=True)

    # ── DB helpers ──

    @database_sync_to_async
    def _finalize_previous_db_session(self):
        """结束用户所有未完成的 DB 记录（新 session 开始时调用）。"""
        from .models import StudySession
        from django.utils import timezone
        qs = StudySession.objects.filter(
            user=self.user, status__in=('active', 'paused')
        )
        if qs.exists():
            qs.update(status='ended', ended_at=timezone.now())

    @database_sync_to_async
    def _save_session_record(self, status: str, task_name: str, duration: int):
        from .models import StudySession
        StudySession.objects.create(
            user=self.user,
            status=status,
            task_name=task_name,
            duration_minutes=duration,
        )

    @database_sync_to_async
    def _update_session_record(self, status: str):
        from .models import StudySession
        from django.utils import timezone
        session = StudySession.objects.filter(
            user=self.user, status__in=('active', 'paused')
        ).order_by('-started_at').first()
        if session:
            session.status = status
            if status == 'paused':
                session.paused_at = timezone.now()
            session.save()

    @database_sync_to_async
    def _finalize_session_record(self, result: dict):
        from .models import StudySession
        from django.utils import timezone
        session = StudySession.objects.filter(
            user=self.user, status__in=('active', 'paused')
        ).order_by('-started_at').first()
        if session:
            session.status = 'ended'
            session.ended_at = timezone.now()
            session.total_focus_seconds = result.get('total_focus_seconds', 0)
            session.save()
