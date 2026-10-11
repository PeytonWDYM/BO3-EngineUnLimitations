#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "../../launch/early_startup/GameLifetime.h"
#include <fstream>
#include <functional>
#include <iostream>
#include <string>
#include <vector>

void Require(bool value,const char* message){if(!value)throw std::runtime_error(message);}

namespace {
struct Child {
    PROCESS_INFORMATION process{};
    ~Child(){if(process.hThread)CloseHandle(process.hThread);if(process.hProcess)CloseHandle(process.hProcess);}
};
void Check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
}
int wmain(int argc,wchar_t** argv) {
    if(argc==3 && std::wstring_view(argv[1])==L"--child") {
        Sleep(150);return static_cast<int>(std::stoul(argv[2]));
    }
    try {
        Check(argc==2,"Use the owned output directory.");
        std::vector<wchar_t> image(32768);
        Check(GetModuleFileNameW(nullptr,image.data(),static_cast<DWORD>(image.size()))!=0,"Cannot locate the fixture.");
        unsigned int recorded=0;
        for(const DWORD code:{0UL,37UL}) {
            auto command=L"\""+std::wstring(image.data())+L"\" --child "+std::to_wstring(code);
            Child child;STARTUPINFOW startup{};startup.cb=sizeof(startup);
            Check(CreateProcessW(nullptr,command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&child.process)!=FALSE,
                "Cannot create the owned child.");
            bo3::job_startup::Receipt receipt;receipt.committed=true;receipt.released=true;
            receipt.patch.editsWritten=1158;receipt.stage="released";
            const auto path=std::filesystem::path(argv[1])/(std::to_wstring(code)+L"-exit.json");
            const auto exit=bo3::early_startup::RecordGameExit(child.process.hProcess,receipt,[&] {
                Check(WaitForSingleObject(child.process.hProcess,0)==WAIT_OBJECT_0,"The receipt was written before child exit.");
                Check(receipt.patch.exited && receipt.patch.exitCode==code && receipt.stage=="exited","The final receipt has stale exit state.");
                Check(receipt.committed && receipt.released && !receipt.terminated && receipt.patch.editsWritten==1158,
                    "Exit changed the startup transaction result.");
                std::ofstream file(path,std::ios::binary);
                file<<"{\"exited\":true,\"exitCode\":"<<receipt.patch.exitCode<<",\"stage\":\""<<receipt.stage
                    <<"\",\"committed\":true,\"editsWritten\":"<<receipt.patch.editsWritten<<"}\n";
                file.flush();Check(file.good(),"Cannot write the owned receipt.");++recorded;
            });
            Check(exit==code,"The launcher did not return the child exit code.");
            bo3::job_startup::Receipt failedWriter;
            bool writeFailed=false;
            std::function<void()> brokenWriter=[]{throw std::runtime_error("owned write refusal");};
            try {bo3::early_startup::RecordGameExit(child.process.hProcess,failedWriter,brokenWriter);}
            catch(const std::runtime_error&){writeFailed=true;}
            Check(writeFailed && failedWriter.patch.exited && failedWriter.patch.exitCode==code,"Receipt failure lost known exit state.");
        }
        bo3::job_startup::Receipt invalid;bool waitFailed=false,writerCalled=false;
        try {bo3::early_startup::RecordGameExit(nullptr,invalid,[&]{writerCalled=true;});}
        catch(const std::runtime_error&){waitFailed=true;}
        Check(waitFailed && !invalid.patch.exited && !writerCalled,"A failed wait invented exit state.");
        std::cout<<"{\"passed\":true,\"ownedChildren\":2,\"finalReceipts\":"<<recorded
            <<",\"nonzeroExitRecorded\":37,\"writerRefusals\":2,\"waitRefusals\":1,\"gameLaunched\":false}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
