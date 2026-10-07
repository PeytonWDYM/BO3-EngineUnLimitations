#include "Identity.h"
#include "BuildIdentity.h"
#include "ProbeContract.h"
#include <detours.h>
#include <algorithm>
#include <iostream>
#include <sstream>

static std::wstring fixedTarget;
// Reject Detours cross-architecture helper fallback. This fixture supports x64 only.
static BOOL WINAPI CreateOwned(LPCWSTR application, LPWSTR command, LPSECURITY_ATTRIBUTES processAttributes,
    LPSECURITY_ATTRIBUTES threadAttributes, BOOL inherit, DWORD flags, LPVOID environment, LPCWSTR directory,
    LPSTARTUPINFOW startup, LPPROCESS_INFORMATION information) {
    if (!application || fixedTarget != application) { SetLastError(ERROR_ACCESS_DENIED); return FALSE; }
    return CreateProcessW(application, command, processAttributes, threadAttributes, inherit, flags,
                          environment, directory, startup, information);
}
static Scenario Parse(const wchar_t* name) {
    const std::pair<const wchar_t*, Scenario> choices[] = {{L"baseline", Scenario::Baseline},
        {L"protected", Scenario::Protected}, {L"early", Scenario::EarlyDependency}, {L"denied", Scenario::Denied},
        {L"live", Scenario::LiveReference}, {L"remove", Scenario::Remove}};
    for (const auto& choice : choices) if (std::wstring(name) == choice.first) return choice.second;
    throw std::runtime_error("Use a fixed owned fixture scenario.");
}
static const char* StageName(DWORD stage) {
    constexpr const char* names[] = {"provider-init", "restore", "helper-ready", "imported-dll", "tls", "entry",
        "live-acquire", "remove-denied", "live-release", "removed", "helper-detach", "after-remove", "error",
        "unload-attempt", "helper-retained"};
    return stage < std::size(names) ? names[stage] : "invalid";
}
int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 3, "Use PreentryLauncher SCENARIO PRIVATE_TRACE_JSON.");
        const auto output = PrivateOutput(argv[2]);
        const auto scenario = Parse(argv[1]);
        wchar_t modulePath[32768]{};
        const DWORD length = GetModuleFileNameW(nullptr, modulePath, 32768);
        Require(length > 0 && length < 32768, "Cannot find the launcher directory.");
        const auto directory = std::filesystem::path(modulePath).parent_path();
        struct Locks { std::vector<HANDLE> values; ~Locks() { for (auto file : values) CloseHandle(file); } } locks;
        locks.values.reserve(4);
        VerifyFile(directory / L"PreentryTarget.exe", kTargetHash, locks.values);
        VerifyFile(directory / L"PreentryProvider.dll", kProviderHash, locks.values);
        VerifyFile(directory / L"PreentryConsumer.dll", kConsumerHash, locks.values);
        if (scenario != Scenario::Baseline) VerifyFile(directory / L"PreentryHelper64.dll", kHelperHash, locks.values);
        Handle traceFile(CreateFileW(output.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr));
        Require(traceFile.value != INVALID_HANDLE_VALUE, "Cannot create the private trace file.");
        SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
        Handle mapping(CreateFileMappingW(INVALID_HANDLE_VALUE, &attributes, PAGE_READWRITE, 0, sizeof(SharedTrace), nullptr));
        Require(mapping.value != nullptr, "Cannot create the owned trace mapping.");
        struct View { SharedTrace* value; ~View() { if (value) UnmapViewOfFile(value); } } view{
            static_cast<SharedTrace*>(MapViewOfFile(mapping.value, FILE_MAP_WRITE, 0, 0, sizeof(SharedTrace)))};
        Require(view.value != nullptr, "Cannot map the owned trace.");
        *view.value = {};
        view.value->magic = kTraceMagic;
        view.value->scenario = scenario;
        const auto mappingText = std::to_wstring(reinterpret_cast<std::uintptr_t>(mapping.value));
        Require(SetEnvironmentVariableW(L"BO3_OWNED_PREENTRY_TRACE", mappingText.c_str()) != FALSE, "Cannot set the owned mapping contract.");
        SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
        STARTUPINFOW startup{};
        startup.cb = sizeof(startup);
        PROCESS_INFORMATION information{};
        fixedTarget = (directory / L"PreentryTarget.exe").wstring();
        std::wstring command = L"\"" + fixedTarget + L"\"";
        BOOL created;
        if (scenario == Scenario::Baseline) {
            created = CreateOwned(fixedTarget.c_str(), command.data(), nullptr, nullptr, TRUE,
                                  CREATE_NO_WINDOW, nullptr, directory.c_str(), &startup, &information);
        } else {
            const auto helperWide = (directory / L"PreentryHelper64.dll").wstring();
            const int size = WideCharToMultiByte(CP_ACP, WC_NO_BEST_FIT_CHARS, helperWide.c_str(), -1, nullptr, 0, nullptr, nullptr);
            Require(size > 0, "Cannot encode the helper path.");
            std::string helper(static_cast<size_t>(size), '\0');
            BOOL substituted = FALSE;
            Require(WideCharToMultiByte(CP_ACP, WC_NO_BEST_FIT_CHARS, helperWide.c_str(), -1, helper.data(), size,
                                       nullptr, &substituted) > 0 && !substituted, "The helper path cannot use the native ANSI contract.");
            LPCSTR helpers[] = {helper.c_str()};
            created = DetourCreateProcessWithDllsW(fixedTarget.c_str(), command.data(), nullptr, nullptr, TRUE,
                CREATE_NO_WINDOW, nullptr, directory.c_str(), &startup, &information, 1, helpers, CreateOwned);
        }
        Require(created != FALSE, "Cannot create the fixed owned fixture process.");
        Handle process(information.hProcess);
        Handle thread(information.hThread);
        const DWORD wait = WaitForSingleObject(process.value, 30000);
        if (wait != WAIT_OBJECT_0) {
            TerminateProcess(process.value, 30);
            WaitForSingleObject(process.value, 5000);
            throw std::runtime_error("The owned fixture did not exit in time.");
        }
        DWORD exit = 0;
        Require(GetExitCodeProcess(process.value, &exit) != FALSE, "Cannot read the owned fixture exit.");
        std::ostringstream json;
        json << "{\"processCreated\":true,\"targetExit\":" << exit << ",\"unsafeCalls\":" << view.value->unsafeCalls
             << ",\"internalErrors\":" << view.value->internalErrors << ",\"events\":[";
        const LONG count = std::clamp(static_cast<LONG>(view.value->count), 0L, static_cast<LONG>(kMaximumEvents));
        for (LONG i = 0; i < count; ++i) {
            const auto& event = view.value->events[i];
            if (i) json << ',';
            json << "{\"sequence\":" << i << ",\"stage\":\"" << StageName(event.stage) << "\",\"ready\":" << event.ready
                 << ",\"output\":" << event.output << ",\"references\":" << event.references << '}';
        }
        json << "]}\n";
        const auto text = json.str();
        DWORD written = 0;
        Require(WriteFile(traceFile.value, text.data(), static_cast<DWORD>(text.size()), &written, nullptr) != FALSE
                && written == text.size(), "Cannot write the private trace.");
        return exit == 0 && view.value->unsafeCalls == 0 && view.value->internalErrors == 0 ? 0 : 2;
    } catch (const std::exception& problem) {
        std::cerr << "Owned pre-entry fixture: " << problem.what() << '\n';
        return 2;
    }
}
