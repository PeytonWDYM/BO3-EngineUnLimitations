#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include "../../launch/startup_gate/GateContract.h"
#include "GameManifest.h"
#include <filesystem>
#include <fstream>
#include <string>
#include <cstring>

extern "C" {
__declspec(dllexport) std::uintptr_t ControlPool{},ControlHash{},OwnedImage{};
__declspec(dllexport) alignas(4096) unsigned char ProbeStorage[4096]{};
__declspec(dllexport) volatile LONG64 WorkerTicks{};
__declspec(dllexport) volatile LONG TriggerBreak{},ForeignBreakHandled{};
int OwnedCrtCaller();
}
namespace {
volatile LONG done{};
DWORD WINAPI Worker(void* arg) {
    bool raised=false;
    while(!InterlockedCompareExchange(&done,0,0)) {
        InterlockedIncrement64(&WorkerTicks);
        if(arg && !raised && InterlockedCompareExchange(&TriggerBreak,0,0)) {
            __try {
                // Use the exact attach export. KernelBase!DebugBreak has a different exception address.
                reinterpret_cast<void(NTAPI*)()>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"DbgBreakPoint"))();
            }
            __except(GetExceptionCode()==EXCEPTION_BREAKPOINT ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
                InterlockedIncrement(&ForeignBreakHandled);
            }
            raised=true;
        }
        Sleep(1);
    }
    return 0;
}
bool Load(const std::filesystem::path& path) {
    OwnedImage=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,494186496,MEM_RESERVE,PAGE_READWRITE));
    if(!OwnedImage)return false;
    std::ifstream file(path,std::ios::binary);std::uint32_t records{};file.read(reinterpret_cast<char*>(&records),4);
    if(!file.good() || records>200)return false;
    for(std::uint32_t i=0;i<records;++i) {
        std::uint32_t rva{},size{};file.read(reinterpret_cast<char*>(&rva),4);file.read(reinterpret_cast<char*>(&size),4);
        if(!file.good() || !size || size>494186496 || rva>494186496-size)return false;
        const auto start=(OwnedImage+rva)&~std::uintptr_t{4095};
        const auto end=(OwnedImage+rva+size+4095)&~std::uintptr_t{4095};
        if(!VirtualAlloc(reinterpret_cast<void*>(start),end-start,MEM_COMMIT,PAGE_READWRITE))return false;
        file.read(reinterpret_cast<char*>(OwnedImage+rva),size);if(!file.good())return false;
    }
    return true;
}
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=4 || !Load(argv[2]))return 1;
    const std::wstring scenario=argv[1];
#ifdef BO3_LATE_STOCK_CONTROL_TARGET
    if(scenario==L"pre-gate-exit")return 23;
#endif
    if(scenario==L"guard")*reinterpret_cast<unsigned char*>(OwnedImage+0x12dba10)^=1;
    if(scenario==L"allocated")*reinterpret_cast<std::uintptr_t*>(OwnedImage+0x5124580)=1;
#ifdef BO3_LATE_STOCK_CONTROL_TARGET
    if(scenario==L"call")*reinterpret_cast<unsigned char*>(OwnedImage+0x22b1559)^=1;
    if(scenario==L"target")*reinterpret_cast<unsigned char*>(OwnedImage+0x227a3a0)^=1;
#endif
    const auto module=GetModuleHandleW(L"Bo3StartupGate.dll");
    const auto state=reinterpret_cast<const bo3::startup_gate::State*>(GetProcAddress(module,"Bo3StartupGateState"));
    HANDLE workers[4]{};
    for(unsigned int i=0;i<4;++i)workers[i]=CreateThread(nullptr,0,Worker,
        scenario==L"foreign-break" && i==0 ? reinterpret_cast<void*>(1) : nullptr,0,nullptr);
    SetLastError(0x2468);const int shown=OwnedCrtCaller();const auto error=GetLastError();
    bool counts=true;
    for(const auto& count:bo3::enhanced::GameCounts) {
        std::uint32_t value{};std::memcpy(&value,reinterpret_cast<void*>(OwnedImage+count.rva+count.immediateOffset),4);
#ifdef BO3_LATE_STOCK_CONTROL_TARGET
        counts=counts && value==130000;
#else
        counts=counts && value==500001;
#endif
    }
    const bool debugger=IsDebuggerPresent()!=FALSE;
    InterlockedExchange(&done,1);WaitForMultipleObjects(4,workers,TRUE,5000);
    for(const auto worker:workers)CloseHandle(worker);
    const bool passed=state && state->phase==static_cast<LONG>(bo3::startup_gate::Phase::Returned)
        && !debugger && counts && shown==10 && error==0x2468 && WorkerTicks>0
        && (scenario!=L"foreign-break" || ForeignBreakHandled==1);
    std::ofstream proof(argv[3]);
    proof<<"{\"passed\":"<<(passed?"true":"false")<<",\"debuggerAtReturn\":"<<(debugger?"true":"false")
        <<",\"all19Counts\":"<<(counts?"true":"false")<<",\"apiResult\":"<<shown<<",\"lastError\":"<<error
        <<",\"workerTicks\":"<<WorkerTicks<<",\"foreignBreakHandled\":"<<ForeignBreakHandled<<",\"gatePhase\":"<<(state?state->phase:-1)<<"}";
    proof.flush();Sleep(500);
#ifdef BO3_LATE_STOCK_CONTROL_TARGET
    if(scenario==L"early-exit")return passed?17:2;
    if(scenario==L"timeout")Sleep(INFINITE);
#endif
    return passed?0:2;
}
