#pragma once
#include "Plan.h"
#include "Audio.h"
#include <cstring>

namespace bo3::startup_intro {
inline constexpr std::uint32_t kLoopRva=0x20f00ba,kPlayingRva=0x12bd900,kPlayerLayoutRva=0x12c0020;
inline constexpr std::array<unsigned char,46> kLoop{
    0xe8,0x81,0xe8,0xbd,0xff,0xe8,0x3c,0xd8,0x1c,0xff,0x84,0xc0,0x74,0x1b,0x0f,0x1f,
    0x84,0x00,0x00,0x00,0x00,0x00,0xb9,0x01,0x00,0x00,0x00,0xe8,0x36,0xb9,0x03,0x00,
    0xe8,0x21,0xd8,0x1c,0xff,0x84,0xc0,0x75,0xed,0xe8,0xd8,0xea,0xbd,0xff,
};
inline constexpr std::array<unsigned char,31> kPlayingEntry{
    0x48,0x89,0x74,0x24,0x10,0x57,0x48,0x83,0xec,0x30,0x8b,0x0d,0xd0,0x7f,0x56,0x19,
    0x65,0x48,0x8b,0x04,0x25,0x58,0x00,0x00,0x00,0x41,0xb9,0xb0,0x00,0x00,0x00,
};
inline constexpr std::array<unsigned char,147> kPlayerLayout{
    0x40,0x57,0x48,0x83,0xec,0x20,0x33,0xff,0x39,0x3d,0x32,0xed,0xa0,0x03,0x7e,0x7d,
    0x48,0x89,0x5c,0x24,0x30,0x48,0x89,0x74,0x24,0x38,0x48,0x8d,0x35,0x7f,0xec,0xa0,
    0x03,0x48,0x8b,0x1e,0x8b,0x83,0xc8,0x21,0x03,0x00,0x85,0xc0,0x74,0x55,0x83,0xf8,
    0x01,0x74,0x2f,0x83,0xf8,0x03,0x74,0x20,0x83,0xf8,0x05,0x7e,0x38,0x83,0xf8,0x07,
    0x7e,0x0c,0x83,0xf8,0x08,0x75,0x2e,0xe8,0xd4,0xce,0xff,0xff,0xeb,0x27,0x48,0x8b,
    0xcb,0xe8,0xaa,0x0e,0x00,0x00,0xeb,0x1d,0x48,0x8b,0xcb,0xe8,0x00,0x2a,0x00,0x00,
    0xeb,0x13,0xe8,0x59,0x3a,0xe0,0x00,0x84,0xc0,0x74,0x0a,0x33,0xd2,0x48,0x8b,0xcb,
    0xe8,0xbb,0x1c,0x00,0x00,0xff,0xc7,0x48,0x83,0xc6,0x08,0x3b,0x3d,0xbf,0xec,0xa0,
    0x03,0x7c,0x9e,0x48,0x8b,0x5c,0x24,0x30,0x48,0x8b,0x74,0x24,0x38,0x48,0x83,0xc4,
    0x20,0x5f,0xc3,
};
inline std::vector<vm_startup::AddressEdit> BuildAudioPlan(vm_startup::ImageRange image,
    vm_startup::ImageRange helper,std::uint32_t bindingsRva,std::uint32_t handlerRva,std::uint32_t startRva,std::uint32_t updateRva,std::uint32_t originalIntroRva,std::uint32_t originalUpdateRva,std::uintptr_t relay,
    std::span<const unsigned char> loop,std::span<const unsigned char> playing,std::span<const unsigned char> layout) {
    const auto same=[](auto actual,auto expected){return actual.size()==expected.size()
        && std::equal(actual.begin(),actual.end(),expected.begin());};
    if(image.size!=494186496 || image.base>UINTPTR_MAX-image.size ||
        !same(loop,std::span(kLoop)) || !same(playing,std::span(kPlayingEntry)) || !same(layout,std::span(kPlayerLayout)))
        throw std::runtime_error("The exact custom intro audio context differs.");
    if(helper.base>UINTPTR_MAX-helper.size || bindingsRva>helper.size ||
        sizeof(AudioBindings)>helper.size-bindingsRva || handlerRva>=helper.size || startRva>=helper.size || updateRva>=helper.size ||
        originalIntroRva>=helper.size || originalUpdateRva>=helper.size || relay>UINTPTR_MAX-48 || (relay&15)!=0)
        throw std::runtime_error("Invalid custom intro audio storage.");
    const AudioBindings bindings{reinterpret_cast<bool (*)()>(image.base+kPlayingRva),
        reinterpret_cast<const volatile std::uint32_t*>(image.base+0x4cced60),
        reinterpret_cast<const volatile std::uintptr_t*>(image.base+0x4ccecc0),
        reinterpret_cast<decltype(AudioBindings::startMovie)>(helper.base+originalIntroRva),
        reinterpret_cast<void (*)()>(helper.base+originalUpdateRva),image.base+kCinematicRva+5,image.base+kPlayerLayoutRva+6};
    std::vector<unsigned char> record(sizeof(bindings));std::memcpy(record.data(),&bindings,sizeof(bindings));
    std::vector<unsigned char> thunk(48,0);thunk[0]=0xff;thunk[1]=0x25;thunk[16]=0xff;thunk[17]=0x25;
    const auto handler=helper.base+handlerRva;std::memcpy(thunk.data()+6,&handler,8);
    const auto start=helper.base+startRva;std::memcpy(thunk.data()+22,&start,8);
    thunk[32]=0xff;thunk[33]=0x25;const auto update=helper.base+updateRva;std::memcpy(thunk.data()+38,&update,8);
    std::vector<vm_startup::AddressEdit> edits{
        {helper.base+bindingsRva,std::vector<unsigned char>(sizeof(bindings),0),std::move(record)},
        {relay,std::vector<unsigned char>(48,0),std::move(thunk)}};
    for(const auto rva:{kCinematicRva,kPlayerLayoutRva,0x20f00bfu,0x20f00dau}) {
        const auto next=image.base+rva+5;
        const auto target=relay+(rva==kCinematicRva?16:rva==kPlayerLayoutRva?32:0);
        const auto distance=target>=next?target-next:next-target;
        if(distance>(target>=next?0x7fffffffull:0x80000000ull))
            throw std::runtime_error("The custom intro audio relay is unreachable.");
        const auto offset=static_cast<std::int32_t>(target>=next?static_cast<std::int64_t>(distance):-static_cast<std::int64_t>(distance));
        const auto bytes=rva==kPlayerLayoutRva?6u:5u;
        std::vector<unsigned char> call(bytes,0x90);call[0]=rva==kCinematicRva || rva==kPlayerLayoutRva?0xe9:0xe8;
        std::memcpy(call.data()+1,&offset,4);
        const auto original=rva==kCinematicRva?std::vector<unsigned char>(kCinematicEntry.begin(),kCinematicEntry.begin()+5)
            :rva==kPlayerLayoutRva?std::vector<unsigned char>(layout.begin(),layout.begin()+6)
            :std::vector<unsigned char>(loop.begin()+rva-kLoopRva,loop.begin()+rva-kLoopRva+5);
        edits.push_back({image.base+rva,original,std::move(call)});
    }
    return edits;
}
}
