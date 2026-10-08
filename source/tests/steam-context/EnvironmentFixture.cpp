#include "EnvironmentFixture.h"
#include "../../launch/preentry/Identity.h"
#include <algorithm>
#include <cwchar>
#include <set>
#include <string_view>

namespace {
bool IsId(std::wstring_view entry) {
    const auto name=entry.substr(0,entry.find(L'=',entry.front()==L'=' ? 1 : 0));
    return CompareStringOrdinal(name.data(),static_cast<int>(name.size()),L"SteamAppId",-1,TRUE)==CSTR_EQUAL
        || CompareStringOrdinal(name.data(),static_cast<int>(name.size()),L"SteamGameId",-1,TRUE)==CSTR_EQUAL;
}
constexpr wchar_t unicodeEntry[]=L"OwnedUnicode=\x03a9\x65e5\x672c\x8a9e\xd83d\xde80";
std::vector<wchar_t> Block(std::vector<std::wstring> entries) {
    std::sort(entries.begin(),entries.end(),[](const auto& a,const auto& b) {
        return CompareStringOrdinal(a.c_str(),-1,b.c_str(),-1,TRUE)==CSTR_LESS_THAN;
    });
    std::vector<wchar_t> block;
    for(const auto& entry:entries) { block.insert(block.end(),entry.begin(),entry.end()); block.push_back(0); }
    block.push_back(0); return block;
}
}
std::vector<wchar_t> SnapshotEnvironment() {
    const auto* raw=GetEnvironmentStringsW(); Require(raw!=nullptr,"Cannot inspect owned environment.");
    const auto* end=raw; while(*end) end+=std::wcslen(end)+1; ++end;
    std::vector<wchar_t> copy(raw,end); FreeEnvironmentStringsW(const_cast<wchar_t*>(raw)); return copy;
}
std::vector<std::wstring> Entries(const std::vector<wchar_t>& block) {
    std::vector<std::wstring> entries;
    for(const wchar_t* entry=block.data();*entry;) { entries.emplace_back(entry); entry+=entries.back().size()+1; }
    return entries;
}
std::uint64_t EnvironmentHash(const std::vector<wchar_t>& block) {
    std::uint64_t hash=14695981039346656037ull;
    for(const auto character:block) {
        hash=(hash^static_cast<unsigned char>(character))*1099511628211ull;
        hash=(hash^static_cast<unsigned char>(character>>8))*1099511628211ull;
    }
    return hash;
}
std::vector<wchar_t> SyntheticParent(const std::vector<wchar_t>& original) {
    auto entries=Entries(original);
    std::erase_if(entries,[](const auto& entry) { return IsId(entry) || entry.starts_with(L"=C:=") || entry.starts_with(L"OwnedUnicode="); });
    entries.emplace_back(L"sTeAmApPiD=wrong-owned-app"); entries.emplace_back(L"STEAMGAMEID=0");
    entries.emplace_back(L"=C:=C:\\owned-context"); entries.emplace_back(unicodeEntry);
    return Block(std::move(entries));
}
bool UnrelatedPreserved(const std::vector<wchar_t>& before,const std::vector<wchar_t>& child) {
    const auto unrelated=[](const auto& block) {
        std::multiset<std::wstring> result;
        for(const auto& entry:Entries(block)) if(!IsId(entry)) result.insert(entry);
        return result;
    };
    return unrelated(before)==unrelated(child);
}
int ProbeChild(HANDLE mapping) {
    auto* trace=static_cast<EnvironmentTrace*>(MapViewOfFile(mapping,FILE_MAP_WRITE,0,0,sizeof(EnvironmentTrace)));
    Require(trace!=nullptr,"Cannot map owned child environment receipt.");
    const auto block=SnapshotEnvironment(); trace->hash=EnvironmentHash(block); trace->idsFixed=1;
    for(const auto& entry:Entries(block)) {
        ++trace->entries;
        if(entry.front()==L'=') ++trace->driveEntries;
        if(IsId(entry)) { ++trace->idEntries; trace->idsFixed &= static_cast<DWORD>(entry.substr(entry.find(L'=')+1)==L"311210"); }
        if(entry==unicodeEntry) trace->unicodeFixed=1;
    }
    trace->done=1; UnmapViewOfFile(trace); return 0;
}
