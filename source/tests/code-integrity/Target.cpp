#include "Fixture.h"
#include "../../patches/code_integrity/Plan.h"
#include "Profile.h"
#include <cstring>
#include <stdexcept>
#include <string>
std::span<const unsigned char> FixtureOriginal(bo3::code_integrity::Family family) {
    static constexpr std::array<unsigned char,6> xorBytes{0x8b,0x0c,0x8b,0x33,0x0c,0x82};
    static constexpr std::array<unsigned char,8> negBytes{0x8b,0x0c,0x8b,0xf7,0xd9,0x03,0x0c,0x82};
    static constexpr std::array<unsigned char,8> cmpBytes{0x8b,0x04,0x82,0x8b,0x14,0x8b,0x3b,0xc2};
    switch(family) {
    case bo3::code_integrity::Family::Xor:case bo3::code_integrity::Family::InputTransform:return xorBytes;
    case bo3::code_integrity::Family::NegAdd:return negBytes;
    case bo3::code_integrity::Family::Compare:return cmpBytes;
    }
    throw std::runtime_error("Unknown authored fixture family.");
}
int wmain(int argc,wchar_t** argv) {
    if (argc != 5) return 2;
    const HANDLE mapping=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,argv[1]);
    const HANDLE ready=OpenEventW(EVENT_MODIFY_STATE,FALSE,argv[2]);
    const HANDLE done=OpenEventW(SYNCHRONIZE,FALSE,argv[3]);
    if (!mapping || !ready || !done) return 3;
    auto* state=static_cast<FixtureState*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(FixtureState)));
    if (!state) return 4;
    const auto image=LoadLibraryW(argv[4]);
    if (!image) return 5;
    state->imageBase=reinterpret_cast<std::uintptr_t>(image);
    auto* code=reinterpret_cast<unsigned char*>(GetProcAddress(image,"OwnedCode"));
    if (!code) return 6;
    std::memset(code,0x90,kFixtureBytes);
    for (const auto& record : bo3::code_integrity::kRecords) {
        auto* location=reinterpret_cast<unsigned char*>(state->imageBase+record.rva);
        const auto original=FixtureOriginal(record.family);
        std::memcpy(location,original.data(),original.size());
        // Authored shape: a flag consumer or further input transform.
        const auto* suffix=record.family==bo3::code_integrity::Family::InputTransform ? "\x33\x0c\x82\x89\x4d\x44" : "\x0f\x84\x00\x00\x00\x00";
        auto* next=location+original.size();
        if(record.imageAddressCount) {
            const unsigned char transport[]{0x49,0xbb};
            std::memcpy(next,transport,2);
            const auto pointer=state->imageBase+record.imageAddresses[0].targetRva;
            std::memcpy(next+2,&pointer,sizeof(pointer));
            next+=10;
        }
        std::memcpy(next,suffix,6);
    }
    DWORD prior{};
    if (!VirtualProtect(code,kFixtureBytes,PAGE_EXECUTE_READWRITE,&prior)) return 7;
    if (!FlushInstructionCache(GetCurrentProcess(),code,kFixtureBytes)) return 8;
    if (!SetEvent(ready)) return 9;
    const auto wait=WaitForSingleObject(done,30000);
    return wait==WAIT_OBJECT_0 ? 0 : 10;
}
