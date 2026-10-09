#include "Receipt.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include <iomanip>

namespace bo3::job_control {
namespace {
void String(std::ostream& out,std::wstring_view text) {
    out<<'"';for(const auto c:text) {
        if(c==L'\\' || c==L'"')out<<'\\';
        if(c>=32 && c<127)out<<static_cast<char>(c);
        else out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<static_cast<unsigned int>(c)<<std::dec;
    }out<<'"';
}
void String(std::ostream& out,const std::string& text){String(out,std::wstring(text.begin(),text.end()));}
}
void WriteReceipt(std::ostream& out,const Receipt& r) {
    const auto yes=[](bool value){return value?"true":"false";};const auto& n=r.native;
    out<<"{\"schema\":1,\"startupMethod\":\"late-crt-job-freeze-control\",\"capacity\":\"stock\",\"serverTotal\":130000"
       <<",\"serverUsable\":129999,\"clientTotal\":65000,\"clientRoots\":8,\"migrationPolicy\":\"stock\",\"gateDeadlineMs\":30000"
       <<",\"processId\":"<<n.processId<<",\"processCreatedFileTime\":"<<n.created<<",\"primaryThreadId\":"<<n.primaryThreadId
       <<",\"imagePath\":";String(out,n.image);
    out<<",\"executableSha256\":\""<<kGameHash<<"\",\"helperSha256\":\""<<kHelperHash<<"\",\"gateSha256\":\""<<kGateHash<<'"'
       <<",\"imageBase\":"<<n.patch.imageBase<<",\"helperBase\":"<<n.helperBase<<",\"gateBase\":"<<n.gateBase<<",\"generation\":"<<n.generation
       <<",\"jobOwned\":"<<yes(n.jobAssigned)<<",\"jobParentOnly\":true,\"killOnJobClose\":true,\"jobMembershipVerified\":"<<yes(n.membershipVerified)
       <<",\"freezeAttempted\":"<<yes(n.freezeAttempted)<<",\"freezeStatus\":"<<n.freezeStatus<<",\"frozenForTransaction\":"<<yes(n.frozen)
       <<",\"threadsObserved\":"<<n.threadsObserved<<",\"primaryPc\":"<<n.primaryPc<<",\"primaryOnlyAdmitted\":"<<yes(n.primaryAdmitted)
       <<",\"runtimeMetadataReads\":"<<n.runtimeMetadataReads<<",\"runtimeMetadataMask\":"<<n.runtimeMetadataMask
       <<",\"stockReadOnlyAdmitted\":"<<yes(r.stockAdmitted)<<",\"stockOriginalsVerified\":"<<yes(r.originalsVerified)
       <<",\"stockOriginalsObserved\":"<<r.originalsObserved<<",\"bindingsUnchanged\":"<<yes(r.bindingsUnchanged)
       <<",\"thawAttempted\":"<<yes(n.thawAttempted)<<",\"thawStatus\":"<<n.thawStatus<<",\"thawed\":"<<yes(n.thawed)
       <<",\"debuggerAbsent\":"<<yes(n.debuggerAbsent)<<",\"released\":"<<yes(n.released)<<",\"terminated\":"<<yes(n.terminated)
       <<",\"cleanupFailed\":"<<yes(n.cleanupFailed)<<",\"exited\":"<<yes(r.exited)<<",\"exitCode\":"<<r.exitCode
       <<",\"traceFailed\":"<<yes(r.traceFailed)<<",\"traceTruncated\":"<<yes(r.traceTruncated)
       <<",\"committed\":false,\"editsWritten\":0,\"relay\":0,\"relayAllocations\":0,\"transactionRemoteWrites\":0"
       <<",\"attached\":false,\"detached\":false,\"debugRegisterWrites\":0,\"expandedPoolEnrollment\":false,\"liveAllocationValidated\":false,\"stage\":";
    String(out,n.stage);out<<",\"refusalReason\":";String(out,n.refusalReason);out<<",\"unwindReason\":";String(out,n.unwindReason);
    out<<",\"observationReason\":";String(out,r.observationReason);
    out<<",\"unwindLookupPc\":"<<n.unwindLookupPc<<",\"phases\":[";bool first=true;
    for(const auto& phase:r.phases){if(!first)out<<',';first=false;out<<"{\"name\":\""<<phase.name<<"\",\"tick\":"<<phase.tick<<'}';}
    out<<"],\"frames\":[";first=true;
    for(const auto pc:n.frames){if(!first)out<<',';first=false;out<<pc;}
    out<<"],\"threadObservations\":[";first=true;
    for(const auto& thread:n.threads){if(!first)out<<',';first=false;
        out<<"{\"threadId\":"<<thread.id<<",\"pc\":"<<thread.pc<<",\"start\":"<<thread.start<<'}';}
    out<<"]}";Require(out.good(),"Cannot serialize the stock job control receipt.");
}
}
