#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <atomic>

struct Slot {
    std::uint64_t value;
    std::uint32_t type;
    std::uint32_t pad;
    std::uint64_t refs;
    std::uint32_t next;
    unsigned char rest[36];
};
static_assert(sizeof(Slot) == 64);
static_assert(offsetof(Slot, type) == 8 && offsetof(Slot, next) == 24);
struct State {
    Slot* pool;
    std::uint32_t deferred;
    std::uint32_t pad;
    const char* error;
    std::uint32_t depth;
};
extern "C" __declspec(dllexport) State vmFixtureState{};
static const char errorText[] = "owned fixture first error";
static std::uint32_t capacity = 256;
static Slot* storage;
static std::atomic<bool> running{true};

// The fixture owns all writes. The reader has no write protocol.
static void healthy() {
    std::memset(storage, 0, static_cast<size_t>(capacity) * sizeof(Slot));
    storage[0].next = 4;
    storage[1].type = 17;
    storage[2].type = 23;
    storage[2].next = 3;
    storage[3].type = 23;
    for (std::uint32_t i = 4; i < capacity; ++i) {
        storage[i].type = 27;
        storage[i].next = i + 1 < capacity ? i + 1 : 0;
    }
    vmFixtureState = {storage, 2, 0, errorText, 3};
}

static std::uint64_t checksum() {
    std::uint64_t hash = 14695981039346656037ULL;
    const auto* bytes = reinterpret_cast<const unsigned char*>(storage);
    for (size_t i = 0; i < static_cast<size_t>(capacity) * sizeof(Slot); ++i)
        hash = (hash ^ bytes[i]) * 1099511628211ULL;
    const auto* state = reinterpret_cast<const unsigned char*>(&vmFixtureState);
    for (size_t i = 0; i < sizeof(State); ++i) hash = (hash ^ state[i]) * 1099511628211ULL;
    return hash;
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const std::string mode = argv[1];
    if (mode == "changing") capacity = 130000;
    storage = static_cast<Slot*>(VirtualAlloc(nullptr, static_cast<size_t>(capacity) * sizeof(Slot),
                                            MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    if (!storage) return 3;
    healthy();
    if (mode == "uninitialized") vmFixtureState = {};
    else if (mode == "missing") vmFixtureState.pool = reinterpret_cast<Slot*>(1);
    else if (mode == "short") {
        auto* pages = static_cast<unsigned char*>(VirtualAlloc(nullptr, 8192, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
        if (!pages) return 4;
        DWORD old;
        if (!VirtualProtect(pages + 4096, 4096, PAGE_NOACCESS, &old)) return 5;
        vmFixtureState.pool = reinterpret_cast<Slot*>(pages + 4096 - sizeof(Slot));
    }
    else if (mode == "cycle") storage[capacity - 1].next = 4;
    else if (mode == "out-of-range") storage[4].next = capacity;
    else if (mode == "disagreement") storage[5].type = 17;
    else if (mode == "orphan-free") storage[0].next = 5;
    else if (mode == "deferred-cycle") storage[3].next = 2;
    else if (mode == "deferred-type") storage[2].type = 17;
    else if (mode == "deferred-range") vmFixtureState.deferred = capacity;
    else if (mode == "exhausted") {
        for (std::uint32_t i = 1; i < capacity; ++i) { storage[i].type = 17; storage[i].next = 0; }
        storage[0].next = 0;
        vmFixtureState.deferred = 0;
    }
    else if (mode == "unreadable-error") vmFixtureState.error = reinterpret_cast<const char*>(1);
    else if (mode == "boundary-error") {
        auto* pages = static_cast<char*>(VirtualAlloc(nullptr, 8192, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
        if (!pages) return 4;
        std::memcpy(pages + 4096 - sizeof(errorText), errorText, sizeof(errorText));
        DWORD old;
        if (!VirtualProtect(pages + 4096, 4096, PAGE_NOACCESS, &old)) return 5;
        vmFixtureState.error = pages + 4096 - sizeof(errorText);
    }
    else if (mode == "truncated-error") {
        auto* text = static_cast<char*>(VirtualAlloc(nullptr, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
        if (!text) return 6;
        std::memset(text, 'x', 4096);
        vmFixtureState.error = text;
    }
    else if (mode != "healthy" && mode != "changing" && mode != "exitsoon") return 7;
    std::thread changer;
    if (mode == "changing") changer = std::thread([] {
        const HANDLE timer = CreateWaitableTimerExW(nullptr, nullptr, 2, TIMER_ALL_ACCESS);
        if (!timer) ExitProcess(9);
        LARGE_INTEGER due;
        due.QuadPart = -5000;
        while (running.load()) {
            InterlockedIncrement64(reinterpret_cast<volatile LONG64*>(&storage[0].value));
            if (!SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE)) ExitProcess(10);
            if (WaitForSingleObject(timer, INFINITE) != WAIT_OBJECT_0) ExitProcess(11);
        }
        CloseHandle(timer);
    });
    if (mode == "exitsoon") std::thread([] { Sleep(600); ExitProcess(0); }).detach();
    std::printf("{\"pid\":%lu,\"capacity\":%u,\"stateSize\":%zu}\n", GetCurrentProcessId(), capacity, sizeof(State));
    std::fflush(stdout);
    char command[64];
    while (std::fgets(command, sizeof(command), stdin)) {
        if (std::strncmp(command, "recover", 7) == 0) { healthy(); std::puts("RECOVERED"); }
        else if (std::strncmp(command, "hash", 4) == 0) std::printf("%016llx\n", checksum());
        else if (std::strncmp(command, "stop", 4) == 0) break;
        else return 8;
        std::fflush(stdout);
    }
    running = false;
    if (changer.joinable()) changer.join();
    return 0;
}
