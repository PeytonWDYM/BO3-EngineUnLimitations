#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cstdio>
namespace {
using Query=BOOL(*)();
Query safe{};
DWORD WINAPI Worker(void*) {return safe()?0:1;}
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=2 && argc!=3)return 1;
    if(argc==3) {FILE* output{};if(_wfreopen_s(&output,argv[2],L"w",stdout))return 1;}
    const auto module=LoadLibraryW(argv[1]);
    if(!module) {std::printf("process-attach-refused error=%lu\n",GetLastError());return 1;}
    safe=reinterpret_cast<Query>(GetProcAddress(module,"Safe"));
    const auto attach=reinterpret_cast<LONG(*)()>(GetProcAddress(module,"ThreadAttach"));
    const auto broken=reinterpret_cast<Query>(GetProcAddress(module,"BrokenLockRefused"));
    if(!safe || !attach || !broken || !safe())return 2;
    std::puts("process-attach-unsafe-and-entry-safe passed");
    const HANDLE thread=CreateThread(nullptr,0,Worker,nullptr,0,nullptr);
    DWORD code=1;
    if(!thread || WaitForSingleObject(thread,5000)!=WAIT_OBJECT_0 || !GetExitCodeThread(thread,&code)
        || code || attach()!=1)return 3;
    CloseHandle(thread);
    std::puts("thread-attach-unsafe-and-entry-safe passed");
    using Lock=LONG(WINAPI*)(ULONG,ULONG*,ULONG_PTR*);
    using Unlock=LONG(WINAPI*)(ULONG,ULONG_PTR);
    const auto ntdll=GetModuleHandleW(L"ntdll.dll");
    const auto lock=reinterpret_cast<Lock>(GetProcAddress(ntdll,"LdrLockLoaderLock"));
    const auto unlock=reinterpret_cast<Unlock>(GetProcAddress(ntdll,"LdrUnlockLoaderLock"));
    ULONG first{},second{};ULONG_PTR one{},two{};
    if(!lock || !unlock || lock(2,&first,&one) || first!=1)return 4;
    if(safe() || !broken() || lock(2,&second,&two) || second!=1 || safe())return 5;
    std::puts("missing-and-unreadable-loader-lock-refused passed");
    if(unlock(0,two) || safe() || unlock(0,one) || !safe())return 6;
    std::puts("recursive-loader-lock-refuses-until-final-unlock passed");
    FreeLibrary(module);
    return 0;
}
