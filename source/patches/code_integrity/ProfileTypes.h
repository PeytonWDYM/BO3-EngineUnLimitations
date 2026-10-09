#pragma once
#include <array>
#include <cstdint>
namespace bo3::code_integrity {
enum class Family { Xor, NegAdd, Compare, InputTransform };
enum class Flags { Zero, ZeroCarry };
struct Region { std::uint32_t rva,size; };
struct ImageAddress { std::uint16_t offset; std::uint32_t targetRva; };
struct Guard {
    std::uint32_t rva,size;
    std::array<unsigned char,32> digest;
    std::array<ImageAddress,2> imageAddresses;
    std::uint32_t imageAddressCount;
};
struct Record {
    std::uint32_t rva;
    Family family;
    Flags liveFlags;
    std::uint32_t guardSize;
    std::array<unsigned char,32> guardDigest;
    std::array<ImageAddress,2> imageAddresses;
    std::uint32_t imageAddressCount;
};
}
