#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include "SteamContext.h"
#include <algorithm>
#include <stdexcept>
#include <string>
#include <string_view>

namespace enhanced {
namespace {
std::wstring_view Name(std::wstring_view entry) {
    // Drive variables have names such as '=C:' followed by their second '='.
    return entry.substr(0,entry.find(L'=',entry.front()==L'=' ? 1 : 0));
}
bool Same(std::wstring_view left,const wchar_t* right) {
    return CompareStringOrdinal(left.data(),static_cast<int>(left.size()),right,-1,TRUE)==CSTR_EQUAL;
}
struct ParentEnvironment {
    wchar_t* block=GetEnvironmentStringsW();
    ~ParentEnvironment() { if(block) FreeEnvironmentStringsW(block); }
};
}
std::vector<wchar_t> SteamChildEnvironment() {
    ParentEnvironment parent;
    if(!parent.block) throw std::runtime_error("Cannot snapshot the process environment.");
    std::vector<std::wstring> entries;
    for(const wchar_t* entry=parent.block;*entry;) {
        const std::wstring_view text(entry);
        const auto name=Name(text);
        if(!Same(name,L"SteamAppId") && !Same(name,L"SteamGameId")) entries.emplace_back(text);
        entry+=text.size()+1;
    }
    entries.emplace_back(L"SteamAppId=311210"); entries.emplace_back(L"SteamGameId=311210");
    std::sort(entries.begin(),entries.end(),[](const auto& left,const auto& right) {
        const auto leftName=Name(left),rightName=Name(right);
        return CompareStringOrdinal(leftName.data(),static_cast<int>(leftName.size()),
            rightName.data(),static_cast<int>(rightName.size()),TRUE)==CSTR_LESS_THAN;
    });
    std::vector<wchar_t> block;
    for(const auto& entry:entries) { block.insert(block.end(),entry.begin(),entry.end()); block.push_back(0); }
    block.push_back(0);
    return block;
}
}
