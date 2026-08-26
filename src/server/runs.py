import asyncio
import time

import attr
from loguru import logger

from server.llm.client import ChatRequest
from server.llm.client import ChatTurn
from server.llm.client import LlmClient
from server.llm.events import Completed
from server.llm.events import Delta
from server.llm.events import DeltaKind
from server.llm.events import Failed
from server.models import Effort
from server.models import Message
from server.models import MessageStatus
from server.models import Role
from server.models import Usage
from server.store import Store

# How often partial output is flushed to sqlite while streaming.  A crash loses at most this
# much; every chunk would be a write per token.
_FLUSH_INTERVAL_SECONDS = 1.0

# Finished runs stay in memory this long so a tab that reconnects mid-stream can replay from its
# cursor instead of refetching.  After that the DB copy is the only one, which is enough.
_RETAIN_FINISHED_SECONDS = 600.0

# How long shutdown waits for cancelled runs to flush their partial output.
_SHUTDOWN_GRACE_SECONDS = 5.0

_DEFAULT_TITLE = "New chat"


@attr.s(auto_attribs=True, frozen=True)
class Chunk:
    kind: DeltaKind
    text: str


class Run:
    """One in-flight assistant response.

    Owns the accumulating text and fans it out to any number of connected tabs.  It keeps running
    (and keeps writing to the DB) when every subscriber disconnects, so closing the tab that
    started a response doesn't throw the response away.
    """

    def __init__(self, chat_id: str, message_id: str) -> None:
        self.chat_id = chat_id
        self.message_id = message_id
        self.chunks: list[Chunk] = []
        self.content = ""
        self.reasoning = ""
        self.status = MessageStatus.STREAMING
        self.error: str | None = None
        self.usage: Usage | None = None
        self.title: str | None = None
        # Set once the title attempt is over (generated, skipped, or failed), so a subscriber can
        # wait for the title without hanging when there'll never be one.
        self.title_settled = False
        self.finished_at: float | None = None
        self._condition = asyncio.Condition()
        self._task: asyncio.Task[None] | None = None

    def set_task(self, task: asyncio.Task[None]) -> None:
        self._task = task

    @property
    def task(self) -> "asyncio.Task[None] | None":
        return self._task

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

    async def append(self, chunk: Chunk) -> None:
        async with self._condition:
            self.chunks.append(chunk)
            if chunk.kind is DeltaKind.CONTENT:
                self.content += chunk.text
            else:
                self.reasoning += chunk.text
            self._condition.notify_all()

    async def notify(self) -> None:
        async with self._condition:
            self._condition.notify_all()

    async def wait_past(self, cursor: int) -> None:
        """Block until there's a chunk at index ``cursor`` or the run is over."""
        async with self._condition:
            await self._condition.wait_for(lambda: len(self.chunks) > cursor or self.is_finished)

    async def wait_for_title(self) -> str | None:
        async with self._condition:
            await self._condition.wait_for(lambda: self.title_settled)
        return self.title

    def cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()


