#pragma once
#include "../job_startup/Coordinator.h"
#include "../../patches/early_integrity/Plan.h"

namespace bo3::early_startup {
inline constexpr std::size_t kNativeEdits=42;
inline constexpr std::string_view kStartupMethod="late-crt-job-freeze-early-checksum";
struct Receipt {
    job_startup::Receipt job;
    bool checksumAdmitted=false;
    bool skipStartupIntro=false;
    bool customStartupIntro=false;
    std::uintptr_t checksumArena{};
    std::size_t checksumArenaBytes{},checksumEdits{};
    std::vector<unsigned char> checksumCapture;
};
void Coordinate(late_startup::OwnedChild&,job_startup::OwnedJob&,late_startup::MappedGate&,
    const late_startup::PreparePlan&,Receipt&);
void WriteReceipt(std::ostream&,const Receipt&);
#ifdef BO3_EARLY_OWNED_TEST
using PrepareChecksum=std::function<early_integrity::PreparedPlan(HANDLE,std::uintptr_t,
    std::span<const vm_startup::AddressEdit>)>;
void SetOwnedPrepareChecksum(PrepareChecksum);
#endif
}
