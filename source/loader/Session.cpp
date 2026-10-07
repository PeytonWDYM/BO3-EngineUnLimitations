#include "Session.h"
#include "MemoryPatch.h"
#include "FixtureProtocol.h"
#include <iostream>

namespace patch {
class ProtocolMapping {
public:
    explicit ProtocolMapping(DWORD pid) {
        const auto name = L"Local\\BO3PatchFixture.Protocol." + std::to_wstring(pid);
        mapping_ = Handle(OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, FALSE, name.c_str()));
        if (!mapping_.get()) throw win_error("Open fixture protocol mapping");
        view_ = static_cast<FixtureProtocol*>(MapViewOfFile(mapping_.get(), FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, sizeof(FixtureProtocol)));
        if (!view_) throw win_error("Map fixture protocol");
    }
    ~ProtocolMapping() { UnmapViewOfFile(view_); }
    FixtureProtocol& get() { return *view_; }
private:
    Handle mapping_;
    FixtureProtocol* view_ = nullptr;
};

class SafePoint {
public:
    explicit SafePoint(const Target& target) : target_(target), request_(open_event(L"Request")), ready_(open_event(L"Ready")), resume_(open_event(L"Resume")), protocol_(target.pid()) {
        const auto name = L"Local\\BO3PatchFixture.Owner." + std::to_wstring(target.pid());
        owner_ = Handle(OpenMutexW(SYNCHRONIZE | MUTEX_MODIFY_STATE, FALSE, name.c_str()));
        if (!owner_.get()) throw win_error("Open fixture session owner");
        const DWORD result = WaitForSingleObject(owner_.get(), 0);
        if (result == WAIT_ABANDONED) {
            ReleaseMutex(owner_.get());
            throw std::runtime_error("A previous loader abandoned this session. Restart the fixture to recover.");
        }
        if (result == WAIT_TIMEOUT) throw std::runtime_error("Another loader already owns this target session.");
        if (result != WAIT_OBJECT_0) throw win_error("Acquire fixture session owner");
    }
    ~SafePoint() {
        if (parked_) {
            InterlockedExchange64(&protocol_.get().resume_generation, generation_);
            SetEvent(resume_.get());
        }
        ReleaseMutex(owner_.get());
    }

    void enter() {
        generation_ = InterlockedIncrement64(&protocol_.get().requested_generation);
        if (!ResetEvent(ready_.get()) || !SetEvent(request_.get())) throw win_error("Request safe point");
        const HANDLE waits[]{ready_.get(), target_.process()};
        const auto deadline = GetTickCount64() + 5000;
        while (true) {
            if (InterlockedCompareExchange64(&protocol_.get().ready_generation, 0, 0) == generation_) {
                parked_ = true;
                if (target_.exited()) throw std::runtime_error("Target exited at its safe point.");
                return;
            }
            const auto now = GetTickCount64();
            const DWORD result = now >= deadline ? WAIT_TIMEOUT : WaitForMultipleObjects(2, waits, FALSE, static_cast<DWORD>(deadline - now));
            if (result == WAIT_OBJECT_0) {
                if (!ResetEvent(ready_.get())) throw win_error("Clear stale safe-point signal");
                continue;
            }
            // A cancellation authorizes only this generation. A stale event cannot
            // release a later request, even if the target signals Ready late.
            ResetEvent(request_.get());
            InterlockedExchange64(&protocol_.get().resume_generation, generation_);
            SetEvent(resume_.get());
            if (result == WAIT_FAILED) throw win_error("Wait for safe point");
            throw std::runtime_error(result == WAIT_OBJECT_0 + 1 ? "Target exited before its safe point." : "Target safe-point timeout.");
        }
    }

    void leave() {
        InterlockedExchange64(&protocol_.get().resume_generation, generation_);
        if (!SetEvent(resume_.get())) throw win_error("Release safe point");
        parked_ = false;
    }
    void keep_parked() {
        parked_ = false;
        std::cerr << "Target remains at its safe point because memory restoration is incomplete. Restart the fixture to recover.\n";
    }
private:
    Handle open_event(const std::wstring& name) {
        const auto full = L"Local\\BO3PatchFixture." + name + L"." + std::to_wstring(target_.pid());
        Handle event(OpenEventW(SYNCHRONIZE | EVENT_MODIFY_STATE, FALSE, full.c_str()));
        if (!event.get()) throw win_error("Open fixture safe-point contract");
        return event;
    }
    const Target& target_;
    Handle request_, ready_, resume_;
    ProtocolMapping protocol_;
    Handle owner_;
    LONG64 generation_ = 0;
    bool parked_ = false;
};

void run_session(const Target& target, const Profile& profile, DWORD hold_ms) {
    if (profile.safety != "fixture-cooperative-v2") throw std::runtime_error("Unsupported target safe-point contract.");
    SafePoint safe_point(target);
    safe_point.enter();
    try {
        apply_records(target, profile.records);
    } catch (const IncompleteMutation&) {
        safe_point.keep_parked();
        throw;
    }
    safe_point.leave();
    const DWORD wait = WaitForSingleObject(target.process(), hold_ms);
    if (wait == WAIT_OBJECT_0) {
        std::cout << "target exited. Runtime patch no longer exists.\n";
        return;
    }
    if (wait == WAIT_FAILED) throw win_error("Wait for patch session");
    safe_point.enter();
    try {
        remove_records(target, profile.records);
    } catch (...) {
        safe_point.keep_parked();
        throw;
    }
    safe_point.leave();
}
}
