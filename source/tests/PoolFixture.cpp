// Independent native pool states for snapshot diagnostics. No game code or layouts.
#include <cstddef>
#include <cstdint>

extern "C" __declspec(dllimport) void __stdcall Sleep(unsigned long milliseconds);

struct Entity {
    uint8_t inUse;
    uint8_t cleanupFlag;
    uint16_t type;
    int32_t freeTime;
    Entity *next;
};

struct State {
    Entity *pool;
    uint32_t highWater;
    int32_t time;
    Entity *head;
    Entity *tail;
};

static_assert(sizeof(Entity) == 16 && sizeof(State) == 32);
static_assert(offsetof(State, head) == 16 && offsetof(State, tail) == 24);

extern "C" {
    __declspec(dllexport) State Healthy{};
    __declspec(dllexport) State Exhausted{};
    __declspec(dllexport) State Recovered{};
    __declspec(dllexport) State Cyclic{};
    __declspec(dllexport) State InvalidFlag{};
    __declspec(dllexport) State InvalidPointer{};
    __declspec(dllexport) State Uninitialized{};
    __declspec(dllexport) State MissingMemory{};
    __declspec(dllexport) State MixedCleanupClock{};
}

void initialize(State &state, Entity *pool, uint32_t highWater) {
    state = {pool, highWater, 1000, nullptr, nullptr};
    for (uint32_t i = 0; i < highWater; ++i) {
        pool[i].inUse = 1;
        pool[i].type = i < 4 ? 1 : 25;
        pool[i].cleanupFlag = i >= 4 ? 1 : 0;
    }
}

int main() {
    static Entity pools[7][32]{};
    initialize(Healthy, pools[0], 10);
    pools[0][24].inUse = 1;
    pools[0][26].inUse = 1;
    initialize(Exhausted, pools[1], 24);
    initialize(Recovered, pools[2], 24);
    for (int i = 4; i < 24; ++i) {
        pools[2][i] = {0, 0, 0, 900, i < 23 ? &pools[2][i + 1] : nullptr};
    }
    Recovered.head = &pools[2][4];
    Recovered.tail = &pools[2][23];
    Cyclic = Recovered;
    Cyclic.pool = pools[3];
    pools[3][4].next = &pools[3][4];
    Cyclic.head = Cyclic.tail = &pools[3][4];
    initialize(InvalidFlag, pools[4], 10);
    pools[4][7].inUse = 9;
    initialize(InvalidPointer, pools[5], 10);
    InvalidPointer.head = InvalidPointer.tail = &pools[5][4];
    MissingMemory = {reinterpret_cast<Entity *>(0x123450000), 10, 1000, nullptr, nullptr};
    initialize(MixedCleanupClock, pools[6], 10);
    // One cleanup flag spans distinct numeric types. The clock is not a creation time.
    for (int i = 4; i < 10; ++i) {
        pools[6][i].type = i >= 6 && i < 8 ? 102 : 4;
        pools[6][i].cleanupFlag = i < 8 ? 1 : 0;
        pools[6][i].freeTime = i < 6 ? 950 : i < 8 ? 500 : 0;
    }
    Sleep(90000);
}
