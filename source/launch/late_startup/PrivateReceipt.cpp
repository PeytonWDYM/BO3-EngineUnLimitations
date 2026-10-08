#include "PrivateReceipt.h"
#include "../preentry/Identity.h"
#include <ShlObj.h>
#include <array>
#include <sstream>

namespace bo3::late_startup {
namespace {
HANDLE LockDirectory(const std::filesystem::path& path) {
    const auto handle=CreateFileW(path.c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    Require(handle!=INVALID_HANDLE_VALUE,"Cannot lock the private receipt directory.");
    try {
        FILE_ATTRIBUTE_TAG_INFO attributes{};
        Require(GetFileInformationByHandleEx(handle,FileAttributeTagInfo,&attributes,sizeof(attributes))!=FALSE
            && (attributes.FileAttributes&FILE_ATTRIBUTE_DIRECTORY) && !(attributes.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT),
            "The receipt directory is not a plain directory.");
        std::array<wchar_t,32768> physical{};
        const auto length=GetFinalPathNameByHandleW(handle,physical.data(),static_cast<DWORD>(physical.size()),FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
        Require(length>4 && length<physical.size() && std::wstring_view(physical.data(),4)==L"\\\\?\\",
            "Cannot resolve the physical receipt directory.");
        const auto requested=std::filesystem::absolute(path).lexically_normal().wstring();
        Require(CompareStringOrdinal(requested.c_str(),-1,physical.data()+4,-1,TRUE)==CSTR_EQUAL,
            "The private receipt directory redirects to another path.");return handle;
    }catch(...){CloseHandle(handle);throw;}
}
}
void PrivateReceipt::Create(const std::filesystem::path& root,const OwnedChild& child) {
    directories_.reserve(3);
    try {
        directories_.push_back(LockDirectory(root));
        auto directory=root;
        for(const auto* name:{L"BO3 Engine UnLimitations",L"sessions"}) {
            directory/=name;
            Require(CreateDirectoryW(directory.c_str(),nullptr)!=FALSE || GetLastError()==ERROR_ALREADY_EXISTS,
                "Cannot create the private receipt directory.");
            directories_.push_back(LockDirectory(directory));
        }
#if defined(BO3_JOB_STARTUP)
        constexpr auto suffix=L"-job.json";
#elif defined(BO3_LATE_PASSIVE_CONTROL)
        constexpr auto suffix=L"-late-passive-control.json";
#elif defined(BO3_LATE_STOCK_CONTROL)
        constexpr auto suffix=L"-late-control.json";
#else
        constexpr auto suffix=L"-late.json";
#endif
        path_=directory/(std::to_wstring(child.payload.processCreatedFileTime)+L"-"+std::to_wstring(child.process.dwProcessId)+suffix);
        file_=CreateFileW(path_.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
        Require(file_!=INVALID_HANDLE_VALUE,"The private receipt path already exists or cannot be created.");
    }catch(...){for(const auto handle:directories_)CloseHandle(handle);directories_.clear();throw;}
}
PrivateReceipt::PrivateReceipt(const OwnedChild& child) {
    PWSTR root{};Require(SHGetKnownFolderPath(FOLDERID_LocalAppData,KF_FLAG_DEFAULT,nullptr,&root)==S_OK,
        "Cannot find private receipt storage.");
    const auto path=std::filesystem::path(root);CoTaskMemFree(root);Create(path,child);
}
#ifdef BO3_LATE_OWNED_TEST
PrivateReceipt::PrivateReceipt(const std::filesystem::path& directory,const OwnedChild& child){Create(directory,child);}
#endif
PrivateReceipt::~PrivateReceipt(){if(file_!=INVALID_HANDLE_VALUE)CloseHandle(file_);for(const auto handle:directories_)CloseHandle(handle);}
#ifdef BO3_JOB_STARTUP
void PrivateReceipt::Write(const job_startup::Receipt& receipt) {
    std::ostringstream stream;job_startup::WriteReceipt(stream,receipt);
#elif defined(BO3_LATE_STOCK_CONTROL)
void PrivateReceipt::Write(const ControlReceipt& receipt) {
    std::ostringstream stream;WriteControlReceipt(stream,receipt);
#else
void PrivateReceipt::Write(const Receipt& receipt) {
    std::ostringstream stream;WriteReceipt(stream,receipt);
#endif
    stream<<'\n';const auto bytes=stream.str();
    LARGE_INTEGER begin{};Require(SetFilePointerEx(file_,begin,nullptr,FILE_BEGIN)!=FALSE,"Cannot rewind the owned receipt.");
    DWORD written{};
    Require(WriteFile(file_,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr)!=FALSE && written==bytes.size()
        && SetEndOfFile(file_) && FlushFileBuffers(file_),"Cannot persist the owned receipt.");
}
}
