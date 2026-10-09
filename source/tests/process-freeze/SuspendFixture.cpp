// Owned fixture for the Wine process-suspend fallback. See failure-cases.txt.
// Parent mode runs every case against fresh copies of this executable started in child mode.
#include "../../launch/process_freeze/NativeJobFreeze.h"
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <stdexcept>
#include <string>

namespace {
constexpr wchar_t kMapping[] = L"Local\\Bo3SuspendFixtureCounter";
void Check(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
std::atomic<unsigned long long>* Counter(HANDLE& mapping, bool create) {
    mapping = create ? CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, 4096, kMapping)
                     : OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, kMapping);
    Check(mapping != nullptr, "Cannot open the counter mapping.");
    auto* view = MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(unsigned long long));
    Check(view != nullptr, "Cannot map the counter.");
    return static_cast<std::atomic<unsigned long long>*>(view);
}
DWORD WINAPI Work(void* counter) {
    for (;;) static_cast<std::atomic<unsigned long long>*>(counter)->fetch_add(1);
}
int RunChild() {
    HANDLE mapping{};
    auto* counter = Counter(mapping, false);
    for (int i = 0; i < 2; ++i) Check(CreateThread(nullptr, 0, Work, counter, 0, nullptr) != nullptr, "Cannot start a worker.");
    Sleep(INFINITE);
    return 0;
}
struct Child {
    PROCESS_INFORMATION process{};
    process_freeze::Identity identity{};
    explicit Child(const std::wstring& self, std::atomic<unsigned long long>* counter) {
        STARTUPINFOW startup{sizeof(startup)};
        std::wstring command = L"\"" + self + L"\" child";
        const auto before = counter->load();
        Check(CreateProcessW(self.c_str(), command.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &startup, &process) != FALSE,
            "Cannot start the child.");
        for (int i = 0; i < 500 && counter->load() == before; ++i) Sleep(10);
        Check(counter->load() != before, "The child workers did not start.");
        identity = process_freeze::ReadIdentity(process.hProcess);
    }
    ~Child() {
        TerminateProcess(process.hProcess, 0);
        WaitForSingleObject(process.hProcess, 5000);
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
    }
};
bool Refuses(const std::function<void()>& action) {
    try { action(); } catch (const std::runtime_error&) { return true; }
    return false;
}
}

