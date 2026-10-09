#include "Coordinator.h"
#include "../preentry/Identity.h"
#include <sstream>

namespace bo3::early_startup {
#ifdef BO3_EARLY_OWNED_TEST
namespace {PrepareChecksum ownedPrepare;}
void SetOwnedPrepareChecksum(PrepareChecksum prepare){ownedPrepare=std::move(prepare);}
#endif
void Coordinate(late_startup::OwnedChild& child,job_startup::OwnedJob& job,late_startup::MappedGate& gate,
    const late_startup::PreparePlan& prepare,const std::array<unsigned char,32>& digest,Receipt& receipt) {
    const auto combined=[&](HANDLE process,std::uintptr_t image,vm_startup::Receipt& patchReceipt) {
        auto plan=prepare(process,image,patchReceipt);
        Require(plan.edits.size()==kNativeEdits && plan.relay && !plan.commitResources,
            "The original complete 42-edit native recipe is required.");
        auto checksum=[&] {
            try {
#ifdef BO3_EARLY_OWNED_TEST
                return ownedPrepare(process,image,digest,plan.edits);
#else
                return early_integrity::PrepareStopped(process,image,digest,plan.edits);
#endif
            }catch(const early_integrity::ContextMismatch& error){receipt.checksumCapture=error.capture;throw;}
        }();
        Require(checksum.edits.size()==early_integrity::kPublicationCount && checksum.arena,
            "The complete early checksum recipe is required.");
        receipt.checksumArena=checksum.arena->address();
        receipt.checksumArenaBytes=checksum.arena->size();
        receipt.checksumEdits=checksum.edits.size();
        plan.edits.insert(plan.edits.end(),std::make_move_iterator(checksum.edits.begin()),
            std::make_move_iterator(checksum.edits.end()));
        // Keep the arena owned until rollback finishes or commit retains it before thaw.
        plan.commitResources=[arena=std::move(checksum.arena)]() noexcept {arena->Commit();};
        receipt.checksumAdmitted=true;
        return plan;
    };
    job_startup::Coordinate(child,job,gate,combined,receipt.job,kNativeEdits+early_integrity::kPublicationCount);
}
void WriteReceipt(std::ostream& out,const Receipt& receipt) {
    std::ostringstream original;job_startup::WriteReceipt(original,receipt.job,kStartupMethod);
    auto bytes=original.str();Require(!bytes.empty() && bytes.back()=='}',"The base startup receipt is incomplete.");
    bytes.pop_back();
    out<<bytes<<",\"earlyChecksumProfile\":\""<<early_integrity::kProfileId
       <<"\",\"checksumAdmitted\":"<<(receipt.checksumAdmitted?"true":"false")
       <<",\"checksumSitesRequired\":"<<early_integrity::kSiteCount
       <<",\"checksumEditsPrepared\":"<<receipt.checksumEdits
       <<",\"checksumArena\":"<<receipt.checksumArena<<",\"checksumArenaBytes\":"<<receipt.checksumArenaBytes
       <<",\"checksumCaptureBytes\":"<<receipt.checksumCapture.size()
       <<",\"nativeEditsRequired\":"<<kNativeEdits
       <<",\"combinedEditsRequired\":"<<kNativeEdits+early_integrity::kPublicationCount
       <<",\"checksumReapplication\":false,\"aaeStoreSitesPreserved\":"<<(receipt.checksumAdmitted?"true":"false")<<'}';
    Require(out.good(),"Cannot write the early checksum receipt.");
}
}
