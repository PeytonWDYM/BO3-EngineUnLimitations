#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <cstdint>
#include <cstddef>

namespace bo3::early_integrity {
// Admit every page before reading hashes; this never changes protection or contents.
void RequireImageMemory(HANDLE process,std::uintptr_t imageBase,std::uintptr_t address,std::size_t size);
}
