#include "Probe.h"
#include "Repository.h"
#include <iomanip>
#include <sstream>

namespace driver_probe {
std::string Utf8(const wchar_t* value) {
    const int count=WideCharToMultiByte(CP_UTF8,0,value,-1,nullptr,0,nullptr,nullptr);
    if(!count) throw Failure(HRESULT_FROM_WIN32(GetLastError()),"UTF8 conversion");
    std::string output(static_cast<size_t>(count),'\0');
    WideCharToMultiByte(CP_UTF8,0,value,-1,output.data(),count,nullptr,nullptr);
    output.pop_back(); return output;
}
std::string Quote(const std::string& value) {
    std::ostringstream out; out << '"';
    for (const unsigned char ch : value) {
        if (ch == '"' || ch == '\\') out << '\\' << ch;
        else if (ch < 0x20) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<unsigned>(ch);
        else out << ch;
    }
    out << '"'; return out.str();
}
std::string Hresult(HRESULT value) {
    std::ostringstream out;
    out << "0x" << std::hex << std::setw(8) << std::setfill('0') << static_cast<unsigned long>(value);
    return out.str();
}
void Trace::Call(const char* stage, HRESULT result) {
    events.push_back("{\"generation\":"+std::to_string(generation)+",\"call\":"+Quote(stage)+",\"hr\":"+Quote(Hresult(result))+'}');
}
void Trace::Fact(const char* name, const std::string& json) {
    events.push_back("{\"generation\":"+std::to_string(generation)+",\"fact\":"+Quote(name)+",\"value\":"+json+'}');
}
void Trace::Publish(IUnknown* object, const char* name) {
    if (publication) publication(object);
    ComPtr<IUnknown> identity;
    Check(*this,name,object->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(identity.GetAddressOf())));
}
void Check(Trace& trace, const char* stage, HRESULT result) {
    trace.Call(stage,result);
    if (FAILED(result)) throw Failure(result,stage);
}
bool SameIdentity(Trace& trace, IUnknown* first, IUnknown* second) {
    ComPtr<IUnknown> a,b;
    Check(trace,"identity.first.IUnknown",first->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(a.GetAddressOf())));
    Check(trace,"identity.second.IUnknown",second->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(b.GetAddressOf())));
    return a.Get()==b.Get();
}
std::filesystem::path EvidencePath(const std::filesystem::path& requested) {
    const auto output=std::filesystem::weakly_canonical(std::filesystem::absolute(requested));
    const auto repository=std::filesystem::weakly_canonical(RepositoryRoot);
    const auto repo=repository.wstring(); const auto path=output.wstring();
    const bool equal=CompareStringOrdinal(repo.c_str(),-1,path.c_str(),-1,TRUE)==CSTR_EQUAL;
    const bool child=path.size()>repo.size() && (path[repo.size()] == L'\\' || path[repo.size()] == L'/') &&
        CompareStringOrdinal(repo.c_str(),static_cast<int>(repo.size()),path.c_str(),static_cast<int>(repo.size()),TRUE)==CSTR_EQUAL;
    if(equal || child) throw Failure(E_ACCESSDENIED,"Write driver evidence outside the repository");
    if(std::filesystem::exists(output)) throw Failure(HRESULT_FROM_WIN32(ERROR_FILE_EXISTS),"Use a new evidence file");
    if(!std::filesystem::is_directory(output.parent_path())) throw Failure(HRESULT_FROM_WIN32(ERROR_PATH_NOT_FOUND),"Create the private evidence parent directory");
    return output;
}
bool ExplicitPhysicalMode(int argc, const wchar_t* const* argv) {
    return argc==3 && std::wstring(argv[1])==L"--physical-silent";
}
}
