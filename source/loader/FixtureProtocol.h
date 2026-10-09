#pragma once
#include <Windows.h>

namespace patch {
// The target owns this mapping. A resume event releases only its exact request
// generation. A named mutex allows one loader to own the complete session.
struct alignas(8) FixtureProtocol {
    volatile LONG64 requested_generation;
    volatile LONG64 ready_generation;
    volatile LONG64 resume_generation;
};
static_assert(sizeof(FixtureProtocol) == 24);
}
