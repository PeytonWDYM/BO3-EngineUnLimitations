#pragma once
#include "Target.h"

namespace patch {
void run_session(const Target& target, const Profile& profile, DWORD hold_ms);
}
