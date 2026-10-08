#include "Lifetime.h"
#include "../preentry/Identity.h"
#include <memory>
#include <iostream>

namespace bo3::job_control {
void Retain(late_startup::OwnedChild& child,const job_startup::OwnedJob& job,const Admitted& admitted,
    late_startup::PrivateReceipt& report,Receipt& receipt) {
    std::unique_ptr<Trace> trace;
    try {trace=std::make_unique<Trace>(report.Path());trace->Append(admitted.frozen,receipt);}
    catch(const std::exception& error){receipt.traceFailed=true;receipt.observationReason=std::string(error.what()).substr(0,512);trace.reset();}
    const auto persist=[&]{try{report.Write(receipt);}catch(const std::exception& error){std::cerr<<error.what()<<'\n';}};
    persist();
    for(;;) {
        const auto state=WaitForSingleObject(child.process.hProcess,1000);
        Require(state==WAIT_OBJECT_0 || state==WAIT_TIMEOUT,"Cannot retain the owned stock control lifetime.");
        if(state==WAIT_OBJECT_0)break;
        if(!trace || receipt.traceTruncated)continue;
        try {
            process_freeze::RequireIdentity(child.process.hProcess,job.Identity());
            trace->Append(Capture(child.process.hProcess,admitted.guardImage,admitted.originals,"running"),receipt);
            if(receipt.traceTruncated)persist();
        }catch(const std::exception& error) {
            receipt.traceFailed=true;receipt.observationReason=std::string(error.what()).substr(0,512);trace.reset();persist();
        }
    }
    Require(GetExitCodeProcess(child.process.hProcess,&receipt.exitCode)!=FALSE,"Cannot read the owned stock control exit code.");
    receipt.exited=true;receipt.native.stage="exited";receipt.phases.push_back({"exited",GetTickCount64()});persist();
}
}
