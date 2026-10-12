// Execute guarded native GS code under Windows dispatch. All body and failure bindings belong to this fixture.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace {
constexpr DWORD OwnedException = 0xE0123401;
using Function = DWORD64(*)(BOOL);
void Require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class T> T Read(std::ifstream& input) {
    T value{}; input.read(reinterpret_cast<char*>(&value), sizeof(value));
    Require(static_cast<bool>(input), "Incomplete native GS fixture input."); return value;
}
std::vector<unsigned char> Bytes(std::ifstream& input) {
    const auto size = Read<std::uint32_t>(input); Require(size == 0x4000, "Unknown native GS image extent.");
    std::vector<unsigned char> bytes(size); input.read(reinterpret_cast<char*>(bytes.data()), size);
    Require(static_cast<bool>(input), "Incomplete native GS image."); return bytes;
}
struct Allocation {
    void* memory = VirtualAlloc(nullptr, 0x4000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    ~Allocation() { if (memory) VirtualFree(memory, 0, MEM_RELEASE); }
    unsigned char* data() { Require(memory != nullptr, "Cannot allocate owned native GS image."); return static_cast<unsigned char*>(memory); }
    DWORD64 base() { return reinterpret_cast<DWORD64>(data()); }
};
struct Registration {
    std::array<RUNTIME_FUNCTION, 4> functions{{{0,697,0x1400},{0x1000,0x101D,0x1428},
                                            {0x1020,0x1083,0x1430},{0x109C,0x10BB,0x1438}}};
    bool active = false;
    ~Registration() { if (active) RtlDeleteFunctionTable(functions.data()); }
    void add(DWORD64 base) {
        active = RtlAddFunctionTable(functions.data(), 4, base) != FALSE;
        Require(active, "Windows refused the owned native GS table.");
    }
    void remove(DWORD64 base) {
        Require(RtlDeleteFunctionTable(functions.data()) != FALSE, "Cannot delete the native GS table."); active = false;
        DWORD64 found{}; Require(RtlLookupFunctionEntry(base + 0x3E, &found, nullptr) == nullptr, "Native GS lookup survived deletion.");
    }
};
[[noreturn]] void CookieFail() { std::cerr << "native_cookie_refused\n"; ExitProcess(23); }
void RaiseOwned() { RaiseException(OwnedException, EXCEPTION_NONCONTINUABLE, 0, nullptr); }
void Thunk(unsigned char* destination, DWORD64 target) {
    constexpr std::array<unsigned char, 2> load{0x48,0xB8}, jump{0xFF,0xE0};
    std::memcpy(destination, load.data(), 2); std::memcpy(destination + 2, &target, 8); std::memcpy(destination + 10, jump.data(), 2);
}
bool CatchOwned(Function function) {
    bool caught = false;
    __try { function(TRUE); }
    __except(GetExceptionCode() == OwnedException ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) { caught = true; }
    return caught;
}
}

int wmain(int argc, wchar_t** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    try {
        Require(argc == 3, "Supply an owned native GS fixture and mode.");
        const std::wstring_view mode(argv[2]);
        Require(mode == L"correct" || mode == L"old-cookie" || mode == L"high-cookie", "Unknown native GS fixture mode.");
        std::ifstream input(argv[1], std::ios::binary);
        Require(Read<std::array<char,8>>(input) == std::array<char,8>{'B','O','3','D','G','S','W','1'}, "Unknown native GS fixture format.");
        Require(Read<std::uint32_t>(input) == 3, "The native GS fixture needs stock, 300, and 500 frames.");
        unsigned int returns{}, caught{}, records{};
        for (const auto expectedActors : {64u,300u,500u}) {
            const auto actors = Read<std::uint32_t>(input); Require(actors == expectedActors, "The native GS frame order differs.");
            const auto bytes = Bytes(input);
            if (mode != L"correct" && actors != 500) continue;
            Allocation image; std::memcpy(image.data(), bytes.data(), bytes.size());
            Thunk(image.data() + 0x2000, reinterpret_cast<DWORD64>(&CookieFail));
            Thunk(image.data() + 0x2020, reinterpret_cast<DWORD64>(&RaiseOwned));
            if (mode == L"old-cookie") { constexpr std::uint32_t offset = 0x160; std::memcpy(image.data() + 0x1424, &offset, sizeof(offset)); }
            if (mode == L"high-cookie") { constexpr DWORD64 cookie = 0x12342A780CACEBAD; std::memcpy(image.data() + 0x3000, &cookie, sizeof(cookie)); }
            DWORD previous{}; Require(VirtualProtect(image.data(), 0x4000, PAGE_EXECUTE_READ, &previous) != FALSE, "Cannot protect native GS fixture code.");
            Require(FlushInstructionCache(GetCurrentProcess(), image.data(), 0x4000) != FALSE, "Cannot flush native GS fixture code.");
            Registration table; table.add(image.base());
            DWORD64 found{};
            Require(RtlLookupFunctionEntry(image.base() + 0x3E, &found, nullptr) == &table.functions[0] && found == image.base(), "Native GS lookup differs.");
            const auto function = reinterpret_cast<Function>(image.data());
            Require(function(FALSE) == 0x1234, "The native GS return or cookie check differs."); ++returns;
            Require(CatchOwned(function), "The native GS handler did not reach the outer Windows catch."); ++caught;
            table.remove(image.base()); records += 4;
        }
        Require(input.peek() == std::char_traits<char>::eof() && mode == L"correct" && returns == 3 && caught == 3, "Native GS coverage or framing differs.");
        std::cout << "{\"passed\":true,\"nativeReturns\":" << returns << ",\"windowsExceptionsCaught\":" << caught
                  << ",\"functionRecordsDeleted\":" << records << ",\"completeNativeCookieLeaf\":true,\"gameWrites\":0}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
