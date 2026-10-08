#include "../../launch/late_startup/FixedPlan.h"
#include "../../launch/late_startup/PrivateReceipt.h"
#include "../../launch/preentry/Identity.h"
#include "BuildIdentity.h"
#include "TargetExports.h"
#include "HandleSnapshot.h"
#include <array>
#include <fstream>
#include <iostream>
#include <cstring>
#include <algorithm>

namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto value:values)CloseHandle(value);}};
std::vector<unsigned char> Snapshot(HANDLE process,const std::vector<vm_startup::AddressEdit>& edits) {
    std::vector<unsigned char> result;
    for(const auto& edit:edits) {
        const auto bytes=vm_startup::ReadStopped(process,edit.address,edit.original.size());
        result.insert(result.end(),bytes.begin(),bytes.end());
    }
    return result;
}
std::vector<DWORD> Protections(HANDLE process,const std::vector<vm_startup::AddressEdit>& edits) {
    std::vector<DWORD> result;
    for(const auto& edit:edits) {MEMORY_BASIC_INFORMATION memory{};
        Require(VirtualQueryEx(process,reinterpret_cast<void*>(edit.address),&memory,sizeof(memory))==sizeof(memory),"Cannot capture owned page protection.");
        result.push_back(memory.Protect);}
    return result;
}
void Save(const std::filesystem::path& path,const std::vector<unsigned char>& bytes) {
    std::ofstream file(path,std::ios::binary);file.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
    Require(file.good(),"Cannot save owned transaction bytes.");
}
}
int RunCase(int argc,wchar_t** argv,bool warmup,bool snapshots=true) {
    try {
        Require(argc==3,"Use a fixed owned case and a new private receipt path.");
        const std::wstring scenario=argv[1];const auto output=PrivateOutput(argv[2]);
        Require(scenario==L"success" || scenario==L"foreign-break" || scenario==L"guard" || scenario==L"allocated"
            || scenario==L"rollback" || scenario==L"continue" || scenario==L"detach" || scenario==L"state" || scenario==L"receipt-refusal",
            "Unknown owned late gate scenario.");
        wchar_t own[32768]{};Require(GetModuleFileNameW(nullptr,own,32768)!=0,"Cannot locate the owned fixture.");
        const auto directory=std::filesystem::path(own).parent_path();
        const auto target=directory/L"VmStartupControlTarget.exe",helperFile=directory/L"Bo3EnhancedHelper.dll",gateFile=directory/L"Bo3StartupGate.dll";
        Locks locks;locks.values.reserve(4);
        VerifyFile(target,kOwnedTargetHash,locks.values);VerifyFile(helperFile,kHelperHash,locks.values);
        VerifyFile(gateFile,kGateHash,locks.values);VerifyFile(directory/L"seed.bin",kSeedHash,locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);bo3::late_startup::MappedGate gate(gateFile);
        const auto targetProof=output.wstring()+L".target.json";
        const auto command=bo3::late_startup::QuoteArgument(target.wstring())+L" "+scenario+L" "+
            bo3::late_startup::QuoteArgument((directory/L"seed.bin").wstring())+L" "+bo3::late_startup::QuoteArgument(targetProof);
        const std::array<std::filesystem::path,2> helpers{helperFile,gateFile};
        DWORD handlesBefore{};Require(GetProcessHandleCount(GetCurrentProcess(),&handlesBefore)!=FALSE,"Cannot record baseline handles.");
        std::vector<std::string> handleRowsBefore;
        if(snapshots)handleRowsBefore=SaveHandles(output.wstring()+L".handles-before.txt");
        auto childOwner=std::make_unique<bo3::late_startup::OwnedChild>(target,command,helpers,1000);
        auto& child=*childOwner;bo3::late_startup::Receipt receipt;
        if(scenario==L"receipt-refusal") {
            HANDLE retained{};
            Require(DuplicateHandle(GetCurrentProcess(),child.process.hProcess,GetCurrentProcess(),&retained,
                SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,0)!=FALSE,"Cannot retain the pre-resume refusal process.");
            bool refused=false;
            try {bo3::late_startup::PrivateReceipt invalid(directory/L"receipt-junction",child);}
            catch(const std::exception&){refused=true;}
            const auto start=GetTickCount64();childOwner.reset();
            const auto drain=GetTickCount64()-start;const bool signaled=WaitForSingleObject(retained,0)==WAIT_OBJECT_0;
            CloseHandle(retained);std::ofstream proof(output);
            proof<<"{\"passed\":"<<(refused && signaled && drain<=5000 ? "true":"false")
                <<",\"preResumeReceiptRefused\":"<<(refused?"true":"false")<<",\"retainedProcessSignaled\":"<<(signaled?"true":"false")
                <<",\"destructorDrainMs\":"<<drain<<",\"nativeEdits\":0}";return refused && signaled && drain<=5000 ? 0 : 1;
        }
        auto report=std::make_unique<bo3::late_startup::PrivateReceipt>(directory,child);
        bool existingRefused=false;
        try {bo3::late_startup::PrivateReceipt duplicate(directory,child);}
        catch(const std::exception&){existingRefused=true;}
        Require(existingRefused,"CREATE_NEW did not refuse the existing process-bound receipt.");
        std::vector<vm_startup::AddressEdit> edits;std::vector<unsigned char> before,applied,restored;
        std::vector<DWORD> protections;bool protectionMatch=false;
        const auto prepare=[&](HANDLE process,std::uintptr_t image,vm_startup::Receipt&) {
            const auto pointer=vm_startup::ReadStopped(process,image+kOwnedImageRva,8);
            std::uintptr_t inert{};std::memcpy(&inert,pointer.data(),8);
            auto plan=bo3::late_startup::PrepareFixedPlan(process,inert,helper,helperFile);
            edits=plan.edits;before=Snapshot(process,edits);protections=Protections(process,edits);
            if(scenario==L"state") {
                const std::uint64_t wrong=0;SIZE_T count{};
                Require(WriteProcessMemory(process,reinterpret_cast<void*>(gate.Base()+kGateStateRva+32),&wrong,8,&count)
                    && count==8,"Cannot inject owned stopped state corruption.");
            }
            return plan;
        };
        using bo3::late_startup::Failure;
        bo3::late_startup::SetOwnedFailure(scenario==L"rollback" ? Failure::AfterApply : scenario==L"continue" ? Failure::Continue
            : scenario==L"detach" ? Failure::Detach : Failure::None);
        bo3::late_startup::SetOwnedStoppedObserver([&](HANDLE process,bool rollback) {
            const auto actual=Snapshot(process,edits);protectionMatch=Protections(process,edits)==protections;
            if(rollback)restored=actual;else applied=actual;
        });
        HANDLE breakin{};bool foreignSeen=false;
        bo3::late_startup::SetOwnedEventObserver([&](HANDLE process,const DEBUG_EVENT& event) {
            if(scenario!=L"foreign-break")return;
            if(event.dwDebugEventCode==CREATE_THREAD_DEBUG_EVENT && event.dwThreadId==receipt.attachThread) {
                breakin=event.u.CreateThread.hThread;
                Require(SuspendThread(breakin)==0,"Cannot hold the owned attach thread for the race.");
                const LONG one=1;SIZE_T count{};
                Require(WriteProcessMemory(process,reinterpret_cast<void*>(receipt.patch.imageBase+kTriggerBreakRva),&one,4,&count)
                    && count==4,"Cannot trigger the owned foreign breakpoint race.");
            } else if(event.dwDebugEventCode==EXCEPTION_DEBUG_EVENT
                && event.u.Exception.ExceptionRecord.ExceptionCode==EXCEPTION_BREAKPOINT
                && reinterpret_cast<std::uintptr_t>(event.u.Exception.ExceptionRecord.ExceptionAddress)==receipt.attachBreakpoint
                && event.dwThreadId!=receipt.attachThread) {
                Require(breakin && !foreignSeen && ResumeThread(breakin)==1,"Cannot release the real owned attach thread.");
                foreignSeen=true;
            }
        });
        bool refused=false;
        try {bo3::late_startup::Coordinate(child,gate,prepare,receipt);}
        catch(const std::exception& error){refused=true;std::cerr<<error.what()<<'\n';}
        Require(WaitForSingleObject(child.process.hProcess,5000)==WAIT_OBJECT_0,"Owned late child lifetime exceeded its bound.");
        DWORD exit{};Require(GetExitCodeProcess(child.process.hProcess,&exit)!=FALSE,"Cannot read owned late exit.");
        const bool success=scenario==L"success" || scenario==L"foreign-break";
        bool passed=refused!=success && (success ? receipt.committed && receipt.detached && receipt.debuggerAbsent && receipt.released
            && !receipt.terminated && exit==0 && receipt.patch.editsWritten==42 && protectionMatch && applied!=before
            : receipt.terminated && !receipt.released && child.Exited());
        if(scenario==L"guard" || scenario==L"allocated" || scenario==L"state")passed=passed && receipt.patch.editsWritten==0 && !receipt.committed;
        if(scenario==L"rollback")passed=passed && receipt.patch.rollbackCompleted && receipt.patch.editsWritten==42 && restored==before && protectionMatch;
        if(scenario==L"continue" || scenario==L"detach")passed=passed && receipt.committed && !receipt.patch.rollbackCompleted && !receipt.detached;
        if(scenario==L"foreign-break")passed=passed && foreignSeen && receipt.writeEventThread==receipt.attachThread;
        if(!before.empty())Save(output.wstring()+L".before.bin",before);
        if(!applied.empty())Save(output.wstring()+L".applied.bin",applied);
        if(!restored.empty())Save(output.wstring()+L".restored.bin",restored);
        report->Write(receipt);report.reset();
        childOwner.reset();DWORD handlesAfter{};
        Require(GetProcessHandleCount(GetCurrentProcess(),&handlesAfter)!=FALSE,"Cannot record final owned handles.");
        std::vector<std::string> handleRowsAfter,newHandles;
        if(snapshots) {
            handleRowsAfter=SaveHandles(output.wstring()+L".handles-after.txt");
            for(const auto& row:handleRowsAfter)if(std::find(handleRowsBefore.begin(),handleRowsBefore.end(),row)==handleRowsBefore.end())newHandles.push_back(row);
        }
        const bool retainedWait=handlesAfter==handlesBefore+1 && newHandles.size()==1
            && newHandles.front().ends_with("\t0\tWaitCompletionPacket");
        passed=passed && (warmup || handlesBefore==handlesAfter || retainedWait);
        std::ofstream file(output);file<<"{\"passed\":"<<(passed?"true":"false")<<",\"exitCode\":"<<exit
            <<",\"handlesBefore\":"<<handlesBefore<<",\"handlesAfter\":"<<handlesAfter
            <<",\"existingReceiptRefused\":"<<(existingRefused?"true":"false")
            <<",\"retainedOsWaitCompletionPacket\":"<<(retainedWait?"true":"false")
            <<",\"coldInfrastructureCycle\":"<<(warmup?"true":"false")<<",\"foreignBreakpointIgnored\":"<<(foreignSeen?"true":"false")
            <<",\"protectionsPreserved\":"<<(protectionMatch?"true":"false")<<",\"receipt\":";
        bo3::late_startup::WriteReceipt(file,receipt);file<<",\"scope\":\"Owned inert image. No BO3 native code execution.\"}";
        Require(file.good(),"Cannot save owned late gate proof.");return passed?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=3)return 2;
    if(std::wstring_view(argv[1])==L"handles-only") {
        try {
            const auto path=PrivateOutput(argv[2]);DWORD before{},first{},second{};
            Require(GetProcessHandleCount(GetCurrentProcess(),&before)!=FALSE,"Cannot count initial handles.");
            SaveHandles(path.wstring()+L".first.txt");
            Require(GetProcessHandleCount(GetCurrentProcess(),&first)!=FALSE,"Cannot count first snapshot handles.");
            SaveHandles(path.wstring()+L".second.txt");
            Require(GetProcessHandleCount(GetCurrentProcess(),&second)!=FALSE,"Cannot count second snapshot handles.");
            std::ofstream file(path);file<<"{\"before\":"<<before<<",\"afterFirstPss\":"<<first<<",\"afterSecondPss\":"<<second<<",\"children\":0}";
            return file.good()?0:2;
        }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
    }
    const auto warmPath=std::wstring(argv[2])+L".warm.json";
    wchar_t success[]=L"success";
    wchar_t* warmArgs[]{argv[0],success,const_cast<wchar_t*>(warmPath.c_str())};
    const int warmResult=RunCase(3,warmArgs,true);
    return warmResult ? warmResult : RunCase(argc,argv,false);
}
