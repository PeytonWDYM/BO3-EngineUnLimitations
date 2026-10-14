"""Guarded actor preparation shapes. Runtime admission also needs codecs, saves, and complete frames."""

from dataclasses import dataclass

ACTOR_BYTES = 0x2110
SECONDARY_ACTOR_BYTES = 0xB00
SENTIENT_BYTES = 0x3088


@dataclass(frozen=True)
class ActorShape:
    actors: int = 300
    sentient_reserve: int = 40

    def __post_init__(self) -> None:
        if (self.actors, self.sentient_reserve) not in ((300, 40), (500, 40)):
            raise ValueError('Only the 300/340 and 500/540 preparation shapes are supported.')

    @property
    def sentients(self) -> int:
        return self.actors + self.sentient_reserve

    @property
    def actor_bytes(self) -> int:
        return self.actors * ACTOR_BYTES

    @property
    def secondary_actor_bytes(self) -> int:
        return self.actors * SECONDARY_ACTOR_BYTES

    @property
    def sentient_bytes(self) -> int:
        return self.sentients * SENTIENT_BYTES

    @property
    def four_actor_groups(self) -> int:
        return self.actors // 4

    @property
    def dobj_bytes(self) -> int:
        return self.actors * 8

    @property
    def handle_head_bytes(self) -> int:
        return self.sentients * 2
