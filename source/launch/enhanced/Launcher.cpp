#include "GameManifest.h"
#include "MappedHelper.h"
#include "SessionReceipt.h"
#include "LaunchLease.h"
#include "SteamContext.h"
#include "../../patches/vm_startup/NearRelay.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include <detours.h>
#include <algorithm>
#include <iostream>
#include <memory>

namespace {
using namespace bo3::enhanced;
constexpr std::uint32_t ServerTotal = 500001;
struct Locks {
    std::vector<HANDLE> values;
    ~Locks() { for (HANDLE handle : values) CloseHandle(handle); }
};
struct Child {
    PROCESS_INFORMATION info{};
    bool exited = false;
    ~Child() {
        if (!info.hProcess) return;
        if (!exited) {
            TerminateProcess(info.hProcess, 97);
            DebugActiveProcessStop(info.dwProcessId);
            WaitForSingleObject(info.hProcess, 5000);
        }
        CloseHandle(info.hThread);
        CloseHandle(info.hProcess);
    }
};
struct Launch {
    MappedHelper& helper;
    const std::filesystem::path& helperFile;
    SessionReceipt& report;
    std::unique_ptr<vm_startup::NearRelay> relay;
};
// DebugGate callbacks run synchronously in this one launcher thread.
Launch* active;
std::vector<vm_startup::AddressEdit> Prepare(HANDLE process, const vm_startup::Receipt& receipt) {
    VerifyGameCode(process, receipt.imageBase, ExactGameManifest);
    VerifyMigrationUnallocated(process, receipt.imageBase);
    for (const auto [rva, size] : {std::pair{0x16dbb638u, 8u}, std::pair{0x16dbb640u, 4u}}) {
        const auto bytes = vm_startup::ReadStopped(process, receipt.imageBase + rva, size);
        Require(std::all_of(bytes.begin(), bytes.end(), [](unsigned char value) { return value == 0; }),
            "Migration receive storage already exists. Early activation is required.");
    }
    active->helper.Admit(process, active->helperFile);
    const vm_startup::ImageRange image{receipt.imageBase, ExactGameManifest.imageSize};
    auto entries = std::vector(ExactGameManifest.entries.begin(), ExactGameManifest.entries.end());
    for (const auto rva : {0x13619e0u,0x13617f0u,0x21f9aa0u,0x21fa750u,0x12e1c0u,0x2277a60u,0x1361a50u,0x12e226u})
        entries.push_back({rva, {}}); // NearRelay uses only RVAs to constrain relative reach.
    active->relay = std::make_unique<vm_startup::NearRelay>(process, image, entries);
    auto edits = vm_startup::BuildNativePlan({image,active->helper.image,ExactGameManifest.entries,active->helper.state,
        active->relay->Address(),ServerTotal,18,8,bo3::vm::NativeModePolicy::ZombiesOnly,{}});
    auto migration = bo3::migration::BuildMigrationPlan({image,active->helper.image,active->helper.migration,
        active->relay->Address() + 64,ServerTotal,18,32 * 1024 * 1024});
    edits.insert(edits.end(), std::make_move_iterator(migration.begin()), std::make_move_iterator(migration.end()));
    Require(edits.size() == 23, "The complete helper and migration plan is required.");
    return edits;
}
void Ready(const vm_startup::Receipt& receipt) {
    Require(receipt.editsWritten == 42, "The startup transaction did not write all required edits.");
    auto committed = receipt;
    committed.activated = true;
    active->report.Write(committed, active->helper.image.base, "ready");
    active->relay->Commit();
    std::cout << "500,000 usable server script slots are active. Keep this launcher open.\n";
}
std::wstring QuoteArgument(std::wstring_view argument) {
    std::wstring result = L"\"";
    unsigned int slashes = 0;
    for (wchar_t character : argument) {
        if (character == L'\\') { ++slashes; continue; }
        result.append(character == L'"' ? slashes * 2 + 1 : slashes, L'\\');
        slashes = 0;
        result += character;
    }
    result.append(slashes * 2, L'\\');
    return result + L'"';
}
}
int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc >= 2, "Use BO3-Enhanced-Zombies.exe <BlackOps3.exe> [game arguments].");
        LaunchLease lease;
        const auto game = std::filesystem::canonical(argv[1]);
        std::array<wchar_t, 32768> ownPath{};
        const auto length = GetModuleFileNameW(nullptr, ownPath.data(), static_cast<DWORD>(ownPath.size()));
        Require(length && length < ownPath.size(), "Cannot locate the enhanced launcher.");
        const auto helperFile = std::filesystem::canonical(std::filesystem::path(ownPath.data()).parent_path() / L"Bo3EnhancedHelper.dll");
        Locks locks;
        locks.values.reserve(2);
        VerifyFile(game, kGameHash, locks.values);
        VerifyFile(helperFile, kHelperHash, locks.values);
        MappedHelper helper(helperFile);
        const auto profile = MakeGameProfile(ExactGameManifest, ServerTotal);
        auto environment = enhanced::SteamChildEnvironment();
        std::wstring command = QuoteArgument(game.wstring());
        for (int i = 2; i < argc; ++i) command += L" " + QuoteArgument(argv[i]);
        std::array<char, 32768> helperName{};
        BOOL substituted = FALSE;
        Require(WideCharToMultiByte(CP_ACP, WC_NO_BEST_FIT_CHARS, helperFile.c_str(), -1, helperName.data(),
            static_cast<int>(helperName.size()), nullptr, &substituted) > 0 && !substituted,
            "Use a helper path that Detours can encode without substitution.");
        LPCSTR helpers[]{helperName.data()};
        STARTUPINFOW startup{sizeof(startup)};
        Child child;
        std::cout << "Experimental Zombies launch. Steam must already be running.\n";
        Require(DetourCreateProcessWithDllsW(game.c_str(), command.data(), nullptr, nullptr, FALSE,
            DEBUG_ONLY_THIS_PROCESS | CREATE_UNICODE_ENVIRONMENT, environment.data(), game.parent_path().c_str(),
            &startup, &child.info, 1, helpers, CreateProcessW) != FALSE, "Cannot create the owned game process.");
        SessionReceipt report(child.info);
        Launch launch{helper,helperFile,report,{}};
        active = &launch;
        vm_startup::Receipt receipt;
        try {
            vm_startup::Activate(child.info, profile, receipt, Ready, Prepare);
            child.exited = receipt.exited;
            report.Write(receipt, helper.image.base, receipt.activated ? "exited" : "refused",
                receipt.activated ? "" : "The game exited before the first allocation gate.");
            std::wcout << L"Session receipt: " << report.Path().wstring() << L'\n';
            return receipt.activated ? static_cast<int>(receipt.exitCode) : 2;
        } catch (const std::exception& error) {
            launch.relay.reset();
            report.Write(receipt, helper.image.base, "refused", error.what());
            throw;
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
