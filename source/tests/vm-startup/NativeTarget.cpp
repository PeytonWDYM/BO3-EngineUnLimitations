#include "NativeOwned.h"
#include "../../launch/preentry/Identity.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
extern "C" {
__declspec(dllexport) __declspec(align(4096)) unsigned char NativeGate[4096]{};
__declspec(dllexport) std::uintptr_t NativePoolPointer=0,NativeHashPointer=0;
__declspec(dllimport) void OwnedConsumerAnchor();
}
int main() {
    try {
        OwnedConsumerAnchor();
        wchar_t text[64]{};
        Require(GetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING",text,64)!=0,"Owned native mapping is missing.");
        auto* shared=static_cast<NativeShared*>(MapViewOfFile(reinterpret_cast<HANDLE>(_wcstoui64(text,nullptr,10)),FILE_MAP_WRITE,0,0,sizeof(NativeShared)));
        Require(shared!=nullptr,"Cannot map owned native composition trace.");
        shared->loader.helperAtTls=shared->loader.helperLoaded;
        SetupNativeImage(shared);
        const unsigned char count[]{0xb8,0xd0,0xfb,0x01,0,0xc3};
        std::memcpy(NativeGate,count,sizeof(count)); std::memcpy(NativeGate+64,count,sizeof(count));
        DWORD old=0;
        Require(VirtualProtect(NativeGate,sizeof(NativeGate),PAGE_EXECUTE_READ,&old)!=FALSE
            && FlushInstructionCache(GetCurrentProcess(),NativeGate,sizeof(NativeGate))!=FALSE,"Cannot publish owned native gate.");
        const auto first=reinterpret_cast<DWORD(*)()>(&NativeGate[0])();
        const auto second=reinterpret_cast<DWORD(*)()>(NativeGate+64)();
        ++shared->loader.calls;
        Require(first==shared->loader.expectedTotal && second==first,"Native gate count differs.");
        RunNativeExports();
        shared->loader.done=1;
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 2; }
}
