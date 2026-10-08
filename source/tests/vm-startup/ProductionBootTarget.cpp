#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include "../../launch/enhanced/Boot.h"
#include "../../patches/vm_pool/NativeStateBridge.h"
#include "../../patches/vm_startup/StateErrors.h"
#include <array>
#include <utility>

int main() {
    if (GetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING", nullptr, 0)) return 1;
    const auto helper = GetModuleHandleW(L"VmStartupHelper.dll");
    if (!helper) return 2;
    const auto* boot = reinterpret_cast<const bo3::enhanced::BootRecord*>(GetProcAddress(helper, "Bo3EnhancedBoot"));
    if (!boot || boot->abi != bo3::enhanced::BootAbi || boot->bytes != sizeof(*boot)
        || boot->module != reinterpret_cast<std::uintptr_t>(helper) || boot->ready != 1 || boot->reserved) return 3;
    const std::array records{
        std::pair{"Bo3VmStateBindings", sizeof(bo3::vm::NativeStateBindings)},
        std::pair{"Bo3VmErrorBindings", sizeof(bo3::vm::ErrorBindings)}};
    for (const auto& [name, size] : records) {
        const auto* data = reinterpret_cast<const unsigned char*>(GetProcAddress(helper, name));
        if (!data) return 4;
        for (std::size_t index = 0; index < size; ++index) if (data[index]) return 5;
    }
    if (GetProcAddress(helper, "FixtureBindingReader") || GetProcAddress(helper, "FixtureBindingWriter")) return 6;
    return 0;
}
