#include "RuntimeUnwind.h"
#include "../preentry/Identity.h"
#include "RuntimeUnwindProfile.h"
#include <cstring>

namespace bo3::job_startup {
#ifdef BO3_JOB_OWNED_TEST
namespace {bool missingGuard{};}
void SetOwnedRuntimeGuardAbsent(bool missing){missingGuard=missing;}
#endif
PVOID RuntimeFunction(HANDLE process,std::uintptr_t base,const unsigned char* local,DWORD64 pc) {
#ifdef BO3_JOB_OWNED_TEST
    Require(!missingGuard,"The game frame has no pinned runtime CRT guard.");
#endif
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(local);
    const auto* pe=reinterpret_cast<const IMAGE_NT_HEADERS64*>(local+dos->e_lfanew);
    const auto header=vm_startup::ReadStopped(process,base+dos->e_lfanew,sizeof(*pe));
    IMAGE_NT_HEADERS64 remote{};std::memcpy(&remote,header.data(),sizeof(remote));
    Require(pe->FileHeader.TimeDateStamp==kRuntimeTimestamp && pe->OptionalHeader.SizeOfImage==kRuntimeImageSize
        && remote.Signature==IMAGE_NT_SIGNATURE && remote.FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64
        && remote.FileHeader.TimeDateStamp==kRuntimeTimestamp && remote.OptionalHeader.SizeOfImage==kRuntimeImageSize,
        "The runtime CRT module identity differs.");
    for(const auto& guard:kRuntimeUnwind) {
        if(pc<base+guard.function.BeginAddress || pc>=base+guard.function.EndAddress)continue;
        Require(std::memcmp(local+guard.tableRva,&guard.function,sizeof(guard.function))==0
            && vm_startup::ReadStopped(process,base+guard.tableRva,sizeof(guard.function))
                ==std::vector<unsigned char>(reinterpret_cast<const unsigned char*>(&guard.function),
                    reinterpret_cast<const unsigned char*>(&guard.function)+sizeof(guard.function)),
            "The pinned runtime CRT function row differs.");
        Require(vm_startup::ReadStopped(process,base+guard.function.UnwindData,guard.infoSize)
            ==std::vector<unsigned char>(guard.info,guard.info+guard.infoSize),
            "The pinned runtime CRT unwind bytes differ.");
        Require(vm_startup::ReadStopped(process,base+guard.function.BeginAddress,guard.codeSize)
            ==std::vector<unsigned char>(guard.code,guard.code+guard.codeSize),
            "The pinned runtime CRT prologue or call differs.");
        return const_cast<RUNTIME_FUNCTION*>(&guard.function);
    }
#ifdef BO3_JOB_OWNED_TEST
    // The owned caller returns through its target's wmain and ordinary linked CRT.
    // Those extra fixture frames retain the original exact disk/runtime admission.
    return nullptr;
#else
    throw std::runtime_error("The game frame has no pinned runtime CRT guard.");
#endif
}
unsigned int RuntimeMetadataReadMask(std::uintptr_t base,DWORD64 address,DWORD size) {
    unsigned int mask=0,index=0;
    for(const auto& guard:kRuntimeUnwind) {
        if(address<base+guard.function.UnwindData+guard.infoSize && address+size>base+guard.function.UnwindData)mask|=1u<<index;
        ++index;
    }
    return mask;
}
}
