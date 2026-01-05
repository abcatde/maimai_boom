import datetime
import asyncio
from src.common.logger import get_logger

logger = get_logger("boom_plugin.scheduler")


class _SimpleJob:
    def __init__(self, id: str | None, name: str | None):
        self.id = id
        self.name = name
        self.next_run_time = None
        self._cancel = False

    def cancel(self):
        self._cancel = True


class SimpleScheduler:
    """一个轻量级的异步调度器，提供 add_job/get_job/get_jobs 接口。"""
    def __init__(self):
        self._jobs: dict[str, _SimpleJob] = {}

    def add_job(self, func, trigger: str, hours: float = 1.0, id: str | None = None, name: str | None = None, next_run_time=None, **kwargs):
        job = _SimpleJob(id=id, name=name)
        self._jobs[id or name or str(id)] = job
        try:
            interval = max(0.0, float(hours)) * 3600.0
            job.next_run_time = datetime.datetime.now() + datetime.timedelta(seconds=interval)
        except Exception:
            job.next_run_time = None

        async def _runner():
            interval = max(0.0, float(hours)) * 3600.0
            while not job._cancel:
                now = datetime.datetime.now()
                job.next_run_time = now + datetime.timedelta(seconds=interval)
                try:
                    result = func()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("调度任务执行出错")
                await asyncio.sleep(interval)

        try:
            asyncio.create_task(_runner())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.get_event_loop().run_in_executor(None, loop.run_forever)
            loop.call_soon_threadsafe(lambda: asyncio.run(_runner()))

        return job

    def get_job(self, id: str):
        return self._jobs.get(id)

    def get_jobs(self):
        return list(self._jobs.values())
