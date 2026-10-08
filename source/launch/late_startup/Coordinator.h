#pragma once
#include "MappedGate.h"
#include "../../patches/vm_startup/NearRelay.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include <functional>
#include <memory>
#include <ostream>

namespace bo3::late_startup {
struct PreparedPlan {
    std::unique_ptr<vm_startup::NearRelay> relay;
    std::vector<vm_startup::AddressEdit> edits;
    std::uintptr_t helperBase{};
};
struct EventRow {DWORD code,thread;std::uintptr_t address;};
struct Receipt {
    vm_startup::Receipt patch{};
    std::uint64_t created{},generation{};
    DWORD processId{},primaryThreadId{},writeEventThread{},threadsObserved{},attachThread{};
    std::uintptr_t gateBase{},helperBase{},attachBreakpoint{},attachThreadEntry{};
    bool attached=false,committed=false,detached=false,debuggerAbsent=false,released=false,terminated=false;
    std::vector<EventRow> events;
};
using PreparePlan=std::function<PreparedPlan(HANDLE,std::uintptr_t,vm_startup::Receipt&)>;
// The production caller binds the fixed recipe. Owned fixtures bind an inert address image.
void Coordinate(OwnedChild&,MappedGate&,const PreparePlan&,Receipt&);
void WriteReceipt(std::ostream&,const Receipt&);
#ifdef BO3_LATE_OWNED_TEST
enum class Failure {None,AfterApply,Continue,Detach};
void SetOwnedFailure(Failure);
void SetOwnedStoppedObserver(std::function<void(HANDLE,bool)>);
void SetOwnedEventObserver(std::function<void(HANDLE,const DEBUG_EVENT&)>);
#endif
}
