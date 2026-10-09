#include "../../launch/integrity_startup/Coordinator.h"
#include "../../launch/late_startup/FixedPlan.h"
#include "../../launch/late_startup/PrivateReceipt.h"
#include "../../launch/preentry/Identity.h"
#include "../job-startup/SerialLoader.h"
#include "BuildIdentity.h"
#include "TargetExports.h"
#include "Profile.h"
#include <Psapi.h>
#include <array>
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iostream>

namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto handle:values)CloseHandle(handle);}};
std::vector<unsigned char> Bytes(HANDLE process,const std::vector<vm_startup::AddressEdit>& edits) {
    std::vector<unsigned char> result;
    for(const auto& edit:edits){const auto bytes=vm_startup::ReadStopped(process,edit.address,edit.original.size());
        result.insert(result.end(),bytes.begin(),bytes.end());}
    return result;
}
void Save(const std::filesystem::path& file,const std::vector<unsigned char>& bytes) {
    std::ofstream out(file,std::ios::binary);out.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
    Require(out.good(),"Cannot save owned transaction bytes.");
}
std::uintptr_t ModuleBase(HANDLE process,const std::filesystem::path& file) {
    std::array<HMODULE,128> modules{};DWORD bytes{};
    Require(K32EnumProcessModulesEx(process,modules.data(),sizeof(modules),&bytes,LIST_MODULES_64BIT) && bytes<=sizeof(modules),
        "Cannot inspect owned module inventory.");
    for(std::size_t i=0;i<bytes/sizeof(HMODULE);++i) {
        std::array<wchar_t,32768> path{};
        Require(K32GetModuleFileNameExW(process,modules[i],path.data(),static_cast<DWORD>(path.size())),"Cannot identify an owned module.");
        if(std::filesystem::path(path.data())==file)return reinterpret_cast<std::uintptr_t>(modules[i]);
    }
    throw std::runtime_error("The authored integrity image is missing.");
}
void SeedGuards(HANDLE process,std::uintptr_t image,const std::filesystem::path& file) {
    std::ifstream input(file,std::ios::binary);std::uint32_t count{};input.read(reinterpret_cast<char*>(&count),4);
    Require(input.good() && count && count<=5000,"Invalid authored guard seed count.");
    for(std::uint32_t i=0;i<count;++i) {
        std::uint32_t rva{},length{};input.read(reinterpret_cast<char*>(&rva),4);input.read(reinterpret_cast<char*>(&length),4);
        Require(input.good() && length && length<=bo3::code_integrity::kImageSize
            && rva<=bo3::code_integrity::kImageSize-length,"Invalid authored guard seed range.");
        std::vector<unsigned char> bytes(length);input.read(reinterpret_cast<char*>(bytes.data()),length);SIZE_T written{};
        Require(input.good() && WriteProcessMemory(process,reinterpret_cast<void*>(image+rva),bytes.data(),length,&written)
            && written==length,"Cannot seed the authored image under freeze.");
    }
    Require(input.peek()==std::char_traits<char>::eof(),"The authored guard seed has trailing bytes.");
    for(const auto& record:bo3::code_integrity::kRecords)for(std::size_t i=0;i<record.imageAddressCount;++i) {
        const auto& field=record.imageAddresses[i];const auto pointer=image+field.targetRva;SIZE_T written{};
        Require(WriteProcessMemory(process,reinterpret_cast<void*>(image+record.rva+field.offset),&pointer,8,&written)
            && written==8,"Cannot bind an authored image-address field.");
    }
}
std::uintptr_t Seed(HANDLE process,const std::filesystem::path& file) {
    constexpr SIZE_T size=0x1d74b000;
    const auto image=reinterpret_cast<std::uintptr_t>(VirtualAllocEx(process,nullptr,size,MEM_RESERVE,PAGE_READWRITE));
    Require(image!=0,"Cannot reserve the owned inert image.");
    std::ifstream input(file,std::ios::binary);std::uint32_t records{};input.read(reinterpret_cast<char*>(&records),4);
    Require(input.good() && records<=200,"Invalid owned seed count.");
    for(std::uint32_t i=0;i<records;++i) {
        std::uint32_t rva{},length{};input.read(reinterpret_cast<char*>(&rva),4);input.read(reinterpret_cast<char*>(&length),4);
        Require(input.good() && length && length<=size && rva<=size-length,"Invalid owned seed range.");
        const auto start=(image+rva)&~std::uintptr_t{4095},end=(image+rva+length+4095)&~std::uintptr_t{4095};
        Require(VirtualAllocEx(process,reinterpret_cast<void*>(start),end-start,MEM_COMMIT,PAGE_READWRITE)!=nullptr,
            "Cannot commit the owned seed.");
        std::vector<unsigned char> bytes(length);input.read(reinterpret_cast<char*>(bytes.data()),length);SIZE_T written{};
        Require(input.good() && WriteProcessMemory(process,reinterpret_cast<void*>(image+rva),bytes.data(),length,&written)
            && written==length,"Cannot write the owned seed.");
    }
    return image;
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use an owned case and a new private output path.");
        const std::wstring scenario=argv[1];const auto output=PrivateOutput(argv[2]);
        const std::array cases{L"success",L"native-short",L"integrity-refusal",L"integrity-short",L"overlap",L"original",
            L"frame",L"rollback",L"partial-write",L"rollback-failed",L"thaw",L"release",L"extra-thread",L"freeze-pending",
            L"module-success",L"module-identity",L"module-guard",L"module-rollback"};
        Require(std::find(cases.begin(),cases.end(),scenario)!=cases.end(),"Unknown owned integrity case.");
        const bool moduleCase=scenario.starts_with(L"module-");
        wchar_t own[32768]{};Require(GetModuleFileNameW(nullptr,own,32768)!=0,"Cannot find the owned fixture.");
        const auto directory=std::filesystem::path(own).parent_path();
        const auto target=directory/L"VmStartupControlTarget.exe",helperFile=directory/L"Bo3EnhancedHelper.dll",
            gateFile=directory/L"Bo3StartupGate.dll";
        Locks locks;
        VerifyFile(target,kOwnedTargetHash,locks.values);VerifyFile(helperFile,kHelperHash,locks.values);
        VerifyFile(gateFile,kGateHash,locks.values);VerifyFile(directory/L"seed.bin",kSeedHash,locks.values);
        VerifyFile(directory/L"IntegrityOwnedImage.dll",kOwnedIntegrityImageHash,locks.values);
        VerifyFile(directory/L"fixture-seed.bin",kOwnedIntegritySeedHash,locks.values);
        VerifyFile(L"C:\\Windows\\System32\\ntdll.dll","a74f7482085eab125ccc09152ab7e0b5994bcb13e1a7b29880bdbb24179ecb8b",locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);bo3::late_startup::MappedGate gate(gateFile);
        const auto command=bo3::late_startup::QuoteArgument(target.wstring())+L" "+scenario+L" "+
            bo3::late_startup::QuoteArgument((directory/L"seed.bin").wstring())+L" "+
            bo3::late_startup::QuoteArgument(output.wstring()+L".target.json");
        std::vector<std::filesystem::path> helpers{helperFile,gateFile};
        if(moduleCase)helpers.push_back(directory/L"IntegrityOwnedImage.dll");
        bo3::job_startup::OwnedJob job;bo3::late_startup::OwnedChild child(target,command,helpers);job.Assign(child);
        ConfigureOwnedSerialLoader(child);
        if(scenario==L"freeze-pending")job.SetOwnedFreezeStatus(0x103);
        bo3::late_startup::PrivateReceipt report(directory,child);bo3::integrity_startup::Receipt receipt;
        std::vector<vm_startup::AddressEdit> edits;
        std::vector<unsigned char> before,applied,restored;std::vector<DWORD> protections;bool protectionsMatch=false;
        std::uintptr_t inert{},endpoint{},integrityImage{};bool integrityCalled=false;
        const auto prepare=[&](HANDLE process,std::uintptr_t image,vm_startup::Receipt&) {
            inert=Seed(process,directory/L"seed.bin");SIZE_T written{};
            Require(WriteProcessMemory(process,reinterpret_cast<void*>(image+kOwnedImageRva),&inert,8,&written) && written==8,
                "Cannot bind the owned inert image.");
            auto plan=bo3::late_startup::PrepareFixedPlan(process,inert,helper,helperFile);
            edits=plan.edits;if(scenario==L"native-short")plan.edits.pop_back();return plan;
        };
        bo3::integrity_startup::SetOwnedPrepareIntegrity([&](HANDLE process,std::uintptr_t,
            const std::array<unsigned char,32>&,std::span<const vm_startup::AddressEdit> native) {
            integrityCalled=true;Require(native.size()==42,"The integrity planner did not receive all native edits.");
            Require(scenario!=L"integrity-refusal","Owned integrity guard refusal.");
            std::vector<vm_startup::AddressEdit> extra;
            if(moduleCase) {
                integrityImage=ModuleBase(process,directory/L"IntegrityOwnedImage.dll");
                SeedGuards(process,integrityImage,directory/L"fixture-seed.bin");
                auto digest=bo3::code_integrity::kExecutableDigest;
                if(scenario==L"module-identity")digest[0]^=1;
                if(scenario==L"module-guard") {
                    const auto& record=bo3::code_integrity::kRecords.front();const unsigned char wrong=0xcc;SIZE_T written{};
                    Require(WriteProcessMemory(process,reinterpret_cast<void*>(integrityImage+record.rva),&wrong,1,&written)
                        && written==1,"Cannot inject the authored module guard refusal.");
                }
                extra=bo3::code_integrity::PrepareStopped(process,integrityImage,digest,native);
            }else {
            endpoint=inert+0x1d740000;
            Require(VirtualAllocEx(process,reinterpret_cast<void*>(endpoint),0xb000,MEM_COMMIT,PAGE_EXECUTE_READ)!=nullptr,
                "Cannot commit owned endpoint storage.");
            for(std::size_t i=0;i<1353;++i)extra.push_back({endpoint+i*16,{0,0},{0x90,0x90}});
            if(scenario==L"integrity-short")extra.pop_back();
            if(scenario==L"overlap")extra.front()=native.front();
            if(scenario==L"original")extra.front().original[0]=1;
            if(scenario==L"frame")extra.front().address=receipt.job.frames.front();
            }
            edits.insert(edits.end(),extra.begin(),extra.end());before=Bytes(process,edits);
            for(const auto& edit:edits){MEMORY_BASIC_INFORMATION memory{};
                Require(VirtualQueryEx(process,reinterpret_cast<void*>(edit.address),&memory,sizeof(memory))==sizeof(memory),
                    "Cannot record owned protection.");protections.push_back(memory.Protect);}
            if(scenario==L"partial-write") {
                // A discarded page after pre-admission is injected through the publication observer below.
                bo3::integrity_startup::SetOwnedBeforeApply([&](HANDLE stopped){
                    Require(VirtualFreeEx(stopped,reinterpret_cast<void*>(endpoint),4096,MEM_DECOMMIT)!=FALSE,
                        "Cannot inject the owned partial-write failure.");});
            }
            return extra;
        });
        using bo3::job_startup::Failure;
        bo3::job_startup::SetOwnedFailure((scenario==L"rollback" || scenario==L"rollback-failed" || scenario==L"module-rollback")?Failure::AfterApply:
            scenario==L"thaw"?Failure::Thaw:scenario==L"release"?Failure::Release:Failure::None);
        bo3::job_startup::SetOwnedObserver([&](HANDLE process,bool rollback) {
            if(rollback && scenario==L"partial-write") {
                restored=Bytes(process,std::vector(edits.begin(),edits.begin()+42));return;
            }
            auto bytes=Bytes(process,edits);if(rollback)restored=std::move(bytes);else applied=std::move(bytes);
            if(moduleCase)for(const auto& record:bo3::code_integrity::kRecords)
                if(record.family==bo3::code_integrity::Family::InputTransform) {
                    const auto original=bo3::code_integrity::Original(record.family);
                    Require(vm_startup::ReadStopped(process,integrityImage+record.rva,original.size())
                        ==std::vector<unsigned char>(original.begin(),original.end()),"A retained authored transform changed.");
                }
            protectionsMatch=true;
            for(std::size_t i=0;i<edits.size();++i){MEMORY_BASIC_INFORMATION memory{};
                protectionsMatch=protectionsMatch && VirtualQueryEx(process,reinterpret_cast<void*>(edits[i].address),&memory,sizeof(memory))
                    ==sizeof(memory) && memory.Protect==protections[i];}
            if(!rollback && scenario==L"rollback-failed")Require(VirtualFreeEx(process,reinterpret_cast<void*>(endpoint),4096,MEM_DECOMMIT),
                "Cannot inject the owned rollback failure.");
        });
        bool refused=false;
        try {bo3::integrity_startup::Coordinate(child,job,gate,prepare,{},receipt);}
        catch(const std::exception& error){refused=true;std::cerr<<error.what()<<'\n';}
        Require(WaitForSingleObject(child.process.hProcess,5000)==WAIT_OBJECT_0,"The owned child did not exit.");
        DWORD exit{};Require(GetExitCodeProcess(child.process.hProcess,&exit),"Cannot read the owned exit.");
        const auto& r=receipt.job;const bool success=scenario==L"success" || scenario==L"module-success";
        std::vector<unsigned char> replacements;
        for(const auto& edit:edits)replacements.insert(replacements.end(),edit.replacement.begin(),edit.replacement.end());
        bool passed=success ? !refused && exit==0 && r.committed && r.thawed && r.released && protectionsMatch
            && r.patch.editsWritten==1395 && receipt.integrityAdmitted && applied==replacements
            : refused && r.terminated && !r.released && exit==97;
        if(scenario==L"rollback" || scenario==L"module-rollback")
            passed=passed && r.patch.rollbackCompleted && r.relayFreed && restored==before && protectionsMatch;
        else if(scenario==L"rollback-failed")passed=passed && !r.patch.rollbackCompleted && r.relayFreed && !r.thawed;
        else if(scenario==L"partial-write") {
            std::size_t nativeBytes=0;for(std::size_t i=0;i<42;++i)nativeBytes+=edits[i].original.size();
            passed=passed && r.patch.editsWritten==42 && !r.thawed && r.relayFreed
                && restored==std::vector(before.begin(),before.begin()+nativeBytes);
        }
        else if(!success && scenario!=L"thaw" && scenario!=L"release")passed=passed && r.patch.editsWritten==0 && !r.committed;
        if(scenario==L"native-short" || scenario==L"extra-thread" || scenario==L"freeze-pending")passed=passed && !integrityCalled;
        if(scenario==L"thaw" || scenario==L"release")passed=passed && r.committed && !r.patch.rollbackCompleted;
        if(!before.empty())Save(output.wstring()+L".before.bin",before);
        if(!applied.empty())Save(output.wstring()+L".applied.bin",applied);
        if(!restored.empty())Save(output.wstring()+L".restored.bin",restored);
        report.Write(receipt);std::ofstream proof(output);
        proof<<"{\"passed\":"<<(passed?"true":"false")<<",\"integrityPlannerCalled\":"<<(integrityCalled?"true":"false")
            <<",\"realOwnedModuleUsed\":"<<(moduleCase?"true":"false")
            <<",\"protectionsPreserved\":"<<(protectionsMatch?"true":"false")<<",\"receipt\":";
        bo3::integrity_startup::WriteReceipt(proof,receipt);
        proof<<",\"scope\":\"Owned full native guards and inert integrity endpoints. No game execution.\"}";
        Require(proof.good(),"Cannot save owned integrity evidence.");return passed?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
