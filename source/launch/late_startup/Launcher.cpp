#include "FixedPlan.h"
#include "PrivateReceipt.h"
#include "../enhanced/LaunchLease.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include <array>
#include <iostream>

namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto value:values)CloseHandle(value);}};
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc>=2,"Use BO3-Late-Zombies.exe <BlackOps3.exe> [game arguments].");
        bo3::enhanced::LaunchLease lease;
        const auto game=std::filesystem::canonical(argv[1]);
        std::array<wchar_t,32768> own{};
        const auto length=GetModuleFileNameW(nullptr,own.data(),static_cast<DWORD>(own.size()));
        Require(length && length<own.size(),"Cannot locate the fixed late launcher.");
        const auto directory=std::filesystem::path(own.data()).parent_path();
        const auto helper=std::filesystem::canonical(directory/L"Bo3EnhancedHelper.dll");
        const auto gateFile=std::filesystem::canonical(directory/L"Bo3StartupGate.dll");
        Locks locks;locks.values.reserve(3);
        VerifyFile(game,kGameHash,locks.values);VerifyFile(helper,kHelperHash,locks.values);VerifyFile(gateFile,kGateHash,locks.values);
        bo3::enhanced::MappedHelper native(helper);bo3::late_startup::MappedGate gate(gateFile);
        auto command=bo3::late_startup::QuoteArgument(game.wstring());
        for(int i=2;i<argc;++i)command+=L" "+bo3::late_startup::QuoteArgument(argv[i]);
        const std::array<std::filesystem::path,2> helpers{helper,gateFile};
        bo3::late_startup::OwnedChild child(game,std::move(command),helpers);
        bo3::late_startup::PrivateReceipt report(child);
        bo3::late_startup::Receipt receipt;
        const auto prepare=[&](HANDLE process,std::uintptr_t image,vm_startup::Receipt&) {
            return bo3::late_startup::PrepareFixedPlan(process,image,native,helper);
        };
        try {bo3::late_startup::Coordinate(child,gate,prepare,receipt);report.Write(receipt);}
        catch(...) {report.Write(receipt);throw;}
        std::wcout<<L"Native recipe committed. CRT gate released after detach. Receipt: "<<report.Path().wstring()<<L'\n';
        Require(WaitForSingleObject(child.process.hProcess,INFINITE)==WAIT_OBJECT_0,"Cannot retain the owned game lifetime.");
        DWORD exit{};Require(GetExitCodeProcess(child.process.hProcess,&exit)!=FALSE,"Cannot read the owned game exit code.");
        return static_cast<int>(exit);
    } catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
