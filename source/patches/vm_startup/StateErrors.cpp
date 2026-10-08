#include "StateErrors.h"

namespace bo3::vm {
extern "C" constinit ErrorBindings Bo3VmErrorBindings{};
namespace {
constexpr char unsupportedMode[]="This enhanced session supports Zombies only. Relaunch BO3 through stock Steam to use this mode (error %d).";
}

void ReadStateOrDrop(std::uint32_t instance, void* file) {
    const auto error=Bo3VmErrorBindings.read(instance,file);
    if(error!=StateError::None)
        Bo3VmErrorBindings.entry("bo3-vm-state",__LINE__,2,error==StateError::UnsupportedMode ? unsupportedMode
            : "VM state read rejected (error %d).",static_cast<int>(error));
}
void WriteStateOrDrop(std::uint32_t instance, void* file) {
    const auto error=Bo3VmErrorBindings.write(instance,file);
    if(error!=StateError::None)
        Bo3VmErrorBindings.entry("bo3-vm-state",__LINE__,2,error==StateError::UnsupportedMode ? unsupportedMode
            : "VM state write rejected (error %d).",static_cast<int>(error));
}
}
