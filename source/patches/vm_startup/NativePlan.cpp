#include "NativePlan.h"
#include "../vm_pool/NativeStateBridge.h"
#include "StateErrors.h"
#include <cstring>
#include <limits>
#include <stdexcept>

namespace vm_startup {
namespace {
void Require(bool valid,const char* message) { if(!valid) throw std::runtime_error(message); }
std::uintptr_t Address(ImageRange image,std::uint32_t rva,std::size_t size) {
    Require(image.base<=UINTPTR_MAX-image.size && rva<image.size && size<=image.size-rva,"Native plan offset exceeds its admitted image.");
    return image.base+rva;
}
template<class T> std::vector<unsigned char> Bytes(const T& value) {
    std::vector<unsigned char> bytes(sizeof(T)); std::memcpy(bytes.data(),&value,sizeof(T)); return bytes;
}
std::vector<unsigned char> Relative(std::uintptr_t entry,std::uintptr_t relay) {
    Require(entry<=UINTPTR_MAX-5,"Native entry address overflows.");
    const auto next=entry+5;
    const auto distance=relay>=next ? relay-next : next-relay;
    Require(distance<=(relay>=next ? 0x7fffffffull : 0x80000000ull),"The native relay exceeds signed rel32 reach.");
    const auto displacement=relay>=next ? static_cast<std::int32_t>(distance)
        : static_cast<std::int32_t>(-static_cast<std::int64_t>(distance));
    std::vector<unsigned char> bytes(5); bytes[0]=0xe9; std::memcpy(bytes.data()+1,&displacement,4); return bytes;
}
}
std::vector<AddressEdit> BuildNativePlan(const NativePlanInput& input) {
    constexpr std::array<NativeEntry,4> exact{{{0x12d52f0,{0x48,0x89,0x5c,0x24,0x10}},
        {0x12d5f20,{0x48,0x89,0x5c,0x24,0x08}}, {0x12d9420,{0x40,0x53,0x49,0x8b,0xd8}},
        {0x20ec0b0,{0x4c,0x89,0x4c,0x24,0x20}}}};
    Require(input.total==130000 || input.total==500001 || input.total==1000001,"Unsupported native plan capacity.");
    Require(input.relay<=UINTPTR_MAX-64,"Native relay address overflows.");
    for(std::size_t index=0;index<exact.size();++index)
        Require(input.entries[index].rva==exact[index].rva && input.entries[index].original==exact[index].original,
            "Native original entries do not match the static exact-build thunks.");
    const auto& offsets=input.exports;
    const auto helper=[&](std::uint32_t rva) { return Address(input.helper,rva,1); };
    bo3::vm::NativeStateBindings state{};
    state.imageBase=input.image.base; state.total=input.total;
    state.clientRoots=input.clientRoots; state.stockClientRoots=input.stockClientRoots;
    state.modePolicy=input.modePolicy;
    state.originalClientReader=reinterpret_cast<bo3::vm::WholeFunction>(helper(offsets.originalReader));
    state.originalClientWriter=reinterpret_cast<bo3::vm::WholeFunction>(helper(offsets.originalWriter));
    state.originalInsert=reinterpret_cast<bo3::vm::InsertFunction>(helper(offsets.originalInsert));
    bo3::vm::ErrorBindings error{};
    error.entry=reinterpret_cast<bo3::vm::ErrorFunction>(Address(input.image,input.entries[3].rva,5));
    error.original=reinterpret_cast<bo3::vm::ErrorFunction>(helper(offsets.originalError));
    error.read=reinterpret_cast<bo3::vm::StateFunction>(helper(offsets.readState));
    error.write=reinterpret_cast<bo3::vm::StateFunction>(helper(offsets.writeState));
    std::vector<AddressEdit> edits;
    for(const auto& count:input.counts) {
        Require(!count.original.empty() && count.original.size()==count.replacement.size(),"Native count edit has unequal sizes.");
        edits.push_back({Address(input.image,count.rva,count.original.size()),count.original,count.replacement});
    }
    edits.push_back({Address(input.helper,offsets.stateBindings,sizeof(state)),std::vector<unsigned char>(sizeof(state),0),Bytes(state)});
    edits.push_back({Address(input.helper,offsets.errorBindings,sizeof(error)),std::vector<unsigned char>(sizeof(error),0),Bytes(error)});
    const std::array destinations{helper(offsets.readOrDrop),helper(offsets.writeOrDrop),helper(offsets.insertState),helper(offsets.errorPrelude)};
    std::vector<unsigned char> relay(64,0);
    for(std::size_t index=0;index<destinations.size();++index) {
        relay[index*16]=0xff; relay[index*16+1]=0x25;
        std::memcpy(relay.data()+index*16+6,&destinations[index],8);
    }
    edits.push_back({input.relay,std::vector<unsigned char>(64,0),std::move(relay)});
    for(std::size_t index=0;index<exact.size();++index) {
        const auto entry=Address(input.image,input.entries[index].rva,5);
        edits.push_back({entry,{input.entries[index].original.begin(),input.entries[index].original.end()},Relative(entry,input.relay+index*16)});
    }
    return edits;
}
}
