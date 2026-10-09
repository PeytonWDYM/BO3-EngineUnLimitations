#pragma once
#include "Coordinator.h"
#include "../late_startup/PrivateReceipt.h"
namespace bo3::job_control {
// Optional sequential observations cannot end the released owned child.
void Retain(late_startup::OwnedChild&,const job_startup::OwnedJob&,const Admitted&,late_startup::PrivateReceipt&,Receipt&);
}
