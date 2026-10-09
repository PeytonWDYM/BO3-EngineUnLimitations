#pragma once
#include "GateContract.h"

namespace bo3::startup_gate {
using LoaderCallout=BOOLEAN(NTAPI*)();
extern Payload configuration;
extern LoaderCallout loaderCallout;
bool AdmitPayload();
}
