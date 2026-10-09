#pragma once
#include <array>
#include <cstdint>

namespace bo3::early_integrity {
struct ImagePointer {std::uint32_t offset, targetRva;};
struct Guard {
    std::uint32_t rva, size, firstPointer, pointerCount;
    std::array<unsigned char,32> digest;
};
struct Site {
    std::uint32_t leaRva, storeRva, expectedRva, chainDestinationRva;
    std::uint32_t computedReadRva, endpointRva;
    unsigned char computedLocalSlot, computedTableSlot, expectedTableSlot, indexSlot;
    bool splitInstaller;
};
struct Region {std::uint32_t rva, size;};
}
