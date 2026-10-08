#include "Observation.h"
#include "ProbeProfile.h"
#include <cstring>

namespace bo3::startup_probe {
extern "C" {
__declspec(dllexport) constinit Observation Bo3StartupProbeObservation{};
__declspec(dllexport) constinit Counters Bo3StartupProbeCounters{};
}
namespace {
bool Read(DWORD rva,void* output,SIZE_T size) {
    InterlockedIncrement(&Bo3StartupProbeCounters.vmReads);
    SIZE_T read{};
    return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(Bo3StartupProbeCounters.imageBase+rva),
        output,size,&read)!=FALSE && read==size;
}
}
// One bounded publication attempt. A collision forwards normally without waiting.
void Observe(std::uintptr_t returnSite,std::uintptr_t apiReturnSlot) {
    auto& counters=Bo3StartupProbeCounters;
    InterlockedIncrement(&counters.attempts);
    unsigned char caller[44]{};
    SIZE_T read{};
    if(!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(counters.imageBase+kCallerRva),caller,sizeof(caller),&read)
        || read!=sizeof(caller) || std::memcmp(caller,kCallerBytes,sizeof(caller))) {
        InterlockedIncrement(&counters.rejected); return;
    }
    if(InterlockedCompareExchange(&counters.publicationLock,1,0)) {
        InterlockedIncrement(&counters.dropped); return;
    }
    auto& record=Bo3StartupProbeObservation;
    InterlockedIncrement(&record.sequence);
    record.threadId=GetCurrentThreadId();
    ++record.count;
    record.returnSite=returnSite;
    record.wrapperCallerReturn=0;
    record.wrapperCallerReadable=0;
    record.wrapperCallerMatches=0;
    ULONG_PTR stackLow{},stackHigh{};
    GetCurrentThreadStackLimits(&stackLow,&stackHigh);
    if(apiReturnSlot<=UINTPTR_MAX-kWrapperCallerDelta) {
        const auto address=apiReturnSlot+kWrapperCallerDelta;
        if(address>=stackLow && stackHigh>=sizeof(std::uintptr_t) && address<=stackHigh-sizeof(std::uintptr_t)) {
            SIZE_T count{};
            record.wrapperCallerReadable=ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),
                &record.wrapperCallerReturn,sizeof(record.wrapperCallerReturn),&count)
                && count==sizeof(record.wrapperCallerReturn);
            record.wrapperCallerMatches=record.wrapperCallerReadable
                && record.wrapperCallerReturn==counters.imageBase+kCrtReturnRva;
        }
    }
    record.readableMask=0;
    std::memcpy(record.caller,caller,sizeof(caller));
    unsigned int bit=0;
    for(unsigned int i=0;i<4;++i,++bit) {
        record.pools[i]=0;
        if(Read(kPoolRvas[i],&record.pools[i],sizeof(record.pools[i]))) record.readableMask|=1u<<bit;
    }
    for(unsigned int i=0;i<5;++i,++bit) {
        record.migrationPointers[i]=0;
        if(Read(kMigrationPointerRvas[i],&record.migrationPointers[i],sizeof(record.migrationPointers[i]))) record.readableMask|=1u<<bit;
    }
    for(unsigned int i=0;i<3;++i,++bit) {
        record.migrationSizes[i]=0;
        if(Read(kMigrationSizeRvas[i],&record.migrationSizes[i],sizeof(record.migrationSizes[i]))) record.readableMask|=1u<<bit;
    }
    std::memset(record.allocatorPrefix,0,sizeof(record.allocatorPrefix));
    if(Read(kAllocatorRva,record.allocatorPrefix,sizeof(record.allocatorPrefix))) record.readableMask|=1u<<bit;
    InterlockedIncrement(&record.sequence);
    InterlockedExchange(&counters.publicationLock,0);
}
}