int wmain(int argc, wchar_t** argv) {
    try {
        if (argc == 2 && std::wstring(argv[1]) == L"child") return RunChild();
        HANDLE mapping{};
        auto* counter = Counter(mapping, true);
        const std::wstring self = argv[0];
        std::printf("wine-ntdll=%s\n", process_freeze::WineNtdll() ? "true" : "false");
        int passed = 0;
        const auto pass = [&](const char* name) { std::printf("%s passed\n", name); ++passed; };
        {
            Child child(self, counter);
            process_freeze::ProcessSuspend suspend;
            Check(suspend.Suspend(child.process.hProcess, child.identity) == 0, "Suspend failed.");
            const auto stopped = counter->load();
            Sleep(300);
            Check(counter->load() == stopped, "A worker advanced while suspended.");
            pass("suspend-stops-every-thread");
            suspend.Verify();
            pass("unchanged-thread-set-verifies");
            Check(suspend.Resume(child.process.hProcess) == 0 && !suspend.Active(), "Resume failed.");
            Sleep(300);
            Check(counter->load() != stopped, "The workers did not resume.");
            pass("resume-restarts-every-thread");
        }
        {
            Child child(self, counter);
            process_freeze::ProcessSuspend suspend;
            Check(suspend.Suspend(child.process.hProcess, child.identity) == 0, "Suspend failed.");
            const auto sleep = reinterpret_cast<LPTHREAD_START_ROUTINE>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "Sleep"));
            const HANDLE remote = CreateRemoteThread(child.process.hProcess, nullptr, 0, sleep, reinterpret_cast<void*>(static_cast<std::uintptr_t>(INFINITE)), 0, nullptr);
            Check(remote != nullptr, "Cannot add a thread to the suspended child.");
            CloseHandle(remote);
            Check(Refuses([&] { suspend.Verify(); }), "A new thread was not refused.");
            Check(Refuses([&] { suspend.Resume(child.process.hProcess); }) && suspend.Active(), "Resume ignored a new thread.");
            pass("new-thread-refused");
        }
        {
            Child child(self, counter);
            process_freeze::ProcessSuspend suspend;
            Check(suspend.Suspend(child.process.hProcess, child.identity) == 0, "Suspend failed.");
            const auto ids = process_freeze::ThreadIds(child.identity.pid);
            const auto worker = ids.front() == child.process.dwThreadId ? ids.back() : ids.front();
            const HANDLE thread = OpenThread(THREAD_TERMINATE | SYNCHRONIZE, FALSE, worker);
            Check(thread && TerminateThread(thread, 0) && WaitForSingleObject(thread, 5000) == WAIT_OBJECT_0, "Cannot end a worker.");
            CloseHandle(thread);
            Check(Refuses([&] { suspend.Verify(); }), "An ended thread was not refused.");
            pass("ended-thread-refused");
        }
        {
            Child child(self, counter);
            process_freeze::ProcessSuspend suspend;
            Check(Refuses([&] { suspend.Resume(child.process.hProcess); }), "Resume without a suspend was not refused.");
            Check(suspend.Suspend(child.process.hProcess, child.identity) == 0, "Suspend failed.");
            Check(Refuses([&] { suspend.Suspend(child.process.hProcess, child.identity); }), "A second suspend was not refused.");
            Check(suspend.Resume(child.process.hProcess) == 0, "Resume failed.");
            pass("double-suspend-and-unmatched-resume-refused");
        }
        {
            Child child(self, counter);
            auto other = child.identity;
            other.created += 1;
            process_freeze::ProcessSuspend suspend;
            const auto before = counter->load();
            Check(Refuses([&] { suspend.Suspend(child.process.hProcess, other); }) && !suspend.Active(), "A different identity was suspended.");
            Sleep(100);
            Check(counter->load() != before, "The refused child was suspended.");
            pass("identity-mismatch-refused-before-suspend");
        }
        {
            Child child(self, counter);
            process_freeze::ProcessSuspend suspend;
            process_freeze::SetSuspendInventoryObserver([](HANDLE process) {
                const auto sleep = reinterpret_cast<LPTHREAD_START_ROUTINE>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "Sleep"));
                const HANDLE remote = CreateRemoteThread(process, nullptr, 0, sleep, reinterpret_cast<void*>(static_cast<std::uintptr_t>(INFINITE)), 0, nullptr);
                Check(remote != nullptr, "Cannot add a thread before the suspend syscall.");
                CloseHandle(remote);
            });
            const bool refused = Refuses([&] { suspend.Suspend(child.process.hProcess, child.identity); });
            process_freeze::SetSuspendInventoryObserver({});
            Check(refused && suspend.Active(), "A thread created during suspend admission was adopted.");
            Check(Refuses([&] { suspend.Resume(child.process.hProcess); }), "A refused inventory was resumed.");
            pass("thread-created-before-syscall-refused");
        }
        {
            Child child(self, counter);
            const HANDLE job = CreateJobObjectW(nullptr, nullptr);
            Check(job && AssignProcessToJobObject(job, child.process.hProcess), "Cannot assign the job.");
            const process_freeze::NativeJobApi api;
            const auto status = process_freeze::ChangeOwnedJobFreeze(api, job, child.process.hProcess, child.identity, true);
            std::printf("job-freeze-status=0x%08lx\n", static_cast<unsigned long>(status));
            Check(process_freeze::WineNtdll() ? status == process_freeze::kNotImplemented : status == 0,
                "The job freeze result does not select the expected backend.");
            if (status == 0) process_freeze::ChangeOwnedJobFreeze(api, job, child.process.hProcess, child.identity, false);
            CloseHandle(job);
            pass("fallback-only-when-job-freeze-is-not-implemented");
        }
        std::printf("%d cases passed\n", passed);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
