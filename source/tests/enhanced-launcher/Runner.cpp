#include "../../launch/enhanced/MappedHelper.h"
#include "../../launch/enhanced/SteamContext.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "../../launch/preentry/Identity.h"
#include "BuildIdentity.h"
#include <detours.h>
#include <fstream>
#include <iostream>

namespace {
struct Locks { std::vector<HANDLE> values; ~Locks() { for (const auto handle : values) CloseHandle(handle); } };
struct Child {
    PROCESS_INFORMATION info{};
    bool done = false;
    ~Child() {
        if (!info.hProcess) return;
        if (!done) { TerminateProcess(info.hProcess,97); DebugActiveProcessStop(info.dwProcessId); WaitForSingleObject(info.hProcess,5000); }
        CloseHandle(info.hThread); CloseHandle(info.hProcess);
    }
};
std::wstring Environment(const wchar_t* name) {
    wchar_t buffer[128]{};
    const auto length = GetEnvironmentVariableW(name, buffer,128);
    Require(length < 128, "Owned parent environment value is too long.");
    return buffer;
}
}
int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 3, "Use an owned scenario and a new private receipt.");
        const std::wstring scenario = argv[1];
        Require(scenario == L"mapped" || scenario == L"boot-invalid" || scenario == L"code-invalid" || scenario == L"unwind-invalid",
            "Unknown owned scenario.");
        const auto output = PrivateOutput(argv[2]);
        wchar_t path[32768]{};
        Require(GetModuleFileNameW(nullptr,path,32768) != 0, "Cannot locate the fixed owned directory.");
        const auto directory = std::filesystem::path(path).parent_path();
        const auto helperFile = directory / L"Bo3EnhancedHelper.dll", target = directory / L"EnhancedOwnedTarget.exe";
        Locks locks; locks.values.reserve(2);
        VerifyFile(helperFile,kHelperHash,locks.values); VerifyFile(target,kOwnedTargetHash,locks.values);
        bo3::enhanced::MappedHelper helper(helperFile);
        const auto appBefore = Environment(L"SteamAppId"), gameBefore = Environment(L"SteamGameId");
        auto environment = enhanced::SteamChildEnvironment();
        char helperName[32768]{}; BOOL substituted = FALSE;
        Require(WideCharToMultiByte(CP_ACP,WC_NO_BEST_FIT_CHARS,helperFile.c_str(),-1,helperName,32768,nullptr,&substituted)>0 && !substituted,
            "The fixed helper path cannot use ANSI encoding.");
        LPCSTR helpers[]{helperName}; STARTUPINFOW startup{sizeof(startup)}; Child child;
        std::wstring command = L"\"" + target.wstring() + L"\"";
        Require(DetourCreateProcessWithDllsW(target.c_str(),command.data(),nullptr,nullptr,FALSE,
            DEBUG_ONLY_THIS_PROCESS | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW,environment.data(),directory.c_str(),
            &startup,&child.info,1,helpers,CreateProcessW), "Cannot create the owned mapping child.");
        bool initial = false, checked = false, refused = false;
        DWORD exitCode = 0;
        const auto deadline = GetTickCount64() + 10000;
        while (!child.done) {
            Require(GetTickCount64() < deadline, "The owned mapping child timed out.");
            DEBUG_EVENT event{};
            if (!WaitForDebugEvent(&event,100)) { Require(GetLastError()==ERROR_SEM_TIMEOUT,"Cannot wait for owned events."); continue; }
            Require(event.dwProcessId == child.info.dwProcessId, "Unexpected owned debug process.");
            DWORD continuation = DBG_CONTINUE;
            if (event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT) { if(event.u.CreateProcessInfo.hFile) CloseHandle(event.u.CreateProcessInfo.hFile); }
            else if (event.dwDebugEventCode == LOAD_DLL_DEBUG_EVENT) { if(event.u.LoadDll.hFile) CloseHandle(event.u.LoadDll.hFile); }
            else if (event.dwDebugEventCode == EXCEPTION_DEBUG_EVENT) {
                if (event.u.Exception.ExceptionRecord.ExceptionCode != EXCEPTION_BREAKPOINT) continuation = DBG_EXCEPTION_NOT_HANDLED;
                else if (!initial) initial = true;
                else {
                    Require(!checked, "Unexpected additional owned breakpoint.");
                    helper.Admit(child.info.hProcess,helperFile);
                    if (scenario != L"mapped") {
                        const auto offset = scenario == L"boot-invalid" ? helper.state.stateBindings : helper.state.readState;
                        // The boot case damages the BootRecord ABI. Its exact export comes from the trusted file.
                        HMODULE mapped = LoadLibraryExW(helperFile.c_str(),nullptr,DONT_RESOLVE_DLL_REFERENCES);
                        Require(mapped != nullptr, "Cannot inspect the boot export.");
                        const auto boot = reinterpret_cast<std::uintptr_t>(GetProcAddress(mapped,"Bo3EnhancedBoot")) - reinterpret_cast<std::uintptr_t>(mapped);
                        const auto* base = reinterpret_cast<const unsigned char*>(mapped);
                        const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
                        const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
                        const auto* function = reinterpret_cast<const RUNTIME_FUNCTION*>(base + nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION].VirtualAddress);
                        const auto unwind = function->UnwindData + 1;
                        FreeLibrary(mapped);
                        const auto address = helper.image.base + (scenario == L"boot-invalid" ? boot : scenario == L"unwind-invalid" ? unwind : offset);
                        auto original = vm_startup::ReadStopped(child.info.hProcess,address,1);
                        auto damaged = original; damaged[0] ^= 1;
                        vm_startup::Receipt receipt;
                        vm_startup::PausedPatch patch(child.info.hProcess,{{address,original,damaged}},receipt);
                        patch.Apply();
                        try { helper.Admit(child.info.hProcess,helperFile); }
                        catch (const std::exception&) { refused = true; }
                        // Rollback uses the same actual transaction code before the child resumes.
                    }
                    checked = true;
                }
            } else if (event.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT) { exitCode = event.u.ExitProcess.dwExitCode; child.done = true; }
            Require(ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation), "Cannot continue the owned child.");
        }
        const bool parentUnchanged = Environment(L"SteamAppId") == appBefore && Environment(L"SteamGameId") == gameBefore;
        const bool passed = checked && exitCode == 0 && parentUnchanged && refused == (scenario != L"mapped");
        std::ofstream report(output);
        report << "{\"passed\":" << (passed?"true":"false") << ",\"exitCode\":" << exitCode
            << ",\"mappedHelperAdmitted\":" << (checked?"true":"false") << ",\"damagedMappingRefused\":" << (refused?"true":"false")
            << ",\"parentEnvironmentUnchanged\":" << (parentUnchanged?"true":"false") << ",\"scope\":\"Owned child and actual combined helper. No BO3 execution.\"}";
        Require(report.good(), "Cannot save the owned mapping receipt.");
        return passed ? 0 : 1;
    } catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
