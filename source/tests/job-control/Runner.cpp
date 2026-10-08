#include "../../launch/job_control/Lifetime.h"
#include "../../launch/preentry/Identity.h"
#include "../../launch/job_startup/RuntimeUnwind.h"
#include "../../launch/job_startup/PrimaryAdmission.h"
#include "../job-startup/SerialLoader.h"
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
        Require(scenario==L"success" || scenario==L"changed" || scenario==L"trace-collision" || scenario==L"trace-cap"
            || scenario==L"guard" || scenario==L"allocated" || scenario==L"helper" || scenario==L"extra-thread"
            || scenario==L"membership" || scenario==L"freeze-pending" || scenario==L"thaw" || scenario==L"release"
            || scenario==L"early-exit","Unknown owned stock job case.");
        wchar_t own[32768]{};Require(GetModuleFileNameW(nullptr,own,32768)!=0,"Cannot locate the owned control.");
        const auto directory=std::filesystem::path(own).parent_path();
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
        if(scenario==L"freeze-pending")job.SetOwnedFreezeStatus(0x103);
        bo3::late_startup::PrivateReceipt report(directory,child);bo3::job_control::Receipt receipt;
        std::unique_ptr<bo3::late_startup::OwnedChild> member;
        bo3::job_control::SetOwnedSetup([&](HANDLE process,std::uintptr_t image) {
            const auto inert=Seed(process,directory/L"seed.bin");SIZE_T written{};
            const auto write=[&](std::uintptr_t address,const void* data,SIZE_T size) {
                Require(WriteProcessMemory(process,reinterpret_cast<void*>(address),data,size,&written) && written==size,"Owned setup write failed.");
            };
            write(image+kOwnedImageRva,&inert,8);
            // Fixture observation ranges only. They do not satisfy or alter any required guard.
            for(const auto rva:{0x22b9b50u,0x1cb94212u,0x4c98c80u,0x22b1559u,0x227a3a0u}) {
                Require(VirtualAllocEx(process,reinterpret_cast<void*>((inert+rva)&~std::uintptr_t{4095}),4096,MEM_COMMIT,PAGE_READWRITE)!=nullptr,
                    "Cannot commit an owned optional observation range.");
            }
            const unsigned char stub[]{0xe9,0xbd,0xa6,0x8d,0x1a};write(inert+0x22b9b50,stub,sizeof(stub));
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
        using bo3::job_control::Failure;
        bo3::job_control::SetOwnedFailure(scenario==L"thaw"?Failure::Thaw:scenario==L"release"?Failure::Release:Failure::None);
        bo3::job_control::Admitted admitted;bool refused=false,unchanged=false,capStopped=false;
        try {admitted=bo3::job_control::Coordinate(child,job,gate,helper,helperFile,receipt);}
        catch(const std::exception& error){refused=true;std::cerr<<error.what()<<'\n';}
        const bool success=scenario==L"success" || scenario==L"changed" || scenario==L"trace-collision" || scenario==L"trace-cap";
        if(!refused) {
            bo3::job_control::VerifyOriginals(child.process.hProcess,admitted.originals);unchanged=true;
            if(scenario==L"trace-collision") {std::ofstream sentinel(report.Path().wstring()+L".observations.jsonl");sentinel<<"preserved";}
            if(scenario==L"trace-cap") {
                bo3::job_control::Trace trace(report.Path().wstring()+L".cap");auto sample=admitted.frozen;
                const auto large=std::find_if(sample.rows.begin(),sample.rows.end(),[](const auto& row){return row.bytes.size()==7941;});
                // The fixture has an optional gap here: bounded synthetic observation data exercises only log capacity.
                if(large==sample.rows.end())sample.rows.front().bytes.assign(7941,0);
                for(unsigned int i=0;i<700;++i){sample.rows.front().bytes[5]=static_cast<unsigned char>(i);trace.Append(sample,receipt);}
                const auto before=std::filesystem::file_size(report.Path().wstring()+L".cap.observations.jsonl");
                trace.Append(sample,receipt);capStopped=receipt.traceTruncated && before==std::filesystem::file_size(report.Path().wstring()+L".cap.observations.jsonl");
            }
            bo3::job_control::Retain(child,job,admitted,report,receipt);
        }else report.Write(receipt);
        bool passed=success ? !refused && receipt.exited && receipt.exitCode==0 && receipt.native.primaryAdmitted
            && receipt.native.thawed && receipt.native.released && receipt.originalsObserved==40 && unchanged
            : refused && receipt.exited && !receipt.native.released;
        if(scenario==L"early-exit")passed=passed && receipt.exitCode==15 && !receipt.native.terminated;
        else if(!success)passed=passed && receipt.exitCode==97 && receipt.native.terminated;
        if(scenario==L"trace-collision")passed=passed && receipt.traceFailed;
        if(scenario==L"trace-cap")passed=passed && capStopped;
        if(scenario==L"freeze-pending")passed=passed && receipt.native.freezeStatus==0x103 && !receipt.native.frozen;
        if(scenario==L"membership")passed=passed && member && member->Exited();
        std::ofstream out(output);out<<"{\"passed\":"<<(passed?"true":"false")<<",\"originalsUnchanged\":"<<(unchanged?"true":"false")
            <<",\"traceCapStopped\":"<<(capStopped?"true":"false")<<",\"receiptPath\":\"";
        for(const auto c:report.Path().string()){if(c=='\\')out<<'\\';out<<c;}
        out<<"\",\"receipt\":";bo3::job_control::WriteReceipt(out,receipt);out<<'}';
        Require(out.good(),"Cannot save owned stock proof.");return passed?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