class RunManager:
    def __init__(self, store: Store, client: LlmClient) -> None:
        self._store = store
        self._client = client
        self._runs: dict[str, Run] = {}

    def get(self, message_id: str) -> Run | None:
        return self._runs.get(message_id)

    def cancel(self, message_id: str) -> bool:
        run = self._runs.get(message_id)
        if run is None or run.is_finished:
            return False
        run.cancel()
        return True

    async def shutdown(self) -> None:
        """Cancel every in-flight run and wait for it to write its partial output, so the
        database isn't closed out from under a task still persisting."""
        tasks = [run.task for run in self._runs.values() if run.task is not None and not run.task.done()]
        for run in self._runs.values():
            run.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=_SHUTDOWN_GRACE_SECONDS)

    def _prune(self) -> None:
        cutoff = time.monotonic() - _RETAIN_FINISHED_SECONDS
        for message_id, run in list(self._runs.items()):
            if run.finished_at is not None and run.finished_at < cutoff:
                del self._runs[message_id]

    def start(self, chat_id: str, assistant_message: Message, model: str, effort: Effort) -> Run:
        self._prune()
        existing = self._runs.get(assistant_message.id)
        if existing is not None and not existing.is_finished:
            return existing
        run = Run(chat_id=chat_id, message_id=assistant_message.id)
        self._runs[assistant_message.id] = run
        run.set_task(asyncio.create_task(self._drive(run, model, effort)))
        return run

    def _history(self, chat_id: str, up_to_message_id: str) -> list[ChatTurn]:
        """The conversation to send upstream: every earlier turn that actually has text.

        Partial output from a cancelled or errored turn still counts — the user saw it, so the
        model should too.
        """
        turns: list[ChatTurn] = []
        for message in self._store.get_messages(chat_id):
            if message.id == up_to_message_id:
                break
            if not message.content.strip():
                continue
            turns.append(ChatTurn(role=message.role.value, content=message.content))
        return turns

    async def _drive(self, run: Run, model: str, effort: Effort) -> None:
        try:
            await self._stream_response(run, model, effort)
        except asyncio.CancelledError:
            run.status = MessageStatus.CANCELLED
            self._persist(run)
            await self._finish(run)
            await self._settle_title(run)
            raise
        except Exception as e:
            logger.opt(exception=True).error("run {} failed", run.message_id)
            run.status = MessageStatus.ERROR
            run.error = f"Unexpected error: {e}"
            self._persist(run)
            await self._finish(run)
            await self._settle_title(run)
            return

        self._persist(run)
        await self._finish(run)
        if run.status is MessageStatus.COMPLETE:
            await self._maybe_title(run, model)
        await self._settle_title(run)

    async def _stream_response(self, run: Run, model: str, effort: Effort) -> None:
        request = ChatRequest(model=model, effort=effort, messages=self._history(run.chat_id, run.message_id))
        last_flush = time.monotonic()
        async for event in self._client.stream_chat(request):
            if isinstance(event, Delta):
                await run.append(Chunk(kind=event.kind, text=event.text))
                if time.monotonic() - last_flush >= _FLUSH_INTERVAL_SECONDS:
                    self._store.save_message_progress(run.message_id, run.content, run.reasoning)
                    last_flush = time.monotonic()
            elif isinstance(event, Failed):
                run.status = MessageStatus.ERROR
                run.error = event.message
                return
            elif isinstance(event, Completed):
                run.usage = event.usage
                run.status = MessageStatus.COMPLETE

    def _persist(self, run: Run) -> None:
        """Never let a persistence failure strand the run: subscribers must still be released."""
        try:
            self._store_finish(run)
        except Exception:
            logger.opt(exception=True).error("could not persist run {}", run.message_id)

    def _store_finish(self, run: Run) -> None:
        self._store.finish_message(
            run.message_id,
            content=run.content,
            reasoning=run.reasoning,
            status=run.status,
            error=run.error,
            usage=run.usage,
        )

    async def _finish(self, run: Run) -> None:
        # Set the flag before awaiting: notify() runs on an already-cancelled task in the stop
        # path and may not get there, but a subscriber's next heartbeat tick will see this.
        run.finished_at = time.monotonic()
        await run.notify()

    async def _settle_title(self, run: Run) -> None:
        run.title_settled = True
        await run.notify()

    async def _maybe_title(self, run: Run, model: str) -> None:
        chat = self._store.get_chat(run.chat_id)
        if chat is None or chat.title != _DEFAULT_TITLE:
            return
        messages = self._store.get_messages(run.chat_id)
        first_user = next((m for m in messages if m.role is Role.USER and m.content.strip()), None)
        if first_user is None:
            return
        title = await self._client.generate_title(first_user.content, model) or _fallback_title(first_user.content)
        self._store.update_chat(run.chat_id, title=title, touch=False)
        run.title = title
        await run.notify()


def _fallback_title(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return (first_line[:60] + "…") if len(first_line) > 60 else (first_line or _DEFAULT_TITLE)
