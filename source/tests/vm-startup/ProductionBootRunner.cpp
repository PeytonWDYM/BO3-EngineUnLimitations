#include "../../launch/preentry/Identity.h"
#include "BuildIdentity.h"
#include <detours.h>
#include <fstream>
#include <iostream>

namespace {
struct Locks { std::vector<HANDLE> values; ~Locks() { for (auto handle : values) CloseHandle(handle); } };
struct Child {
    PROCESS_INFORMATION info{};
    bool done = false;
    ~Child() {
        if (!info.hProcess) return;
        if (!done) { TerminateProcess(info.hProcess, 97); WaitForSingleObject(info.hProcess, 5000); }
        CloseHandle(info.hProcess);
        CloseHandle(info.hThread);
    }
};
}
int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 2, "Use a new private production-boot receipt.");
        const auto output = PrivateOutput(argv[1]);
        wchar_t path[32768]{};
        Require(GetModuleFileNameW(nullptr, path, 32768) != 0, "Cannot locate owned fixture directory.");
        const auto directory = std::filesystem::path(path).parent_path();
        const auto target = directory / L"VmProductionBootTarget.exe", helper = directory / L"VmStartupHelper.dll";
        Locks locks;
        locks.values.reserve(2);
        VerifyFile(target, kProductionBootTargetHash, locks.values);
        VerifyFile(helper, kHelperHash, locks.values);
        Require(SetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING", nullptr) != FALSE, "Cannot remove the fixture-only input.");
        char helperPath[32768]{};
        BOOL substituted = FALSE;
        Require(WideCharToMultiByte(CP_ACP, WC_NO_BEST_FIT_CHARS, helper.c_str(), -1, helperPath, 32768, nullptr, &substituted) > 0
            && !substituted, "The fixed helper path does not support Detours ANSI encoding.");
        LPCSTR helpers[]{helperPath};
        STARTUPINFOW startup{};
        startup.cb = sizeof(startup);
        Child child;
        std::wstring command = L"\"" + target.wstring() + L"\"";
        Require(DetourCreateProcessWithDllsW(target.c_str(), command.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
            nullptr, directory.c_str(), &startup, &child.info, 1, helpers, CreateProcessW) != FALSE, "Cannot start the fixed owned boot child.");
        Require(WaitForSingleObject(child.info.hProcess, 10000) == WAIT_OBJECT_0, "The owned boot child did not stop.");
        child.done = true;
        DWORD exitCode = 0;
        Require(GetExitCodeProcess(child.info.hProcess, &exitCode) != FALSE, "Cannot read the owned boot result.");
        const bool passed = exitCode == 0;
        std::ofstream report(output);
        report << "{\"passed\":" << (passed ? "true" : "false") << ",\"exitCode\":" << exitCode
            << ",\"fixtureEnvironmentAbsent\":true,\"scope\":\"Fixed owned child. No BO3 execution.\"}";
        return passed ? 0 : 1;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
