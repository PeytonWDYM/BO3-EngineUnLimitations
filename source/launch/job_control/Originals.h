#pragma once
#include "../enhanced/MappedHelper.h"
#include <string>
namespace bo3::job_control {
struct Original {std::string name;std::uintptr_t address;std::vector<unsigned char> bytes;};
std::vector<Original> StockOriginals(std::uintptr_t,const enhanced::MappedHelper&);
void VerifyOriginals(HANDLE,const std::vector<Original>&);
}
