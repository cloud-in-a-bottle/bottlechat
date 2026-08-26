from enum import StrEnum

import attr

from server.models import Usage


class DeltaKind(StrEnum):
    CONTENT = "content"
    REASONING = "reasoning"


@attr.s(auto_attribs=True, frozen=True)
class Delta:
    kind: DeltaKind
    text: str


@attr.s(auto_attribs=True, frozen=True)
class Completed:
    usage: Usage | None


@attr.s(auto_attribs=True, frozen=True)
class Failed:
    message: str


StreamEvent = Delta | Completed | Failed
