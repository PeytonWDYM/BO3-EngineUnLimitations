#include "PassiveControl.h"
#include "PrivateReceipt.h"
#include "../enhanced/LaunchLease.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include <Psapi.h>
#include <array>
#include <iostream>

namespace {
struct Locks {std::vector<HANDLE> values;~Locks(){for(const auto value:values)CloseHandle(value);}};
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc>=2,"Use BO3-Late-Passive-Control.exe <BlackOps3.exe> [game arguments].");
        bo3::enhanced::LaunchLease lease;const auto game=std::filesystem::canonical(argv[1]);
        std::array<wchar_t,32768> own{};
        const auto length=GetModuleFileNameW(nullptr,own.data(),static_cast<DWORD>(own.size()));
        Require(length && length<own.size(),"Cannot locate the fixed passive control.");
        const auto directory=std::filesystem::path(own.data()).parent_path();
        const auto helperFile=std::filesystem::canonical(directory/L"Bo3EnhancedHelper.dll");
        const auto gateFile=std::filesystem::canonical(directory/L"Bo3StartupGate.dll");
        Locks locks;locks.values.reserve(3);
        VerifyFile(game,kGameHash,locks.values);VerifyFile(helperFile,kHelperHash,locks.values);VerifyFile(gateFile,kGateHash,locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);bo3::late_startup::MappedGate gate(gateFile);
        auto command=bo3::late_startup::QuoteArgument(game.wstring());
        for(int i=2;i<argc;++i)command+=L" "+bo3::late_startup::QuoteArgument(argv[i]);
        const std::array<std::filesystem::path,2> helpers{helperFile,gateFile};
        bo3::late_startup::OwnedChild child(game,std::move(command),helpers);
        bo3::late_startup::PrivateReceipt report(child);bo3::late_startup::ControlReceipt receipt;
        const auto image=[](HANDLE process) {
            std::array<HMODULE,2048> modules{};DWORD bytes{};
            Require(K32EnumProcessModulesEx(process,modules.data(),sizeof(modules),&bytes,LIST_MODULES_64BIT)
                && bytes>=sizeof(HMODULE) && bytes<=sizeof(modules) && bytes%sizeof(HMODULE)==0,
                "Cannot identify the owned passive main image.");
            return reinterpret_cast<std::uintptr_t>(modules[0]);
        };
        try {
            bo3::late_startup::CoordinatePassiveControl(child,gate,helper,helperFile,image,receipt);report.Write(receipt);
            std::wcout<<L"Passive stock control released after sequential checks. Receipt: "<<report.Path().wstring()<<L'\n';
            bo3::late_startup::ObserveControl(child,receipt);report.Write(receipt);
        }catch(...) {report.Write(receipt);throw;}
        return static_cast<int>(receipt.observedExitCode);
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
