#include "ErrorHooks.h"
#include "../../launch/preentry/Identity.h"
#include <array>
#include <fstream>
#include <iostream>
#include <string_view>

namespace {
constexpr DWORD errorExit=0xe042564d;
constexpr std::array names{"read-success","write-success","read-errors","write-errors","arguments",
    "decode-error","later-read","later-arguments","suppress","unwind"};

// The owned native exception deliberately bypasses the adapter's ordinary return.
void Invoke() {
    __try {
        switch(errorTrace.scenario) {
        case ErrorScenario::WriteSuccess: case ErrorScenario::WriteErrors:
            bo3::vm::WriteStateOrDrop(0,&errorTrace); break;
        case ErrorScenario::Arguments: case ErrorScenario::LaterArguments:
            CallOwnedError(); break;
        case ErrorScenario::Suppress:
            bo3::vm::Bo3VmErrorBindings.entry("owned",1,2,"VCRedist owned suppression"); break;
        default: bo3::vm::ReadStateOrDrop(0,&errorTrace); break;
        }
    } __except(GetExceptionCode()==errorExit ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
        ++errorTrace.exits;
        ErrorStage(4);
    }
}

void CheckUnwind() {
    DWORD64 imageBase=0;
    const auto pc=reinterpret_cast<DWORD64>(VmErrorPreludeBody);
    auto* function=RtlLookupFunctionEntry(pc,&imageBase,nullptr);
    Require(function!=nullptr,"The prelude has no Windows unwind entry.");
    alignas(16) std::array<DWORD64,32> stack{};
    const auto bodyRsp=reinterpret_cast<DWORD64>(stack.data());
    constexpr DWORD64 returnAddress=0x1234567812345678ull;
    stack[9]=returnAddress;
    CONTEXT context{};
    context.Rip=pc; context.Rsp=bodyRsp;
    void* handler=nullptr;
    DWORD64 establisher=0;
    RtlVirtualUnwind(UNW_FLAG_NHANDLER,imageBase,pc,function,&context,&handler,&establisher,nullptr);
    errorTrace.unwindPassed=context.Rip==returnAddress && context.Rsp==bodyRsp+0x50 && establisher==bodyRsp;
}

bool Validate() {
    const auto scenario=errorTrace.scenario;
    const bool writes=scenario==ErrorScenario::WriteSuccess || scenario==ErrorScenario::WriteErrors;
    const bool reads=scenario==ErrorScenario::ReadSuccess || scenario==ErrorScenario::ReadErrors
        || scenario==ErrorScenario::DecodeError || scenario==ErrorScenario::LaterRead;
    const bool allErrors=scenario==ErrorScenario::ReadErrors || scenario==ErrorScenario::WriteErrors;
    const DWORD expected=allErrors ? static_cast<DWORD>(bo3::vm::StateError::UnsupportedMode) : 1;
    if(errorTrace.readCalls!=(reads ? expected : 0) || errorTrace.writeCalls!=(writes ? expected : 0)
        || errorTrace.errors!=0) return false;
    if(scenario==ErrorScenario::Unwind) return errorTrace.unwindPassed;
    if(scenario==ErrorScenario::ReadSuccess || scenario==ErrorScenario::WriteSuccess)
        return errorTrace.readCalls+errorTrace.writeCalls==1 && errorTrace.clearCalls==0
            && errorTrace.originalCalls==0 && errorTrace.exits==0 && !ownedImportContext.active;
    if(scenario==ErrorScenario::Suppress)
        return errorTrace.laterCalls==1 && errorTrace.originalCalls==0 && errorTrace.clearCalls==0
            && errorTrace.exits==0 && ownedImportContext.active;
    const bool later=scenario==ErrorScenario::LaterRead || scenario==ErrorScenario::LaterArguments;
    const DWORD sequence[]{2,1,3,4};
    bool order=errorTrace.stageCount==expected*(later ? 4u : 3u);
    for(DWORD index=0;index<errorTrace.stageCount;++index)
        order &= errorTrace.stages[index]==sequence[(index%(later ? 4u : 3u))+(later ? 0u : 1u)];
    return errorTrace.clearCalls==expected && errorTrace.originalCalls==expected
        && errorTrace.homeStores==expected && errorTrace.exits==expected && errorTrace.lastCode==2
        && errorTrace.laterCalls==(later ? expected : 0) && order
        && errorTrace.argumentsPreserved && errorTrace.originalSawInactive && !ownedImportContext.active
        && errorTrace.errors==0;
}
}

int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use a fixed owned scenario and a new private receipt path.");
        const std::wstring_view requested=argv[1];
        std::size_t selected=0;
        for(;selected<names.size();++selected) {
            const std::string_view candidate=names[selected];
            if(requested==std::wstring(candidate.begin(),candidate.end())) break;
        }
        Require(selected<names.size(),"Unknown owned error scenario.");
        const auto output=PrivateOutput(argv[2]);
        errorTrace.scenario=static_cast<ErrorScenario>(selected);
        ErrorHooks hooks;
        BindErrorFixture(hooks.Entry(),hooks.Original(),hooks.LaterOriginal());
        if(errorTrace.scenario==ErrorScenario::LaterRead || errorTrace.scenario==ErrorScenario::LaterArguments
            || errorTrace.scenario==ErrorScenario::Suppress) hooks.InstallLater();
        if(errorTrace.scenario==ErrorScenario::Unwind) CheckUnwind();
        else if(errorTrace.scenario==ErrorScenario::ReadErrors || errorTrace.scenario==ErrorScenario::WriteErrors) {
            for(int value=1;value<=static_cast<int>(bo3::vm::StateError::UnsupportedMode);++value) {
                errorTrace.stateError=static_cast<bo3::vm::StateError>(value);
                ownedImportContext.active=true;
                Invoke();
            }
        } else {
            const bool success=selected<=1;
            errorTrace.stateError=success ? bo3::vm::StateError::None : bo3::vm::StateError::CapacityMismatch;
            ownedImportContext.active=!success;
            Invoke();
        }
        const bool passed=Validate();
        std::ofstream receipt(output);
        receipt<<"{\"scenario\":\""<<names[selected]<<"\",\"passed\":"<<(passed ? "true" : "false")
            <<",\"bindingBytes\":"<<sizeof(bo3::vm::ErrorBindings)<<",\"readCalls\":"<<errorTrace.readCalls
            <<",\"writeCalls\":"<<errorTrace.writeCalls<<",\"clearCalls\":"<<errorTrace.clearCalls
            <<",\"originalCalls\":"<<errorTrace.originalCalls<<",\"laterCalls\":"<<errorTrace.laterCalls
            <<",\"homeStores\":"<<errorTrace.homeStores<<",\"exits\":"<<errorTrace.exits
            <<",\"lastCode\":"<<errorTrace.lastCode<<",\"lastStateError\":"<<errorTrace.lastStateError
            <<",\"errors\":"<<errorTrace.errors<<",\"argumentsPreserved\":"<<(errorTrace.argumentsPreserved ? "true" : "false")
            <<",\"originalSawInactive\":"<<(errorTrace.originalSawInactive ? "true" : "false")
            <<",\"unwindPassed\":"<<(errorTrace.unwindPassed ? "true" : "false")<<",\"stages\":[";
        for(DWORD index=0;index<errorTrace.stageCount;++index) receipt<<(index ? "," : "")<<errorTrace.stages[index];
        receipt<<"]}";
        Require(receipt.good(),"Cannot write the owned receipt.");
        return passed ? 0 : 1;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 2; }
}
