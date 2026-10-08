#include "../../launch/bindings_control/Lifetime.h"
#include "../../launch/preentry/Identity.h"
#include "../../launch/job_startup/RuntimeUnwind.h"
#include "../../launch/job_startup/PrimaryAdmission.h"
#include "../job-startup/SerialLoader.h"
#include "../job-startup/ParentDeath.h"
#include "BuildIdentity.h"
#include "TargetExports.h"
#include <array>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <cstring>
#include <memory>
namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto handle:values)CloseHandle(handle);}};
std::uintptr_t Seed(HANDLE process,const std::filesystem::path& file) {
    const auto image=reinterpret_cast<std::uintptr_t>(VirtualAllocEx(process,nullptr,494186496,MEM_RESERVE,PAGE_READWRITE));
    Require(image!=0,"Cannot reserve the owned inert image.");
    std::ifstream input(file,std::ios::binary);std::uint32_t records{};input.read(reinterpret_cast<char*>(&records),4);
    Require(input.good() && records<=200,"Invalid owned seed record count.");
    for(std::uint32_t i=0;i<records;++i) {
        std::uint32_t rva{},size{};input.read(reinterpret_cast<char*>(&rva),4);input.read(reinterpret_cast<char*>(&size),4);
        Require(input.good() && size && size<=494186496 && rva<=494186496-size,"Invalid owned seed range.");
        const auto start=(image+rva)&~std::uintptr_t{4095};const auto end=(image+rva+size+4095)&~std::uintptr_t{4095};
        Require(VirtualAllocEx(process,reinterpret_cast<void*>(start),end-start,MEM_COMMIT,PAGE_READWRITE)!=nullptr,
            "Cannot commit the owned inert image.");
        std::vector<unsigned char> bytes(size);input.read(reinterpret_cast<char*>(bytes.data()),size);SIZE_T written{};
        Require(input.good() && WriteProcessMemory(process,reinterpret_cast<void*>(image+rva),bytes.data(),size,&written)
            && written==size,"Cannot seed the owned inert image.");
    }
    return image;
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use owned case and a new private output path.");
        const std::wstring scenario=argv[1];const auto output=PrivateOutput(argv[2]);
        Require(scenario==L"success" || scenario==L"guard" || scenario==L"allocated" || scenario==L"helper"
            || scenario==L"extra-thread" || scenario==L"membership" || scenario==L"rollback" || scenario==L"rollback-failed" || scenario==L"deadline"
            || scenario==L"thaw" || scenario==L"release" || scenario==L"early-exit" || scenario==L"parent-death" || scenario==L"death-child","Unknown owned bindings case.");
        wchar_t own[32768]{};Require(GetModuleFileNameW(nullptr,own,32768)!=0,"Cannot locate the owned control.");
        const auto directory=std::filesystem::path(own).parent_path();
        if(scenario==L"parent-death")return VerifyOwnedParentDeath(own,output);
        const auto target=directory/L"VmStartupControlTarget.exe",helperFile=directory/L"Bo3EnhancedHelper.dll",gateFile=directory/L"Bo3StartupGate.dll";
        Locks locks;locks.values.reserve(5);
        VerifyFile(target,kOwnedTargetHash,locks.values);VerifyFile(helperFile,kHelperHash,locks.values);VerifyFile(gateFile,kGateHash,locks.values);
        VerifyFile(directory/L"seed.bin",kSeedHash,locks.values);
        VerifyFile(L"C:\\Windows\\System32\\ntdll.dll","a74f7482085eab125ccc09152ab7e0b5994bcb13e1a7b29880bdbb24179ecb8b",locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);bo3::late_startup::MappedGate gate(gateFile);
        const auto command=bo3::late_startup::QuoteArgument(target.wstring())+L" "+scenario+L" unused "+
            bo3::late_startup::QuoteArgument(output.wstring()+L".target.json");
        const std::array<std::filesystem::path,2> helpers{helperFile,gateFile};
        bo3::job_startup::OwnedJob job;bo3::late_startup::OwnedChild child(target,command,helpers);job.Assign(child);
        ConfigureOwnedSerialLoader(child);
        bo3::late_startup::PrivateReceipt report(directory,child);bo3::bindings_control::Receipt receipt;
        std::unique_ptr<bo3::late_startup::OwnedChild> member;
        bo3::bindings_control::SetOwnedSetup([&](HANDLE process,std::uintptr_t image) {
            const auto inert=Seed(process,directory/L"seed.bin");SIZE_T written{};
            const auto write=[&](std::uintptr_t address,const void* data,SIZE_T size) {
                Require(WriteProcessMemory(process,reinterpret_cast<void*>(address),data,size,&written) && written==size,"Owned setup write failed.");
            };
            write(image+kOwnedImageRva,&inert,8);
            for(const auto rva:{0x22b1559u,0x227a3a0u})
                Require(VirtualAllocEx(process,reinterpret_cast<void*>((inert+rva)&~std::uintptr_t{4095}),4096,MEM_COMMIT,PAGE_READWRITE)!=nullptr,
                "Cannot commit the owned protected observation range.");
            if(scenario==L"guard") {auto wrong=vm_startup::ReadStopped(process,inert+0x12dba10,1);wrong[0]^=1;write(inert+0x12dba10,wrong.data(),1);}
            if(scenario==L"allocated"){const std::uintptr_t one=1;write(inert+0x5124580,&one,8);}
            if(scenario==L"helper") {
                helper.Admit(process,helperFile);const auto address=helper.image.base+helper.state.readState;
                DWORD prior{},discarded{};const unsigned char wrong=0;
                Require(VirtualProtectEx(process,reinterpret_cast<void*>(address),1,PAGE_READWRITE,&prior),"Owned helper corruption failed.");
                write(address,&wrong,1);Require(VirtualProtectEx(process,reinterpret_cast<void*>(address),1,prior,&discarded),"Owned helper restore failed.");
            }
            if(scenario==L"membership") {member=std::make_unique<bo3::late_startup::OwnedChild>(target,command,helpers);job.AddOwnedMember(member->process.hProcess);}
            return inert;
        });
        using bo3::bindings_control::Failure;
        bo3::bindings_control::SetOwnedFailure((scenario==L"rollback" || scenario==L"rollback-failed")?Failure::AfterApply:scenario==L"thaw"?Failure::Thaw:
            scenario==L"release"?Failure::Release:Failure::None);
        bo3::bindings_control::Selected admitted;bool observed=false,rolledBack=false;
        bo3::bindings_control::SetOwnedObserver([&](HANDLE process,const bo3::bindings_control::Selected& selected,bo3::bindings_control::Phase phase) {
            if(phase==bo3::bindings_control::Phase::Prepared) {
                if(scenario==L"death-child")DieAfterPartialWrite(child,output,selected.publications);
                return;
            }
            const bool rollback=phase==bo3::bindings_control::Phase::RolledBack;
            bo3::job_control::VerifyOriginals(process,selected.stock);
            for(const auto& edit:selected.publications)
                Require(vm_startup::ReadStopped(process,edit.address,edit.original.size())==(rollback?edit.original:edit.replacement),
                    "Owned publication/rollback observation failed.");
            admitted=selected;if(rollback)rolledBack=true;else observed=true;
            if(scenario==L"rollback-failed" && !rollback)
                Require(VirtualFreeEx(process,reinterpret_cast<void*>(receipt.native.relay),0,MEM_RELEASE),"Cannot invalidate owned rollback storage.");
        });
        bool refused=false,unchanged=false,relayRetained=false;
        try {bo3::bindings_control::Coordinate(child,job,gate,helper,helperFile,receipt);}
        catch(const std::exception& error){refused=true;std::cerr<<error.what()<<'\n';}
        if(!refused) {
            bo3::job_control::VerifyOriginals(child.process.hProcess,admitted.stock);unchanged=true;
            MEMORY_BASIC_INFORMATION memory{};
            relayRetained=VirtualQueryEx(child.process.hProcess,reinterpret_cast<void*>(receipt.native.relay),&memory,sizeof(memory))==sizeof(memory)
                && memory.State==MEM_COMMIT;
            bo3::bindings_control::Retain(child,job,report,receipt);
        }else report.Write(receipt);
        const auto& native=receipt.native;
        const bool success=scenario==L"success" || scenario==L"deadline";
        bool passed=success ? !refused && native.patch.exited && native.patch.exitCode==(scenario==L"deadline"?97u:0u)
            && native.primaryAdmitted && native.thawed && native.released && native.committed && native.patch.editsWritten==9
            && receipt.stockVerified && observed && unchanged && relayRetained
            : refused && native.patch.exited && !native.released;
        if(scenario==L"early-exit")passed=passed && native.patch.exitCode==15 && !native.terminated;
        else if(!success)passed=passed && native.patch.exitCode==97 && native.terminated;
        if(scenario==L"rollback")passed=passed && observed && rolledBack && native.patch.rollbackCompleted && native.relayFreed && !native.committed;
        if(scenario==L"rollback-failed")passed=passed && observed && !rolledBack && !native.patch.rollbackCompleted && !native.thawAttempted;
        if(scenario==L"deadline")passed=passed && receipt.deadlineTerminated && native.terminated && receipt.exitTick-receipt.releasedTick>=120000;
        if(scenario==L"membership")passed=passed && member && member->Exited();
        std::ofstream out(output);out<<"{\"passed\":"<<(passed?"true":"false")<<",\"originalsUnchanged\":"<<(unchanged?"true":"false")
            <<",\"publicationObserved\":"<<(observed?"true":"false")<<",\"rollbackObserved\":"<<(rolledBack?"true":"false")
            <<",\"relayRetained\":"<<(relayRetained?"true":"false")<<",\"receiptPath\":\"";
        for(const auto c:report.Path().string()){if(c=='\\')out<<'\\';out<<c;}
        out<<"\",\"receipt\":";bo3::bindings_control::WriteReceipt(out,receipt);out<<'}';
        Require(out.good(),"Cannot save owned bindings proof.");return passed?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
