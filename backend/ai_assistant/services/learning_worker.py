"""Run browser code locally in development, or in a bounded production unit."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from django.conf import settings


def run(filename, data, *, max_output_bytes=65536):
    with ExitStack() as stack:
        environment = {'PATH': os.defpath, 'HOME': str(Path.home())}
        command = [sys.executable, str(Path(__file__).with_name(filename))]
        if not settings.DEBUG:
            import fcntl
            root = Path(settings.UNIMIND_LEARNING_WORKER_ROOT)
            if not root.is_absolute() or not (root / 'venv/bin/python').is_file():
                raise ValueError('学习运行器尚未配置。')
            slots = root / 'slots'
            slots.mkdir(mode=0o700, exist_ok=True)
            for index in range(2):
                slot = (slots / str(index)).open('a')
                try:
                    fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    slot.close()
                    continue
                stack.enter_context(slot)
                break
            else:
                raise ValueError('学习运行器繁忙，请稍后重试。')
            command = ['/usr/bin/systemd-run', '--quiet', '--pipe', '--wait', '--collect',
                f'--unit=unimind-learning-{index}', '--uid=unimind-learning',
                '--property=MemoryMax=512M', '--property=MemorySwapMax=0',
                '--property=TasksMax=96', '--property=CPUQuota=100%', '--property=RuntimeMaxSec=10s',
                '--property=PrivateNetwork=yes', '--property=PrivateTmp=yes',
                '--property=NoNewPrivileges=yes', '--property=ProtectSystem=strict',
                '--property=ProtectHome=yes', '--property=InaccessiblePaths=/opt/unimind /opt/unimind-venvs /var/lib/unimind',
                '--property=ReadWritePaths=/var/lib/unimind-learning',
                '--setenv=HOME=/var/lib/unimind-learning', f'--setenv=PLAYWRIGHT_BROWSERS_PATH={root / "browsers"}',
                str(root / 'venv/bin/python'), str(root / filename)]
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, start_new_session=True, env=environment) as process:
            try:
                output, _ = process.communicate(json.dumps(data), timeout=12)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise
        if process.returncode or len(output.encode()) > max_output_bytes:
            raise ValueError('学习运行器未能完成，请稍后重试。')
        return json.loads(output)
