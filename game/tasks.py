"""Background tasks: game timers, Robo's moves, grace periods, online-status timers."""

import asyncio
import logging

logger = logging.getLogger(__name__)

# The event loop keeps only a weak reference to a task, so hold one until it ends,
# and log whatever kills it.
_background_tasks = set()


def spawn(coro):
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_task_done)
    return task


def _task_done(task):
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error('Background task failed', exc_info=task.exception())
