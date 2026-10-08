#pragma once
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cstdint>
#include <string>
#include <vector>
struct EnvironmentTrace { std::uint64_t hash; DWORD entries,driveEntries,idEntries,idsFixed,unicodeFixed,done; };
std::vector<wchar_t> SnapshotEnvironment();
std::vector<std::wstring> Entries(const std::vector<wchar_t>&);
std::uint64_t EnvironmentHash(const std::vector<wchar_t>&);
std::vector<wchar_t> SyntheticParent(const std::vector<wchar_t>&);
bool UnrelatedPreserved(const std::vector<wchar_t>& before,const std::vector<wchar_t>& child);
int ProbeChild(HANDLE mapping);
