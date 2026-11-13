import asyncio
import os
import socket
import subprocess
import sys
import time

import httpx
import uvicorn

from ideadesk.main import run_all
from ideadesk.service import Service
from ideadesk.web import create_app, hash_password


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_start_without_a_required_setting_fails_naming_it(tmp_path):
    env = {
        "PATH": os.environ["PATH"], "PYTHONPATH": "app", "SECRETS_DIR": str(tmp_path),
        "TELEGRAM_BOT_TOKEN": "t", "OWNER_TELEGRAM_ID": "1", "SITE_PASSWORD_HASH": "h",
        "LIBRARY_REPO_URL": "u", "LIBRARY_GIT_TOKEN": "g", "PUBLIC_BASE_URL": "https://x", "CLAUDE_CODE_OAUTH_TOKEN": "c",
    }  # SESSION_SECRET manque
    done = subprocess.run([sys.executable, "-m", "ideadesk.main"], env=env, capture_output=True, text=True, timeout=30)
    assert done.returncode != 0 and "SESSION_SECRET" in done.stderr


def test_site_answers_while_polling_runs_and_shutdown_stops_polling_and_finishes_writes(store):
    port = free_port()
    app = create_app(store, hash_password("pw"), "secret")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    events = {"polling": False, "stopped": False, "write_done": False}

    async def go():
        stop = asyncio.Event()

        async def start_poll():
            events["polling"] = True
            await stop.wait()

        async def stop_poll():
            events["stopped"] = True
            stop.set()

        service = Service(store, None, None, "https://x.example", 1)
        service.start()

        async def slow_write():
            await asyncio.sleep(0.3)
            events["write_done"] = True

        service._queue.put_nowait(slow_write)
        main_task = asyncio.create_task(run_all(server, service, start_poll, stop_poll))
        async with httpx.AsyncClient() as client:
            for _ in range(100):
                try:
                    res = await client.get(f"http://127.0.0.1:{port}/healthz")
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)
        assert res.status_code == 200 and events["polling"]
        server.should_exit = True
        await asyncio.wait_for(main_task, 10)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(go())
    finally:
        loop.close()
    assert events["stopped"] and events["write_done"]
