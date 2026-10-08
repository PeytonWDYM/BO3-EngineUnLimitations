#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <fstream>
#include <string>
#include <cstring>
#include "../../launch/startup_gate/GateContract.h"
#include "../../launch/startup_probe/Observation.h"
#include "StackEvidence.h"
using bo3::startup_gate::State;
using bo3::startup_gate::Phase;
extern "C" {
__declspec(dllexport) std::uintptr_t ControlPool{},ControlHash{};
__declspec(dllexport) alignas(4096) unsigned char ProbeStorage[4096]{};
int OwnedCaller(); int OwnedCrtCaller();
__declspec(dllimport) DWORD ConsumerProof();
__declspec(dllimport) const StackEvidence* ConsumerStack();
}
namespace {
bool tlsProof{};
DWORD tlsQuery{},tlsError{}; LONG tlsBefore{},tlsAfter{};
StackEvidence tlsStack{};
State* StateRecord() {
    return reinterpret_cast<State*>(GetProcAddress(GetModuleHandleW(L"Bo3StartupGate.dll"),"Bo3StartupGateState"));
}
void NTAPI Tls(PVOID,DWORD reason,PVOID) {
    if(reason!=DLL_PROCESS_ATTACH) return;
    using Query=BOOLEAN(NTAPI*)();
    const auto query=reinterpret_cast<Query>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"RtlIsThreadWithinLoaderCallout"));
    auto* state=StateRecord();
    tlsQuery=query(); tlsBefore=state->phase;
    tlsStack=CaptureEntryStack();
    SetLastError(0x2468); OwnedCrtCaller();
    tlsError=GetLastError(); tlsAfter=state->phase;
    tlsProof=tlsStack.anchorAvailable && !tlsStack.anchorPresent && tlsError==0x2468
        && state->phase==static_cast<LONG>(Phase::Armed) && !state->generation;
}
#pragma const_seg(".CRT$XLB")
extern "C" const PIMAGE_TLS_CALLBACK GateTls=Tls;
#pragma const_seg()
#pragma comment(linker,"/INCLUDE:GateTls")
#pragma comment(linker,"/INCLUDE:_tls_used")
DWORD WINAPI WrongThread(void*) { OwnedCrtCaller(); return 0; }
DWORD ExceptionProof() {
    __try { GetStartupInfoW(nullptr); }
    __except(GetExceptionCode()==EXCEPTION_ACCESS_VIOLATION ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) { return GetExceptionCode(); }
    return 0;
}
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=4) return 1;
    const std::wstring scenario=argv[1];
    auto* state=StateRecord();
    const auto helper=GetModuleHandleW(L"Bo3StartupGate.dll");
    auto* counters=reinterpret_cast<bo3::startup_probe::Counters*>(GetProcAddress(helper,"Bo3StartupProbeCounters"));
    const auto mainStack=CaptureEntryStack();
    using Startup=void(WINAPI*)(LPSTARTUPINFOW);
    const auto original=reinterpret_cast<Startup>(counters->originalTrampoline);
    STARTUPINFOW expected{},actual{};
    SetLastError(0x13579); original(&expected); const auto error=GetLastError();
    SetLastError(0x13579); GetStartupInfoW(&actual);
    bool api=std::memcmp(&expected,&actual,sizeof(actual))==0 && GetLastError()==error;
    wchar_t app[32]{},game[32]{};
    GetEnvironmentVariableW(L"SteamAppId",app,32); GetEnvironmentVariableW(L"SteamGameId",game,32);
    const bool env=std::wstring(app)==L"311210" && std::wstring(game)==L"311210" && std::wstring(argv[3])==L"quoted \"value\" \\";
    DWORD unwind{};
    if(scenario==L"unwind") unwind=ExceptionProof();
    else if(scenario==L"noncrt") OwnedCaller();
    else if(scenario==L"wrongthread") {
        HANDLE thread=CreateThread(nullptr,0,WrongThread,nullptr,0,nullptr);
        if(!thread || WaitForSingleObject(thread,2000)!=WAIT_OBJECT_0) return 2;
        CloseHandle(thread);
    } else if(scenario==L"changedcaller") {
        auto* byte=reinterpret_cast<unsigned char*>(OwnedCaller)+29;
        DWORD old{}; if(!VirtualProtect(byte,1,PAGE_EXECUTE_READWRITE,&old)) return 3;
        *byte^=1; OwnedCrtCaller(); *byte^=1;
        VirtualProtect(byte,1,old,&old); FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(OwnedCaller),44);
    } else if(scenario!=L"nonmatch") {
        SetLastError(0x13579); const int shown=OwnedCrtCaller();
        api=api && GetLastError()==error && shown==((expected.dwFlags&STARTF_USESHOWWINDOW) ? expected.wShowWindow : 10);
        if(scenario==L"repeated") OwnedCrtCaller();
    }
    const bool gateExpected=scenario==L"success" || scenario==L"repeated";
    const bool good=tlsProof && ConsumerProof()==1 && env && api && !IsDebuggerPresent()
        && state->phase==static_cast<LONG>(gateExpected ? Phase::Returned : Phase::Armed)
        && state->generation==(gateExpected ? 1u : 0u) && counters->vmReads==(gateExpected ? 13 : 0)
        && (scenario!=L"unwind" || unwind==EXCEPTION_ACCESS_VIOLATION);
    std::ofstream proof(argv[2]);
    proof << "{\"passed\":" << (good?"true":"false") << ",\"tlsLoaderProof\":" << (tlsProof?"true":"false")
        << ",\"tlsQuery\":" << tlsQuery << ",\"tlsBefore\":" << tlsBefore << ",\"tlsAfter\":" << tlsAfter << ",\"tlsError\":" << tlsError
        << ",\"anchorAvailable\":" << mainStack.anchorAvailable << ",\"anchorStart\":" << mainStack.anchorStart << ",\"anchorEnd\":" << mainStack.anchorEnd
        << ",\"mainAnchor\":" << mainStack.anchorPresent << ",\"tlsAnchor\":" << tlsStack.anchorPresent << ",\"dllAnchor\":" << ConsumerStack()->anchorPresent
        << ",\"dllLoaderProof\":" << (ConsumerProof()==1?"true":"false") << ",\"apiPreserved\":" << (api?"true":"false")
        << ",\"environmentPreserved\":" << (env?"true":"false") << ",\"debugger\":" << (IsDebuggerPresent()?"true":"false")
        << ",\"phase\":" << state->phase << ",\"generation\":" << state->generation << ",\"vmReads\":" << counters->vmReads
        << ",\"unwindCode\":" << unwind;
    for(const auto& item: {std::pair<const char*,const StackEvidence*>("mainFrames",&mainStack),{"tlsFrames",&tlsStack},{"dllFrames",ConsumerStack()}}) {
        proof << ",\"" << item.first << "\":[";
        for(DWORD i=0;i<item.second->count;++i) { if(i) proof << ','; proof << item.second->frames[i]; }
        proof << ']';
    }
    proof << "}\n";
    return good ? 0 : 4;
}
