"""The researched 300-actor pose and history layouts. These do not admit a save format."""
from dataclasses import dataclass
from shape import ActorShape


@dataclass(frozen=True)
class TemporalLayout:
    shape: ActorShape = ActorShape()

    @property
    def vector_bytes(self) -> int:
        return self.shape.actors * 12

    @property
    def output_valid_offset(self) -> int:
        return self.vector_bytes * 2

    @property
    def output_bytes(self) -> int:
        return self.output_valid_offset + self.shape.actors

    @property
    def history_state_offset(self) -> int:
        return self.vector_bytes * 2

    @property
    def history_valid_offset(self) -> int:
        return self.history_state_offset + self.shape.actors

    @property
    def history_time_offset(self) -> int:
        return (self.history_valid_offset + self.shape.actors + 3) & ~3

    @property
    def history_row_bytes(self) -> int:
        return self.history_time_offset + 4

    @property
    def history_bytes(self) -> int:
        return self.history_row_bytes * 20
