#include "StartupObservation.h"
#include "../preentry/Identity.h"
#include <Psapi.h>
#include <array>

namespace bo3::startup_control {
namespace {
void ObserveModules(HANDLE process,const Profile& profile,Timeline& trace) {
    std::array<HMODULE,2048> modules{};
    DWORD bytes{};
    if(!K32EnumProcessModulesEx(process,modules.data(),static_cast<DWORD>(sizeof(modules)),&bytes,LIST_MODULES_64BIT)
        || bytes>sizeof(modules) || bytes%sizeof(HMODULE)) {
        const auto fields="\"modulesReadable\":false,\"error\":"+std::to_string(GetLastError());
        trace.Event("inventory",fields.c_str()); return;
    }
    std::uintptr_t image{},helper{};
    for(std::size_t i=0;i<bytes/sizeof(HMODULE);++i) {
        std::array<wchar_t,32768> name{};
        const DWORD length=K32GetModuleFileNameExW(process,modules[i],name.data(),static_cast<DWORD>(name.size()));
        if(!length || length>=name.size()) continue;
        const auto file=std::filesystem::path(name.data()).filename().wstring();
        if(i==0) image=reinterpret_cast<std::uintptr_t>(modules[i]);
        if(CompareStringOrdinal(file.c_str(),-1,L"Bo3EnhancedHelper.dll",-1,TRUE)==CSTR_EQUAL)
            helper=reinterpret_cast<std::uintptr_t>(modules[i]);
    }
    RecordObservation(process,image,helper,profile,trace);
}
}
Outcome ObservePassive(const PROCESS_INFORMATION& child,const Profile& profile,Timeline& trace,ObservationLimit limit) {
    Outcome outcome;
    const auto deadlineMs=static_cast<DWORD>(limit);
    const auto deadline=GetTickCount64()+deadlineMs;
    ULONGLONG nextObservation{};
    for(;;) {
        if(RecordSignaledExit(child.hProcess,outcome,trace)) return outcome;
        const auto now=GetTickCount64();
        if(now>=deadline) {
            const auto fields="\"deadlineMs\":"+std::to_string(deadlineMs)+",\"activated\":false,\"editsWritten\":0";
            trace.Event("timeout",fields.c_str());
            if(!TerminateProcess(child.hProcess,97)) {
                if(RecordSignaledExit(child.hProcess,outcome,trace)) return outcome;
                Require(false,"Cannot terminate passive diagnostic child at deadline.");
            }
            outcome.timedOut=true;
            Require(WaitForSingleObject(child.hProcess,5000)==WAIT_OBJECT_0,"Passive diagnostic child did not exit.");
            Require(RecordSignaledExit(child.hProcess,outcome,trace),"Passive diagnostic exit was not signaled.");
            return outcome;
        }
        if(now>=nextObservation) {
            ObserveModules(child.hProcess,profile,trace);
            nextObservation=GetTickCount64()+250;
        }
        const DWORD wait=WaitForSingleObject(child.hProcess,100);
        Require(wait==WAIT_OBJECT_0 || wait==WAIT_TIMEOUT,"Cannot wait for passive diagnostic child.");
    }
}
}
