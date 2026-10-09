#include "../../launch/integrity_startup/Coordinator.h"
#include "BuildIdentity.h"
#include <filesystem>
#include <fstream>

int wmain(int argc,wchar_t** argv) {
    if(argc!=8)return 2;
    const auto target=std::filesystem::path(argv[6]);
    if(target.filename()!=L"IntegrityEnrollmentFixture.exe")return 3;
    const auto pid=static_cast<DWORD>(std::stoul(argv[1]));
    const auto created=std::stoull(argv[2]),image=std::stoull(argv[3]),helper=std::stoull(argv[4]);
    const auto primary=static_cast<DWORD>(std::stoul(argv[5]));
    auto handle=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);if(!handle)return 4;
    FILETIME times[4]{};DWORD exit{};wchar_t path[32768]{};DWORD size=32768;
    const auto same=GetProcessTimes(handle,&times[0],&times[1],&times[2],&times[3])
        && ((static_cast<std::uint64_t>(times[0].dwHighDateTime)<<32)|times[0].dwLowDateTime)==created
        && QueryFullProcessImageNameW(handle,0,path,&size) && std::filesystem::equivalent(target,path)
        && GetExitCodeProcess(handle,&exit) && exit==STILL_ACTIVE;
    CloseHandle(handle);if(!same)return 5;
    bo3::integrity_startup::Receipt r;r.integrityAdmitted=true;auto& job=r.job;
    job.processId=pid;job.created=created;job.primaryThreadId=primary;job.generation=1;
    job.image=target.wstring();job.patch.imageBase=image;job.helperBase=helper;job.gateBase=helper;
    job.primaryPc=image+1;job.relay=image+1;job.threadsObserved=1;
    job.jobAssigned=true;job.freezeAttempted=true;job.frozen=true;job.membershipVerified=true;
    job.primaryAdmitted=true;job.thawAttempted=true;job.thawed=true;job.committed=true;
    job.debuggerAbsent=true;job.released=true;job.patch.editsWritten=1395;
    job.stage="released";job.runtimeMetadataReads=16;job.runtimeMetadataMask=3;
    job.frames={image+1};job.threads={{primary,image+1,image+1}};
    std::ofstream output(argv[7]);bo3::integrity_startup::WriteReceipt(output,r);return output.good()?0:6;
}
