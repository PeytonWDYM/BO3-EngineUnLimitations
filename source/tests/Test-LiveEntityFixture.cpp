// Change native metadata while the external reader samples a large pool.
#include <cstdint>
#include <windows.h>

struct Entity {
    uint8_t inUse;
    uint8_t temporary;
    uint16_t type;
    int32_t freeTime;
    Entity *next;
    char padding[1008];
};

struct State {
    Entity *pool;
    uint32_t highWater;
    volatile int32_t time;
    Entity *head;
    Entity *tail;
};

static_assert(sizeof(Entity) == 1024 && sizeof(State) == 32);
extern "C" __declspec(dllexport) State Moving{};

int main() {
    static Entity pool[8192]{};
    Moving.pool = pool;
    Moving.highWater = 10;
    for (int i = 0; i < 10; ++i) pool[i].inUse = 1;
    HANDLE timer = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
    if (!timer) return 1;
    LARGE_INTEGER interval{};
    interval.QuadPart = -10000;
    for (int i = 0; i < 30000; ++i) {
        Moving.time = i;
        if (!SetWaitableTimer(timer, &interval, 0, nullptr, nullptr, FALSE)) return 2;
        WaitForSingleObject(timer, INFINITE);
    }
    CloseHandle(timer);
}
