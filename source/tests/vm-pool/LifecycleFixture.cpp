#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <atomic>

struct Arena { std::uint64_t kind, unused, start, size; };
struct State {
    std::uint64_t pool;
    std::int32_t serverTime;
    std::uint32_t padding;
    std::uint64_t entities;
    alignas(8) unsigned char record[0xf68];
};
extern "C" __declspec(dllexport) State lifecycleState{};
extern "C" __declspec(dllexport) __declspec(noinline) int lifecycleFixtureGuard() { return 13579; }
static Arena arena{};
static char names[2][128] = {"$init", "Level"};
static std::atomic<bool> running{true};

template<class T> static void set(std::size_t offset, T value) {
    std::memcpy(lifecycleState.record + offset, &value, sizeof(value));
}

static std::uint64_t checksum() {
    std::uint64_t result = 14695981039346656037ULL;
    const auto hash = [&result](const void* p, std::size_t n) {
        const auto* bytes = static_cast<const unsigned char*>(p);
        for (std::size_t i = 0; i < n; ++i) result = (result ^ bytes[i]) * 1099511628211ULL;
    };
    hash(&lifecycleState, sizeof(lifecycleState));
    hash(&arena, sizeof(arena));
    hash(names, sizeof(names));
    return result;
}

// Only this owned process changes the metadata. Pool contents remain PAGE_NOACCESS.
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const std::string mode = argv[1];
    void* reservation = VirtualAlloc(nullptr, 0x200000, MEM_RESERVE, PAGE_NOACCESS);
    if (!reservation) return 3;
    arena = {2, 0, reinterpret_cast<std::uint64_t>(reservation), 0x200000};
    lifecycleState.pool = arena.start + 0x3000;
    lifecycleState.entities = arena.start + 0x5000;
    lifecycleState.serverTime = 1000;
    set<std::uint64_t>(0x10, 0x10000);
    set<std::uint32_t>(0x38, 2);
    set<std::uint64_t>(0x40, reinterpret_cast<std::uint64_t>(names[0]));
    set<std::uint64_t>(0x48, 0);
    set<std::uint64_t>(0x70, reinterpret_cast<std::uint64_t>(names[1]));
    set<std::uint64_t>(0x78, 0x2000);
    set<std::uint64_t>(0xf40, reinterpret_cast<std::uint64_t>(&arena));
    if (mode == "uninitialized") lifecycleState = {};
    else if (mode == "bad-descriptor") set<std::uint64_t>(0xf40, 1);
    else if (mode == "bad-name") set<std::uint64_t>(0x40, 1);
    else if (mode == "long-name") std::memset(names[0], 'x', sizeof(names[0]));
    else if (mode == "mark-count") set<std::uint32_t>(0x38, 81);
    else if (mode == "cursor-overflow") set<std::uint64_t>(0x10, arena.size + 1);
    else if (mode == "pool-outside") lifecycleState.pool = arena.start + arena.size;
    else if (mode == "descending-marks") { set<std::uint64_t>(0x48, 0x4000); set<std::uint64_t>(0x78, 0x2000); }
    else if (mode != "healthy" && mode != "changing" && mode != "exitsoon") return 4;
    std::thread changer;
    if (mode == "changing") changer = std::thread([] {
        auto* value = reinterpret_cast<volatile LONG64*>(lifecycleState.record + 0x50);
        while (running.load()) InterlockedIncrement64(value);
    });
    if (mode == "exitsoon") std::thread([] { Sleep(1000); ExitProcess(0); }).detach();
    FILETIME created{}, exited{}, kernel{}, user{};
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user)) return 5;
    const auto ticks = (static_cast<std::uint64_t>(created.dwHighDateTime) << 32) | created.dwLowDateTime;
    std::printf("{\"pid\":%lu,\"startTicks\":%llu}\n", GetCurrentProcessId(), ticks);
    std::fflush(stdout);
    char command[64];
    while (std::fgets(command, sizeof(command), stdin)) {
        if (std::strncmp(command, "hash", 4) == 0) std::printf("%016llx\n", checksum());
        else if (std::strncmp(command, "replace", 7) == 0) {
            lifecycleState.pool += 0x1000;
            lifecycleState.entities += 0x1000;
            lifecycleState.serverTime = 0;
            std::memcpy(names[1], "Reloaded", sizeof("Reloaded"));
            std::puts("REPLACED");
        } else if (std::strncmp(command, "retain", 6) == 0) {
            lifecycleState.serverTime = 0;
            std::puts("RETAINED");
        } else if (std::strncmp(command, "stop", 4) == 0) break;
        else return 6;
        std::fflush(stdout);
    }
    running = false;
    if (changer.joinable()) changer.join();
    VirtualFree(reservation, 0, MEM_RELEASE);
    return 0;
}
