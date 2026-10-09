#pragma once
#include "GateContract.h"

namespace bo3::startup_gate {
// Called only during process attach. Unknown loader state always forbids waiting.
bool AdmitLoaderSafety();
bool WithinLoaderCallout();
}
