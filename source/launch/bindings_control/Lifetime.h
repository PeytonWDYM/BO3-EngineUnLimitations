#pragma once
#include "Coordinator.h"
#include "../late_startup/PrivateReceipt.h"

namespace bo3::bindings_control {
void Retain(late_startup::OwnedChild&,job_startup::OwnedJob&,late_startup::PrivateReceipt&,Receipt&);
}
