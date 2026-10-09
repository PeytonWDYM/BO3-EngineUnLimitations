#pragma once
#include <windows.h>
#include <cstdint>
constexpr std::uint32_t kFixtureBytes = 0x40000;
constexpr std::uint32_t kFixtureRecords = 1365;
struct FixtureState { std::uintptr_t imageBase; DWORD failure; };
void ProveSemantics();
