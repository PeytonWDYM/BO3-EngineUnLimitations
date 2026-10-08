#include "EnvironmentFixture.h"
#include "../../launch/enhanced/SteamContext.h"
#include "../../launch/preentry/Identity.h"
#include <cstdlib>
#include <fstream>
#include <iostream>

namespace {
DWORD Launch(const std::filesystem::path& executable,std::wstring command,std::vector<wchar_t>& environment) {
    STARTUPINFOW startup{}; startup.cb=sizeof(startup); PROCESS_INFORMATION child{};
    Require(CreateProcessW(executable.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW,
        environment.data(),nullptr,&startup,&child)!=FALSE,"Cannot launch fixed owned environment child.");
    const auto wait=WaitForSingleObject(child.hProcess,10000);
    if(wait!=WAIT_OBJECT_0) { TerminateProcess(child.hProcess,97); WaitForSingleObject(child.hProcess,5000); }
    DWORD exit=0; GetExitCodeProcess(child.hProcess,&exit);
    CloseHandle(child.hProcess); CloseHandle(child.hThread);
    Require(wait==WAIT_OBJECT_0,"Fixed owned environment child did not stop."); return exit;
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use fixed owned mode and private receipt or inherited mapping handle.");
        const std::wstring mode=argv[1];
        if(mode==L"probe") return ProbeChild(reinterpret_cast<HANDLE>(_wcstoui64(argv[2],nullptr,10)));
        Require(mode==L"parent" || mode==L"synthetic","Unknown owned environment mode.");
        const auto output=PrivateOutput(argv[2]);
        wchar_t path[32768]{}; Require(GetModuleFileNameW(nullptr,path,32768)!=0,"Cannot locate fixed owned executable.");
        const std::filesystem::path executable(path);
        const auto before=SnapshotEnvironment();
        if(mode==L"synthetic") {
            auto environment=SyntheticParent(before);
            const auto command=L"\""+executable.wstring()+L"\" parent \""+output.wstring()+L"\"";
            const auto exit=Launch(executable,command,environment);
            Require(before==SnapshotEnvironment(),"The outer parent environment changed.");
            return static_cast<int>(exit);
        }
        auto environment=enhanced::SteamChildEnvironment();
        const bool preserved=UnrelatedPreserved(before,environment);
        const bool constructionUnchanged=before==SnapshotEnvironment();
        SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,TRUE};
        Handle mapping(CreateFileMappingW(INVALID_HANDLE_VALUE,&attributes,PAGE_READWRITE,0,sizeof(EnvironmentTrace),nullptr));
        Require(mapping.value!=nullptr,"Cannot create owned environment receipt mapping.");
        auto* trace=static_cast<EnvironmentTrace*>(MapViewOfFile(mapping.value,FILE_MAP_WRITE,0,0,sizeof(EnvironmentTrace)));
        Require(trace!=nullptr,"Cannot inspect owned environment receipt."); ZeroMemory(trace,sizeof(*trace));
        const auto command=L"\""+executable.wstring()+L"\" probe "+std::to_wstring(reinterpret_cast<std::uintptr_t>(mapping.value));
        const auto exit=Launch(executable,command,environment);
        const bool unchanged=constructionUnchanged && before==SnapshotEnvironment();
        bool synthetic=false;
        for(const auto& entry:Entries(before)) synthetic |= entry==L"sTeAmApPiD=wrong-owned-app";
        const bool passed=exit==0 && unchanged && preserved && trace->done==1 && trace->idsFixed==1 && trace->idEntries==2
            && trace->hash==EnvironmentHash(environment) && (!synthetic || (trace->driveEntries>0 && trace->unicodeFixed==1));
        std::ofstream report(output);
        report<<"{\"passed\":"<<(passed ? "true" : "false")<<",\"syntheticParent\":"<<(synthetic ? "true" : "false")
            <<",\"parentUnchanged\":"<<(unchanged ? "true" : "false")<<",\"unrelatedPreserved\":"<<(preserved ? "true" : "false")
            <<",\"childExactBlock\":"<<(trace->hash==EnvironmentHash(environment) ? "true" : "false")<<",\"childIdsFixed\":"<<trace->idsFixed
            <<",\"idEntries\":"<<trace->idEntries<<",\"entryCount\":"<<trace->entries<<",\"driveEntries\":"<<trace->driveEntries
            <<",\"unicodeFixed\":"<<trace->unicodeFixed<<",\"childEnvironmentHash\":"<<trace->hash<<"}";
        Require(report.good(),"Cannot write owned environment receipt."); UnmapViewOfFile(trace); return passed ? 0 : 1;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 2; }
}
