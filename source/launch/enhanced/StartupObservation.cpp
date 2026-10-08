#include "StartupObservation.h"
#include "Boot.h"
#include "../preentry/Identity.h"
#include <sstream>

namespace bo3::startup_control {
namespace {
template<class T> bool Read(HANDLE process,std::uintptr_t address,T& value) {
    SIZE_T read{};
    return ReadProcessMemory(process,reinterpret_cast<const void*>(address),&value,sizeof(value),&read)!=FALSE
        && read==sizeof(value);
}
}
void RecordObservation(HANDLE process,std::uintptr_t image,std::uintptr_t helper,const Profile& profile,Timeline& trace) {
    std::uintptr_t pool{},hash{};
    enhanced::BootRecord boot{};
    const bool poolRead=image && Read(process,image+profile.poolPointerRva,pool);
    const bool hashRead=image && Read(process,image+profile.hashPointerRva,hash);
    const bool bootRead=helper && Read(process,helper+profile.helperBootRva,boot);
    std::ostringstream fields;
    fields << "\"provisional\":true,\"imageBase\":" << image << ",\"helperBase\":" << helper
        << ",\"poolReadable\":" << (poolRead?"true":"false") << ",\"poolPointer\":" << pool
        << ",\"hashReadable\":" << (hashRead?"true":"false") << ",\"hashPointer\":" << hash
        << ",\"bootReadable\":" << (bootRead?"true":"false") << ",\"bootAbi\":" << boot.abi
        << ",\"bootBytes\":" << boot.bytes << ",\"bootModule\":" << boot.module
        << ",\"bootReady\":" << boot.ready << ",\"bootReserved\":" << boot.reserved;
    trace.Event("observation",fields.str().c_str());
}
bool RecordSignaledExit(HANDLE process,Outcome& outcome,Timeline& trace) {
    const DWORD wait=WaitForSingleObject(process,0);
    Require(wait==WAIT_OBJECT_0 || wait==WAIT_TIMEOUT,"Cannot observe diagnostic process lifetime.");
    if(wait==WAIT_TIMEOUT) return false;
    Require(GetExitCodeProcess(process,&outcome.exitCode)!=FALSE,"Cannot read signaled diagnostic exit code.");
    const auto fields="\"exitCode\":"+std::to_string(outcome.exitCode)+",\"source\":\"process-handle\"";
    trace.Event("process-exit",fields.c_str());
    return true;
}
}
