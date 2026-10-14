#pragma once
// Compare plain/prefixed relative jumps on the actual Windows CPU with owned code and bindings.
inline unsigned int CheckBranchExecution() {
    Allocation image;
    constexpr std::array<unsigned char,6> seed{0x48,0x39,0xD1,0x4D,0x89,0xC3};
    constexpr std::array<unsigned char,8> target{0x4C,0x89,0xD8,0x9C,0x41,0x8F,0x01,0xC3};
    for (const auto entry : {0x200u,0x300u,0x600u,0x700u}) {
        const bool prefix = entry == 0x300u || entry == 0x700u;
        const auto destination = entry < 0x500 ? 0x400u : 0x500u;
        std::memcpy(image.data()+entry,seed.data(),seed.size());
        auto* branch = image.data()+entry+seed.size();
        if (prefix) *branch++ = 0x40;
        *branch++ = 0xE9;
        const auto displacement = static_cast<std::int32_t>(destination)-static_cast<std::int32_t>(entry+seed.size()+(prefix ? 6 : 5));
        std::memcpy(branch,&displacement,4);
        std::memcpy(image.data()+destination,target.data(),target.size());
    }
    image.protect();
    Require(FlushInstructionCache(GetCurrentProcess(),image.data(),131072)!=FALSE,"Cannot flush the owned CPU branch comparison.");
    using Function = DWORD64(*)(DWORD64,DWORD64,DWORD64,DWORD64*);
    constexpr std::array<std::array<DWORD64,2>,5> values{{{0,0},{1,0},{0,1},{~DWORD64{0},0},{0,~DWORD64{0}}}};
    unsigned int comparisons{};
    for (const auto entry : {0x200u,0x600u}) {
        const auto plain = reinterpret_cast<Function>(image.data()+entry);
        const auto prefixed = reinterpret_cast<Function>(image.data()+entry+0x100);
        for (const auto& pair : values) {
            DWORD64 first{},second{};
            constexpr DWORD64 marker = 0xABCDEF0123456789;
            Require(plain(pair[0],pair[1],marker,&first)==marker && prefixed(pair[0],pair[1],marker,&second)==marker,
                    "The prefixed CPU branch lost its target or register argument.");
            Require((first&0x8D5)==(second&0x8D5),"The prefixed CPU branch changed arithmetic flags.");
            ++comparisons;
        }
    }
    return comparisons;
}
