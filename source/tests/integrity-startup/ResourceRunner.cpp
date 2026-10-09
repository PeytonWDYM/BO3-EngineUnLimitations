#include "../../launch/job_startup/Coordinator.h"
#include "../../launch/late_startup/FixedPlan.h"
#include "../../launch/preentry/Identity.h"
#include "../job-startup/SerialLoader.h"
#include "BuildIdentity.h"
#include "TargetExports.h"
#include <array>
#include <fstream>
#include <iostream>

namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto handle:values)CloseHandle(handle);}};
struct Observation {
    bool committed=false,removed=false,removedUnderFreeze=false,liveAtCommit=false;
    std::uintptr_t address{};
};
class OwnedResource {
    HANDLE process_;
    bo3::job_startup::Receipt& receipt_;
    Observation& observed_;
public:
    OwnedResource(HANDLE process,bo3::job_startup::Receipt& receipt,Observation& observed)
        :process_(process),receipt_(receipt),observed_(observed) {
        observed_.address=reinterpret_cast<std::uintptr_t>(VirtualAllocEx(process_,nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READ));
        Require(observed_.address!=0,"Cannot allocate the owned publication resource.");
    }
    void Commit() noexcept {
        observed_.liveAtCommit=receipt_.frozen && !receipt_.thawed && WaitForSingleObject(process_,0)==WAIT_TIMEOUT;
        observed_.committed=true;
    }
    ~OwnedResource() {
        if(observed_.committed)return;
        const bool freed=VirtualFreeEx(process_,reinterpret_cast<void*>(observed_.address),0,MEM_RELEASE)!=FALSE;
        MEMORY_BASIC_INFORMATION memory{};
        observed_.removed=freed && VirtualQueryEx(process_,reinterpret_cast<void*>(observed_.address),&memory,sizeof(memory))
            ==sizeof(memory) && memory.State==MEM_FREE;
        observed_.removedUnderFreeze=observed_.removed && receipt_.frozen && !receipt_.thawed
            && WaitForSingleObject(process_,0)==WAIT_TIMEOUT;
    }
};
std::uintptr_t Seed(HANDLE process,const std::filesystem::path& file) {
    constexpr SIZE_T size=0x1d74b000;
    const auto image=reinterpret_cast<std::uintptr_t>(VirtualAllocEx(process,nullptr,size,MEM_RESERVE,PAGE_READWRITE));
    Require(image!=0,"Cannot reserve the owned native image.");
    std::ifstream input(file,std::ios::binary);std::uint32_t count{};input.read(reinterpret_cast<char*>(&count),4);
    Require(input.good() && count<=200,"Invalid owned native seed count.");
    for(std::uint32_t i=0;i<count;++i) {
        std::uint32_t rva{},length{};input.read(reinterpret_cast<char*>(&rva),4);input.read(reinterpret_cast<char*>(&length),4);
        Require(input.good() && length && length<=size && rva<=size-length,"Invalid owned native seed range.");
        const auto start=(image+rva)&~std::uintptr_t{4095},end=(image+rva+length+4095)&~std::uintptr_t{4095};
        Require(VirtualAllocEx(process,reinterpret_cast<void*>(start),end-start,MEM_COMMIT,PAGE_READWRITE),"Cannot commit owned native seed.");
        std::vector<unsigned char> bytes(length);input.read(reinterpret_cast<char*>(bytes.data()),length);SIZE_T written{};
        Require(input.good() && WriteProcessMemory(process,reinterpret_cast<void*>(image+rva),bytes.data(),length,&written)
            && written==length,"Cannot populate the owned native seed.");
    }
    return image;
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use a resource case and a new private output path.");
        const std::wstring scenario=argv[1];const auto output=PrivateOutput(argv[2]);
        Require(scenario==L"success" || scenario==L"rollback" || scenario==L"plan-refusal"
            || scenario==L"thaw" || scenario==L"release","Unknown owned resource case.");
        wchar_t own[32768]{};Require(GetModuleFileNameW(nullptr,own,32768),"Cannot find the owned resource fixture.");
        const auto directory=std::filesystem::path(own).parent_path();
        const auto target=directory/L"VmStartupControlTarget.exe",helperFile=directory/L"Bo3EnhancedHelper.dll",gateFile=directory/L"Bo3StartupGate.dll";
        Locks locks;VerifyFile(target,kOwnedTargetHash,locks.values);VerifyFile(helperFile,kHelperHash,locks.values);
        VerifyFile(gateFile,kGateHash,locks.values);VerifyFile(directory/L"seed.bin",kSeedHash,locks.values);
        VerifyFile(L"C:\\Windows\\System32\\ntdll.dll","a74f7482085eab125ccc09152ab7e0b5994bcb13e1a7b29880bdbb24179ecb8b",locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);bo3::late_startup::MappedGate gate(gateFile);
        const auto command=bo3::late_startup::QuoteArgument(target.wstring())+L" success "+
            bo3::late_startup::QuoteArgument((directory/L"seed.bin").wstring())+L" "+
            bo3::late_startup::QuoteArgument(output.wstring()+L".target.json");
        const std::array<std::filesystem::path,2> helpers{helperFile,gateFile};
        bo3::job_startup::OwnedJob job;bo3::late_startup::OwnedChild child(target,command,helpers);job.Assign(child);
        ConfigureOwnedSerialLoader(child);bo3::job_startup::Receipt receipt;Observation observed;
        std::weak_ptr<OwnedResource> lease;
        const auto prepare=[&](HANDLE process,std::uintptr_t image,vm_startup::Receipt&) {
            const auto inert=Seed(process,directory/L"seed.bin");SIZE_T written{};
            Require(WriteProcessMemory(process,reinterpret_cast<void*>(image+kOwnedImageRva),&inert,8,&written) && written==8,
                "Cannot bind the owned native image.");
            auto plan=bo3::late_startup::PrepareFixedPlan(process,inert,helper,helperFile);
            auto resource=std::make_shared<OwnedResource>(process,receipt,observed);lease=resource;
            plan.commitResources=[resource]() noexcept {resource->Commit();};
            if(scenario==L"plan-refusal")throw std::runtime_error("Owned refusal after resource preparation.");
            return plan;
        };
        using bo3::job_startup::Failure;
        bo3::job_startup::SetOwnedFailure(scenario==L"rollback"?Failure::AfterApply:
            scenario==L"thaw"?Failure::Thaw:scenario==L"release"?Failure::Release:Failure::None);
        bool leasePresentDuringApply=false;
        bo3::job_startup::SetOwnedObserver([&](HANDLE process,bool rollback) {
            if(rollback)return;
            MEMORY_BASIC_INFORMATION memory{};
            leasePresentDuringApply=!lease.expired() && VirtualQueryEx(process,reinterpret_cast<void*>(observed.address),&memory,sizeof(memory))
                ==sizeof(memory) && memory.State==MEM_COMMIT && !observed.committed;
        });
        bool refused=false;
        try {bo3::job_startup::Coordinate(child,job,gate,prepare,receipt);}
        catch(const std::exception& error){refused=true;std::cerr<<error.what()<<'\n';}
        Require(WaitForSingleObject(child.process.hProcess,5000)==WAIT_OBJECT_0,"The owned resource target did not exit.");
        DWORD exit{};Require(GetExitCodeProcess(child.process.hProcess,&exit),"Cannot read the owned resource exit.");
        bool passed=lease.expired();
        if(scenario==L"success")passed=passed && !refused && exit==0 && receipt.released && observed.committed
            && observed.liveAtCommit && leasePresentDuringApply && !observed.removed;
        else passed=passed && refused && exit==97 && receipt.terminated && !receipt.released;
        if(scenario==L"rollback")passed=passed && receipt.patch.rollbackCompleted && observed.removedUnderFreeze
            && !observed.committed && leasePresentDuringApply;
        if(scenario==L"plan-refusal")passed=passed && receipt.patch.editsWritten==0 && observed.removedUnderFreeze && !observed.committed;
        if(scenario==L"thaw" || scenario==L"release")passed=passed && observed.committed && observed.liveAtCommit && !observed.removed;
        std::ofstream proof(output);proof<<"{\"passed\":"<<(passed?"true":"false")
            <<",\"resourcePresentDuringApply\":"<<(leasePresentDuringApply?"true":"false")
            <<",\"resourceCommittedUnderFreeze\":"<<(observed.liveAtCommit?"true":"false")
            <<",\"resourceRemovedUnderFreeze\":"<<(observed.removedUnderFreeze?"true":"false")
            <<",\"leaseReleased\":"<<(lease.expired()?"true":"false")<<",\"receipt\":";
        bo3::job_startup::WriteReceipt(proof,receipt);
        proof<<",\"scope\":\"Owned allocation lifetime with reviewed42 publication. No store-correction semantics or game execution.\"}";
        Require(proof.good(),"Cannot save owned resource lifetime evidence.");return passed?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
