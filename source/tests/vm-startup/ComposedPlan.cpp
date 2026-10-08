#include "ComposedPlan.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "../../patches/vm_pool/NativeStateBridge.h"
#include "../../launch/preentry/Identity.h"
#include <cstring>

namespace {
Shared* shared;
DWORD gate, config, reader, writer, clientReader, clientWriter, insert;
DWORD Export(HMODULE module, const char* name) {
    const auto address = reinterpret_cast<std::uintptr_t>(GetProcAddress(module, name));
    Require(address > reinterpret_cast<std::uintptr_t>(module), "An owned composition export is missing.");
    return static_cast<DWORD>(address-reinterpret_cast<std::uintptr_t>(module));
}
std::vector<unsigned char> OriginalHook() {
    std::vector<unsigned char> code(14,0x90);
    const unsigned char start[]{0xb8,0xd0,0xfb,0x01,0x00,0xc3};
    std::memcpy(code.data(),start,sizeof(start));
    return code;
}
std::vector<unsigned char> Jump(std::uintptr_t address) {
    std::vector<unsigned char> code(14,0);
    code[0]=0xff; code[1]=0x25;
    std::memcpy(code.data()+6,&address,sizeof(address));
    return code;
}
}
void SetComposedPlan(Shared* state, HMODULE target, HMODULE helper, DWORD gateRva) {
    shared=state; gate=gateRva;
    config=Export(helper,"Bo3VmStateBindings");
    reader=Export(helper,"FixtureBindingReader"); writer=Export(helper,"FixtureBindingWriter");
    clientReader=Export(target,"OwnedClientReader"); clientWriter=Export(target,"OwnedClientWriter");
    insert=Export(target,"OwnedInsert");
}
std::vector<vm_startup::AddressEdit> PrepareComposed(HANDLE, const vm_startup::Receipt& receipt) {
    Require(shared->helperLoaded==1 && shared->helperBase!=0 && shared->configZeroAtLoad==1,
        "The pre-imported helper has no loader readiness.");
    Require(shared->helperAtImport==1 && shared->helperAtTls==1,
        "The helper did not precede the imported consumer and TLS.");
    bo3::vm::NativeStateBindings bindings;
    ZeroMemory(&bindings,sizeof(bindings));
    bindings.imageBase=receipt.imageBase; bindings.total=shared->expectedTotal;
    bindings.clientRoots=8; bindings.stockClientRoots=8;
    bindings.originalClientReader=reinterpret_cast<bo3::vm::WholeFunction>(receipt.imageBase+clientReader);
    bindings.originalClientWriter=reinterpret_cast<bo3::vm::WholeFunction>(receipt.imageBase+clientWriter);
    bindings.originalInsert=reinterpret_cast<bo3::vm::InsertFunction>(receipt.imageBase+insert);
    std::vector<unsigned char> bytes(sizeof(bindings));
    std::memcpy(bytes.data(),&bindings,sizeof(bindings));
    return {{shared->helperBase+config,std::vector<unsigned char>(sizeof(bindings),0),std::move(bytes)},
            {receipt.imageBase+gate+128,OriginalHook(),Jump(shared->helperBase+reader)},
            {receipt.imageBase+gate+192,OriginalHook(),Jump(shared->helperBase+writer)}};
}
bool CompositionOriginal(HANDLE process, std::uintptr_t imageBase) {
    MEMORY_BASIC_INFORMATION memory{};
    if(VirtualQueryEx(process,reinterpret_cast<void*>(imageBase+gate),&memory,sizeof(memory))!=sizeof(memory)
        || memory.Protect!=PAGE_EXECUTE_READ) return false;
    auto readerOriginal=OriginalHook();
    if(shared->scenario==Scenario::HookMismatch) readerOriginal[0]=0xb9;
    if(vm_startup::ReadStopped(process,imageBase+gate+128,14)!=readerOriginal
        || vm_startup::ReadStopped(process,imageBase+gate+192,14)!=OriginalHook()) return false;
    if(shared->helperBase==0) return true;
    if(VirtualQueryEx(process,reinterpret_cast<void*>(shared->helperBase+config),&memory,sizeof(memory))!=sizeof(memory)
        || memory.Protect!=PAGE_READWRITE) return false;
    bo3::vm::NativeStateBindings original;
    ZeroMemory(&original,sizeof(original));
    if(shared->scenario==Scenario::HelperDirty) original.total=130000;
    std::vector<unsigned char> bytes(sizeof(original));
    std::memcpy(bytes.data(),&original,sizeof(original));
    return vm_startup::ReadStopped(process,shared->helperBase+config,bytes.size())==bytes;
}
