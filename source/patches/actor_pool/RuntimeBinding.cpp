#include "RuntimeBinding.h"
#include "ActorArena.h"

namespace bo3::actors {
extern "C" {__declspec(dllexport) constinit RuntimeBindings Bo3ActorRuntimeBindings{};}
namespace {constinit volatile LONG registered{};}
bool ActivateActorRuntime() {
    const auto& binding=Bo3ActorRuntimeBindings;
    if(!binding.image || !binding.arena || !binding.functions || !binding.functionCount ||
            !binding.phases || !binding.phaseCount)return false;
    if(binding.arena<binding.image+494186496 || binding.arena-binding.image>0x7FFFFFFFull-ActorArena::Bytes)return false;
    const auto begin=binding.arena-binding.image,end=begin+0x400000;
    for(std::uint32_t index=0;index<binding.functionCount;++index) {
        const auto& row=binding.functions[index];
        if(row.BeginAddress<begin || row.EndAddress<=row.BeginAddress || row.EndAddress>begin+0x200000 ||
                row.UnwindData<begin+0x200000 || row.UnwindData>end-4 ||
                (index && binding.functions[index-1].EndAddress>row.BeginAddress))return false;
    }
    if(InterlockedCompareExchange(&registered,1,0)!=0)return false;
    if(!RtlAddFunctionTable(binding.functions,binding.functionCount,binding.image))return false;
    for(std::uint32_t index=0;index<binding.functionCount;++index) {
        DWORD64 image{};
        if(RtlLookupFunctionEntry(binding.image+binding.functions[index].BeginAddress,&image,nullptr)!=binding.functions+index ||
                image!=binding.image) {
            RtlDeleteFunctionTable(binding.functions);return false;
        }
    }
    return true;
}
EXCEPTION_DISPOSITION ActorPhaseHandler(PEXCEPTION_RECORD exception,PVOID frame,PCONTEXT context,PDISPATCHER_CONTEXT dispatcher) {
    const auto index=*static_cast<const std::uint32_t*>(dispatcher->HandlerData);
    return actor_pool::DispatchNativeHandler(exception,frame,context,dispatcher,Bo3ActorRuntimeBindings.phases[index]);
}
}
