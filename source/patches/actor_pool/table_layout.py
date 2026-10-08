"""Address contract for stable external sentient tables at the native record stride."""

from dataclasses import dataclass
from typing import Iterator, NewType

NativeSentientAddress = NewType('NativeSentientAddress', int)
ExternalTableAddress = NewType('ExternalTableAddress', int)

NATIVE_SENTIENT_BYTES = 0x3088
NATIVE_TABLE_OFFSET = 0x12A0
TABLE_ENTRY_BYTES = 0x48


@dataclass(frozen=True)
class TableLayout:
    native_pool: NativeSentientAddress
    external_table: ExternalTableAddress
    capacity: int = 240
    entry_bytes: int = TABLE_ENTRY_BYTES
    native_offset: int = NATIVE_TABLE_OFFSET

    def __post_init__(self) -> None:
        if self.capacity != 240:
            raise ValueError('This exact plan supports only the 240-sentient layout.')
        if (self.entry_bytes,self.native_offset) not in ((0x48,0x12A0),(2,0x112C)):
            raise ValueError('Use a verified indexed sentient field layout.')
        if self.native_pool <= 0 or self.external_table <= 0:
            raise ValueError('Pool and table addresses must be positive.')
        native_end = self.native_pool + self.capacity * NATIVE_SENTIENT_BYTES
        table_end = self.external_table + self.table_bytes
        if native_end > 1 << 64 or table_end > 1 << 64:
            raise ValueError('Pool or table storage exceeds the native address width.')
        if self.native_pool < table_end and self.external_table < native_end:
            raise ValueError('External table storage must not overlap native sentient records.')

    @property
    def row_bytes(self) -> int:
        return self.capacity * self.entry_bytes

    @property
    def table_bytes(self) -> int:
        return self.capacity * self.row_bytes

    def owner_index(self, owner: NativeSentientAddress) -> int:
        offset = owner - self.native_pool
        index, remainder = divmod(offset, NATIVE_SENTIENT_BYTES)
        if remainder or not 0 <= index < self.capacity:
            raise ValueError('The sentient address is misaligned or outside its native pool.')
        return index

    def entry(self, owner: NativeSentientAddress, target: NativeSentientAddress) -> ExternalTableAddress:
        return ExternalTableAddress(self.external_table + self.owner_index(owner) * self.row_bytes
                                    + self.owner_index(target) * self.entry_bytes)

    def mapped_member(self, owner: NativeSentientAddress, legacy_address: int, width: int) -> ExternalTableAddress:
        offset = legacy_address - owner - self.native_offset
        target, field = divmod(offset, self.entry_bytes)
        if not 0 <= target < self.capacity or not 0 < width <= self.entry_bytes-field:
            raise ValueError('The guarded member access exceeds its external table entry.')
        return ExternalTableAddress(self.external_table + self.owner_index(owner) * self.row_bytes + offset)

    def row(self, owner: NativeSentientAddress) -> tuple[ExternalTableAddress, int]:
        return ExternalTableAddress(self.external_table + self.owner_index(owner) * self.row_bytes), self.row_bytes

    def column(self, target: NativeSentientAddress) -> Iterator[ExternalTableAddress]:
        target_index = self.owner_index(target)
        for owner_index in range(self.capacity):
            yield ExternalTableAddress(self.external_table + owner_index*self.row_bytes + target_index*self.entry_bytes)
