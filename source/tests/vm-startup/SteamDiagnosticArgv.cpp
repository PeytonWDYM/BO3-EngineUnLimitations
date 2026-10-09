// Inert native recorder. It never opens or launches the supplied game path.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <string>
#include <string_view>

std::string Json(std::wstring_view text) {
    const int count=WideCharToMultiByte(CP_UTF8,0,text.data(),static_cast<int>(text.size()),nullptr,0,nullptr,nullptr);
    std::string encoded(static_cast<std::size_t>(count),'\0');
    if(count) WideCharToMultiByte(CP_UTF8,0,text.data(),static_cast<int>(text.size()),encoded.data(),count,nullptr,nullptr);
    std::string result="\"";
    for(char c:encoded) {
        switch(c) { case '"': result+="\\\""; break; case '\\': result+="\\\\"; break;
            case '\n': result+="\\n"; break; case '\r': result+="\\r"; break; case '\t': result+="\\t"; break;
            default: result+=c; }
    }
    return result+'"';
}

int wmain(int argc,wchar_t** argv) {
    if(argc<6 || std::wstring_view(argv[1])!=L"--no-debugger"
       || std::wstring_view(argv[2])!=L"--observe-seconds" || std::wstring_view(argv[3])!=L"120") return 2;
    std::string data="{\"arguments\":[";
    for(int index=1;index<argc;++index) { if(index>1) data+=','; data+=Json(argv[index]); }
    data+="],\"environment\":{";
    const wchar_t* names[]{L"SteamAppId",L"SteamGameId",L"SteamOverlayGameId"};
    for(unsigned index=0;index<3;++index) {
        wchar_t value[256]{};
        GetEnvironmentVariableW(names[index],value,256);
        if(index) data+=',';
        data+=Json(names[index])+':'+Json(value);
    }
    data+="}}\n";
    const HANDLE file=CreateFileW(argv[5],GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE) return 3;
    DWORD written{};
    const BOOL ok=WriteFile(file,data.data(),static_cast<DWORD>(data.size()),&written,nullptr);
    CloseHandle(file);
    return ok && written==data.size() ? 0 : 4;
}
