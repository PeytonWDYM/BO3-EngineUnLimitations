#include "CounterProfile.h"
#include "CounterManifest.h"
#include "GameManifest.h"
#include "../../launch/preentry/Identity.h"
#include "../vm_startup/PausedPatch.h"
#include <algorithm>
#include <cstring>

namespace bo3::clientfields {
void AdmitCounters(HANDLE process,std::uintptr_t image) {
    auto manifest=enhanced::ExactGameManifest;manifest.guards=CounterGuards;
    enhanced::VerifyGameCode(process,image,manifest);
    for(const auto& row:CounterInstructions)
        Require(vm_startup::ReadStopped(process,image+row.rva,row.size)
            ==std::vector<unsigned char>(row.bytes.begin(),row.bytes.begin()+row.size),"A counter instruction differs.");
    for(const auto rva:{0x5124580u,0x5124500u,0x5124680u,0x5124600u}) {
        const auto bytes=vm_startup::ReadStopped(process,image+rva,8);
        Require(std::all_of(bytes.begin(),bytes.end(),[](unsigned char value){return value==0;}),"VM backing already exists. Counter activation refused.");
    }
    const auto original=vm_startup::ReadStopped(process,image+kStockCounterPoolRva,2048*24);
    Require(std::all_of(original.begin(),original.end(),[](unsigned char value){return value==0;}),
        "The native counter table already contains state. Counter activation refused.");
}
std::vector<vm_startup::AddressEdit> BuildCounterPlan(std::uintptr_t image,std::uintptr_t pool) {
    Require(image<=UINTPTR_MAX-enhanced::ExactGameManifest.imageSize && pool>=0x10000 && pool%16==0
        && pool<=UINTPTR_MAX-kCounterStorageBytes,"Invalid counter image or allocation interval.");
    Require(pool+kCounterStorageBytes<=image || pool>=image+enhanced::ExactGameManifest.imageSize,
        "Counter backing overlaps the native image.");
    std::vector<vm_startup::AddressEdit> edits;edits.reserve(CounterInstructions.size());
    for(const auto& row:CounterInstructions) {
        std::vector<unsigned char> original(row.bytes.begin(),row.bytes.begin()+row.size),replacement=original;
        std::uint32_t value{};
        if(row.operand==CounterOperand::Capacity)value=kCounterCapacity;
        else if(row.operand==CounterOperand::Bytes)value=kCounterStorageBytes;
        else {
            const auto target=pool+CounterOffset(row.operand),next=image+row.rva+row.size;
            const auto distance=target>=next ? target-next : next-target;
            Require(distance<=(target>=next ? 0x7FFFFFFFull : 0x80000000ull),"Complete counter backing is outside native reach.");
            value=target>=next ? static_cast<std::uint32_t>(distance) : 0u-static_cast<std::uint32_t>(distance);
        }
        std::memcpy(replacement.data()+row.offset,&value,row.width);
        edits.push_back({image+row.rva,std::move(original),std::move(replacement)});
    }
    Require(edits.size()==11,"The counter plan is incomplete.");return edits;
}
}
