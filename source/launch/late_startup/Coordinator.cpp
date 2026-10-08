#include "Coordinator.h"
#include "../preentry/Identity.h"
#include <Psapi.h>
#include <array>
#include <algorithm>
#include <cstring>
#include <exception>

namespace bo3::late_startup {
namespace {
struct DebugHandles {
    HANDLE process{};
    std::vector<std::pair<DWORD,HANDLE>> threads;
    ~DebugHandles(){if(process)CloseHandle(process);for(const auto& [id,handle]:threads){(void)id;CloseHandle(handle);}}
    void ExitedThread(DWORD id){threads.erase(std::remove_if(threads.begin(),threads.end(),[&](const auto& item){return item.first==id;}),threads.end());}
    // ContinueDebugEvent closes these event handles after the corresponding exit event.
    void ExitedProcess(){process=nullptr;threads.clear();}
};
#ifdef BO3_LATE_OWNED_TEST
Failure ownedFailure=Failure::None;
std::function<void(HANDLE,bool)> ownedObserver;
std::function<void(HANDLE,const DEBUG_EVENT&)> ownedEventObserver;
#endif
struct AttachEntries {std::uintptr_t breakpoint,threadEntry;};
AttachEntries SystemEntries(HANDLE process) {
    const auto local=GetModuleHandleW(L"ntdll.dll");
    const auto entry=GetProcAddress(local,"DbgBreakPoint");
    const auto threadEntry=GetProcAddress(local,"DbgUiRemoteBreakin");
    Require(entry && threadEntry,"Cannot find the system attachment exports.");
    std::array<wchar_t,32768> file{};
    Require(GetModuleFileNameW(local,file.data(),static_cast<DWORD>(file.size()))!=0,"Cannot identify system ntdll.");
    const auto localBase=reinterpret_cast<std::uintptr_t>(local);
    const auto dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(local);
    const auto header=reinterpret_cast<const IMAGE_NT_HEADERS64*>(localBase+dos->e_lfanew);
    const auto offset=reinterpret_cast<std::uintptr_t>(entry)-localBase;
    const auto threadOffset=reinterpret_cast<std::uintptr_t>(threadEntry)-localBase;
    Require(offset<header->OptionalHeader.SizeOfImage && threadOffset<header->OptionalHeader.SizeOfImage,
        "System attachment exports exceed ntdll.");
    std::array<HMODULE,2048> modules{};DWORD bytes{};
    Require(K32EnumProcessModulesEx(process,modules.data(),sizeof(modules),&bytes,LIST_MODULES_64BIT)
        && bytes<=sizeof(modules) && bytes%sizeof(HMODULE)==0,"Cannot inspect system modules before attach.");
    std::uintptr_t remote=0;
    for(std::size_t i=0;i<bytes/sizeof(HMODULE);++i) {
        std::array<wchar_t,32768> name{};
        const auto length=K32GetModuleFileNameExW(process,modules[i],name.data(),static_cast<DWORD>(name.size()));
        Require(length && length<name.size(),"Cannot identify a child system module.");
        if(std::filesystem::equivalent(file.data(),name.data())) {Require(!remote,"Ambiguous system ntdll mapping.");remote=reinterpret_cast<std::uintptr_t>(modules[i]);}
    }
    Require(remote!=0,"The child system ntdll mapping is missing.");
    const auto remoteHeader=vm_startup::ReadStopped(process,remote+dos->e_lfanew,sizeof(IMAGE_NT_HEADERS64));
    IMAGE_NT_HEADERS64 actual{};std::memcpy(&actual,remoteHeader.data(),sizeof(actual));
    Require(actual.Signature==header->Signature && actual.FileHeader.TimeDateStamp==header->FileHeader.TimeDateStamp
        && actual.OptionalHeader.SizeOfImage==header->OptionalHeader.SizeOfImage
        && vm_startup::ReadStopped(process,remote+offset,1)==std::vector<unsigned char>{0xcc},
        "The system attach breakpoint identity differs.");
    return {remote+offset,remote+threadOffset};
}
void InspectRegisters(HANDLE thread) {
    CONTEXT context{};context.ContextFlags=CONTEXT_DEBUG_REGISTERS;
    Require(GetThreadContext(thread,&context)!=FALSE,"Cannot inspect stopped thread debug registers.");
    Require(!context.Dr0 && !context.Dr1 && !context.Dr2 && !context.Dr3 && !(context.Dr7&0xff),
        "A stopped thread already has hardware breakpoints.");
}
}
#ifdef BO3_LATE_OWNED_TEST
void SetOwnedFailure(Failure failure){ownedFailure=failure;}
void SetOwnedStoppedObserver(std::function<void(HANDLE,bool)> observer){ownedObserver=std::move(observer);}
void SetOwnedEventObserver(std::function<void(HANDLE,const DEBUG_EVENT&)> observer){ownedEventObserver=std::move(observer);}
#endif
void Coordinate(OwnedChild& child,MappedGate& gate,const PreparePlan& prepare,Receipt& receipt) {
    const auto deadline=GetTickCount64()+child.payload.deadlineMs;
    receipt.processId=child.process.dwProcessId;receipt.primaryThreadId=child.process.dwThreadId;
    receipt.created=child.payload.processCreatedFileTime;
    bool pending=false,attached=false;DEBUG_EVENT event{};
    DebugHandles handles;
    try {
        child.Resume();child.WaitReady(deadline);gate.Admit(child.process.hProcess);
        const auto state=gate.Read(child.process.hProcess);receipt.generation=state.generation;receipt.gateBase=gate.Base();
        gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
        BOOL already=FALSE;
        Require(CheckRemoteDebuggerPresent(child.process.hProcess,&already)!=FALSE && !already,"The owned child already has a debugger.");
        const auto entries=SystemEntries(child.process.hProcess);
        receipt.attachBreakpoint=entries.breakpoint;receipt.attachThreadEntry=entries.threadEntry;
        Require(DebugActiveProcess(child.process.dwProcessId)!=FALSE,"Cannot attach to the waiting owned child.");
        attached=true;receipt.attached=true;
        Require(DebugSetProcessKillOnExit(TRUE)!=FALSE,"Cannot retain debugger failure ownership.");
        bool sawProcess=false;
        for(;;) {
            Require(GetTickCount64()<deadline,"The late allocation gate exceeded its fixed deadline.");
            Require(!child.Exited(),"The owned child exited before the late transaction.");
            if(!WaitForDebugEvent(&event,50)) {Require(GetLastError()==ERROR_SEM_TIMEOUT,"Cannot wait for late debug events.");continue;}
            pending=true;
            Require(event.dwProcessId==child.process.dwProcessId,"A debug event belongs to another process.");
            std::uintptr_t address=0;
            if(event.dwDebugEventCode==EXCEPTION_DEBUG_EVENT)
                address=reinterpret_cast<std::uintptr_t>(event.u.Exception.ExceptionRecord.ExceptionAddress);
            if(event.dwDebugEventCode==CREATE_THREAD_DEBUG_EVENT)
                address=reinterpret_cast<std::uintptr_t>(event.u.CreateThread.lpStartAddress);
            receipt.events.push_back({event.dwDebugEventCode,event.dwThreadId,address});
            DWORD status=DBG_CONTINUE;
            if(event.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT) {
                if(event.u.CreateProcessInfo.hFile)CloseHandle(event.u.CreateProcessInfo.hFile);
                Require(!sawProcess,"Duplicate late attach process event.");sawProcess=true;
                handles.process=event.u.CreateProcessInfo.hProcess;
                handles.threads.push_back({event.dwThreadId,event.u.CreateProcessInfo.hThread});
                receipt.patch.imageBase=reinterpret_cast<std::uintptr_t>(event.u.CreateProcessInfo.lpBaseOfImage);
                InspectRegisters(event.u.CreateProcessInfo.hThread);++receipt.threadsObserved;
            } else if(event.dwDebugEventCode==CREATE_THREAD_DEBUG_EVENT) {
                handles.threads.push_back({event.dwThreadId,event.u.CreateThread.hThread});
                if(address==receipt.attachThreadEntry) {
                    Require(sawProcess && !receipt.attachThread,"Ambiguous late attach break-in thread.");
                    receipt.attachThread=event.dwThreadId;
                }
                InspectRegisters(event.u.CreateThread.hThread);++receipt.threadsObserved;
            } else if(event.dwDebugEventCode==EXIT_THREAD_DEBUG_EVENT) {
                handles.ExitedThread(event.dwThreadId);
            } else if(event.dwDebugEventCode==LOAD_DLL_DEBUG_EVENT) {
                if(event.u.LoadDll.hFile)CloseHandle(event.u.LoadDll.hFile);
            } else if(event.dwDebugEventCode==EXIT_PROCESS_DEBUG_EVENT) {
                receipt.patch.exited=true;receipt.patch.exitCode=event.u.ExitProcess.dwExitCode;
                Require(ContinueDebugEvent(event.dwProcessId,event.dwThreadId,DBG_CONTINUE)!=FALSE,"Cannot finish owned exit event.");
                handles.ExitedProcess();
                pending=false;attached=false;throw std::runtime_error("The owned child exited during late attach.");
            } else if(event.dwDebugEventCode==EXCEPTION_DEBUG_EVENT) {
                const auto& exception=event.u.Exception;
                const bool qualified=sawProcess && exception.dwFirstChance==1
                    && exception.ExceptionRecord.ExceptionCode==EXCEPTION_BREAKPOINT
                    && address==receipt.attachBreakpoint && receipt.attachThread && event.dwThreadId==receipt.attachThread;
                if(!qualified)status=DBG_EXCEPTION_NOT_HANDLED;
                else {
                    gate.Admit(child.process.hProcess);gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
                    receipt.writeEventThread=event.dwThreadId;receipt.patch.stoppedThread=event.dwThreadId;
                    auto plan=prepare(child.process.hProcess,receipt.patch.imageBase,receipt.patch);
                    Require(plan.edits.size()==42 && plan.relay!=nullptr,"The complete fixed native transaction is required.");
                    receipt.helperBase=plan.helperBase;
                    gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
                    try {
                        vm_startup::PausedPatch patch(child.process.hProcess,std::move(plan.edits),receipt.patch);patch.Apply();
#ifdef BO3_LATE_OWNED_TEST
                        if(ownedObserver)ownedObserver(child.process.hProcess,false);
                        Require(ownedFailure!=Failure::AfterApply,"Owned stopped-rollback injection.");
#endif
                        gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
                        Require(GetTickCount64()<deadline,"The stopped transaction exceeded its gate deadline.");
                        patch.Commit();plan.relay->Commit();receipt.committed=true;
                    } catch(...) {
#ifdef BO3_LATE_OWNED_TEST
                        // Capture restored relay bytes before the uncommitted relay allocation is freed.
                        if(receipt.patch.rollbackCompleted && ownedObserver)ownedObserver(child.process.hProcess,true);
#endif
                        throw;
                    }
                    DWORD continueThread=event.dwThreadId;
#ifdef BO3_LATE_OWNED_TEST
                    if(ownedFailure==Failure::Continue)continueThread=0;
#endif
                    Require(ContinueDebugEvent(event.dwProcessId,continueThread,DBG_CONTINUE)!=FALSE,"Cannot continue the committed attach breakpoint.");
                    pending=false;
#ifdef BO3_LATE_OWNED_TEST
                    Require(ownedFailure!=Failure::Detach,"Owned detach failure injection.");
#endif
                    Require(DebugActiveProcessStop(child.process.dwProcessId)!=FALSE,"Cannot detach the committed owned child.");
                    attached=false;receipt.detached=true;
                    BOOL debugger=TRUE;
                    Require(CheckRemoteDebuggerPresent(child.process.hProcess,&debugger)!=FALSE && !debugger,
                        "The child still has a debugger after detach.");receipt.debuggerAbsent=true;
                    Require(!child.Exited(),"The owned child exited before gate release.");
                    gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
                    Require(GetTickCount64()<deadline,"Detach exceeded the cooperative gate deadline.");
                    child.Release();receipt.released=true;return;
                }
            }
#ifdef BO3_LATE_OWNED_TEST
            if(ownedEventObserver)ownedEventObserver(child.process.hProcess,event);
#endif
            Require(ContinueDebugEvent(event.dwProcessId,event.dwThreadId,status)!=FALSE,"Cannot continue late attach enumeration.");pending=false;
        }
    } catch(...) {
        const auto original=std::current_exception();
        // PausedPatch and uncommitted relays have already unwound while the event remained pending.
        // Cleanup must still drain a pending event if the child has already started exit.
        if(WaitForSingleObject(child.process.hProcess,0)!=WAIT_OBJECT_0)TerminateProcess(child.process.hProcess,97);
        receipt.terminated=true;
        if(pending)ContinueDebugEvent(event.dwProcessId,event.dwThreadId,DBG_CONTINUE);
        if(attached)DebugActiveProcessStop(child.process.dwProcessId);
        WaitForSingleObject(child.process.hProcess,5000);std::rethrow_exception(original);
    }
}
void WriteReceipt(std::ostream& stream,const Receipt& receipt) {
    const auto yes=[](bool value){return value?"true":"false";};
    stream<<"{\"schema\":1,\"candidate\":\"0.1.0-test.3\",\"startupMethod\":\"late-crt-gate\""
        <<",\"serverTotal\":500001,\"clientTotal\":65000,\"clientRoots\":18,\"stockClientRoots\":8,\"migrationBufferBytes\":33554432"
        <<",\"processId\":"<<receipt.processId<<",\"processCreatedFileTime\":"<<receipt.created
        <<",\"primaryThreadId\":"<<receipt.primaryThreadId<<",\"generation\":"<<receipt.generation
        <<",\"imageBase\":"<<receipt.patch.imageBase<<",\"helperBase\":"<<receipt.helperBase<<",\"gateBase\":"<<receipt.gateBase
        <<",\"attachBreakpoint\":"<<receipt.attachBreakpoint<<",\"attachThreadEntry\":"<<receipt.attachThreadEntry
        <<",\"attachThread\":"<<receipt.attachThread<<",\"writeEventThread\":"<<receipt.writeEventThread<<",\"threadsObserved\":"<<receipt.threadsObserved
        <<",\"editsWritten\":"<<receipt.patch.editsWritten<<",\"rollbackCompleted\":"<<yes(receipt.patch.rollbackCompleted)
        <<",\"attached\":"<<yes(receipt.attached)<<",\"committed\":"<<yes(receipt.committed)
        <<",\"detached\":"<<yes(receipt.detached)<<",\"debuggerAbsent\":"<<yes(receipt.debuggerAbsent)
        <<",\"released\":"<<yes(receipt.released)<<",\"terminated\":"<<yes(receipt.terminated)
        <<",\"liveAllocationValidated\":false,\"debugRegisterWrites\":0,\"events\":[";
    bool first=true;for(const auto& event:receipt.events) {if(!first)stream<<',';first=false;
        stream<<"{\"code\":"<<event.code<<",\"threadId\":"<<event.thread<<",\"address\":"<<event.address<<'}';}
    stream<<"]}";Require(stream.good(),"Cannot write the late gate receipt.");
}
}
