#pragma once
#include "../job_startup/Coordinator.h"
#include "../../patches/code_integrity/Plan.h"
#include <array>

namespace bo3::integrity_startup {
inline constexpr std::size_t kNativeEdits=42,kIntegrityEdits=code_integrity::kEditCount,
    kAdmittedPatterns=code_integrity::kPatternCount,kRetainedTransforms=code_integrity::kRetainedTransformCount;
inline constexpr std::string_view kStartupMethod="late-crt-job-freeze-code-integrity";
struct Receipt {
    job_startup::Receipt job;
    bool integrityAdmitted=false;
};
void Coordinate(late_startup::OwnedChild&,job_startup::OwnedJob&,late_startup::MappedGate&,
    const late_startup::PreparePlan&,const std::array<unsigned char,32>& verifiedExecutableDigest,Receipt&);
void WriteReceipt(std::ostream&,const Receipt&);
#ifdef BO3_INTEGRITY_OWNED_TEST
using PrepareIntegrity=std::function<std::vector<vm_startup::AddressEdit>(HANDLE,std::uintptr_t,
    const std::array<unsigned char,32>&,std::span<const vm_startup::AddressEdit>)>;
void SetOwnedPrepareIntegrity(PrepareIntegrity);
void SetOwnedBeforeApply(std::function<void(HANDLE)>);
#endif
}
