#include "Coordinator.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include <sstream>

namespace bo3::integrity_startup {
#ifdef BO3_INTEGRITY_OWNED_TEST
namespace {PrepareIntegrity ownedPrepare;}
void SetOwnedPrepareIntegrity(PrepareIntegrity prepare){ownedPrepare=std::move(prepare);}
void SetOwnedBeforeApply(std::function<void(HANDLE)> before){job_startup::SetOwnedBeforeApply(std::move(before));}
#endif
void Coordinate(late_startup::OwnedChild& child,job_startup::OwnedJob& job,late_startup::MappedGate& gate,
    const late_startup::PreparePlan& prepare,const std::array<unsigned char,32>& digest,Receipt& receipt) {
    const auto combined=[&](HANDLE process,std::uintptr_t image,vm_startup::Receipt& patchReceipt) {
        auto plan=prepare(process,image,patchReceipt);
        Require(plan.edits.size()==kNativeEdits && plan.relay,"The original complete 42-edit recipe is required.");
#ifdef BO3_INTEGRITY_OWNED_TEST
        auto integrity=ownedPrepare(process,image,digest,plan.edits);
#else
        auto integrity=bo3::code_integrity::PrepareStopped(process,image,digest,plan.edits);
#endif
        Require(integrity.size()==kIntegrityEdits,"The complete fixed integrity profile is required.");
        plan.edits.insert(plan.edits.end(),std::make_move_iterator(integrity.begin()),std::make_move_iterator(integrity.end()));
        receipt.integrityAdmitted=true;
        return plan;
    };
    job_startup::Coordinate(child,job,gate,combined,receipt.job,kNativeEdits+kIntegrityEdits);
}
void WriteReceipt(std::ostream& out,const Receipt& receipt) {
    std::ostringstream original;job_startup::WriteReceipt(original,receipt.job,kStartupMethod);
    auto bytes=original.str();Require(!bytes.empty() && bytes.back()=='}',"The base startup receipt is incomplete.");bytes.pop_back();
#ifdef BO3_INTEGRITY_OWNED_TEST
    const auto profile=kIntegrityProfileId,originalDigest=kIntegrityOriginalDigest,replacementDigest=kIntegrityReplacementDigest;
#else
    const auto profile=code_integrity::kProfileId,originalDigest=code_integrity::kOriginalDigest,
        replacementDigest=code_integrity::kReplacementDigest;
#endif
    out<<bytes<<",\"integrityProfile\":\""<<profile<<"\",\"integrityOriginalDigest\":\""<<originalDigest
       <<"\",\"integrityReplacementDigest\":\""<<replacementDigest<<"\",\"integrityAdmitted\":"
       <<(receipt.integrityAdmitted?"true":"false")<<",\"integrityPatternsAdmitted\":"<<(receipt.integrityAdmitted?kAdmittedPatterns:0)
       <<",\"integrityEditsPrepared\":"<<(receipt.integrityAdmitted?kIntegrityEdits:0)
       <<",\"integrityTransformsRetained\":"<<(receipt.integrityAdmitted?kRetainedTransforms:0)
       <<",\"nativeEditsRequired\":"<<kNativeEdits<<",\"combinedEditsRequired\":"<<kNativeEdits+kIntegrityEdits
       <<",\"integrityInputAttributionVerified\":"<<(code_integrity::kProductionInputAttributionVerified?"true":"false")
       <<",\"integrityReapplication\":false}";
    Require(out.good(),"Cannot write the integrity startup receipt.");
}
}
