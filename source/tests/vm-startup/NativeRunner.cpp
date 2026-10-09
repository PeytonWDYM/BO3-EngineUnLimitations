#include "NativeContract.h"
#include "../../patches/vm_startup/DebugGate.h"
#include "../../patches/vm_startup/NearRelay.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "../../launch/preentry/Identity.h"
#include "../../launch/enhanced/Boot.h"
#include "BuildIdentity.h"
#include <detours.h>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>

namespace {
NativeShared* shared;
vm_startup::ImageRange helperImage;
vm_startup::HelperOffsets offsets;
[[maybe_unused]] DWORD bootOffset;
std::unique_ptr<vm_startup::NearRelay> relay;
std::vector<vm_startup::AddressEdit> prepared;
DWORD Export(HMODULE module,const char* name) {
    const auto base=reinterpret_cast<std::uintptr_t>(module),address=reinterpret_cast<std::uintptr_t>(GetProcAddress(module,name));
    Require(address>base,"Fixed native helper export is missing."); return static_cast<DWORD>(address-base);
}
DWORD ImageSize(HMODULE module) {
    const auto* base=reinterpret_cast<const unsigned char*>(module);
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    return reinterpret_cast<const IMAGE_NT_HEADERS64*>(base+dos->e_lfanew)->OptionalHeader.SizeOfImage;
}
std::vector<unsigned char> Count(DWORD value) {
    std::vector<unsigned char> bytes(4); std::memcpy(bytes.data(),&value,4); return bytes;
}
std::vector<vm_startup::AddressEdit> Prepare(HANDLE process,const vm_startup::Receipt&) {
    Require(shared->loader.helperLoaded==1 && shared->loader.configZeroAtLoad==1 && shared->loader.helperAtImport==1,
        "Fixed native helper was not ready before the imported consumer.");
    helperImage.base=shared->loader.helperBase;
#ifdef VM_STARTUP_PRODUCTION_HELPER
    const auto bootBytes=vm_startup::ReadStopped(process,helperImage.base+bootOffset,sizeof(bo3::enhanced::BootRecord));
    bo3::enhanced::BootRecord boot{};
    std::memcpy(&boot,bootBytes.data(),sizeof(boot));
    Require(boot.abi==bo3::enhanced::BootAbi && boot.bytes==sizeof(boot) && boot.module==helperImage.base
        && boot.ready==1 && boot.reserved==0,"Production helper boot record was not admitted.");
#endif
    const vm_startup::ImageRange image{shared->imageBase,shared->imageSize};
    relay=std::make_unique<vm_startup::NearRelay>(process,image,NativeEntries);
    shared->relay=relay->Address();
    const auto address=shared->scenario==NativeScenario::FarRelay ? shared->imageBase+0x90000000ull : shared->relay;
    vm_startup::NativePlanInput input{image,helperImage,NativeEntries,offsets,address,shared->loader.expectedTotal,18,8,bo3::vm::NativeModePolicy::ZombiesOnly,
        {{0x10000,Count(130000),Count(shared->loader.expectedTotal)},{0x10004,Count(130000),Count(shared->loader.expectedTotal)}}};
    prepared=vm_startup::BuildNativePlan(input);
    return prepared;
}
void Ready(const vm_startup::Receipt&) {
    if(shared->scenario==NativeScenario::Rollback) throw std::runtime_error("Owned composed native readiness refusal.");
    shared->readyBeforeCalls=shared->loader.calls==0 && shared->serverReads==0 && shared->clientReads==0;
    shared->ready=1;
    relay->Commit();
}
bool Restored(HANDLE process) {
    for(const auto& edit:prepared) {
        auto original=edit.original;
        if(shared->scenario==NativeScenario::EntryMismatch && edit.address==shared->imageBase+0x12d52f0) original[0]=0x49;
        if(vm_startup::ReadStopped(process,edit.address,original.size())!=original) return false;
        MEMORY_BASIC_INFORMATION memory{};
        if(VirtualQueryEx(process,reinterpret_cast<void*>(edit.address),&memory,sizeof(memory))!=sizeof(memory)) return false;
        const bool code=edit.address==shared->relay
            || (edit.address>=shared->imageBase+0x12d0000 && edit.address<shared->imageBase+0x20f0000);
        if(memory.Protect!=static_cast<DWORD>(code ? PAGE_EXECUTE_READ : PAGE_READWRITE)) return false;
    }
    return true;
}
struct Child {
    PROCESS_INFORMATION info{};
    bool done=false;
    ~Child() {
        if(info.hProcess) {
            if(!done) { TerminateProcess(info.hProcess,97); DebugActiveProcessStop(info.dwProcessId); WaitForSingleObject(info.hProcess,5000); }
            CloseHandle(info.hProcess); CloseHandle(info.hThread);
        }
    }
};
struct Locks { std::vector<HANDLE> values; ~Locks() { for(auto handle:values) CloseHandle(handle); } };
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==4,"Use fixed native scenario, capacity and new private receipt.");
        const std::wstring requested=argv[1];
        const std::array names{L"roundtrip",L"decode-error",L"state-error",L"later-error",L"rollback",L"entry-mismatch",L"far-relay",L"boot-invalid",L"boot-not-ready"};
        std::size_t scenario=0; for(;scenario<names.size() && requested!=names[scenario];++scenario) {}
        Require(scenario<names.size(),"Unknown owned native scenario.");
        const auto total=static_cast<DWORD>(std::stoul(argv[2]));
        Require(total==500001 || total==1000001,"Use a declared owned expanded capacity.");
        const auto output=PrivateOutput(argv[3]);
        wchar_t path[32768]{}; Require(GetModuleFileNameW(nullptr,path,32768)!=0,"Cannot locate fixed native fixture directory.");
        const auto directory=std::filesystem::path(path).parent_path(),target=directory/L"VmNativeTarget.exe",helper=directory/L"VmStartupHelper.dll";
        Locks locks; locks.values.reserve(3);
        VerifyFile(target,kNativeTargetHash,locks.values); VerifyFile(helper,kHelperHash,locks.values);
        VerifyFile(directory/L"VmStartupConsumer.dll",kConsumerHash,locks.values);
        const auto mapped=LoadLibraryExW(target.c_str(),nullptr,DONT_RESOLVE_DLL_REFERENCES);
        Require(mapped!=nullptr,"Cannot inspect fixed native target PE.");
        const auto gate=Export(mapped,"NativeGate"),pool=Export(mapped,"NativePoolPointer"),hash=Export(mapped,"NativeHashPointer");
        vm_startup::Profile profile{ImageSize(mapped),gate,pool,hash,{},{}};
        const std::vector<unsigned char> original{0xb8,0xd0,0xfb,0x01,0,0xc3};
        for(auto offset:{0u,64u}) { profile.checks.push_back({gate+offset,original}); profile.edits.push_back({gate+offset+1,Count(130000),Count(total)}); }
        FreeLibrary(mapped);
        const auto helperMapped=LoadLibraryExW(helper.c_str(),nullptr,DONT_RESOLVE_DLL_REFERENCES);
        Require(helperMapped!=nullptr,"Cannot inspect fixed native helper PE.");
        helperImage={0,ImageSize(helperMapped)};
