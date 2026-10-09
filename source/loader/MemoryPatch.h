#pragma once
#include "Target.h"

namespace patch {
class IncompleteMutation : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

void apply_records(const Target& target, const std::vector<Record>& records);
void remove_records(const Target& target, const std::vector<Record>& records);
}
