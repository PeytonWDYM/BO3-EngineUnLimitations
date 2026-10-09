#include "ControlAdmission.h"
#include "../enhanced/GameProfile.h"
#include "../preentry/Identity.h"
#include "../../patches/vm_startup/StateErrors.h"
#include "GameManifest.h"
#include <algorithm>
#include <array>
#include <iomanip>

namespace bo3::late_startup {
namespace {
void Zero(HANDLE process,std::uintptr_t address,std::size_t bytes) {
    const auto raw=vm_startup::ReadStopped(process,address,bytes);
    Require(std::all_of(raw.begin(),raw.end(),[](unsigned char value){return value==0;}),
        "Stock control requires unallocated storage and unpublished helper bindings.");
}
}
void VerifyControlBindings(HANDLE process,const enhanced::MappedHelper& helper) {
    const std::array<std::pair<std::uint32_t,std::size_t>,7> records{{
        {helper.state.stateBindings,sizeof(bo3::vm::NativeStateBindings)},
        {helper.state.errorBindings,sizeof(bo3::vm::ErrorBindings)},
        {helper.migration.bindings,sizeof(bo3::migration::Bindings)},
        {helper.migration.versionBranches,sizeof(bo3::migration::VersionBranches)},
        {helper.migration.loadBindings,sizeof(bo3::migration::LoadBindings)},
        {helper.migration.reentries,sizeof(bo3::migration::Reentries)},
        {helper.migration.flushBindings,sizeof(bo3::migration::FlushBindings)}}};
    for(const auto& [rva,bytes]:records)Zero(process,helper.image.base+rva,bytes);
}
void CaptureControlBeforeAttach(HANDLE process,std::uintptr_t image,ControlReceipt& receipt) {
    receipt.preAttachCallBytes=vm_startup::ReadStopped(process,image+0x22b1559u,5);
    receipt.preAttachTargetBytes=vm_startup::ReadStopped(process,image+0x227a3a0u,64);
}
void AdmitStockControl(HANDLE process,std::uintptr_t image,enhanced::MappedHelper& helper,
    const std::filesystem::path& file,ControlReceipt& receipt) {
    const auto& manifest=enhanced::ExactGameManifest;
    Require(manifest.guards.size()==82 && manifest.counts.size()==19,"The fixed complete inventory is required.");
    enhanced::VerifyGameCode(process,image,manifest);
    for(const auto& count:manifest.counts)
        Require(vm_startup::ReadStopped(process,image+count.rva,count.size)==
            std::vector<unsigned char>(count.bytes.begin(),count.bytes.begin()+count.size),
            "A complete stock count instruction differs.");
    for(const auto& entry:manifest.entries)
        Require(vm_startup::ReadStopped(process,image+entry.rva,entry.original.size())==
            std::vector<unsigned char>(entry.original.begin(),entry.original.end()),"A stock native entry differs.");
    enhanced::VerifyMigrationUnallocated(process,image);
    for(const auto rva:{0x5124580u,0x5124500u,0x5124680u,0x5124600u,0x16dbb638u})Zero(process,image+rva,8);
    Zero(process,image+0x16dbb640u,4);
    helper.Admit(process,file);VerifyControlBindings(process,helper);receipt.helperBase=helper.image.base;
    // These protected ranges are observations. The later plaintext reference is not a gate-phase guard.
    receipt.callBytes=vm_startup::ReadStopped(process,image+0x22b1559u,5);
    receipt.targetBytes=vm_startup::ReadStopped(process,image+0x227a3a0u,64);
}
void ObserveControl(OwnedChild& child,ControlReceipt& receipt,DWORD limitMs) {
#ifndef BO3_LATE_OWNED_TEST
    Require(limitMs==120000,"The stock control observation limit is fixed.");
#endif
    receipt.observationLimitMs=limitMs;
    const auto start=GetTickCount64();const auto result=WaitForSingleObject(child.process.hProcess,limitMs);
    Require(result==WAIT_OBJECT_0 || result==WAIT_TIMEOUT,"Cannot observe the owned control child.");
    if(result==WAIT_TIMEOUT) {
        receipt.observationTimedOut=true;
        if(!child.Exited())receipt.terminated=TerminateProcess(child.process.hProcess,97)!=FALSE;
        Require(WaitForSingleObject(child.process.hProcess,5000)==WAIT_OBJECT_0,"Cannot drain the owned control deadline.");
    }
    receipt.observationMs=GetTickCount64()-start;
    Require(GetExitCodeProcess(child.process.hProcess,&receipt.observedExitCode)!=FALSE,"Cannot read the owned control exit code.");
    receipt.observedExited=true;
}
void WriteControlReceipt(std::ostream& stream,const ControlReceipt& receipt) {
    const auto yes=[](bool value){return value?"true":"false";};
    const auto bytes=[&](const std::vector<unsigned char>& raw) {
        stream<<'"';for(const auto value:raw)stream<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned int>(value);
        stream<<std::dec<<'"';
    };
#ifdef BO3_LATE_PASSIVE_CONTROL
    stream<<"{\"schema\":1,\"startupMethod\":\"late-crt-passive-control\",\"readsSequential\":true,\"allThreadsStopped\":false"
        <<",\"readOnlyChecksPassed\":"<<yes(receipt.admitted)<<",\"admitted\":false";
#else
    stream<<"{\"schema\":1,\"startupMethod\":\"late-crt-control\",\"admitted\":"<<yes(receipt.admitted);
#endif
    stream<<",\"capacity\":\"stock\",\"serverTotal\":130000,\"clientTotal\":65000"
        <<",\"gateDeadlineMs\":"<<receipt.gateDeadlineMs<<",\"observationLimitMs\":"<<receipt.observationLimitMs<<",\"processId\":"<<receipt.processId
        <<",\"processCreatedFileTime\":"<<receipt.created<<",\"primaryThreadId\":"<<receipt.primaryThreadId
        <<",\"imageBase\":"<<receipt.patch.imageBase<<",\"helperBase\":"<<receipt.helperBase<<",\"gateBase\":"<<receipt.gateBase
        <<",\"generation\":"<<receipt.generation<<",\"attachThread\":"<<receipt.attachThread
        <<",\"stoppedEventThread\":"<<receipt.writeEventThread<<",\"threadsObserved\":"<<receipt.threadsObserved
        <<",\"editsWritten\":0,\"relayAllocations\":0,\"debugRegisterWrites\":0,\"liveAllocationValidated\":false"
        <<",\"attached\":"<<yes(receipt.attached)
        <<",\"committed\":false,\"detached\":"<<yes(receipt.detached)<<",\"debuggerAbsent\":"<<yes(receipt.debuggerAbsent)
        <<",\"released\":"<<yes(receipt.released)<<",\"terminated\":"<<yes(receipt.terminated)
        <<",\"bindingsUnchanged\":"<<yes(receipt.bindingsUnchanged)<<",\"observationTimedOut\":"<<yes(receipt.observationTimedOut)
        <<",\"observedExitCode\":"<<receipt.observedExitCode<<",\"observationMs\":"<<receipt.observationMs
        <<",\"observedExited\":"<<yes(receipt.observedExited)<<",\"exitDebugEventObserved\":"<<yes(receipt.exitDebugEventObserved)
        <<",\"debugEventExitCode\":"<<(receipt.exitDebugEventObserved?receipt.patch.exitCode:0)
        <<",\"nativeCallRva\":36377945,\"nativeCallBytes\":";bytes(receipt.callBytes);
    stream<<",\"nativeTargetRva\":36152224,\"nativeTargetBytes\":";bytes(receipt.targetBytes);
#ifdef BO3_LATE_PASSIVE_CONTROL
    stream<<",\"beforeChecksCallBytes\":";bytes(receipt.preAttachCallBytes);
    stream<<",\"beforeChecksTargetBytes\":";bytes(receipt.preAttachTargetBytes);
#else
    stream<<",\"preAttachCallBytes\":";bytes(receipt.preAttachCallBytes);
    stream<<",\"preAttachTargetBytes\":";bytes(receipt.preAttachTargetBytes);
#endif
    stream<<",\"events\":[";bool first=true;
    for(const auto& event:receipt.events) {if(!first)stream<<',';first=false;
        stream<<"{\"code\":"<<event.code<<",\"threadId\":"<<event.thread<<",\"address\":"<<event.address<<'}';}
    stream<<"]}";Require(stream.good(),"Cannot write the stock control receipt.");
}
}
