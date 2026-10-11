#include "PendingProfile.h"
#include "PendingManifest.h"
#include "GameManifest.h"
#include "../../launch/preentry/Identity.h"
#include "../vm_startup/PausedPatch.h"
#include <algorithm>
#include <cstring>

namespace bo3::clientfields {
namespace {
template<class T> T Read(HANDLE process,std::uintptr_t address) {
    const auto bytes=vm_startup::ReadStopped(process,address,sizeof(T));
    T value;std::memcpy(&value,bytes.data(),sizeof(value));return value;
}
std::vector<unsigned char> PointerBytes(std::uintptr_t value) {
    std::vector<unsigned char> bytes(sizeof(value));std::memcpy(bytes.data(),&value,sizeof(value));return bytes;
}
}
std::uintptr_t AdmitPendingCallbacks(HANDLE process,std::uintptr_t image) {
    auto manifest=enhanced::ExactGameManifest;manifest.guards=PendingGuards;
    enhanced::VerifyGameCode(process,image,manifest);
    for(const auto& row:PendingInstructions)
        Require(vm_startup::ReadStopped(process,image+row.rva,row.size)
            ==std::vector<unsigned char>(row.bytes.begin(),row.bytes.begin()+row.size),"A callback instruction differs.");
    for(const auto rva:{0x5124580u,0x5124500u,0x5124680u,0x5124600u})
        Require(Read<std::uintptr_t>(process,image+rva)==0,"VM backing already exists. Callback activation refused.");
    const auto published=Read<std::uintptr_t>(process,image+kPendingPointerRva);
    Require(published==0 || published==image+kStockPendingPoolRva,"The callback backing is already replaced.");
    for(const auto offset:{0u,4u})
        Require(Read<std::uint32_t>(process,image+kStockPendingPoolRva+0x20000+offset)==0,
            "Pending callbacks exist. Callback activation refused.");
    return published;
}
std::vector<vm_startup::AddressEdit> BuildPendingPlan(std::uintptr_t image,std::uintptr_t pool,std::uintptr_t published) {
    Require(image<=UINTPTR_MAX-enhanced::ExactGameManifest.imageSize && pool>=0x10000 && pool%4096==0
        && pool<=UINTPTR_MAX-kPendingStorageBytes,"Invalid callback image or allocation interval.");
    Require(pool+kPendingStorageBytes<=image || pool>=image+enhanced::ExactGameManifest.imageSize,
        "Callback backing overlaps the native image.");
    Require(published==0 || published==image+kStockPendingPoolRva,"Invalid original callback pointer.");
    std::vector<vm_startup::AddressEdit> edits;edits.reserve(18);
    for(const auto& row:PendingInstructions) {
        Require(row.size>=4 && row.size<=row.bytes.size() && row.width<=row.size
            && row.offset<=row.size-row.width,"Invalid callback operand inventory.");
        std::vector<unsigned char> original(row.bytes.begin(),row.bytes.begin()+row.size),replacement=original;
        std::uint32_t value{};
        switch(row.operand) {
        case PendingOperand::Pool: {
            const auto next=image+row.rva+row.size;
            const auto distance=pool>=next ? pool-next : next-pool;
            Require(distance<=(pool>=next ? 0x7FFFFFFFull : 0x80000000ull),"Callback backing is outside native reach.");
            value=pool>=next ? static_cast<std::uint32_t>(distance) : 0u-static_cast<std::uint32_t>(distance);break;
        }
        case PendingOperand::Bytes:value=kPendingStorageBytes;break;
        case PendingOperand::Counts:value=kPendingCountOffset;break;
        case PendingOperand::Capacity:value=kPendingCapacity;break;
        case PendingOperand::Shift:value=13;break;
        }
        Require((row.width==4) || (row.width==1 && value<=255),"Invalid callback operand width.");
        std::memcpy(replacement.data()+row.offset,&value,row.width);
        edits.push_back({image+row.rva,std::move(original),std::move(replacement)});
    }
    edits.push_back({image+kPendingPointerRva,PointerBytes(published),PointerBytes(pool)});
    Require(edits.size()==18,"The callback plan is incomplete.");return edits;
}
}
