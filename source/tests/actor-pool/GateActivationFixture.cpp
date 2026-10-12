// Exercise the production gate return and actor registration in owned Windows memory.
#include "../../launch/startup_gate/Gate.h"
#include "../../launch/startup_gate/Admission.h"
#include "../../launch/startup_probe/Observation.h"
#include "../../patches/actor_pool/RuntimeBinding.h"
#include "ProbeProfile.h"
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>

namespace bo3::startup_gate {
Payload configuration{};
BOOLEAN NTAPI OwnedLoaderQuery(){return FALSE;}
LoaderCallout loaderCallout=OwnedLoaderQuery;
bool HasNativeEntry(State& state){state.entryAnchorStart=1;state.entryAnchorEnd=2;state.entryFrameCount=1;state.entryAnchorPresent=1;return true;}
}
namespace bo3::startup_probe {
extern "C" {Observation Bo3StartupProbeObservation{};Counters Bo3StartupProbeCounters{};}
void Observe(std::uintptr_t,std::uintptr_t){Bo3StartupProbeObservation.count=1;}
}
namespace {
void Require(bool value,const char* reason){if(!value)throw std::runtime_error(reason);}
bool callbackOnPrimary{},callbackAfterRelease{};
unsigned int callbacks{};
bool Register() {
    ++callbacks;
    callbackOnPrimary=GetCurrentThreadId()==bo3::startup_gate::configuration.primaryThreadId;
    callbackAfterRelease=bo3::startup_gate::Bo3StartupGateState.phase==static_cast<LONG>(bo3::startup_gate::Phase::Released);
    return bo3::actors::ActivateActorRuntime();
}
}
int main(int argc,char** argv) {
    try {
        Require(argc==3,"Supply the owned gate mode and receipt path.");
        const auto game=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,0x23000000,MEM_RESERVE,PAGE_NOACCESS));
        Require(game!=0,"Cannot reserve the owned game and actor ranges.");
        const auto arena=game+0x20000000;
        Require(VirtualAlloc(reinterpret_cast<void*>(game),0x4000,MEM_COMMIT,PAGE_READWRITE)!=nullptr,"Cannot commit the owned gate caller.");
        Require(VirtualAlloc(reinterpret_cast<void*>(arena),0x400000,MEM_COMMIT,PAGE_READWRITE)!=nullptr,"Cannot commit owned actor metadata.");
        std::memcpy(reinterpret_cast<void*>(game+kCallerRva),kCallerBytes,sizeof(kCallerBytes));
        auto* table=reinterpret_cast<RUNTIME_FUNCTION*>(arena+0x200000);*table={0x20001000,0x20001001,0x20200100};
        *reinterpret_cast<unsigned char*>(game+table->BeginAddress)=0xC3;
        *reinterpret_cast<DWORD*>(game+table->UnwindData)=1;
        bo3::actor_pool::NativeHandlerFrame native{};
        if(std::strcmp(argv[1],"success")==0)bo3::actors::Bo3ActorRuntimeBindings={game,arena,table,1,1,&native};
        else Require(std::strcmp(argv[1],"refuse")==0,"Unknown owned gate mode.");
        DWORD previous{};
        Require(VirtualProtect(reinterpret_cast<void*>(arena),0x200000,PAGE_EXECUTE_READ,&previous)!=FALSE,"Cannot protect owned actor code.");
        Require(VirtualProtect(reinterpret_cast<void*>(arena+0x200000),0x200000,PAGE_READONLY,&previous)!=FALSE,"Cannot protect owned actor metadata.");
        const auto ready=CreateEventW(nullptr,TRUE,FALSE,nullptr),release=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        Require(ready && release,"Cannot create the owned gate events.");
        auto& config=bo3::startup_gate::configuration;
        const auto parentProcess=OpenProcess(SYNCHRONIZE,FALSE,GetCurrentProcessId());Require(parentProcess!=nullptr,"Cannot open the owned gate process handle.");
        config.primaryThreadId=GetCurrentThreadId();config.parentProcess=reinterpret_cast<std::uint64_t>(parentProcess);
        config.readyEvent=reinterpret_cast<std::uint64_t>(ready);config.releaseEvent=reinterpret_cast<std::uint64_t>(release);config.deadlineMs=5000;
        bo3::startup_probe::Bo3StartupProbeCounters.imageBase=game;
        bo3::startup_gate::Bo3StartupGateState.phase=static_cast<LONG>(bo3::startup_gate::Phase::Armed);
        bo3::startup_gate::Bo3StartupGateContinuation=Register;
        alignas(16) std::array<std::uintptr_t,32> stack{};stack[kWrapperCallerDelta/sizeof(std::uintptr_t)]=game+kCrtReturnRva;
        std::thread parent([&]{if(WaitForSingleObject(ready,5000)==WAIT_OBJECT_0)SetEvent(release);});
        bo3::startup_gate::Enter(game+kReturnRva,reinterpret_cast<std::uintptr_t>(stack.data()));
        parent.join();
        Require(callbacks==1 && callbackOnPrimary && callbackAfterRelease,"The actor callback did not precede the native return.");
        Require(bo3::startup_gate::Bo3StartupGateState.phase==static_cast<LONG>(bo3::startup_gate::Phase::Returned),"The admitted gate did not return.");
        DWORD64 base{};Require(RtlLookupFunctionEntry(game+table->BeginAddress,&base,nullptr)==table && base==game,"The gate returned before registration.");
        Require(RtlDeleteFunctionTable(table)!=FALSE,"Cannot delete the owned actor table.");
        CloseHandle(ready);CloseHandle(release);CloseHandle(parentProcess);Require(VirtualFree(reinterpret_cast<void*>(game),0,MEM_RELEASE)!=FALSE,"Cannot release owned actor memory.");
        std::ofstream receipt(argv[2]);Require(receipt.good(),"Cannot write the owned gate receipt.");
        receipt<<"{\"passed\":true,\"callbacks\":1,\"primaryThread\":true,\"afterRelease\":true,\"registeredBeforeReturn\":true,\"gameWrites\":0}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
