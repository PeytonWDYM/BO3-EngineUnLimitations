#include "../../launch/late_startup/ControlAdmission.h"
#include "../../launch/late_startup/PrivateReceipt.h"
#include "../../launch/preentry/Identity.h"
#include "BuildIdentity.h"
#include "TargetExports.h"
#include "GameManifest.h"
#include <array>
#include <fstream>
#include <iostream>
#include <cstring>
#include <Psapi.h>

namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto value:values)CloseHandle(value);}};
std::uintptr_t Image(HANDLE process,std::uintptr_t module) {
    const auto raw=vm_startup::ReadStopped(process,module+kOwnedImageRva,8);
    std::uintptr_t image{};std::memcpy(&image,raw.data(),8);return image;
}
std::vector<unsigned char> Snapshot(HANDLE process,std::uintptr_t image) {
    std::vector<unsigned char> result;
    for(const auto& guard:bo3::enhanced::ExactGameManifest.guards) {
        const auto raw=vm_startup::ReadStopped(process,image+guard.rva,guard.size);
        result.insert(result.end(),raw.begin(),raw.end());
    }
    for(const auto rva:{0x22b1559u,0x227a3a0u}) {
        const auto raw=vm_startup::ReadStopped(process,image+rva,rva==0x22b1559u?5:64);
        result.insert(result.end(),raw.begin(),raw.end());
    }
    return result;
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use an owned control case and a new proof path.");
        const std::wstring scenario=argv[1];const auto output=PrivateOutput(argv[2]);
        Require(scenario==L"success" || scenario==L"guard" || scenario==L"allocated" || scenario==L"call"
            || scenario==L"target" || scenario==L"continue" || scenario==L"detach" || scenario==L"early-exit"
            || scenario==L"timeout" || scenario==L"pre-gate-exit","Unknown owned control case.");
        wchar_t own[32768]{};Require(GetModuleFileNameW(nullptr,own,32768)!=0,"Cannot locate the owned control.");
        const auto directory=std::filesystem::path(own).parent_path();
        const auto target=directory/L"VmStartupControlTarget.exe",helperFile=directory/L"Bo3EnhancedHelper.dll",gateFile=directory/L"Bo3StartupGate.dll";
        Locks locks;VerifyFile(target,kOwnedTargetHash,locks.values);VerifyFile(helperFile,kHelperHash,locks.values);
        VerifyFile(gateFile,kGateHash,locks.values);VerifyFile(directory/L"seed.bin",kSeedHash,locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);bo3::late_startup::MappedGate gate(gateFile);
        const auto targetProof=output.wstring()+L".target.json";
        const auto command=bo3::late_startup::QuoteArgument(target.wstring())+L" "+scenario+L" "+
            bo3::late_startup::QuoteArgument((directory/L"seed.bin").wstring())+L" "+bo3::late_startup::QuoteArgument(targetProof);
        const std::array<std::filesystem::path,2> helpers{helperFile,gateFile};
        bo3::late_startup::OwnedChild child(target,command,helpers,1000);
        bo3::late_startup::PrivateReceipt report(directory,child);bo3::late_startup::ControlReceipt receipt;
        std::vector<unsigned char> before,after;bool unchanged=false,refused=false;
        const auto admit=[&](HANDLE process,std::uintptr_t module,bo3::late_startup::ControlReceipt& row) {
            const auto image=Image(process,module);before=Snapshot(process,image);
            try {bo3::late_startup::AdmitStockControl(process,image,helper,helperFile,row);}
            catch(...) {after=Snapshot(process,image);unchanged=before==after;throw;}
            after=Snapshot(process,image);unchanged=before==after;
            bo3::late_startup::VerifyControlBindings(process,helper);
        };
        const auto capture=[&](HANDLE process,bo3::late_startup::ControlReceipt& row) {
            HMODULE module{};DWORD bytes{};
            Require(K32EnumProcessModulesEx(process,&module,sizeof(module),&bytes,LIST_MODULES_64BIT)!=FALSE,"Cannot locate owned image.");
            bo3::late_startup::CaptureControlBeforeAttach(process,Image(process,reinterpret_cast<std::uintptr_t>(module)),row);
        };
        using bo3::late_startup::Failure;
        bo3::late_startup::SetOwnedFailure(scenario==L"continue"?Failure::Continue:scenario==L"detach"?Failure::Detach:Failure::None);
        const auto checkBindings=[&](HANDLE process){bo3::late_startup::VerifyControlBindings(process,helper);};
        try {
            bo3::late_startup::CoordinateControl(child,gate,admit,capture,checkBindings,receipt);
            bo3::late_startup::ObserveControl(child,receipt,1000);
        } catch(const std::exception& error) {refused=true;std::cerr<<error.what()<<'\n';}
        report.Write(receipt);
        Require(child.Exited(),"The owned control child remains active.");
        const bool success=scenario==L"success" || scenario==L"call" || scenario==L"target" || scenario==L"early-exit" || scenario==L"timeout";
        const DWORD expected=scenario==L"early-exit"?17:scenario==L"timeout"?97:0;
        const bool passed=scenario==L"pre-gate-exit" ? refused && !receipt.released && !receipt.terminated
            && receipt.observedExitCode==23 : unchanged && receipt.patch.editsWritten==0 && !receipt.committed
            && (success ? !refused && receipt.admitted && receipt.detached && receipt.debuggerAbsent && receipt.released
                && receipt.bindingsUnchanged && receipt.observedExitCode==expected
                && receipt.observationTimedOut==(scenario==L"timeout")
                && receipt.preAttachCallBytes==receipt.callBytes && receipt.preAttachTargetBytes==receipt.targetBytes
                : refused && !receipt.released && receipt.terminated);
        for(const auto& [name,bytes]:std::array<std::pair<const wchar_t*,const std::vector<unsigned char>*>,2>{{{L".before.bin",&before},{L".after.bin",&after}}}) {
            std::ofstream file(output.wstring()+name,std::ios::binary);file.write(reinterpret_cast<const char*>(bytes->data()),bytes->size());
            Require(file.good(),"Cannot save unchanged owned code bytes.");
        }
        std::ofstream proof(output);proof<<"{\"passed\":"<<(passed?"true":"false")<<",\"scope\":\"Owned fixture only\""
            <<",\"nativeBytesUnchanged\":"<<(before.empty()?"null":unchanged?"true":"false")<<",\"nativeEdits\":0,\"relayAllocations\":0"
            <<",\"refused\":"<<(refused?"true":"false")<<",\"released\":"<<(receipt.released?"true":"false")
            <<",\"receipt\":\""<<report.Path().generic_string()<<"\"}";
        Require(proof.good(),"Cannot persist the owned control proof.");return passed?0:1;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
