#pragma once
#include "../late_startup/FixedPlan.h"
#include "../job_control/Originals.h"

namespace bo3::bindings_control {
struct Observation {std::uintptr_t address;std::string before,after;};
struct Proof {
    std::vector<Observation> publications,stock;
    std::string bootBefore,bootAfter;
};
struct Selected {
    std::vector<vm_startup::AddressEdit> publications;
    std::vector<job_control::Original> stock;
};
Selected Select(const late_startup::PreparedPlan&,std::uintptr_t,const enhanced::MappedHelper&);
void Capture(HANDLE,const Selected&,const enhanced::MappedHelper&,Proof&,bool after);
}
