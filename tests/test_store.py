from pathlib import Path

import pytest

from server.db import Database
from server.models import Effort
from server.models import MessageStatus
from server.models import Role
from server.models import Usage
from server.store import _HIT_CLOSE
from server.store import _HIT_OPEN
from server.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(Database(tmp_path / "chats.sqlite"))


def test_messages_get_sequential_positions(store: Store) -> None:
    chat = store.create_chat(model="mock/fast-1", effort=Effort.OFF)
    first = store.append_message(chat.id, Role.USER, content="hello")
    second = store.append_message(chat.id, Role.ASSISTANT, status=MessageStatus.STREAMING)
    assert [first.seq, second.seq] == [0, 1]
    assert [m.id for m in store.get_messages(chat.id)] == [first.id, second.id]


def test_finish_message_records_status_and_usage(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.HIGH)
    message = store.append_message(chat.id, Role.ASSISTANT, status=MessageStatus.STREAMING)
    store.finish_message(
        message.id,
        content="done",
        reasoning="thought",
        status=MessageStatus.COMPLETE,
        error=None,
        usage=Usage(prompt_tokens=3, completion_tokens=5, reasoning_tokens=2),
    )
    stored = store.get_message(message.id)
    assert stored is not None
    assert stored.content == "done"
    assert stored.reasoning == "thought"
    assert stored.status is MessageStatus.COMPLETE
    assert stored.usage == Usage(prompt_tokens=3, completion_tokens=5, reasoning_tokens=2)


def test_search_matches_message_bodies_and_highlights(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    store.append_message(chat.id, Role.USER, content="how do python generators work")
    other = store.create_chat(model=None, effort=Effort.OFF)
    store.append_message(other.id, Role.USER, content="best pasta recipe")

    hits = store.search_chats("generators", limit=10)
    assert [h.id for h in hits] == [chat.id]
    assert hits[0].snippet is not None and "<mark>generators</mark>" in hits[0].snippet


def test_search_matches_titles(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    store.update_chat(chat.id, title="Rust thread pools")
    assert [h.id for h in store.search_chats("thread", limit=10)] == [chat.id]


def test_search_treats_a_trailing_word_as_a_prefix(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    store.append_message(chat.id, Role.USER, content="tell me about hummingbirds")
    assert [h.id for h in store.search_chats("humming", limit=10)] == [chat.id]


def test_search_does_not_choke_on_fts_operators(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    store.append_message(chat.id, Role.USER, content="a OR b")
    assert store.search_chats('" OR NEAR(', limit=10) == []


def test_editing_a_message_reindexes_it(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    message = store.append_message(chat.id, Role.ASSISTANT, content="placeholder")
    store.finish_message(
        message.id, content="quicksort partitions", reasoning="", status=MessageStatus.COMPLETE, error=None, usage=None
    )
    assert [h.id for h in store.search_chats("quicksort", limit=10)] == [chat.id]
    assert store.search_chats("placeholder", limit=10) == []


def test_deleting_a_chat_removes_its_messages_from_search(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    store.append_message(chat.id, Role.USER, content="ephemeral")
    assert store.delete_chat(chat.id) is True
    assert store.search_chats("ephemeral", limit=10) == []
    assert store.get_messages(chat.id) == []


def test_share_tokens_are_stable_and_revocable(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    share = store.create_share(chat.id)
    assert store.create_share(chat.id).token == share.token
    assert store.chat_for_share_token(share.token) is not None
    assert store.revoke_share(chat.id) is True
    assert store.chat_for_share_token(share.token) is None


def test_renaming_does_not_reorder_the_sidebar(store: Store) -> None:
    older = store.create_chat(model=None, effort=Effort.OFF)
    newer = store.create_chat(model=None, effort=Effort.OFF)
    store.update_chat(older.id, title="renamed", touch=False)
    assert [c.id for c in store.list_chats(limit=10, offset=0)] == [newer.id, older.id]


def test_interrupted_streams_are_recovered_at_startup(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    message = store.append_message(chat.id, Role.ASSISTANT, status=MessageStatus.STREAMING)
    assert store.mark_streaming_as_interrupted() == 1
    stored = store.get_message(message.id)
    assert stored is not None and stored.status is MessageStatus.INTERRUPTED


def test_settings_round_trip(store: Store) -> None:
    store.save_settings(model="mock/thinker-1", effort=Effort.MEDIUM)
    settings = store.get_settings()
    assert settings.model == "mock/thinker-1"
    assert settings.effort is Effort.MEDIUM


def test_search_also_covers_what_the_model_was_thinking(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.HIGH)
    message = store.append_message(chat.id, Role.ASSISTANT, status=MessageStatus.STREAMING)
    store.finish_message(
        message.id,
        content="Use a heap.",
        reasoning="A priority queue keeps the smallest element at the front.",
        status=MessageStatus.COMPLETE,
        error=None,
        usage=None,
    )
    hits = store.search_chats("priority queue", limit=10)
    assert [h.id for h in hits] == [chat.id]
    assert hits[0].snippet is not None and "<mark>priority</mark>" in hits[0].snippet


def test_search_snippets_escape_the_surrounding_text(store: Store) -> None:
    """fts5 returns the message verbatim around the hit, and the sidebar renders snippets as
    HTML — so anything but the <mark> wrapper has to come back escaped."""
    chat = store.create_chat(model=None, effort=Effort.OFF)
    store.append_message(chat.id, Role.USER, content="<img src=x onerror=alert(1)> parsnips")

    snippet = store.search_chats("parsnips", limit=10)[0].snippet
    assert snippet is not None
    assert "<img" not in snippet
    assert "&lt;img src=x onerror=alert(1)&gt;" in snippet
    assert "<mark>parsnips</mark>" in snippet


def test_snippet_sentinels_in_user_text_cannot_forge_markup(store: Store) -> None:
    chat = store.create_chat(model=None, effort=Effort.OFF)
    store.append_message(chat.id, Role.USER, content=f"{_HIT_OPEN} spoofed {_HIT_CLOSE} rutabaga")

    snippet = store.search_chats("rutabaga", limit=10)[0].snippet
    assert snippet is not None
    # Sentinels the user typed become <mark> like any other hit marker — inert, and the only tag
    # this function can ever emit.
    assert "<" not in snippet.replace("<mark>", "").replace("</mark>", "")
