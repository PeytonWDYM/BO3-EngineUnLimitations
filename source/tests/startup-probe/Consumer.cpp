#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include "../../launch/enhanced/Boot.h"
#include "../../launch/startup_probe/Observation.h"
namespace { DWORD proof{}; }
extern "C" __declspec(dllexport) DWORD ConsumerProof() { return proof; }
BOOL WINAPI DllMain(HINSTANCE,DWORD reason,LPVOID) {
    if(reason!=DLL_PROCESS_ATTACH) return TRUE;
    const auto helper=GetModuleHandleW(L"Bo3EnhancedHelper.dll");
    const auto* boot=reinterpret_cast<const bo3::enhanced::BootRecord*>(GetProcAddress(helper,"Bo3EnhancedBoot"));
    const auto* counters=reinterpret_cast<const bo3::startup_probe::Counters*>(GetProcAddress(helper,"Bo3StartupProbeCounters"));
    const LONG before=counters ? counters->vmReads : -1;
    STARTUPINFOW info{};
    SetLastError(0x13579); GetStartupInfoW(&info);
    proof=helper && boot && boot->ready==1 && counters && counters->vmReads==before
        && before==0 && info.cb==sizeof(info) && GetLastError()==0x13579;
    return TRUE;
}
