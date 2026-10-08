#include "Observation.h"
#include "../preentry/Identity.h"
#include <array>
#include <cstring>
#include <iomanip>
#include <sstream>

namespace bo3::job_control {
Snapshot Capture(HANDLE process,std::uintptr_t image,const std::vector<Original>& originals,const char* phase) {
    Snapshot result{phase,GetTickCount64(),{}};
    const auto read=[&](const char* name,std::uintptr_t address,DWORD size) {
        Observed row{name,address,std::vector<unsigned char>(size),0};SIZE_T count{};
        if(!ReadProcessMemory(process,reinterpret_cast<void*>(address),row.bytes.data(),size,&count) || count!=size) {
            row.error=GetLastError();if(!row.error)row.error=ERROR_PARTIAL_COPY;row.bytes.clear();
        }
        MEMORY_BASIC_INFORMATION page{};
        if(VirtualQueryEx(process,reinterpret_cast<void*>(address),&page,sizeof(page))==sizeof(page)) {
            row.regionBase=reinterpret_cast<std::uintptr_t>(page.BaseAddress);row.regionSize=page.RegionSize;
            row.protect=page.Protect;row.state=page.State;row.type=page.Type;
        }else row.queryError=GetLastError();
        result.rows.push_back(std::move(row));
    };
    read("valid-native-stub",image+0x22b9b50,68);
    std::int32_t displacement{};
    const auto& stub=result.rows.front();bool follows=false;
    if(stub.bytes.size()>=5 && stub.bytes[0]==0xe9) {
        std::memcpy(&displacement,stub.bytes.data()+1,4);
        follows=static_cast<std::int64_t>(0x22b9b55)+displacement==0x1cb94212;
    }
    if(follows)read("verified-forward",image+0x1cb94212,54);
    else result.rows.push_back({"verified-forward",image+0x1cb94212,{},ERROR_INVALID_DATA});
    const std::array<std::pair<DWORD,DWORD>,8> ranges{{{0x147f130,7941},{0x1a850000,24},{0x314027c,52},
        {0x1484178,120},{0x4c98c80,8},{0x35eea10,16},{0x22b1559,5},{0x227a3a0,64}}};
    for(const auto& [rva,size]:ranges)read("native-observation",image+rva,size);
    const std::array<std::pair<DWORD,DWORD>,12> storage{{{0x5124580,8},{0x5124500,8},{0x5124680,8},{0x5124600,8},
        {0x3ec4ed8,8},{0x3ec4ee0,8},{0x3ec4ee8,8},{0x3ec4ef0,8},{0x16dbb638,8},
        {0x3ec4ef8,4},{0x3ec4efc,4},{0x16dbb640,4}}};
    for(const auto& [rva,size]:storage)read("vm-migration-storage",image+rva,size);
    for(const auto& row:originals)read(row.name.c_str(),row.address,static_cast<DWORD>(row.bytes.size()));
    return result;
}
Trace::Trace(const std::filesystem::path& receipt) {
    file_=CreateFileW((receipt.wstring()+L".observations.jsonl").c_str(),GENERIC_WRITE,FILE_SHARE_READ,
        nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    Require(file_!=INVALID_HANDLE_VALUE,"Cannot create the private observation trace.");
}
Trace::~Trace(){if(file_!=INVALID_HANDLE_VALUE)CloseHandle(file_);}
void Trace::Append(const Snapshot& snapshot,Receipt& receipt) {
    if(receipt.traceTruncated)return;
    for(std::size_t i=0;i<snapshot.rows.size();++i) {
        const auto& row=snapshot.rows[i];
        if(i<previous_.size() && row.bytes==previous_[i].bytes && row.error==previous_[i].error
            && row.regionBase==previous_[i].regionBase && row.regionSize==previous_[i].regionSize
            && row.protect==previous_[i].protect && row.state==previous_[i].state && row.type==previous_[i].type
            && row.queryError==previous_[i].queryError)continue;
        std::ostringstream out;out<<"{\"phase\":\""<<snapshot.phase<<"\",\"tick\":"<<snapshot.tick
            <<",\"regionBase\":"<<row.regionBase<<",\"regionSize\":"<<row.regionSize
            <<",\"protect\":"<<row.protect<<",\"state\":"<<row.state<<",\"type\":"<<row.type<<",\"queryError\":"<<row.queryError
            <<",\"name\":\""<<row.name<<"\",\"address\":"<<row.address<<",\"error\":"<<row.error<<",\"bytes\":\"";
        for(const auto value:row.bytes)out<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned int>(value);
        out<<"\"}\n";const auto text=out.str();
        if(rows_>=2048 || text.size()>8*1024*1024-bytes_){receipt.traceTruncated=true;return;}
        DWORD written{};
        Require(WriteFile(file_,text.data(),static_cast<DWORD>(text.size()),&written,nullptr) && written==text.size(),
            "Cannot persist the private observation trace.");
        bytes_+=text.size();++rows_;
    }
    previous_=snapshot.rows;
    Require(FlushFileBuffers(file_)!=FALSE,"Cannot flush the private observation trace.");
}
}
