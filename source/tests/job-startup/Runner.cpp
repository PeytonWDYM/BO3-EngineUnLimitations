#include "../../launch/job_startup/Coordinator.h"
#include "../../launch/late_startup/FixedPlan.h"
#include "../../launch/late_startup/PrivateReceipt.h"
#include "../../launch/preentry/Identity.h"
#include "BuildIdentity.h"
#include "TargetExports.h"
#include "SerialLoader.h"
#include "ParentDeath.h"
#include "../../launch/job_startup/RuntimeUnwind.h"
#include "RuntimeUnwindProfile.h"
#include <array>
#include <fstream>
#include <iostream>
#include <cstring>
#include <algorithm>

namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto handle:values)CloseHandle(handle);}};
std::vector<unsigned char> Bytes(HANDLE process,const std::vector<vm_startup::AddressEdit>& edits) {
    std::vector<unsigned char> out;
    for(const auto& edit:edits){const auto bytes=vm_startup::ReadStopped(process,edit.address,edit.original.size());
        out.insert(out.end(),bytes.begin(),bytes.end());}
    return out;
}
void Save(const std::filesystem::path& file,const std::vector<unsigned char>& bytes) {
    std::ofstream out(file,std::ios::binary);out.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
    Require(out.good(),"Cannot save owned publication bytes.");
}
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
        Require(argc==3,"Use an owned case and new private output path.");
        const std::wstring scenario=argv[1];const auto output=PrivateOutput(argv[2]);
        Require(scenario==L"success" || scenario==L"guard" || scenario==L"allocated" || scenario==L"rollback"
            || scenario==L"rollback-failed" || scenario==L"parent-death" || scenario==L"death-child"
            || scenario==L"freeze-pending" || scenario==L"deadline"
            || scenario==L"thaw" || scenario==L"release" || scenario==L"state" || scenario==L"membership"
            || scenario==L"extra-thread" || scenario==L"helper" || scenario==L"runtime-rva" || scenario==L"runtime-row"
            || scenario==L"runtime-bytes" || scenario==L"runtime-call" || scenario==L"runtime-missing"
            || scenario==L"runtime-identity","Unknown owned job case.");
        wchar_t own[32768]{};Require(GetModuleFileNameW(nullptr,own,32768)!=0,"Cannot locate owned job fixture.");
        const auto directory=std::filesystem::path(own).parent_path();
        if(scenario==L"parent-death")return VerifyOwnedParentDeath(own,output);
        const auto target=directory/L"VmStartupControlTarget.exe",helperFile=directory/L"Bo3EnhancedHelper.dll",gateFile=directory/L"Bo3StartupGate.dll";
        Locks locks;locks.values.reserve(5);
        VerifyFile(target,kOwnedTargetHash,locks.values);VerifyFile(helperFile,kHelperHash,locks.values);
        VerifyFile(gateFile,kGateHash,locks.values);VerifyFile(directory/L"seed.bin",kSeedHash,locks.values);
        VerifyFile(L"C:\\Windows\\System32\\ntdll.dll","a74f7482085eab125ccc09152ab7e0b5994bcb13e1a7b29880bdbb24179ecb8b",locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);bo3::late_startup::MappedGate gate(gateFile);
        const auto command=bo3::late_startup::QuoteArgument(target.wstring())+L" "+scenario+L" "+
            bo3::late_startup::QuoteArgument((directory/L"seed.bin").wstring())+L" "+bo3::late_startup::QuoteArgument(output.wstring()+L".target.json");
        const std::array<std::filesystem::path,2> helpers{helperFile,gateFile};
        bo3::job_startup::OwnedJob job;bo3::late_startup::OwnedChild child(target,command,helpers);job.Assign(child);
        ConfigureOwnedSerialLoader(child);
        if(scenario==L"freeze-pending")job.SetOwnedFreezeStatus(0x103);
        bo3::late_startup::PrivateReceipt report(directory,child);bo3::job_startup::Receipt receipt;
        bo3::job_startup::SetOwnedRuntimeGuardAbsent(scenario==L"runtime-missing");
        bo3::job_startup::SetOwnedPrimarySetup([&](HANDLE process,std::uintptr_t image) {
            std::uintptr_t address{};std::vector<unsigned char> bytes;
            const auto& guard=kRuntimeUnwind[0];
            if(scenario==L"runtime-rva" || scenario==L"runtime-row") {
                auto function=guard.function;
                if(scenario==L"runtime-rva")function.UnwindData+=4;else --function.EndAddress;
                address=image+guard.tableRva;
                const auto* data=reinterpret_cast<const unsigned char*>(&function);bytes.assign(data,data+sizeof(function));
            }else if(scenario==L"runtime-bytes" || scenario==L"runtime-call") {
                address=image+(scenario==L"runtime-bytes"?guard.function.UnwindData:guard.function.BeginAddress);
                bytes=vm_startup::ReadStopped(process,address,1);bytes[0]^=1;
            }else if(scenario==L"runtime-identity") {
                const auto offset=vm_startup::ReadStopped(process,image+60,4);DWORD pe{};std::memcpy(&pe,offset.data(),4);
                address=image+pe+8;bytes=vm_startup::ReadStopped(process,address,4);bytes[0]^=1;
            }
            if(!address)return;
            DWORD prior{},discarded{};SIZE_T written{};
            Require(VirtualProtectEx(process,reinterpret_cast<void*>(address),bytes.size(),PAGE_READWRITE,&prior)
                && WriteProcessMemory(process,reinterpret_cast<void*>(address),bytes.data(),bytes.size(),&written)
                && written==bytes.size() && VirtualProtectEx(process,reinterpret_cast<void*>(address),bytes.size(),prior,&discarded),
                "Cannot inject the owned runtime metadata refusal.");
        });
        std::vector<vm_startup::AddressEdit> edits;std::vector<unsigned char> before,applied,restored;
        std::vector<DWORD> protections;bool protectionMatch=false;
        std::uintptr_t inertImage{};
        std::unique_ptr<bo3::late_startup::OwnedChild> member;
        const auto prepare=[&](HANDLE process,std::uintptr_t image,vm_startup::Receipt&) {
            const auto inert=Seed(process,directory/L"seed.bin");SIZE_T written{};
            inertImage=inert;
            Require(WriteProcessMemory(process,reinterpret_cast<void*>(image+kOwnedImageRva),&inert,8,&written) && written==8,
                "Cannot bind the owned inert image.");
            if(scenario==L"guard") {
                auto bytes=vm_startup::ReadStopped(process,inert+0x12dba10,1);bytes[0]^=1;
                Require(WriteProcessMemory(process,reinterpret_cast<void*>(inert+0x12dba10),bytes.data(),1,&written) && written==1,
                    "Cannot inject the owned guard refusal.");
            }
            if(scenario==L"allocated") {
                const std::uintptr_t allocated=1;
                Require(WriteProcessMemory(process,reinterpret_cast<void*>(inert+0x5124580),&allocated,8,&written) && written==8,
                    "Cannot inject the owned storage refusal.");
            }
            if(scenario==L"helper") {
                helper.Admit(process,helperFile);
                const auto address=helper.image.base+helper.state.readState;DWORD prior{},discarded{};const unsigned char wrong=0;
                Require(VirtualProtectEx(process,reinterpret_cast<void*>(address),1,PAGE_READWRITE,&prior)
                    && WriteProcessMemory(process,reinterpret_cast<void*>(address),&wrong,1,&written) && written==1
                    && VirtualProtectEx(process,reinterpret_cast<void*>(address),1,prior,&discarded),"Cannot inject helper identity refusal.");
            }
            auto plan=bo3::late_startup::PrepareFixedPlan(process,inert,helper,helperFile);
            if(scenario==L"deadline")Sleep(30001);
            edits=plan.edits;before=Bytes(process,edits);
            if(scenario==L"state") {
                const auto mapped=LoadLibraryExW(gateFile.c_str(),nullptr,DONT_RESOLVE_DLL_REFERENCES);
                Require(mapped!=nullptr,"Cannot inspect owned state offset.");
                const auto offset=reinterpret_cast<std::uintptr_t>(GetProcAddress(mapped,"Bo3StartupGateState"))
                    -reinterpret_cast<std::uintptr_t>(mapped);FreeLibrary(mapped);
                const auto wrong=child.payload.nonce[0]^1ull;
                Require(WriteProcessMemory(process,reinterpret_cast<void*>(gate.Base()+offset+32),&wrong,8,&written) && written==8,
                    "Cannot inject the owned gate nonce refusal.");
            }
            if(scenario==L"death-child")DieAfterPartialWrite(child,output,edits);
            if(scenario==L"membership") {
                member=std::make_unique<bo3::late_startup::OwnedChild>(target,command,helpers);
                job.AddOwnedMember(member->process.hProcess);
            }
            for(const auto& edit:edits){MEMORY_BASIC_INFORMATION info{};
                Require(VirtualQueryEx(process,reinterpret_cast<void*>(edit.address),&info,sizeof(info))==sizeof(info),"Cannot save protections.");
                protections.push_back(info.Protect);}
            return plan;
        };
        using bo3::job_startup::Failure;
        bo3::job_startup::SetOwnedFailure((scenario==L"rollback" || scenario==L"rollback-failed")?Failure::AfterApply:scenario==L"thaw"?Failure::Thaw:
            scenario==L"release"?Failure::Release:Failure::None);
        bo3::job_startup::SetOwnedObserver([&](HANDLE process,bool rollback) {
            auto actual=Bytes(process,edits);if(rollback)restored=std::move(actual);else applied=std::move(actual);
            protectionMatch=true;
            for(std::size_t i=0;i<edits.size();++i){MEMORY_BASIC_INFORMATION info{};
                protectionMatch=protectionMatch && VirtualQueryEx(process,reinterpret_cast<void*>(edits[i].address),&info,sizeof(info))==sizeof(info)
                    && info.Protect==protections[i];}
            if(!rollback && scenario==L"rollback-failed") {
                const auto edit=std::find_if(edits.begin(),edits.end(),[&](const auto& row){return row.address>=inertImage
                    && row.address<inertImage+494186496;});
                Require(edit!=edits.end(),"The owned native code edit is missing.");
                const auto page=edit->address&~std::uintptr_t{4095};
                Require(VirtualFreeEx(process,reinterpret_cast<void*>(page),4096,MEM_DECOMMIT)!=FALSE,
                    "Cannot inject the owned failed rollback.");
            }
        });
        bool refused=false;
        try {bo3::job_startup::Coordinate(child,job,gate,prepare,receipt);}
        catch(const std::exception& error){refused=true;std::cerr<<error.what()<<'\n';}
        Require(WaitForSingleObject(child.process.hProcess,5000)==WAIT_OBJECT_0,"Owned job child did not exit.");
        DWORD exit{};Require(GetExitCodeProcess(child.process.hProcess,&exit)!=FALSE,"Cannot read owned job exit.");
        const bool success=scenario==L"success";
        bool passed=success ? !refused && exit==0 && receipt.committed && receipt.thawed && receipt.released
            && receipt.primaryAdmitted && receipt.threadsObserved==1 && receipt.patch.editsWritten==42 && protectionMatch
            : refused && receipt.terminated && !receipt.released && exit==97;
        if(scenario==L"guard" || scenario==L"allocated" || scenario==L"membership" || scenario==L"extra-thread" || scenario==L"state" || scenario==L"helper"
            || scenario==L"freeze-pending" || scenario==L"deadline")
            passed=passed && !receipt.committed && receipt.patch.editsWritten==0;
        if(scenario==L"rollback")passed=passed && receipt.patch.rollbackCompleted && receipt.relayFreed && restored==before && protectionMatch;
        if(scenario==L"rollback-failed")passed=passed && !receipt.patch.rollbackCompleted && receipt.relayFreed
            && receipt.patch.editsWritten==42 && !receipt.thawed;
        if(scenario==L"membership")passed=passed && member && member->Exited() && receipt.relayFreed;
        if(scenario==L"freeze-pending")passed=passed && receipt.freezeStatus==0x103 && !receipt.frozen;
        if(scenario==L"deadline")passed=passed && receipt.frozen && receipt.relayFreed && !receipt.thawed;
        if(scenario==L"state")passed=passed && receipt.relayFreed;
        if(scenario.starts_with(L"runtime-"))passed=passed && receipt.patch.editsWritten==0 && receipt.relay==0
            && !receipt.primaryAdmitted && receipt.stage=="primary-admission" && !receipt.refusalReason.empty();
        if(scenario==L"thaw" || scenario==L"release")passed=passed && receipt.committed && !receipt.patch.rollbackCompleted;
        if(!before.empty())Save(output.wstring()+L".before.bin",before);
        if(!applied.empty())Save(output.wstring()+L".applied.bin",applied);
        if(!restored.empty())Save(output.wstring()+L".restored.bin",restored);
        report.Write(receipt);
        std::ofstream out(output);out<<"{\"passed\":"<<(passed?"true":"false")<<",\"exitCode\":"<<exit
            <<",\"protectionsPreserved\":"<<(protectionMatch?"true":"false")<<",\"receipt\":";
        bo3::job_startup::WriteReceipt(out,receipt);out<<",\"scope\":\"Owned inert image. No game execution.\"}";
        Require(out.good(),"Cannot save owned job proof.");return passed?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
