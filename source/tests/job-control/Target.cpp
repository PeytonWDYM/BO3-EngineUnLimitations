#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include "../../launch/startup_gate/GateContract.h"
#include "GameManifest.h"
#include <fstream>
#include <string>
#include <cstring>

extern "C" {
__declspec(dllexport) std::uintptr_t OwnedImage{},ControlPool{},ControlHash{};
__declspec(dllexport) alignas(4096) unsigned char ProbeStorage[4096]{};
int OwnedCrtCaller();
int OwnedCaller();
}
namespace {DWORD WINAPI Extra(void*){Sleep(INFINITE);return 0;}}
// This owned fixture alone restores two encrypted disk unwind records before its caller runs.
// It reproduces the game's disk/runtime metadata distinction without game execution.
bool RestoreOwnedUnwind() {
    const unsigned char wrapper[]{1,7,2,0,7,1,19,0},crt[]{1,4,1,0,4,66,0,0};
    const std::pair<DWORD64,const unsigned char*> rows[]{
        {reinterpret_cast<DWORD64>(OwnedCaller),wrapper},{reinterpret_cast<DWORD64>(OwnedCrtCaller),crt}};
    for(const auto& [pc,bytes]:rows) {
        DWORD64 base{};const auto* row=RtlLookupFunctionEntry(pc,&base,nullptr);
        if(!row)return false;
        auto* info=reinterpret_cast<void*>(base+row->UnwindData);DWORD prior{},discarded{};
        if(!VirtualProtect(info,8,PAGE_READWRITE,&prior))return false;
        std::memcpy(info,bytes,8);
        if(!VirtualProtect(info,8,prior,&discarded))return false;
    }
    return true;
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=4)return 1;
    if(!RestoreOwnedUnwind())return 4;
    const std::wstring scenario=argv[1];
    if(scenario==L"extra-thread") {
        const auto thread=CreateThread(nullptr,0,Extra,nullptr,0,nullptr);
        if(!thread)return 3;
        CloseHandle(thread);
    }
    if(scenario==L"early-exit")return 15;
    const auto module=GetModuleHandleW(L"Bo3StartupGate.dll");
    const auto state=reinterpret_cast<const bo3::startup_gate::State*>(GetProcAddress(module,"Bo3StartupGateState"));
    SetLastError(0x2468);const int shown=OwnedCrtCaller();const auto error=GetLastError();
    bool counts=OwnedImage!=0;
    for(const auto& count:bo3::enhanced::GameCounts) {
        std::uint32_t value{};if(OwnedImage)std::memcpy(&value,reinterpret_cast<void*>(OwnedImage+count.rva+count.immediateOffset),4);
        counts=counts && value==130000;
    }
    const bool debugger=IsDebuggerPresent()!=FALSE;
    const bool passed=state && state->phase==static_cast<LONG>(bo3::startup_gate::Phase::Returned)
        && !debugger && counts && shown==10 && error==0x2468;
    if(scenario==L"changed") {
        // Fixture-only observable change after gate release, outside all stock spans.
        *reinterpret_cast<unsigned char*>(OwnedImage+0x4c98c80)=0x5a;
        const unsigned char wrong=0xc3;
        std::memcpy(reinterpret_cast<void*>(OwnedImage+0x22b9b50),&wrong,1);
        DWORD prior{};VirtualProtect(reinterpret_cast<void*>(OwnedImage+bo3::enhanced::GameCounts[0].rva),4,PAGE_READONLY,&prior);
    }
    // Fixture-only lifetime ensures the real parent polling loop has a running observation.
    Sleep(1600);
    std::ofstream proof(argv[3]);
    proof<<"{\"passed\":"<<(passed?"true":"false")<<",\"debuggerAtReturn\":"<<(debugger?"true":"false")
        <<",\"all19Counts\":"<<(counts?"true":"false")<<",\"apiResult\":"<<shown<<",\"lastError\":"<<error
        <<",\"gatePhase\":"<<(state?state->phase:-1)<<"}";
    return passed?0:2;
}