#ifdef VM_STARTUP_PRODUCTION_HELPER
        bootOffset=Export(helperMapped,"Bo3EnhancedBoot");
#else
        Require(scenario<7,"Boot refusal checks require the production helper.");
#endif
        offsets={Export(helperMapped,"Bo3VmStateBindings"),Export(helperMapped,"Bo3VmErrorBindings"),Export(helperMapped,"ReadNativeState"),Export(helperMapped,"WriteNativeState"),
            Export(helperMapped,"InsertNativeStateKey"),Export(helperMapped,"ReadStateOrDrop"),Export(helperMapped,"WriteStateOrDrop"),Export(helperMapped,"VmErrorPrelude"),
            Export(helperMapped,"NativeOriginalReader"),Export(helperMapped,"NativeOriginalWriter"),Export(helperMapped,"NativeOriginalInsert"),Export(helperMapped,"NativeOriginalError")};
        FreeLibrary(helperMapped);
        SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,TRUE};
        Handle mapping(CreateFileMappingW(INVALID_HANDLE_VALUE,&attributes,PAGE_READWRITE,0,sizeof(NativeShared),nullptr));
        Require(mapping.value!=nullptr,"Cannot create owned native trace mapping.");
        shared=static_cast<NativeShared*>(MapViewOfFile(mapping.value,FILE_MAP_WRITE,0,0,sizeof(NativeShared)));
        Require(shared!=nullptr,"Cannot map owned native trace."); ZeroMemory(shared,sizeof(*shared));
        shared->loader.scenario=Scenario::Entry; shared->loader.expectedTotal=total; shared->scenario=static_cast<NativeScenario>(scenario);
        if(shared->scenario==NativeScenario::BootInvalid) shared->loader.scenario=Scenario::HelperDirty;
        if(shared->scenario==NativeScenario::BootNotReady) shared->loader.scenario=Scenario::HelperNoReady;
        const auto mappingText=std::to_wstring(reinterpret_cast<std::uintptr_t>(mapping.value));
        Require(SetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING",mappingText.c_str())!=FALSE,"Cannot publish fixed native mapping.");
        SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
        char helperPath[32768]{}; BOOL substituted=FALSE;
        Require(WideCharToMultiByte(CP_ACP,WC_NO_BEST_FIT_CHARS,helper.c_str(),-1,helperPath,32768,nullptr,&substituted)>0 && !substituted,"Fixed helper path cannot use Detours ANSI encoding.");
        LPCSTR helpers[]{helperPath}; STARTUPINFOW startup{}; startup.cb=sizeof(startup); Child child;
        std::wstring command=L"\""+target.wstring()+L"\"";
        Require(DetourCreateProcessWithDllsW(target.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW|DEBUG_ONLY_THIS_PROCESS,
            nullptr,directory.c_str(),&startup,&child.info,1,helpers,CreateProcessW)!=FALSE,"Cannot create fixed native child.");
        vm_startup::Receipt receipt; bool refused=false;
        try { vm_startup::Activate(child.info,profile,receipt,Ready,Prepare); }
        catch(const std::exception&) {
            refused=true;
            shared->rollbackOriginal=Restored(child.info.hProcess)
                && vm_startup::ReadStopped(child.info.hProcess,receipt.imageBase+gate+1,4)==Count(130000)
                && vm_startup::ReadStopped(child.info.hProcess,receipt.imageBase+gate+65,4)==Count(130000);
            relay.reset(); MEMORY_BASIC_INFORMATION memory{};
            shared->relayFreed=shared->relay && VirtualQueryEx(child.info.hProcess,reinterpret_cast<void*>(shared->relay),&memory,sizeof(memory))==sizeof(memory) && memory.State==MEM_FREE;
            TerminateProcess(child.info.hProcess,97); DebugActiveProcessStop(child.info.dwProcessId);
        }
        Require(WaitForSingleObject(child.info.hProcess,30000)==WAIT_OBJECT_0,"Owned native child did not stop."); child.done=true;
        DWORD exitCode=0; GetExitCodeProcess(child.info.hProcess,&exitCode);
        const bool bootRefusal=shared->scenario==NativeScenario::BootInvalid || shared->scenario==NativeScenario::BootNotReady;
        const bool expectedRefusal=shared->scenario==NativeScenario::Rollback || shared->scenario==NativeScenario::EntryMismatch || shared->scenario==NativeScenario::FarRelay || bootRefusal;
        const bool passed=expectedRefusal ? refused && shared->rollbackOriginal && (bootRefusal ? shared->relay==0 : shared->relayFreed!=0) && shared->loader.calls==0 && shared->ready==0
                && (shared->scenario==NativeScenario::Rollback ? receipt.rollbackCompleted && receipt.editsWritten==11 : receipt.editsWritten==0)
            : !refused && exitCode==0 && receipt.activated && shared->passed==1 && shared->clientReads==1 && shared->clientWrites==1;
        std::ofstream report(output);
        std::string name; for(const auto character:requested) name.push_back(static_cast<char>(character));
        report<<"{\"scenario\":\""<<name<<"\",\"total\":"<<total<<",\"passed\":"<<(passed ? "true" : "false")
            <<",\"exitCode\":"<<exitCode<<",\"editsWritten\":"<<receipt.editsWritten<<",\"activated\":"<<(receipt.activated ? "true" : "false")
            <<",\"rollbackCompleted\":"<<(receipt.rollbackCompleted ? "true" : "false")<<",\"restored\":"<<shared->rollbackOriginal<<",\"relayFreed\":"<<shared->relayFreed
            <<",\"ready\":"<<shared->ready<<",\"readyBeforeCalls\":"<<shared->readyBeforeCalls<<",\"serverReads\":"<<shared->serverReads
            <<",\"serverWrites\":"<<shared->serverWrites<<",\"clientReads\":"<<shared->clientReads<<",\"clientWrites\":"<<shared->clientWrites
            <<",\"inserts\":"<<shared->inserts<<",\"errorCalls\":"<<shared->errorCalls<<",\"laterCalls\":"<<shared->laterCalls
            <<",\"nonLocalExits\":"<<shared->nonLocalExits<<",\"stateErrorCode\":"<<shared->stateErrorCode<<",\"insertUnwind\":"<<shared->insertUnwind
            <<",\"errorUnwind\":"<<shared->errorUnwind<<",\"leafUnwinds\":"<<shared->leafUnwinds
            <<",\"clientRoots\":18,\"stockClientRoots\":8,\"modePolicy\":\"ZombiesOnly\",\"encodedBytes\":"<<shared->encodedBytes<<",\"encodedHash\":"<<shared->encodedHash<<"}";
        Require(report.good(),"Cannot write native composition receipt."); return passed ? 0 : 1;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 2; }
}
