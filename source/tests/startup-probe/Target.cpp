#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <fstream>
#include <string>
#include <cstring>
#include "../../launch/enhanced/Boot.h"
#include "../../launch/startup_probe/Observation.h"
using bo3::startup_probe::Observation;
using bo3::startup_probe::Counters;
extern "C" {
__declspec(dllexport) std::uintptr_t ControlPool{},ControlHash{};
__declspec(dllexport) alignas(4096) unsigned char ProbeStorage[4096]{};
int OwnedCaller(); int OwnedCrtCaller();
__declspec(dllimport) DWORD ConsumerProof();
}
namespace {
Counters* counters{};
Observation* record{};
bool tlsReady{};
void Locate() {
    const auto helper=GetModuleHandleW(L"Bo3EnhancedHelper.dll");
    counters=reinterpret_cast<Counters*>(GetProcAddress(helper,"Bo3StartupProbeCounters"));
    record=reinterpret_cast<Observation*>(GetProcAddress(helper,"Bo3StartupProbeObservation"));
}
void NTAPI Tls(PVOID,DWORD reason,PVOID) {
    if(reason!=DLL_PROCESS_ATTACH) return;
    Locate();
    const auto helper=GetModuleHandleW(L"Bo3EnhancedHelper.dll");
    const auto* boot=reinterpret_cast<const bo3::enhanced::BootRecord*>(GetProcAddress(helper,"Bo3EnhancedBoot"));
    const LONG before=counters ? counters->vmReads : -1;
    STARTUPINFOW info{}; SetLastError(0x2468); GetStartupInfoW(&info);
    tlsReady=boot && boot->ready==1 && counters && before==0 && counters->vmReads==0
        && info.cb==sizeof(info) && GetLastError()==0x2468;
}
#pragma const_seg(".CRT$XLB")
extern "C" const PIMAGE_TLS_CALLBACK ProbeTls=Tls;
#pragma const_seg()
#pragma comment(linker,"/INCLUDE:ProbeTls")
#pragma comment(linker,"/INCLUDE:_tls_used")
bool Copy(Observation& out) {
    const LONG before=InterlockedCompareExchange(&record->sequence,0,0);
    if(before&1) return false;
    SIZE_T count{};
    if(!ReadProcessMemory(GetCurrentProcess(),record,&out,sizeof(out),&count) || count!=sizeof(out)) return false;
    const LONG after=InterlockedCompareExchange(&record->sequence,0,0);
    return before==after && out.sequence==after && !(after&1);
}
DWORD WINAPI Writer(void*) { for(unsigned int i=0;i<1000;++i) OwnedCrtCaller(); return 0; }
LONG Unwind() {
    __try { GetStartupInfoW(nullptr); }
    __except(GetExceptionCode()==EXCEPTION_ACCESS_VIOLATION ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) { return GetExceptionCode(); }
    return 0;
}
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=4) return 1;
    Locate();
    const std::wstring scenario=argv[1];
    const bool ready=tlsReady && ConsumerProof()==1 && counters && record
        && counters->abi==1 && counters->bytes==sizeof(Counters) && record->abi==1 && record->bytes==sizeof(Observation);
    wchar_t app[32]{},game[32]{};
    GetEnvironmentVariableW(L"SteamAppId",app,32); GetEnvironmentVariableW(L"SteamGameId",game,32);
    const bool environment=std::wstring(app)==L"311210" && std::wstring(game)==L"311210"
        && std::wstring(argv[3])==L"quoted \"value\" with trailing \\";
    using Startup=void(WINAPI*)(LPSTARTUPINFOW);
    const auto original=reinterpret_cast<Startup>(counters->originalTrampoline);
    STARTUPINFOW baseline{},observed{};
    SetLastError(0x13579); original(&baseline); const DWORD expectedError=GetLastError();
    SetLastError(0x13579); GetStartupInfoW(&observed);
    bool api=std::memcmp(&baseline,&observed,sizeof(baseline))==0 && GetLastError()==expectedError;
    const LONG initialReads=counters->vmReads;
    LONG unwind{};
    DWORD discarded{};
    if(scenario==L"unwind") unwind=Unwind();
    else if(scenario==L"changed-caller") {
        auto* byte=reinterpret_cast<unsigned char*>(OwnedCaller)+29;
        if(!VirtualProtect(byte,1,PAGE_EXECUTE_READWRITE,&discarded)) return 2;
        *byte^=1; // Change the owned fallback immediate while retaining a callable wrapper.
        SetLastError(0x13579); OwnedCrtCaller();
        *byte^=1;
        VirtualProtect(byte,1,discarded,&discarded);
        FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(OwnedCaller),44);
    } else if(scenario==L"race") {
        HANDLE threads[4]{}; DWORD ids[4]{};
        for(unsigned int i=0;i<4;++i) threads[i]=CreateThread(nullptr,0,Writer,nullptr,0,&ids[i]);
        unsigned int accepted{}; Observation view{};
        while(WaitForMultipleObjects(4,threads,TRUE,0)==WAIT_TIMEOUT) {
            if(Copy(view) && view.count) {
                if(view.sequence!=static_cast<LONG>(view.count*2) || view.readableMask!=8191 || !view.wrapperCallerMatches) return 3;
                ++accepted;
            }
        }
        for(auto thread:threads) CloseHandle(thread);
        if(!accepted || counters->attempts!=4000 || static_cast<LONG>(record->count)+counters->dropped!=4000) return 4;
    } else if(scenario==L"unreadable") {
        if(!VirtualProtect(ProbeStorage,sizeof(ProbeStorage),PAGE_NOACCESS,&discarded)) return 5;
        OwnedCrtCaller();
        VirtualProtect(ProbeStorage,sizeof(ProbeStorage),discarded,&discarded);
    } else if(scenario==L"nonmatch") {
        for(unsigned int i=0;i<3;++i) GetStartupInfoW(&observed);
    } else {
        SetLastError(0x13579);
        const int shown=scenario==L"other-wrapper-caller" ? OwnedCaller() : OwnedCrtCaller();
        api=api && shown==((baseline.dwFlags&STARTF_USESHOWWINDOW) ? baseline.wShowWindow : 10) && GetLastError()==expectedError;
        if(scenario==L"repeated") for(unsigned int i=0;i<4;++i) OwnedCrtCaller();
    }
    Observation snapshot{};
    if(!Copy(snapshot)) return 6;
    const bool noReads=scenario==L"nonmatch" || scenario==L"unwind" || scenario==L"changed-caller";
    const bool good=ready && environment && api && !IsDebuggerPresent()
        && (!noReads || counters->vmReads==initialReads)
        && (scenario!=L"unwind" || unwind==static_cast<LONG>(EXCEPTION_ACCESS_VIOLATION))
        && (scenario!=L"changed-caller" || counters->rejected==1)
        && (scenario!=L"other-wrapper-caller" || (snapshot.wrapperCallerReadable && !snapshot.wrapperCallerMatches));
    std::ofstream proof(argv[2]);
    proof << "{\"ready\":" << (ready?"true":"false") << ",\"apiPreserved\":" << (api?"true":"false")
        << ",\"environmentPreserved\":" << (environment?"true":"false") << ",\"debugger\":" << (IsDebuggerPresent()?"true":"false")
        << ",\"count\":" << snapshot.count << ",\"sequence\":" << snapshot.sequence << ",\"threadId\":" << snapshot.threadId
        << ",\"returnSite\":" << snapshot.returnSite << ",\"wrapperCallerReturn\":" << snapshot.wrapperCallerReturn
        << ",\"wrapperCallerReadable\":" << snapshot.wrapperCallerReadable << ",\"wrapperCallerMatches\":" << snapshot.wrapperCallerMatches
        << ",\"readableMask\":" << snapshot.readableMask << ",\"attempts\":" << counters->attempts
        << ",\"rejected\":" << counters->rejected << ",\"dropped\":" << counters->dropped << ",\"vmReads\":" << counters->vmReads
        << ",\"unwindCode\":" << static_cast<DWORD>(unwind) << ",\"passed\":" << (good?"true":"false") << "}\n";
    return good ? 0 : 7;
}
