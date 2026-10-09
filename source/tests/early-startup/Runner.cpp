#include "../../launch/early_startup/Coordinator.h"
#include "../../launch/late_startup/FixedPlan.h"
#include "../../launch/late_startup/PrivateReceipt.h"
#include "../../launch/preentry/Identity.h"
#include "../job-startup/SerialLoader.h"
#include "../early-integrity/Fixture.h"
#include "BuildIdentity.h"
#include "TargetExports.h"
#include "EarlyIntegrityProfile.h"
#include <Psapi.h>
#include <array>
#include <algorithm>
#include <fstream>
#include <iostream>

namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto handle:values)CloseHandle(handle);}};
struct Observation {
    std::uintptr_t address{};
    std::size_t size{};
    bool checksumCalled=false,arenaDestroyed=false,removedUnderFreeze=false,retainedUnderFreeze=false;
};
std::vector<unsigned char> Bytes(HANDLE process,const std::vector<vm_startup::AddressEdit>& edits) {
    std::vector<unsigned char> result;
    for(const auto& edit:edits){const auto bytes=vm_startup::ReadStopped(process,edit.address,edit.original.size());
        result.insert(result.end(),bytes.begin(),bytes.end());}
    return result;
}
void Save(const std::filesystem::path& file,const std::vector<unsigned char>& bytes) {
    std::ofstream out(file,std::ios::binary);out.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
    Require(out.good(),"Cannot save owned publication bytes.");
}
std::uintptr_t ModuleBase(HANDLE process,const std::filesystem::path& file) {
    std::array<HMODULE,256> modules{};DWORD bytes{};
    Require(K32EnumProcessModulesEx(process,modules.data(),sizeof(modules),&bytes,LIST_MODULES_64BIT) && bytes<=sizeof(modules),
        "Cannot inspect the owned module inventory.");
    for(std::size_t i=0;i<bytes/sizeof(HMODULE);++i) {
        std::array<wchar_t,32768> path{};
        Require(K32GetModuleFileNameExW(process,modules[i],path.data(),static_cast<DWORD>(path.size())),"Cannot identify an owned module.");
        if(std::filesystem::path(path.data())==file)return reinterpret_cast<std::uintptr_t>(modules[i]);
    }
    throw std::runtime_error("The inert checksum image is missing.");
}
std::uintptr_t SeedNative(HANDLE process,const std::filesystem::path& file) {
    constexpr SIZE_T size=0x1d74b000;
    const auto image=reinterpret_cast<std::uintptr_t>(VirtualAllocEx(process,nullptr,size,MEM_RESERVE,PAGE_READWRITE));
    Require(image!=0,"Cannot reserve the owned native image.");
    std::ifstream input(file,std::ios::binary);std::uint32_t count{};input.read(reinterpret_cast<char*>(&count),4);
    Require(input.good() && count<=200,"Invalid owned native seed count.");
    for(std::uint32_t i=0;i<count;++i) {
        std::uint32_t rva{},length{};input.read(reinterpret_cast<char*>(&rva),4);input.read(reinterpret_cast<char*>(&length),4);
        Require(input.good() && length && length<=size && rva<=size-length,"Invalid owned native seed range.");
        const auto start=(image+rva)&~std::uintptr_t{4095},end=(image+rva+length+4095)&~std::uintptr_t{4095};
        Require(VirtualAllocEx(process,reinterpret_cast<void*>(start),end-start,MEM_COMMIT,PAGE_READWRITE),"Cannot commit the native seed.");
        std::vector<unsigned char> bytes(length);input.read(reinterpret_cast<char*>(bytes.data()),length);SIZE_T written{};
        Require(input.good() && WriteProcessMemory(process,reinterpret_cast<void*>(image+rva),bytes.data(),length,&written)
            && written==length,"Cannot populate the owned native seed.");
    }
    Require(input.peek()==std::char_traits<char>::eof(),"The native seed has trailing bytes.");
    return image;
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use an owned startup case and a new private output path.");
        const std::wstring scenario=argv[1];const auto output=PrivateOutput(argv[2]);
        const std::array cases{L"success",L"native-short",L"checksum-short",L"identity",L"context",L"original",L"overlap",L"frame",L"rollback",L"thaw",L"release"};
        Require(std::find(cases.begin(),cases.end(),scenario)!=cases.end(),"Unknown early startup case.");
        wchar_t own[32768]{};Require(GetModuleFileNameW(nullptr,own,32768),"Cannot locate the owned startup fixture.");
        const auto directory=std::filesystem::path(own).parent_path();
        const auto target=directory/L"VmStartupControlTarget.exe",helperFile=directory/L"Bo3EnhancedHelper.dll",
            gateFile=directory/L"Bo3StartupGate.dll",checksumFile=directory/L"EarlyIntegrityOwnedImage.dll";
        Locks locks;VerifyFile(target,kOwnedTargetHash,locks.values);VerifyFile(helperFile,kHelperHash,locks.values);
        VerifyFile(gateFile,kGateHash,locks.values);VerifyFile(directory/L"seed.bin",kSeedHash,locks.values);
        VerifyFile(checksumFile,kOwnedChecksumImageHash,locks.values);
        VerifyFile(L"C:\\Windows\\System32\\ntdll.dll","a74f7482085eab125ccc09152ab7e0b5994bcb13e1a7b29880bdbb24179ecb8b",locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);bo3::late_startup::MappedGate gate(gateFile);
        const auto command=bo3::late_startup::QuoteArgument(target.wstring())+L" success "+
            bo3::late_startup::QuoteArgument((directory/L"seed.bin").wstring())+L" "+
            bo3::late_startup::QuoteArgument(output.wstring()+L".target.json");
        const std::array<std::filesystem::path,3> helpers{helperFile,gateFile,checksumFile};
        bo3::job_startup::OwnedJob job;bo3::late_startup::OwnedChild child(target,command,helpers);job.Assign(child);
        ConfigureOwnedSerialLoader(child);bo3::early_startup::Receipt receipt;Observation observed;
        std::vector<vm_startup::AddressEdit> edits;
        std::vector<unsigned char> before,applied,restored;std::vector<DWORD> protections;bool protectionsMatch=false;
        const auto prepare=[&](HANDLE process,std::uintptr_t image,vm_startup::Receipt&) {
            const auto inert=SeedNative(process,directory/L"seed.bin");SIZE_T written{};
            Require(WriteProcessMemory(process,reinterpret_cast<void*>(image+kOwnedImageRva),&inert,8,&written) && written==8,
                "Cannot bind the owned native image.");
            auto plan=bo3::late_startup::PrepareFixedPlan(process,inert,helper,helperFile);
            edits=plan.edits;if(scenario==L"native-short")plan.edits.pop_back();return plan;
        };
        bo3::early_startup::SetOwnedPrepareChecksum([&](HANDLE process,std::uintptr_t,
            const std::array<unsigned char,32>&,std::span<const vm_startup::AddressEdit> native) {
            observed.checksumCalled=true;
            Require(native.size()==42,"The checksum planner did not receive the complete native recipe.");
            auto digest=bo3::early_integrity::kExecutableDigest;if(scenario==L"identity")digest[0]^=1;
            const auto checksumImage=ModuleBase(process,checksumFile);
            if(scenario==L"context") {
                const auto address=checksumImage+bo3::early_integrity::kGuards.front().rva;
                auto byte=vm_startup::ReadStopped(process,address,1);byte.front()^=1;SIZE_T written{};
                Require(WriteProcessMemory(process,reinterpret_cast<void*>(address),byte.data(),1,&written) && written==1,
                    "Cannot seed the owned context mismatch.");
            }
            SeedFixtureProtection(process,checksumImage);
            auto checksum=bo3::early_integrity::PrepareStopped(process,checksumImage,digest,native);
            observed.address=checksum.arena->address();observed.size=checksum.arena->size();
            const auto pointer=checksum.arena.get();
            checksum.arena=std::shared_ptr<bo3::early_integrity::RelayArena>(pointer,
                [&,owner=std::move(checksum.arena),process](bo3::early_integrity::RelayArena*) mutable noexcept {
                    owner.reset();observed.arenaDestroyed=true;MEMORY_BASIC_INFORMATION memory{};
                    const bool frozen=receipt.job.frozen && !receipt.job.thawed && WaitForSingleObject(process,0)==WAIT_TIMEOUT;
                    if(VirtualQueryEx(process,reinterpret_cast<void*>(observed.address),&memory,sizeof(memory))==sizeof(memory)) {
                        observed.removedUnderFreeze=frozen && memory.State==MEM_FREE;
                        observed.retainedUnderFreeze=frozen && memory.State==MEM_COMMIT;
                    }
                });
            if(scenario==L"checksum-short")checksum.edits.pop_back();
            if(scenario==L"original")checksum.edits.front().original[0]^=1;
            if(scenario==L"overlap")checksum.edits.front()=native.front();
            if(scenario==L"frame") {
                const auto frame=receipt.job.frames.front();
                checksum.edits.front()={frame,vm_startup::ReadStopped(process,frame,1),{0x90}};
            }
            edits.insert(edits.end(),checksum.edits.begin(),checksum.edits.end());
            before=Bytes(process,edits);
            for(const auto& edit:edits){MEMORY_BASIC_INFORMATION memory{};
                Require(VirtualQueryEx(process,reinterpret_cast<void*>(edit.address),&memory,sizeof(memory))==sizeof(memory),
                    "Cannot record publication protection.");protections.push_back(memory.Protect);}
            return checksum;
        });
        using bo3::job_startup::Failure;
        bo3::job_startup::SetOwnedFailure(scenario==L"rollback"?Failure::AfterApply:
            scenario==L"thaw"?Failure::Thaw:scenario==L"release"?Failure::Release:Failure::None);
        bo3::job_startup::SetOwnedObserver([&](HANDLE process,bool rollback) {
            auto bytes=Bytes(process,edits);if(rollback)restored=std::move(bytes);else applied=std::move(bytes);
            protectionsMatch=true;
            for(std::size_t i=0;i<edits.size();++i){MEMORY_BASIC_INFORMATION memory{};
                protectionsMatch=protectionsMatch && VirtualQueryEx(process,reinterpret_cast<void*>(edits[i].address),&memory,sizeof(memory))
                    ==sizeof(memory) && memory.Protect==protections[i];}
        });
        bool refused=false;
        try {bo3::early_startup::Coordinate(child,job,gate,prepare,bo3::early_integrity::kExecutableDigest,receipt);}
        catch(const std::exception& error){refused=true;std::cerr<<error.what()<<'\n';}
        Require(WaitForSingleObject(child.process.hProcess,5000)==WAIT_OBJECT_0,"The owned startup child did not exit.");
        DWORD exit{};Require(GetExitCodeProcess(child.process.hProcess,&exit),"Cannot read the owned exit code.");
        bool passed=scenario==L"success"?!refused && exit==0 && receipt.job.released && receipt.job.committed:
            refused && exit==97 && receipt.job.terminated && !receipt.job.released;
        if(scenario==L"native-short")passed=passed && !observed.checksumCalled && receipt.job.patch.editsWritten==0;
        else if(scenario==L"identity" || scenario==L"context")passed=passed && observed.checksumCalled && !observed.address && receipt.job.patch.editsWritten==0;
        else passed=passed && observed.arenaDestroyed;
        if(scenario==L"success" || scenario==L"thaw" || scenario==L"release")passed=passed && protectionsMatch
            && observed.retainedUnderFreeze && !observed.removedUnderFreeze
            && receipt.job.patch.editsWritten==42+bo3::early_integrity::kPublicationCount;
        if(scenario==L"rollback")passed=passed && receipt.job.patch.rollbackCompleted && before==restored
            && protectionsMatch && observed.removedUnderFreeze;
        if(scenario==L"checksum-short" || scenario==L"original" || scenario==L"overlap" || scenario==L"frame")
            passed=passed && receipt.job.patch.editsWritten==0 && observed.removedUnderFreeze;
        if(scenario==L"context") {
            Require(!receipt.checksumCapture.empty() && receipt.job.refusalReason.size()<=512,"The context refusal lost its capture.");
            bo3::late_startup::PrivateReceipt privateReport(output.parent_path(),child);privateReport.Write(receipt);
            auto captured=privateReport.Path();captured.replace_extension(L".checksum-guards.bin");
            std::ifstream input(captured,std::ios::binary);std::vector<unsigned char> saved(receipt.checksumCapture.size());
            input.read(reinterpret_cast<char*>(saved.data()),static_cast<std::streamsize>(saved.size()));
            Require(input.good() && saved==receipt.checksumCapture,"The private frozen capture was not preserved.");
        }
        Save(output.wstring()+L".before.bin",before);Save(output.wstring()+L".applied.bin",applied);Save(output.wstring()+L".restored.bin",restored);
        std::ofstream proof(output);proof<<"{\"passed\":"<<(passed?"true":"false")
            <<",\"arenaRemovedUnderFreeze\":"<<(observed.removedUnderFreeze?"true":"false")
            <<",\"arenaRetainedUnderFreeze\":"<<(observed.retainedUnderFreeze?"true":"false")
            <<",\"protectionsMatch\":"<<(protectionsMatch?"true":"false")<<",\"receipt\":";
        bo3::early_startup::WriteReceipt(proof,receipt);
        proof<<",\"scope\":\"Complete native42 plus real checksum planner in owned inert images. No game execution.\"}";
        Require(proof.good(),"Cannot save the owned startup receipt.");return passed?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
