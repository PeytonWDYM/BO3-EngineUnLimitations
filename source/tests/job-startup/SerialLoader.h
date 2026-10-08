#pragma once
#include "../../launch/late_startup/OwnedChild.h"
// Exact owned fixture setup only. Production never writes process parameters.
void ConfigureOwnedSerialLoader(const bo3::late_startup::OwnedChild&);
