#include "Coordinator.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include <iomanip>
namespace bo3::bindings_control {
namespace {
void JsonPath(std::ostream& out,std::wstring_view path) {
    out<<'"';
    for(const auto c:path) {
        if(c==L'\\' || c==L'"')out<<'\\';
        if(c>=32 && c<127)out<<static_cast<char>(c);
        else out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<static_cast<unsigned int>(c)<<std::dec;
    }
    out<<'"';
}
}
void WriteReceipt(std::ostream& out,const Receipt& result) {
    const auto& r=result.native;const auto yes=[](bool value){return value?"true":"false";};
    out<<"{\"schema\":1,\"candidate\":\"0.1.0-test.3\",\"startupMethod\":\"late-crt-job-freeze-bindings-control\""
       <<",\"capacity\":\"stock\",\"serverTotal\":130000,\"serverUsable\":129999,\"clientTotal\":65000,\"clientRoots\":8,\"migrationPolicy\":\"stock\""
       <<",\"intendedUnpublishedServerTotal\":500001,\"intendedUnpublishedClientRoots\":18,\"intendedUnpublishedMigrationBufferBytes\":33554432"
       <<",\"expandedPoolEnrollment\":false,\"gameInstructionEdits\":0,\"hookActivation\":false,\"gateDeadlineMs\":30000,\"observationLimitMs\":120000"
       <<",\"processId\":"<<r.processId<<",\"processCreatedFileTime\":"<<r.created<<",\"primaryThreadId\":"<<r.primaryThreadId
       <<",\"imagePath\":";JsonPath(out,r.image);
    out<<",\"executableSha256\":\""<<kGameHash<<"\",\"helperSha256\":\""<<kHelperHash<<"\",\"gateSha256\":\""<<kGateHash<<'"'
       <<",\"generation\":"<<r.generation<<",\"imageBase\":"<<r.patch.imageBase<<",\"helperBase\":"<<r.helperBase<<",\"gateBase\":"<<r.gateBase
       <<",\"jobOwned\":"<<yes(r.jobAssigned)<<",\"jobParentOnly\":true,\"killOnJobClose\":true"
       <<",\"freezeAttempted\":"<<yes(r.freezeAttempted)<<",\"freezeStatus\":"<<r.freezeStatus<<",\"frozenForTransaction\":"<<yes(r.frozen)
       <<",\"jobMembershipVerified\":"<<yes(r.membershipVerified)<<",\"threadsObserved\":"<<r.threadsObserved<<",\"primaryPc\":"<<r.primaryPc
       <<",\"primaryOnlyAdmitted\":"<<yes(r.primaryAdmitted)<<",\"thawAttempted\":"<<yes(r.thawAttempted)<<",\"thawStatus\":"<<r.thawStatus
       <<",\"thawed\":"<<yes(r.thawed)<<",\"editsWritten\":"<<r.patch.editsWritten<<",\"rollbackCompleted\":"<<yes(r.patch.rollbackCompleted)
       <<",\"relay\":"<<r.relay<<",\"relayFreed\":"<<yes(r.relayFreed)<<",\"committed\":"<<yes(r.committed)
       <<",\"debuggerAbsent\":"<<yes(r.debuggerAbsent)<<",\"released\":"<<yes(r.released)<<",\"terminated\":"<<yes(r.terminated)
       <<",\"cleanupFailed\":"<<yes(r.cleanupFailed)<<",\"exited\":"<<yes(r.patch.exited)<<",\"exitCode\":"<<r.patch.exitCode
       <<",\"stage\":";JsonPath(out,std::wstring(r.stage.begin(),r.stage.end()));
    out<<",\"refusalReason\":";JsonPath(out,std::wstring(r.refusalReason.begin(),r.refusalReason.end()));
    out<<",\"unwindReason\":";JsonPath(out,std::wstring(r.unwindReason.begin(),r.unwindReason.end()));
    out<<",\"unwindLookupPc\":"<<r.unwindLookupPc<<",\"runtimeMetadataReads\":"<<r.runtimeMetadataReads
       <<",\"runtimeMetadataMask\":"<<r.runtimeMetadataMask
       <<",\"attached\":false,\"detached\":false,\"liveAllocationValidated\":false,\"debugRegisterWrites\":0,\"frames\":[";
    bool first=true;for(const auto pc:r.frames){if(!first)out<<',';first=false;out<<pc;}
    out<<"],\"threadObservations\":[";first=true;
    for(const auto& row:r.threads){if(!first)out<<',';first=false;
        out<<"{\"threadId\":"<<row.id<<",\"pc\":"<<row.pc<<",\"start\":"<<row.start<<'}';}
    out<<"],\"stockReadOnlyAdmitted\":"<<yes(result.stockAdmitted)<<",\"stock33Verified\":"<<yes(result.stockVerified)
       <<",\"deadlineTerminated\":"<<yes(result.deadlineTerminated)<<",\"persistFailed\":"<<yes(result.persistFailed)
       <<",\"releasedTick\":"<<result.releasedTick<<",\"exitTick\":"<<result.exitTick;
    const auto observations=[&](const char* name,const std::vector<Observation>& rows) {
        out<<",\""<<name<<"\":[";bool initial=true;
        for(const auto& row:rows){if(!initial)out<<',';initial=false;
            out<<"{\"address\":"<<row.address<<",\"before\":\""<<row.before<<"\",\"after\":\""<<row.after<<"\"}";}
        out<<']';
    };
    observations("publicationReadbacks",result.proof.publications);observations("stockSpanSha256",result.proof.stock);
    out<<",\"helperBootBefore\":\""<<result.proof.bootBefore<<"\",\"helperBootAfter\":\""<<result.proof.bootAfter<<"\"}";
    Require(out.good(),"Cannot serialize the bindings-only diagnostic receipt.");
}
}
