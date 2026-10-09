#include "Contract.h"
#include "../../launch/process_freeze/NativeState.h"
#include "../../launch/process_freeze/NativeJobFreeze.h"
#include <tlhelp32.h>
#include <array>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using process_freeze::NativeApi;
using process_freeze::State;
void Check(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
struct Handle {
    HANDLE value = nullptr;
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle() = default;
    explicit Handle(HANDLE handle) : value(handle) {}
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
};
std::wstring Executable() {
    wchar_t path[32768]{};
    Check(GetModuleFileNameW(nullptr, path, static_cast<DWORD>(std::size(path))) != 0, "Fixture path unavailable.");
    return path;
}
PROCESS_INFORMATION Spawn(std::wstring command, const std::vector<HANDLE>& handles, DWORD flags) {
    SIZE_T bytes = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &bytes);
    std::vector<unsigned char> storage(bytes);
    auto* attributes = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage.data());
    Check(InitializeProcThreadAttributeList(attributes, 1, 0, &bytes) != FALSE, "Handle list initialization failed.");
    Check(UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
        const_cast<HANDLE*>(handles.data()), handles.size() * sizeof(HANDLE), nullptr, nullptr) != FALSE,
        "Handle inheritance admission failed.");
    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb = sizeof(startup); startup.lpAttributeList = attributes;
    PROCESS_INFORMATION process{};
    const auto ok = CreateProcessW(Executable().c_str(), command.data(), nullptr, nullptr, TRUE,
        flags | EXTENDED_STARTUPINFO_PRESENT | DETACHED_PROCESS, nullptr, nullptr, &startup.StartupInfo, &process);
    DeleteProcThreadAttributeList(attributes);
    Check(ok != FALSE, "Owned fixture creation failed.");
    return process;
}
using Counters = std::array<LONG64, kCounters>;
Counters Read(Shared& shared) {
    Counters values{};
    for (size_t i = 0; i < values.size(); ++i) values[i] = InterlockedCompareExchange64(&shared.counters[i], 0, 0);
    return values;
}
struct Target {
    Handle mapping, wake, job, process, thread;
    Shared* shared = nullptr;
    process_freeze::Identity identity{};
    std::thread pulser;
    volatile LONG stopPulse = 0;
    explicit Target(int mode = 0) {
        try {
        SECURITY_ATTRIBUTES inherited{sizeof(inherited), nullptr, TRUE};
        mapping.value = CreateFileMappingW(INVALID_HANDLE_VALUE, &inherited, PAGE_READWRITE, 0, sizeof(Shared), nullptr);
        wake.value = CreateEventW(&inherited, FALSE, FALSE, nullptr);
        Check(mapping.value && wake.value, "Fixture shared objects failed.");
        shared = static_cast<Shared*>(MapViewOfFile(mapping.value, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(Shared)));
        Check(shared != nullptr, "Fixture mapping failed.");
        job.value = CreateJobObjectW(nullptr, nullptr);
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        Check(job.value && SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits)),
            "Fixture ownership job failed.");
        std::wstring command = L"\"" + Executable() + L"\" --target " +
            std::to_wstring(reinterpret_cast<uintptr_t>(mapping.value)) + L" " +
            std::to_wstring(reinterpret_cast<uintptr_t>(wake.value)) + L" " + std::to_wstring(mode);
        const auto child = Spawn(command, {mapping.value, wake.value}, CREATE_SUSPENDED);
        process.value = child.hProcess; thread.value = child.hThread;
        identity = process_freeze::ReadIdentity(process.value);
        Check(identity.image == Executable(), "Owned executable differs.");
        Check(AssignProcessToJobObject(job.value, process.value) != FALSE, "Owned child job assignment failed before resume.");
        DWORD jobFlags = HANDLE_FLAG_INHERIT;
        Check(GetHandleInformation(job.value, &jobFlags) && (jobFlags & HANDLE_FLAG_INHERIT) == 0, "Ownership job inherits.");
        Check(ResumeThread(thread.value) == 1, "Initial owned child resume failed.");
        const auto deadline = GetTickCount64() + 5000;
        while (!shared->ready && GetTickCount64() < deadline) Sleep(1);
        Check(shared->ready && shared->pid == identity.pid && shared->created == identity.created, "Owned startup identity failed.");
        for (size_t i = 0; mode != 2 && i <= 5; ++i) {
            while (!shared->started[i] && GetTickCount64() < deadline) Sleep(1);
            Check(shared->started[i] != 0, "Existing worker did not start.");
        }
        pulser = std::thread([this] {
            while (!InterlockedCompareExchange(&stopPulse, 0, 0)) { SetEvent(wake.value); Sleep(5); }
        });
        Sleep(30);
        } catch (...) {
            if (process.value && WaitForSingleObject(process.value, 0) == WAIT_TIMEOUT) {
                TerminateProcess(process.value, 95); WaitForSingleObject(process.value, 5000);
            }
            if (shared) { UnmapViewOfFile(shared); shared = nullptr; }
            throw;
        }
    }
    ~Target() {
        InterlockedExchange(&stopPulse, 1);
        if (pulser.joinable()) pulser.join();
        if (process.value && WaitForSingleObject(process.value, 0) == WAIT_TIMEOUT) {
            TerminateProcess(process.value, 96); WaitForSingleObject(process.value, 5000);
        }
        if (shared) UnmapViewOfFile(shared);
    }
    DWORD ThreadCount() const {
        Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0));
        Check(snapshot.value != INVALID_HANDLE_VALUE, "Owned thread inventory failed.");
        THREADENTRY32 entry{sizeof(entry)};
        DWORD count = 0;
        for (auto ok = Thread32First(snapshot.value, &entry); ok; ok = Thread32Next(snapshot.value, &entry))
            if (entry.th32OwnerProcessID == identity.pid) ++count;
        return count;
    }
};
void ArrayJson(std::ostream& out, const Counters& values) {
    out << '[';
    for (size_t i = 0; i < values.size(); ++i) { if (i) out << ','; out << values[i]; }
    out << ']';
}
std::string Utf8(const std::wstring& value) {
    const auto bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    Check(bytes > 0, "Receipt image conversion failed.");
    std::string result(static_cast<size_t>(bytes), '\0');
    Check(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), result.data(), bytes, nullptr, nullptr) == bytes,
        "Receipt image conversion differs.");
    return result;
}
struct Receipt {
    std::ofstream out;
    bool first = true;
    explicit Receipt(const wchar_t* path) : out(path, std::ios::binary) {
        Check(out.good(), "Receipt creation failed.");
        out << "{\"scope\":\"Owned native fixtures only. No BO3 or Steam execution.\",\"samples\":[";
    }
    void Row(const char* label, Target& target, NTSTATUS status = 0) {
        if (!first) out << ','; first = false;
        out << "{\"label\":" << std::quoted(label) << ",\"pid\":" << target.identity.pid
            << ",\"creationFileTime\":" << target.identity.created << ",\"image\":" << std::quoted(Utf8(target.identity.image)) << ",\"nativeStatus\":"
            << static_cast<unsigned long>(status) << ",\"elapsedTick\":" << GetTickCount64()
            << ",\"threadCount\":" << target.ThreadCount() << ",\"partialObserved\":"
            << target.shared->partialObserved << ",\"hiddenCreateStatus\":" << target.shared->hiddenStatus
            << ",\"bypassCreateStatus\":" << target.shared->bypassStatus
            << ",\"controllerCreateStatus\":" << target.shared->controllerCreateStatus
            << ",\"controllerSuspendStatus\":" << target.shared->controllerSuspendStatus
            << ",\"controllerAssignError\":" << target.shared->controllerAssignError
            << ",\"childStateReference\":" << target.shared->childStateReference
            << ",\"observedExitCode\":" << target.shared->observedExitCode
            << ",\"exitObserved\":" << (target.shared->exitObserved ? "true" : "false") << ",\"counters\":";
        ArrayJson(out, Read(*target.shared));
        out << ",\"workerEntryReached\":[";
        for (size_t i = 0; i < kCounters; ++i) { if (i) out << ','; out << target.shared->started[i]; }
        out << "],\"workerTids\":[";
        for (size_t i = 0; i < kCounters; ++i) { if (i) out << ','; out << target.shared->tids[i]; }
        out << "]}"; out.flush();
    }
    void Finish(bool passed, const std::string& error) {
        out << "],\"passed\":" << (passed ? "true" : "false") << ",\"error\":" << std::quoted(error) << '}';
    }
};
void Stable(Target& target, Receipt& receipt, const char* label, bool bypassAllowed = false) {
    const auto before = Read(*target.shared);
    receipt.Row(label, target);
    for (int sample = 0; sample < 30; ++sample) {
        Sleep(10); const auto current = Read(*target.shared);
        for (size_t i = 0; i < kCounters; ++i) {
            if (bypassAllowed && (i == 7 || i == 9)) continue;
            Check(current[i] == before[i], "Worker advanced after native suspend returned.");
        }
    }
    receipt.Row("frozen-end", target);
}
void Progress(Target& target, Receipt& receipt, const char* label) {
    const auto before = Read(*target.shared); Sleep(100); const auto after = Read(*target.shared);
    for (size_t i = 0; i <= 6; ++i) Check(after[i] > before[i], "Existing worker did not resume.");
    receipt.Row(label, target);
}
void Future(NativeApi& api, Target& target, size_t index, ULONG flags, Receipt& receipt) {
    HANDLE created = nullptr;
    const auto argument = target.shared->remoteMapping + offsetof(Shared, args) + index * sizeof(WorkerArgument);
    const auto status = api.thread(&created, THREAD_ALL_ACCESS, nullptr, target.process.value,
        reinterpret_cast<void*>(target.shared->worker), reinterpret_cast<void*>(argument), flags, 0, 0, 0, nullptr);
    Handle thread(created); receipt.Row(flags ? "future-bypass-create" : "future-ordinary-create", target, status);
    Check(status >= 0, "Future native thread creation failed.");
}
void NativeRefusals(NativeApi& api, Target& target, Receipt& receipt) {
    Handle restricted(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, target.identity.pid));
    Check(restricted.value != nullptr, "Restricted process open failed.");
    HANDLE badState = nullptr;
    auto refusal = [&](const char* label, NTSTATUS status) { receipt.Row(label, target, status); Check(status < 0, "Native refusal unexpectedly succeeded."); };
    refusal("create-process-access", api.create(&badState, 1, nullptr, restricted.value, 0));
    refusal("create-reserved", api.create(&badState, 1, nullptr, target.process.value, 1));
    State state(api, target.process.value, target.identity);
    refusal("change-process-access", api.change(state.Handle(), restricted.value, 0, nullptr, 0, 0));
    refusal("change-invalid-state-handle", api.change(nullptr, target.process.value, 0, nullptr, 0, 0));
    refusal("change-invalid-action", api.change(state.Handle(), target.process.value, 2, nullptr, 0, 0));
    refusal("change-reserved", api.change(state.Handle(), target.process.value, 0, nullptr, 0, 1));
    ULONG extended = 0;
    refusal("change-extended", api.change(state.Handle(), target.process.value, 0, &extended, sizeof(extended), 0));
    HANDLE noAccessRaw = nullptr;
    Check(DuplicateHandle(GetCurrentProcess(), state.Handle(), GetCurrentProcess(), &noAccessRaw, 0, FALSE, 0), "Zero-access state duplicate failed.");
    Handle noAccess(noAccessRaw);
    refusal("change-state-access", api.change(noAccess.value, target.process.value, 0, nullptr, 0, 0));
    Target other;
    refusal("change-wrong-target", api.change(state.Handle(), other.process.value, 0, nullptr, 0, 0));
    bool identityRejected = false;
    auto wrong = target.identity; ++wrong.created;
    try { State mismatch(api, target.process.value, wrong); } catch (const std::runtime_error&) { identityRejected = true; }
    Check(identityRejected, "Wrong creation time was admitted.");
    wrong = target.identity; ++wrong.pid; identityRejected = false;
    try { State mismatch(api, target.process.value, wrong); } catch (const std::runtime_error&) { identityRejected = true; }
    Check(identityRejected, "Wrong PID was admitted.");
    Progress(target, receipt, "refusals-left-target-running");
}
void RunCase(const std::string& name, NativeApi& api, Receipt& receipt) {
    Target target(name == "primary-only" || name == "job-primary" ? 2 :
        name == "bypass" || name == "job-future-bypass" || name == "job-death-bypass" ? 1 : 0); receipt.Row("running", target);
    if (name == "refusals") { NativeRefusals(api, target, receipt); return; }
    if (name == "death-raw" || name == "death-safe-job-first" || name == "death-safe-state-first" ||
        name == "job-death" || name == "job-death-bypass") {
        const bool safe = name != "death-raw";
        auto command = L"\"" + Executable() + L"\" --controller " +
            std::to_wstring(reinterpret_cast<uintptr_t>(target.mapping.value)) + L" " +
            std::to_wstring(target.identity.pid) + L" " + std::to_wstring(target.identity.created) + L" " +
            (name.starts_with("job-") ? L"2" : safe ? L"1" : L"0") + L" " + (name == "death-safe-state-first" ? L"1" : L"0");
        const auto controller = Spawn(command, {target.mapping.value}, 0);
        Handle process(controller.hProcess), thread(controller.hThread);
        Check(WaitForSingleObject(process.value, 5000) == WAIT_OBJECT_0, "Controller did not exit.");
        DWORD controllerCode = 0; Check(GetExitCodeProcess(process.value, &controllerCode), "Controller code unavailable.");
        Check(controllerCode == 73 && target.shared->controllerReady, "Controller did not reach partial-publication crash.");
        if (safe) {
            Check(WaitForSingleObject(target.process.value, 5000) == WAIT_OBJECT_0, "Frozen child job kill did not complete.");
            Check(target.shared->partialObserved == 0, "Worker observed partial marker before job death.");
            DWORD code = 0; Check(GetExitCodeProcess(target.process.value, &code), "Raw child exit unavailable.");
            target.shared->observedExitCode = code;
            target.shared->exitObserved = 1;
            receipt.Row("job-killed-frozen-child", target);
        } else {
            Sleep(150);
            Check(target.shared->partialObserved > 0, "Raw controller death did not expose partial marker.");
            receipt.Row("negative-control-auto-thaw-partial-observed", target);
        }
        return;
    }
    if (name.starts_with("job-")) {
        process_freeze::NativeJobApi jobApi;
        if (name == "job-refusals") {
            process_freeze::JobFreezeInformation information{};
            information.flags = 1; information.freeze = TRUE;
            auto refuse = [&](const char* label, NTSTATUS status) {
                receipt.Row(label, target, status); Check(status < 0, "Native job refusal unexpectedly succeeded.");
            };
            refuse("job-invalid-handle", jobApi.set(nullptr, 18, &information, sizeof(information)));
            refuse("job-invalid-size", jobApi.set(target.job.value, 18, &information, sizeof(information) - 1));
            HANDLE restrictedRaw = nullptr;
            Check(DuplicateHandle(GetCurrentProcess(), target.job.value, GetCurrentProcess(), &restrictedRaw, JOB_OBJECT_QUERY,
                FALSE, 0), "Restricted job duplicate failed.");
            Handle restricted(restrictedRaw);
            refuse("job-insufficient-access", jobApi.set(restricted.value, 18, &information, sizeof(information)));
            bool refused = false;
            auto wrong = target.identity; ++wrong.created;
            try { process_freeze::ChangeOwnedJobFreeze(jobApi, target.job.value, target.process.value, wrong, true); }
            catch (const std::runtime_error&) { refused = true; }
            Check(refused, "Job wrapper accepted wrong creation identity.");
            Target other;
            refused = false;
            try { process_freeze::ChangeOwnedJobFreeze(jobApi, target.job.value, other.process.value, other.identity, true); }
            catch (const std::runtime_error&) { refused = true; }
            Check(refused, "Job wrapper accepted wrong membership.");
            Progress(target, receipt, "job-refusals-left-target-running"); return;
        }
        if (name == "job-primary") Check(target.ThreadCount() == 1, "Initial job primary-only inventory differs.");
        const auto freeze = process_freeze::ChangeOwnedJobFreeze(jobApi, target.job.value, target.process.value, target.identity, true);
        receipt.Row("job-freeze-return", target, freeze); Check(freeze >= 0, "Native job freeze refused.");
        Stable(target, receipt, "job-all-fixture-workers-frozen");
        if (name == "job-future-bypass" || name == "job-primary") {
            Future(api, target, 8, 0, receipt); Future(api, target, 9, 0x40, receipt);
            Stable(target, receipt, "job-future-ordinary-and-bypass-held");
            Check(!target.shared->started[8] && !target.shared->started[9], "Future thread entered frozen job.");
        }
        if (name == "job-close-kill") {
            CloseHandle(target.job.value); target.job.value = nullptr;
            Check(WaitForSingleObject(target.process.value, 5000) == WAIT_OBJECT_0, "Last job close left frozen child alive.");
            Check(GetExitCodeProcess(target.process.value, &target.shared->observedExitCode), "Job-close raw exit unavailable.");
            target.shared->exitObserved = 1;
            receipt.Row("last-job-close-killed-owned-child", target); return;
        }
        const auto thaw = process_freeze::ChangeOwnedJobFreeze(jobApi, target.job.value, target.process.value, target.identity, false);
        receipt.Row("job-thaw-return", target, thaw); Check(thaw >= 0, "Native job thaw failed.");
        if (name == "job-primary") {
            Sleep(100); Check(target.shared->counters[6] && target.shared->started[8] && target.shared->started[9], "Primary job workers did not resume.");
            receipt.Row("job-primary-resumed", target);
        } else {
            Progress(target, receipt, "job-workers-resumed");
            if (name == "job-future-bypass") Check(target.shared->started[8] && target.shared->started[9] && target.shared->counters[7] > 0,
                "Job bypass or future worker did not resume.");
        }
        return;
    }
    if (name == "prior-thread-suspend") {
        Handle worker(OpenThread(THREAD_SUSPEND_RESUME, FALSE, target.shared->tids[0]));
        Check(worker.value && SuspendThread(worker.value) == 0, "Prior worker suspension failed.");
        State frozen(api, target.process.value, target.identity);
        Check(frozen.Change(0) >= 0, "Process freeze with prior suspension failed.");
        Stable(target, receipt, "prior-thread-and-process-frozen");
        Check(frozen.Change(1) >= 0, "Process resume with prior suspension failed.");
        const auto before = Read(*target.shared); Sleep(100); const auto after = Read(*target.shared);
        Check(before[0] == after[0] && after[1] > before[1], "Process resume changed prior thread suspension.");
        receipt.Row("prior-thread-suspension-preserved", target);
        Check(ResumeThread(worker.value) == 1, "Prior thread suspension balance differs.");
        Progress(target, receipt, "prior-thread-resumed"); return;
    }
    State state(api, target.process.value, target.identity);
    const auto suspend = state.Change(0); receipt.Row("suspend-return", target, suspend); Check(suspend >= 0, "Native suspend failed.");
    if (name == "primary-only") {
        Check(target.ThreadCount() == 1, "Strict primary-only inventory failed.");
        Stable(target, receipt, "primary-only-frozen");
        Future(api, target, 8, 0, receipt); Stable(target, receipt, "future-ordinary-held");
        Check(!target.shared->started[8], "Future ordinary thread entered primary-only target.");
        Future(api, target, 9, 0x40, receipt); Sleep(100);
        Check(target.shared->started[9] && target.shared->counters[9] > 0, "Primary-only bypass counterexample missing.");
        Check(target.ThreadCount() > 1, "Changed primary-only inventory was accepted.");
        receipt.Row("primary-only-inventory-no-longer-eligible", target);
        Check(state.Change(1) >= 0, "Primary-only state resume failed.");
        Sleep(100); Check(target.shared->started[8], "Future ordinary thread failed to start after resume.");
        receipt.Row("primary-only-resumed", target); return;
    }
    if (name == "bypass") {
        const auto before = Read(*target.shared); Future(api, target, 9, 0x40, receipt);
        Stable(target, receipt, "bypass-frozen", true);
        const auto after = Read(*target.shared);
        // Evidence reports whether deep process-state freeze includes the bypass flag on this kernel.
        receipt.Row(after[7] > before[7] || after[9] > before[9] ? "bypass-ran-during-freeze" : "bypass-held-during-freeze", target);
    } else {
        Stable(target, receipt, "ordinary-hidden-waiting-churn-frozen");
    }
    if (name == "future") {
        Future(api, target, 8, 0, receipt); Stable(target, receipt, "future-ordinary-held");
        Check(target.shared->started[8] == 0, "Future ordinary thread entered while frozen.");
    }
    if (name == "close") state.Close();
    else if (name == "duplicate") {
        HANDLE duplicate = nullptr;
        Check(DuplicateHandle(GetCurrentProcess(), state.Handle(), GetCurrentProcess(), &duplicate, 0, FALSE, DUPLICATE_SAME_ACCESS), "State duplicate failed.");
        Handle last(duplicate); state.Close(); Stable(target, receipt, "duplicate-retains-freeze");
        CloseHandle(last.value); last.value = nullptr;
    } else if (name == "nested") {
        State second(api, target.process.value, target.identity);
        Check(second.Change(0) >= 0, "Nested state suspend failed.");
        Check(state.Change(1) >= 0, "First nested state resume failed.");
        Stable(target, receipt, "second-state-retains-freeze");
        Check(second.Change(1) >= 0, "Second nested resume failed.");
    } else if (name == "child-reference") {
        HANDLE remote = nullptr;
        Check(DuplicateHandle(GetCurrentProcess(), state.Handle(), target.process.value, &remote, 0, FALSE, DUPLICATE_SAME_ACCESS), "Child state reference failed.");
        const auto resume = state.Change(1); receipt.Row("explicit-resume", target, resume); Check(resume >= 0, "Explicit resume failed.");
        HANDLE local = nullptr;
        // CLOSE_SOURCE consumes the remote handle even if duplication reports failure. Never retry it.
        const auto closed = DuplicateHandle(target.process.value, remote, GetCurrentProcess(), &local, 0, FALSE,
            DUPLICATE_CLOSE_SOURCE | DUPLICATE_SAME_ACCESS);
        Handle recovered(local); Check(closed != FALSE, "Remote state reference close failed.");
        receipt.Row("child-state-reference-consumed", target);
    } else if (name == "target-exit") {
        Check(TerminateProcess(target.process.value, 81), "Frozen owned target termination failed.");
        Check(WaitForSingleObject(target.process.value, 5000) == WAIT_OBJECT_0, "Frozen target exit did not signal.");
        DWORD code = 0; Check(GetExitCodeProcess(target.process.value, &code) && code == 81, "Raw target exit differs.");
        target.shared->observedExitCode = code;
        target.shared->exitObserved = 1;
        bool identityRejected = false;
        try { state.Change(1); } catch (const std::runtime_error&) { identityRejected = true; }
        receipt.Row(identityRejected ? "wrapper-refused-post-exit-identity" : "wrapper-retained-post-exit-identity", target);
        const auto status = api.change(state.Handle(), target.process.value, 1, nullptr, 0, 0);
        receipt.Row("raw-resume-exited-owned-target", target, status);
        return;
    } else {
        const auto resume = state.Change(1); receipt.Row("explicit-resume", target, resume); Check(resume >= 0, "Explicit resume failed.");
    }
    Progress(target, receipt, "resumed");
    if (name == "future") Check(target.shared->started[8] && target.shared->counters[8] > 0, "Future ordinary thread did not resume.");
}
int wmain(int argc, wchar_t** argv) {
    try {
        if (argc >= 2 && std::wstring(argv[1]) == L"--target") {
            Check(argc == 5, "Target argument contract differs.");
            return RunTarget(reinterpret_cast<HANDLE>(std::stoull(argv[2])), reinterpret_cast<HANDLE>(std::stoull(argv[3])), std::stoi(argv[4]));
        }
        if (argc >= 2 && std::wstring(argv[1]) == L"--controller") {
            Check(argc == 7, "Controller argument contract differs.");
            return RunController(reinterpret_cast<HANDLE>(std::stoull(argv[2])), std::stoul(argv[3]), std::stoull(argv[4]),
                std::stoi(argv[5]), std::stoi(argv[6]) != 0);
        }
        Check(argc == 3, "Use a fixed owned case and receipt path.");
        Receipt receipt(argv[2]);
        try {
            NativeApi api;
            const std::wstring wide(argv[1]); std::string name;
            for (const auto letter : wide) { Check(letter <= 0x7f, "Case name must be ASCII."); name.push_back(static_cast<char>(letter)); }
            const std::vector<std::string> allowed{"explicit","close","duplicate","nested","future","bypass","child-reference","refusals",
                "target-exit","death-raw","death-safe-job-first","death-safe-state-first","prior-thread-suspend","primary-only",
                "job-explicit","job-future-bypass","job-primary","job-close-kill","job-refusals","job-death","job-death-bypass"};
            Check(std::find(allowed.begin(), allowed.end(), name) != allowed.end(), "Unknown owned case.");
            RunCase(name, api, receipt); receipt.Finish(true, ""); return 0;
        } catch (const std::exception& error) { receipt.Finish(false, error.what()); std::cerr << error.what() << '\n'; return 1; }
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
