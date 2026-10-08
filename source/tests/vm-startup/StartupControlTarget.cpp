#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <cstdint>
#include <fstream>
#include <string>
#include <cwchar>
#include <intrin.h>
#include "../../launch/enhanced/Boot.h"

extern "C" {
__declspec(dllexport) std::uintptr_t ControlPool{};
__declspec(dllexport) std::uintptr_t ControlHash{};
}
namespace {
unsigned int handled{};
LONG WINAPI Handler(EXCEPTION_POINTERS* exception) {
    if(exception->ExceptionRecord->ExceptionCode!=0xe0427630
        && exception->ExceptionRecord->ExceptionCode!=EXCEPTION_BREAKPOINT) return EXCEPTION_CONTINUE_SEARCH;
    if(exception->ExceptionRecord->ExceptionCode==EXCEPTION_BREAKPOINT) ++exception->ContextRecord->Rip;
    ++handled; return EXCEPTION_CONTINUE_EXECUTION;
}
void NTAPI Tls(PVOID,DWORD reason,PVOID) {
    if(reason==DLL_PROCESS_ATTACH && std::wcsstr(GetCommandLineW(),L"tls-breakpoint")) {
        const auto handler=AddVectoredExceptionHandler(1,Handler);
        if(!handler) ExitProcess(6);
        __debugbreak();
        RemoveVectoredExceptionHandler(handler);
    }
}
}
extern "C" const PIMAGE_TLS_CALLBACK ControlTls=Tls;
#pragma comment(linker,"/INCLUDE:ControlTls")
#pragma comment(linker,"/INCLUDE:_tls_used")
#pragma const_seg(".CRT$XLB")
extern "C" const PIMAGE_TLS_CALLBACK ControlTlsEntry=Tls;
#pragma const_seg()
#pragma comment(linker,"/INCLUDE:ControlTlsEntry")
int wmain(int argc,wchar_t** argv) {
    if(argc!=4) return 1;
    CONTEXT context{}; context.ContextFlags=CONTEXT_ALL;
    using Query=LONG(NTAPI*)(HANDLE,CONTEXT*);
    const auto query=reinterpret_cast<Query>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtGetContextThread"));
    const LONG status=query(GetCurrentThread(),&context);
    const auto helper=GetModuleHandleW(L"Bo3EnhancedHelper.dll");
    if(!helper) return 2;
    const auto* boot=reinterpret_cast<const bo3::enhanced::BootRecord*>(GetProcAddress(helper,"Bo3EnhancedBoot"));
    const bool ready=boot && boot->abi==1 && boot->bytes==24 && boot->ready==1
        && boot->module==reinterpret_cast<std::uintptr_t>(helper) && boot->reserved==0;
    const std::wstring scenario=argv[1];
    const bool passive=scenario.starts_with(L"passive-");
    const bool debugger=IsDebuggerPresent()!=FALSE;
    if(scenario==L"exception" || scenario==L"passive-exception" || scenario==L"breakpoint") {
        const auto handler=AddVectoredExceptionHandler(1,Handler);
        if(!handler) return 3;
        if(scenario==L"breakpoint") __debugbreak();
        else RaiseException(0xe0427630,0,0,nullptr);
        RemoveVectoredExceptionHandler(handler);
    }
    wchar_t app[32]{},game[32]{};
    GetEnvironmentVariableW(L"SteamAppId",app,32); GetEnvironmentVariableW(L"SteamGameId",game,32);
    const bool ids=std::wstring(app)==L"311210" && std::wstring(game)==L"311210";
    const bool argument=std::wstring(argv[3])==L"quoted \"value\" with trailing \\";
    std::ofstream proof(argv[2]);
    proof << "{\"queryStatus\":" << status << ",\"debugger\":" << (debugger?"true":"false")
        << ",\"bootReady\":" << (ready?"true":"false") << ",\"steamIds\":" << (ids?"true":"false")
        << ",\"argumentPreserved\":" << (argument?"true":"false") << ",\"handled\":" << handled
        << ",\"dr0\":" << context.Dr0 << ",\"dr1\":" << context.Dr1 << ",\"dr2\":" << context.Dr2
        << ",\"dr3\":" << context.Dr3 << ",\"dr7\":" << context.Dr7 << "}\n";
    proof.close();
    if(status<0 || !ready || !ids || !argument || debugger==passive || context.Dr0 || context.Dr1
        || context.Dr2 || context.Dr3 || (context.Dr7&0xffff00ff)) return 4;
    if(scenario==L"timeout" || scenario==L"passive-timeout") Sleep(INFINITE);
    if(scenario==L"event-stream") for(;;) { OutputDebugStringW(L"Owned deadline event stream"); Sleep(10); }
    if(scenario==L"detach-exit") {
        Sleep(350); // Let the observer record ready Boot before the owned detach.
        // Owned fixture only: reproduce loss of EXIT_PROCESS_DEBUG_EVENT.
        using QueryProcess=LONG(NTAPI*)(HANDLE,ULONG,void*,ULONG,ULONG*);
        using RemoveDebug=LONG(NTAPI*)(HANDLE,HANDLE);
        const auto ntdll=GetModuleHandleW(L"ntdll.dll");
        const auto queryProcess=reinterpret_cast<QueryProcess>(GetProcAddress(ntdll,"NtQueryInformationProcess"));
        const auto removeDebug=reinterpret_cast<RemoveDebug>(GetProcAddress(ntdll,"NtRemoveProcessDebug"));
        HANDLE object{};
        if(queryProcess(GetCurrentProcess(),30,&object,sizeof(object),nullptr)<0) return 7;
        const LONG removed=removeDebug(GetCurrentProcess(),object);
        CloseHandle(object);
        if(removed<0) return 8;
        return 23;
    }
    if(passive) Sleep(350); // Allow one positive passive inventory without changing launcher timing.
    if(scenario==L"passive-exit") return 23;
    return (scenario==L"exception" || scenario==L"passive-exception") && handled!=1 ? 5 : 0;
}
