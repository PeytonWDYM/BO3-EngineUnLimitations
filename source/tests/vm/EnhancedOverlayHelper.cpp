#include <Windows.h>
#include <cstdint>
struct Boot { std::uint32_t abi,bytes; std::uintptr_t module; std::uint32_t ready,reserved; };
struct Bindings { std::uintptr_t image; std::uint32_t total,clients,stockClients,mode; std::uintptr_t callbacks[3]; };
static_assert(sizeof(Boot)==24 && sizeof(Bindings)==48);
extern "C" {
__declspec(dllexport) Boot Bo3EnhancedBoot{};
__declspec(dllexport) Bindings Bo3VmStateBindings{};
__declspec(dllexport) void OwnedCallback() {}
}
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) Bo3EnhancedBoot={1,24,reinterpret_cast<std::uintptr_t>(module),1,0};
    return TRUE;
}
