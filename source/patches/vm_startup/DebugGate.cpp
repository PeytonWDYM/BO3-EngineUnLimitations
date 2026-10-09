#include "DebugGate.h"
#include "PausedPatch.h"
#include <algorithm>
#include <map>
#include <stdexcept>
#include <string>

namespace vm_startup {
namespace {
void Require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
CONTEXT Context(HANDLE thread) {
    CONTEXT value{};
    value.ContextFlags = CONTEXT_DEBUG_REGISTERS | CONTEXT_CONTROL;
    Require(GetThreadContext(thread, &value) != FALSE, "Cannot read thread context.");
    return value;
}
struct Thread {
    HANDLE handle;
    DWORD64 dr0;
    DWORD64 dr6;
    DWORD64 dr7;
    bool gated;
    bool gateAcknowledged = false;
};
struct Threads {
    std::map<DWORD, Thread> entries;
    ~Threads() { for (const auto& [id, thread] : entries) { (void)id; CloseHandle(thread.handle); } }
};
constexpr DWORD64 kDebugMask = 0xffff00ff;
void Retain(Threads& threads, DWORD id, HANDLE handle, std::uintptr_t gate, Receipt& receipt) {
    auto context = Context(handle);
    if (!receipt.activated)
        Require((context.Dr7 & kDebugMask) == 0 && context.Dr0 == 0 && context.Dr1 == 0
            && context.Dr2 == 0 && context.Dr3 == 0 && (context.Dr6 & 1) == 0,
            "A thread already owns debug registers.");
    HANDLE owned = nullptr;
    Require(DuplicateHandle(GetCurrentProcess(), handle, GetCurrentProcess(), &owned, 0, FALSE,
        DUPLICATE_SAME_ACCESS) != FALSE, "Cannot retain the thread handle.");
    threads.entries.emplace(id, Thread{owned, context.Dr0, context.Dr6, context.Dr7, !receipt.activated});
    ++receipt.retainedThreads;
    if (receipt.activated) return;
    context.Dr0 = gate;
    context.Dr7 |= 1;
    Require(SetThreadContext(handle, &context) != FALSE, "Cannot arm allocation gate.");
    ++receipt.armedThreads;
}
void Validate(const Profile& profile) {
    Require(profile.imageSize >= sizeof(std::uintptr_t) && profile.entryRva < profile.imageSize
        && profile.poolPointerRva <= profile.imageSize - sizeof(std::uintptr_t)
        && profile.hashPointerRva <= profile.imageSize - sizeof(std::uintptr_t), "Invalid gate bounds.");
    Require(!profile.checks.empty() && !profile.edits.empty(), "The gate requires exact code checks and edits.");
    for (const auto& check : profile.checks) {
        Require(!check.bytes.empty() && check.bytes.size() <= profile.imageSize
            && check.rva <= profile.imageSize - check.bytes.size(), "Invalid code check.");
    }
    bool entryChecked = false;
    for (const auto& check : profile.checks)
        entryChecked |= check.rva <= profile.entryRva && profile.entryRva - check.rva < check.bytes.size();
    Require(entryChecked, "The allocation entry has no exact byte check.");
    for (size_t index = 0; index < profile.edits.size(); ++index) {
        const auto& edit = profile.edits[index];
        Require(!edit.original.empty() && edit.original.size() == edit.replacement.size()
            && edit.original.size() <= profile.imageSize
            && edit.rva <= profile.imageSize - edit.original.size(), "Invalid edit bounds.");
        bool covered = false;
        for (const auto& check : profile.checks) {
            if (edit.rva >= check.rva && edit.rva - check.rva <= check.bytes.size()
                && edit.original.size() <= check.bytes.size() - (edit.rva - check.rva)) {
                covered |= std::equal(edit.original.begin(), edit.original.end(),
                    check.bytes.begin() + (edit.rva - check.rva));
            }
        }
        Require(covered, "An edit has no matching enclosing code check.");
        for (size_t other = 0; other < index; ++other) {
            const auto& prior = profile.edits[other];
            Require(static_cast<size_t>(edit.rva) + edit.original.size() <= prior.rva
                || static_cast<size_t>(prior.rva) + prior.original.size() <= edit.rva, "Edits overlap.");
        }
    }
}

}
void Activate(const PROCESS_INFORMATION& process, const Profile& profile, Receipt& receipt,
    void (*ready)(const Receipt&), std::vector<AddressEdit> (*prepare)(HANDLE, const Receipt&)) {
    Validate(profile);
    Threads threads;
    bool initialBreakpoint = false;
    const ULONGLONG deadline = GetTickCount64() + 30000;
    for (;;) {
        Require(receipt.activated || GetTickCount64() < deadline, "The first allocation gate timed out.");
        DEBUG_EVENT event{};
        if (!WaitForDebugEvent(&event, 100)) {
            Require(GetLastError() == ERROR_SEM_TIMEOUT, "Cannot wait for a debug event.");
            continue;
        }
        Require(event.dwProcessId == process.dwProcessId, "Unexpected debug process.");
        DWORD continuation = DBG_CONTINUE;
        if (event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT) {
            const auto& created = event.u.CreateProcessInfo;
            if (created.hFile) CloseHandle(created.hFile);
            receipt.imageBase = reinterpret_cast<std::uintptr_t>(created.lpBaseOfImage);
            Retain(threads, event.dwThreadId, created.hThread, receipt.imageBase + profile.entryRva, receipt);
        } else if (event.dwDebugEventCode == CREATE_THREAD_DEBUG_EVENT) {
            Retain(threads, event.dwThreadId, event.u.CreateThread.hThread, receipt.imageBase + profile.entryRva, receipt);
        } else if (event.dwDebugEventCode == EXIT_THREAD_DEBUG_EVENT) {
            const auto found = threads.entries.find(event.dwThreadId);
            Require(found != threads.entries.end(), "An exiting thread has no gate record.");
            CloseHandle(found->second.handle);
            threads.entries.erase(found);
        } else if (event.dwDebugEventCode == LOAD_DLL_DEBUG_EVENT) {
            if (event.u.LoadDll.hFile) CloseHandle(event.u.LoadDll.hFile);
        } else if (event.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT) {
            receipt.exited = true;
            receipt.exitCode = event.u.ExitProcess.dwExitCode;
        } else if (event.dwDebugEventCode == EXCEPTION_DEBUG_EVENT) {
            const auto& exception = event.u.Exception;
            const auto address = reinterpret_cast<std::uintptr_t>(exception.ExceptionRecord.ExceptionAddress);
            if (exception.ExceptionRecord.ExceptionCode == EXCEPTION_BREAKPOINT && !initialBreakpoint) {
                initialBreakpoint = true;
            } else if (exception.ExceptionRecord.ExceptionCode == EXCEPTION_SINGLE_STEP
                && address == receipt.imageBase + profile.entryRva) {
                const auto stopped = threads.entries.find(event.dwThreadId);
                Require(stopped != threads.entries.end(), "The stopped thread has no gate record.");
                const auto context = Context(stopped->second.handle);
                if (receipt.activated && (!stopped->second.gated || stopped->second.gateAcknowledged
                    || context.Rip != address || (context.Dr6 & 0xe000) != 0 || (context.EFlags & 0x100) != 0)) {
                    Require(ContinueDebugEvent(event.dwProcessId, event.dwThreadId, DBG_EXCEPTION_NOT_HANDLED) != FALSE,
                        "Cannot forward a nonowned single-step exception.");
                    continue;
                }
                Require(context.Rip == address && (receipt.activated || (context.Dr6 & 1) != 0),
                    "The exception is not the owned execute gate.");
                Require(stopped->second.gated, "The stopped thread never owned an allocation gate.");
                if (receipt.activated) {
                    auto live = context;
                    live.Dr0 = stopped->second.dr0;
                    live.Dr6 = stopped->second.dr6;
                    live.Dr7 = stopped->second.dr7;
                    Require(SetThreadContext(stopped->second.handle, &live) != FALSE,
                        "Cannot clear a pending allocation trap.");
                    Require(ContinueDebugEvent(event.dwProcessId, event.dwThreadId, DBG_CONTINUE) != FALSE,
                        "Cannot acknowledge a pending allocation trap.");
                    stopped->second.gateAcknowledged = true;
                    ++receipt.pendingTraps;
                    continue;
                }
                for (const auto& [id, thread] : threads.entries) {
                    (void)id;
                    const auto live = Context(thread.handle);
                    Require(live.Dr0 == address && (live.Dr7 & kDebugMask) == 1
                        && live.Dr1 == 0 && live.Dr2 == 0 && live.Dr3 == 0 && (live.EFlags & 0x100) == 0,
                        "A thread changed the debug-register contract.");
                }
                for (const auto rva : {profile.poolPointerRva, profile.hashPointerRva}) {
                    const auto pointer = ReadStopped(process.hProcess, receipt.imageBase + rva, sizeof(std::uintptr_t));
                    Require(std::all_of(pointer.begin(), pointer.end(), [](unsigned char value) { return value == 0; }),
                        "A server pool or hash already exists. Activation refused.");
                }
                for (const auto& check : profile.checks)
                    Require(ReadStopped(process.hProcess, receipt.imageBase + check.rva, check.bytes.size()) == check.bytes,
                        "The decrypted code does not match this profile.");
                std::vector<AddressEdit> edits;
                for (const auto& edit : profile.edits)
                    edits.push_back({receipt.imageBase + edit.rva, edit.original, edit.replacement});
                if (prepare) {
                    auto extra = prepare(process.hProcess, receipt);
                    edits.insert(edits.end(), std::make_move_iterator(extra.begin()), std::make_move_iterator(extra.end()));
                }
                PausedPatch patch(process.hProcess, std::move(edits), receipt);
                patch.Apply();
                for (const auto& [id, thread] : threads.entries) {
                    (void)id;
                    auto live = Context(thread.handle);
                    live.Dr0 = thread.dr0;
                    live.Dr6 = thread.dr6;
                    live.Dr7 = thread.dr7;
                    Require(SetThreadContext(thread.handle, &live) != FALSE, "Cannot restore a thread's debug registers.");
                    const auto restored = Context(thread.handle);
                    Require(restored.Dr0 == thread.dr0 && restored.Dr7 == thread.dr7,
                        "A thread retained the execute gate.");
                    ++receipt.restoredThreads;
                }
                receipt.stoppedThread = event.dwThreadId;
                stopped->second.gateAcknowledged = true;
                if (ready) ready(receipt);
                patch.Commit();
                receipt.activated = true;
            } else {
                continuation = DBG_EXCEPTION_NOT_HANDLED;
            }
        }
        Require(ContinueDebugEvent(event.dwProcessId, event.dwThreadId, continuation) != FALSE,
            "Cannot continue a debug event.");
        if (receipt.exited) return;
    }
}
}
