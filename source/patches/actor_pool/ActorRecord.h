#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <initializer_list>

namespace bo3::actors {
// Replay the guarded native constructor writes in complete, zeroed 0x2110-byte records.
inline void InitializeActorRecords(std::byte* records,std::uint32_t count,std::uintptr_t image) {
    const auto vtable=image+0x2F1BB88;
    constexpr std::uint32_t positive=0x7E967699,negative=0xFE967699,zero=0;
    for(std::uint32_t index=0;index<count;++index) {
        auto* record=records+static_cast<std::size_t>(index)*0x2110;
        std::memcpy(record+0x8A0,&vtable,sizeof(vtable));
        std::memset(record+0x8B0,0,0x60);
        for(auto offset:{0x8B0,0x8B4,0x8B8})std::memcpy(record+offset,&positive,sizeof(positive));
        for(auto offset:{0x8C0,0x8C4,0x8C8})std::memcpy(record+offset,&negative,sizeof(negative));
        std::memcpy(record+0x920,&zero,sizeof(zero));
        record[0x924]=std::byte{};
    }
}
}
