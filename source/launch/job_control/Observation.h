#pragma once
#include "Originals.h"
#include "Receipt.h"
namespace bo3::job_control {
struct Observed {
    std::string name;std::uintptr_t address;std::vector<unsigned char> bytes;DWORD error;
    std::uintptr_t regionBase{};SIZE_T regionSize{};DWORD protect{},state{},type{},queryError{};
};
struct Snapshot {const char* phase;ULONGLONG tick;std::vector<Observed> rows;};
Snapshot Capture(HANDLE,std::uintptr_t,const std::vector<Original>&,const char*);
// The receipt retains directory locks while this CREATE_NEW sibling trace is open.
class Trace {
    HANDLE file_=INVALID_HANDLE_VALUE;
    std::vector<Observed> previous_;
    std::size_t bytes_=0,rows_=0;
public:
    explicit Trace(const std::filesystem::path& receipt);
    ~Trace();
    void Append(const Snapshot&,Receipt&);
};
}
