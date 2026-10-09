#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <cstdint>
#include <iostream>
#include <string>
#include "../loader/FixtureProtocol.h"

// This fixture uses one thread. The main thread stops all patch-location access
// before it signals Ready, and resumes only after the loader signals Resume.
extern "C" __declspec(dllexport) volatile DWORD FixtureData = 41;
#pragma section(".fixture", execute, read)
extern "C" __declspec(dllexport) __declspec(allocate(".fixture")) const unsigned char FixtureCode[] = {
    0xb8, 0x29, 0x00, 0x00, 0x00, 0xc3, 0xcc, 0xcc
};

static HANDLE create_event(const wchar_t* part, bool manual) {
    const auto name = L"Local\\BO3PatchFixture." + std::wstring(part) + L"." + std::to_wstring(GetCurrentProcessId());
    return CreateEventW(nullptr, manual, FALSE, name.c_str());
}

static DWORD protection(const void* address) {
    MEMORY_BASIC_INFORMATION region{};
    if (!VirtualQuery(address, &region, sizeof(region))) return 0;
    return region.Protect;
}

int wmain(int argc, wchar_t* argv[]) {
    const std::wstring mode = argc == 2 ? argv[1] : L"--normal";
    const auto base = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    const bool no_events = mode == L"--no-events";
    const HANDLE request = no_events ? nullptr : create_event(L"Request", false);
    const HANDLE ready = no_events ? nullptr : create_event(L"Ready", true);
    const HANDLE resume = no_events ? nullptr : create_event(L"Resume", false);
    if (!no_events && (!request || !ready || !resume)) return 3;
    const auto suffix = std::to_wstring(GetCurrentProcessId());
    const HANDLE owner = CreateMutexW(nullptr, FALSE, (L"Local\\BO3PatchFixture.Owner." + suffix).c_str());
    const HANDLE mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(patch::FixtureProtocol), (L"Local\\BO3PatchFixture.Protocol." + suffix).c_str());
    if (!owner || !mapping) return 5;
    const auto protocol = static_cast<patch::FixtureProtocol*>(MapViewOfFile(mapping, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, sizeof(patch::FixtureProtocol)));
    if (!protocol) return 6;
    std::cout << "READY pid=" << GetCurrentProcessId() << " image_size=" << nt->OptionalHeader.SizeOfImage
              << " timestamp=" << nt->FileHeader.TimeDateStamp << " data_rva=0x" << std::hex
              << reinterpret_cast<uintptr_t>(&FixtureData) - base << " code_rva=0x"
              << reinterpret_cast<uintptr_t>(&FixtureCode[1]) - base << std::dec << '\n' << std::flush;
    DWORD previous_data = 0, previous_code = 0;
    const auto code = reinterpret_cast<DWORD(*)()>(const_cast<unsigned char*>(FixtureCode));
    bool first_request = true;
    while (true) {
        if (no_events || mode == L"--ignore-safe-point") Sleep(10);
        else if (WaitForSingleObject(request, 10) == WAIT_OBJECT_0) {
            const LONG64 generation = InterlockedCompareExchange64(&protocol->requested_generation, 0, 0);
            if (mode == L"--delay-first-safe-point" && first_request) Sleep(5200);
            first_request = false;
            std::cout << "PARKED generation=" << generation << '\n' << std::flush;
            InterlockedExchange64(&protocol->ready_generation, generation);
            SetEvent(ready);
            do {
                if (WaitForSingleObject(resume, INFINITE) != WAIT_OBJECT_0) return 4;
            } while (InterlockedCompareExchange64(&protocol->resume_generation, 0, 0) != generation);
            std::cout << "RESUMED generation=" << generation << '\n' << std::flush;
        }
        if (mode == L"--mutate-after-resume" && FixtureData == 42) FixtureData = 99;
        const DWORD data_value = FixtureData;
        const DWORD code_value = code();
        if (data_value != previous_data || code_value != previous_code) {
            std::cout << "VALUE data=" << data_value << " code=" << code_value
                      << " data_protect=" << protection(const_cast<const DWORD*>(&FixtureData))
                      << " code_protect=" << protection(FixtureCode) << '\n' << std::flush;
            previous_data = data_value;
            previous_code = code_value;
        }
        if (mode == L"--exit-after-resume" && data_value == 42) return 0;
    }
}
