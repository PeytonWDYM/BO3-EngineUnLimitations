// Execute owned native frame and cookie-handler copies with authored body and CRT endpoints.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <excpt.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string_view>

extern "C" EXCEPTION_DISPOSITION __CxxFrameHandler3(PEXCEPTION_RECORD, void*, PCONTEXT, PDISPATCHER_CONTEXT);

namespace {
constexpr std::uint64_t Cookie = 0xABCDEF0123456789, Marker = 0xA1B2C3D4E5F60718;
unsigned int CookieChecks{}, CleanupCalls{};
void* CleanupObject{};
bool Throw{};
void Require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class T> T Read(std::ifstream& input) {
    T value{}; input.read(reinterpret_cast<char*>(&value), sizeof(value));
    Require(static_cast<bool>(input), "Incomplete caller exception fixture input."); return value;
}
struct Allocation {
    void* memory = VirtualAlloc(nullptr, 65536, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    ~Allocation() { if (memory) VirtualFree(memory, 0, MEM_RELEASE); }
    unsigned char* data() { Require(memory != nullptr, "Cannot allocate caller exception storage."); return static_cast<unsigned char*>(memory); }
    DWORD64 base() { return reinterpret_cast<DWORD64>(data()); }
    void protect() {
        DWORD previous{};
        Require(VirtualProtect(data(), 65536, PAGE_EXECUTE_READ, &previous) != FALSE, "Cannot protect caller exception code.");
        Require(FlushInstructionCache(GetCurrentProcess(), data(), 65536) != FALSE, "Cannot flush caller exception code.");
    }
    void release() { Require(VirtualFree(memory, 0, MEM_RELEASE) != FALSE, "Cannot release caller exception storage."); memory = nullptr; }
};
struct Registration {
    std::array<RUNTIME_FUNCTION, 4> functions{{{0,1599,0x2000},{0x1000,0x108F,0x2100},{0x1100,0x1163,0x2120},{0x1200,0x124E,0x2130}}};
    bool active = false;
    ~Registration() { if (active) RtlDeleteFunctionTable(functions.data()); }
    void add(DWORD64 base) {
        active = RtlAddFunctionTable(functions.data(), static_cast<DWORD>(functions.size()), base) != FALSE;
        Require(active, "Windows refused the caller exception table.");
        for (auto& function : functions) {
            DWORD64 found{};
            Require(RtlLookupFunctionEntry(base + function.BeginAddress, &found, nullptr) == &function && found == base, "Caller exception runtime lookup differs.");
        }
    }
    void remove(DWORD64 base) {
        Require(RtlDeleteFunctionTable(functions.data()) != FALSE, "Cannot delete the caller exception table."); active = false;
        for (auto& function : functions) {
            DWORD64 found{};
            Require(RtlLookupFunctionEntry(base + function.BeginAddress, &found, nullptr) == nullptr, "A caller exception registration survived deletion.");
        }
    }
};
void CheckCookie(std::uint64_t value) noexcept {
    ++CookieChecks;
    if (value != Cookie) ExitProcess(23);
}
void Body(void* object) {
    CleanupObject = object;
    std::memcpy(object, &Marker, sizeof(Marker));
    if (Throw) throw 37;
}
void Cleanup(void* object) noexcept {
    std::uint64_t marker{}; std::memcpy(&marker, object, sizeof(marker));
    if (object != CleanupObject || marker != Marker) ExitProcess(24);
    ++CleanupCalls;
}
void Jump(unsigned char* image, unsigned int offset, std::uintptr_t target) {
    const std::array<unsigned char, 2> load{0x48, 0xB8}, jump{0xFF, 0xE0};
    std::memcpy(image + offset, load.data(), load.size()); std::memcpy(image + offset + 2, &target, 8);
    std::memcpy(image + offset + 10, jump.data(), jump.size());
}
}

int wmain(int argc, wchar_t** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    try {
        Require(argc == 3, "Supply the caller exception file and test mode.");
        const bool oldCookie = std::wstring_view(argv[2]) == L"old-cookie";
        Require(oldCookie || std::wstring_view(argv[2]) == L"correct", "Unknown caller exception mode.");
        std::ifstream input(argv[1], std::ios::binary);
        Require(Read<std::array<char, 8>>(input) == std::array<char, 8>{'B','O','3','C','E','X','0','1'}, "Unknown caller exception fixture format.");
        Require(Read<std::uint32_t>(input) == 2, "The exception fixture needs stock and expanded frames.");
        unsigned int normalReturns{}, caughtExceptions{}, cookieChecks{}, cleanupCalls{};
        constexpr std::array<std::array<unsigned int, 2>, 12> Extents{{{0,1599},{0x1000,143},{0x1100,99},{0x1200,78},
            {0x1300,12},{0x2000,80},{0x2100,24},{0x2120,8},{0x2130,8},{0x3000,40},{0x3040,8},{0x3050,24}}};
        for (unsigned int variant = 0; variant < 2; ++variant) {
            Require(Read<std::uint32_t>(input) == variant && Read<std::uint32_t>(input) == Extents.size(), "Invalid caller exception variant.");
            Allocation image;
            for (const auto& extent : Extents) {
                Require(Read<std::uint32_t>(input) == extent[0] && Read<std::uint32_t>(input) == extent[1], "Caller exception byte extent differs.");
                input.read(reinterpret_cast<char*>(image.data() + extent[0]), extent[1]); Require(static_cast<bool>(input), "Incomplete caller exception bytes.");
            }
            if (variant && oldCookie) {
                constexpr std::uint32_t stale = 0x3D22;
                std::memcpy(image.data() + 0x204C, &stale, sizeof(stale));
            }
            std::memcpy(image.data() + 0x4000, &Cookie, sizeof(Cookie));
            Jump(image.data(), 0x1400, reinterpret_cast<std::uintptr_t>(&CheckCookie));
            Jump(image.data(), 0x1410, reinterpret_cast<std::uintptr_t>(&__CxxFrameHandler3));
            Jump(image.data(), 0x1420, reinterpret_cast<std::uintptr_t>(&Body));
            Jump(image.data(), 0x1430, reinterpret_cast<std::uintptr_t>(&Cleanup));
            image.protect(); Registration table; table.add(image.base());
            const auto caller = reinterpret_cast<void(*)()>(image.data());
            CookieChecks = CleanupCalls = 0; CleanupObject = nullptr; Throw = false;
            caller();
            Require(CookieChecks == 1 && CleanupCalls == 0 && CleanupObject != nullptr, "The native caller normal return differs.");
            ++normalReturns; cookieChecks += CookieChecks;
            CookieChecks = CleanupCalls = 0; CleanupObject = nullptr; Throw = true;
            bool caught = false;
            try { caller(); } catch (int value) { caught = value == 37; }
            Require(caught && CookieChecks >= 2 && CleanupCalls == 1, "The captured handler did not preserve exception cleanup and catch.");
            ++caughtExceptions; cookieChecks += CookieChecks; cleanupCalls += CleanupCalls;
            table.remove(image.base()); image.release();
        }
        Require(input.peek() == std::char_traits<char>::eof() && !oldCookie, "The stale cookie candidate escaped refusal.");
        std::cout << "{\"passed\":true,\"normalReturns\":" << normalReturns << ",\"caughtExceptions\":" << caughtExceptions
                  << ",\"cookieChecks\":" << cookieChecks << ",\"cleanupCalls\":" << cleanupCalls
                  << ",\"functionRecordsDeleted\":8,\"allocationsReleased\":2,\"gameCrtVerified\":false,\"gameWrites\":0}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
