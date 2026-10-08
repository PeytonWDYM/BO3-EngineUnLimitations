// Inert direct launcher stand-in. It never opens or launches the supplied game.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <string>
#include <string_view>

std::string Json(std::wstring_view text) {
    const int count=WideCharToMultiByte(CP_UTF8,0,text.data(),static_cast<int>(text.size()),nullptr,0,nullptr,nullptr);
    std::string encoded(static_cast<std::size_t>(count),'\0');
    if(count)WideCharToMultiByte(CP_UTF8,0,text.data(),static_cast<int>(text.size()),encoded.data(),count,nullptr,nullptr);
    std::string result="\"";
    for(char c:encoded) {
        switch(c) {case '"':result+="\\\"";break;case '\\':result+="\\\\";break;
            case '\n':result+="\\n";break;case '\r':result+="\\r";break;case '\t':result+="\\t";break;default:result+=c;}
    }
    return result+'"';
}
int wmain(int argc,wchar_t** argv) {
    if(argc<2)return 2;
    wchar_t output[32768]{};
    if(!GetEnvironmentVariableW(L"OWNED_STEAM_OUTPUT",output,32768))return 2;
    std::string data="{\"arguments\":[";
    for(int i=1;i<argc;++i){if(i>1)data+=',';data+=Json(argv[i]);}
    data+="],\"environment\":{";
    const wchar_t* names[]{L"SteamAppId",L"SteamGameId",L"SteamOverlayGameId"};
    for(unsigned i=0;i<3;++i){wchar_t value[256]{};GetEnvironmentVariableW(names[i],value,256);
        if(i)data+=',';data+=Json(names[i])+':'+Json(value);}
    data+="}}\n";
    const HANDLE file=CreateFileW(output,GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)return 3;
    DWORD written{};const BOOL ok=WriteFile(file,data.data(),static_cast<DWORD>(data.size()),&written,nullptr);
    CloseHandle(file);return ok && written==data.size()?0:4;
}
