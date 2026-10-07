#pragma once
#include "Probe.h"

namespace driver_probe {
// Read current routes and endpoint controls. This function has no setters.
std::string DeviceSnapshot(Trace& trace);
}
