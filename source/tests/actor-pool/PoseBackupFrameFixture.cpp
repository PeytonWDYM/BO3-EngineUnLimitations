// Execute captured pose frame shells and GS/EH handlers in owned Windows memory.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <excpt.h>
#include <intrin.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <vector>

extern "C" EXCEPTION_DISPOSITION __CxxFrameHandler3(PEXCEPTION_RECORD, void*, PCONTEXT, PDISPATCHER_CONTEXT);

namespace {
constexpr std::uint64_t Cookie = 0xABCDEF0123456789;
constexpr std::array<unsigned int, 8> Nonvolatile{3,5,6,7,12,13,14,15};
unsigned int CookieChecks{}, CleanupCalls{}, Actors{};
void* Object{};
bool Throw{};
std::uintptr_t BodyRsp{}, BodyStackLimit{};
void Require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class T> T Read(std::ifstream& input) {
    T value{}; input.read(reinterpret_cast<char*>(&value), sizeof(value));
    Require(static_cast<bool>(input), "Incomplete pose frame fixture input."); return value;
}
struct Allocation {
    void* memory = VirtualAlloc(nullptr, 65536, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    ~Allocation() { if (memory) VirtualFree(memory, 0, MEM_RELEASE); }
    unsigned char* data() { Require(memory != nullptr, "Cannot allocate pose frame storage."); return static_cast<unsigned char*>(memory); }
    DWORD64 base() { return reinterpret_cast<DWORD64>(data()); }
    void protect() {
        DWORD previous{};
        Require(VirtualProtect(data(), 65536, PAGE_EXECUTE_READ, &previous) != FALSE, "Cannot protect pose frame code.");
        Require(FlushInstructionCache(GetCurrentProcess(), data(), 65536) != FALSE, "Cannot flush pose frame code.");
    }
};
struct Registration {
    std::vector<RUNTIME_FUNCTION> functions;
    bool active{};
    ~Registration() { if (active) RtlDeleteFunctionTable(functions.data()); }
    void add(DWORD64 base) {
        active = RtlAddFunctionTable(functions.data(), static_cast<DWORD>(functions.size()), base) != FALSE;
        Require(active, "Windows refused the pose frame table.");
        for (auto& function : functions) {
            DWORD64 found{};
            Require(RtlLookupFunctionEntry(base + function.BeginAddress, &found, nullptr) == &function && found == base,
                    "Pose frame runtime lookup differs.");
        }
    }
    void remove(DWORD64 base) {
        Require(RtlDeleteFunctionTable(functions.data()) != FALSE, "Cannot delete the pose frame table."); active = false;
        for (const auto& function : functions) {
            DWORD64 found{};
            Require(RtlLookupFunctionEntry(base + function.BeginAddress, &found, nullptr) == nullptr,
                    "A pose frame registration survived deletion.");
        }
    }
};
void Jump(unsigned char* image, unsigned int offset, std::uintptr_t target) {
    image[offset] = 0x48; image[offset + 1] = 0xB8;
    std::memcpy(image + offset + 2, &target, 8); image[offset + 10] = 0xFF; image[offset + 11] = 0xE0;
}
void CheckCookie(std::uint64_t value) noexcept {
    ++CookieChecks;
    if (value != Cookie) ExitProcess(23);
}
void Body(void* object) {
    BodyRsp = reinterpret_cast<std::uintptr_t>(_AddressOfReturnAddress()) + 8;
    BodyStackLimit = reinterpret_cast<std::uintptr_t>(reinterpret_cast<NT_TIB*>(NtCurrentTeb())->StackLimit);
    Object = object;
    auto* bytes = static_cast<unsigned char*>(object);
    std::memset(bytes, 0x11, Actors * 12);
    std::memset(bytes + Actors * 12, 0x22, Actors * 12);
    bytes[Actors * 24] = 1;
    if (Throw) throw 37;
}
struct ThreadInput {
    void (*caller)();
    std::uintptr_t beforeLimit{}, afterLimit{}, bodyRsp{}, bodyLimit{};
    unsigned int allocation{}, accessiblePages{};
    bool pagesCommitted{true};
};
DWORD WINAPI FrameThread(void* parameter) {
    auto& thread = *static_cast<ThreadInput*>(parameter);
    thread.beforeLimit = reinterpret_cast<std::uintptr_t>(reinterpret_cast<NT_TIB*>(NtCurrentTeb())->StackLimit);
    thread.caller();
    thread.afterLimit = reinterpret_cast<std::uintptr_t>(reinterpret_cast<NT_TIB*>(NtCurrentTeb())->StackLimit);
    thread.bodyRsp = BodyRsp; thread.bodyLimit = BodyStackLimit;
    for (auto page = thread.bodyRsp & ~std::uintptr_t{4095}; page < thread.bodyRsp + thread.allocation; page += 4096) {
        MEMORY_BASIC_INFORMATION region{};
        thread.pagesCommitted &= VirtualQuery(reinterpret_cast<void*>(page), &region, sizeof(region)) == sizeof(region) &&
                                 region.State == MEM_COMMIT && !(region.Protect & (PAGE_GUARD | PAGE_NOACCESS));
        ++thread.accessiblePages;
    }
    return 0;
}
ThreadInput CheckStackGrowth(void (*caller)(), unsigned int allocation) {
    ThreadInput observed{caller};
    observed.allocation = allocation;
    HANDLE thread = CreateThread(nullptr, 262144, FrameThread, &observed, STACK_SIZE_PARAM_IS_A_RESERVATION, nullptr);
    Require(thread != nullptr, "Cannot create an owned pose frame thread.");
    const auto waited = WaitForSingleObject(thread, INFINITE);
    DWORD exitCode{};
    const auto queried = GetExitCodeThread(thread, &exitCode), closed = CloseHandle(thread);
    Require(waited == WAIT_OBJECT_0 && queried && closed && exitCode == 0, "The owned pose frame thread failed.");
    if (Actors == 500) {
        Require(observed.bodyLimit < observed.beforeLimit && observed.bodyLimit <= (observed.bodyRsp & ~std::uintptr_t{4095}),
                "The enlarged pose frame did not commit its complete lower stack.");
        Require(observed.afterLimit == observed.bodyLimit, "The owned pose stack limit changed after its body.");
    }
    Require(observed.pagesCommitted && observed.accessiblePages != 0, "An allocated pose stack page is not committed and accessible.");
    return observed;
}
void Cleanup(void* object) noexcept {
    if (object != Object) ExitProcess(24);
    const auto* bytes = static_cast<const unsigned char*>(object);
    for (unsigned int offset = 0; offset < Actors * 12; ++offset)
        if (bytes[offset] != 0x11 || bytes[Actors * 12 + offset] != 0x22) ExitProcess(24);
    if (bytes[Actors * 24] != 1) ExitProcess(24);
    ++CleanupCalls;
}
DWORD64& Register(CONTEXT& context, unsigned int index) {
    switch (index) {
    case 3:return context.Rbx; case 5:return context.Rbp; case 6:return context.Rsi; case 7:return context.Rdi;
    case 12:return context.R12; case 13:return context.R13; case 14:return context.R14; case 15:return context.R15;
    default:throw std::runtime_error("A pose frame requests a volatile register.");
    }
}
CONTEXT Seed(DWORD64 rip, DWORD64 rsp) {
    CONTEXT context{}; context.ContextFlags = CONTEXT_ALL; context.Rip = rip; context.Rsp = rsp;
    for (auto index : Nonvolatile) Register(context, index) = 0x100000000ull + index;
    for (int index = 6; index < 16; ++index) (&context.Xmm0)[index] = {0x200000000ull + index, 0x210000000ll + index};
    return context;
}
struct Header { std::uint32_t site, end, prolog, object, actors, allocation, blobs, points, functions; };
struct Point { std::uint32_t control, returnOffset, saves, functionIndex, restoredGprs, restoredVectors, r11Offset; };
struct Save { std::uint32_t offset, width, reg; };
bool CheckUnwind(Allocation& image, RUNTIME_FUNCTION& function, const Point& point, const std::vector<Save>& saves) {
    alignas(16) std::array<std::uint64_t, 16384> stack; stack.fill(0xDEADBEEF11111111ull);
    const auto rsp = reinterpret_cast<DWORD64>(&stack[1024]) + (point.returnOffset % 16 == 0 ? 8 : 0);
    constexpr DWORD64 returnPc = 0x1234567812345678ull;
    std::memcpy(reinterpret_cast<void*>(rsp + point.returnOffset), &returnPc, 8);
    std::array<bool, 16> gprs{}, vectors{};
    for (const auto& save : saves) {
        Require(save.offset + save.width < 65536 && (save.width == 8 || save.width == 16), "Invalid pose stack save.");
        if (save.width == 8) {
            Require(save.reg < 16, "Invalid pose GPR save."); gprs[save.reg] = true;
            const auto value = 0x300000000ull + save.reg;
            std::memcpy(reinterpret_cast<void*>(rsp + save.offset), &value, 8);
        } else {
            Require(save.reg >= 6 && save.reg < 16, "Invalid pose XMM save."); vectors[save.reg] = true;
            const M128A value{0x400000000ull + save.reg, 0x410000000ll + save.reg};
            std::memcpy(reinterpret_cast<void*>(rsp + save.offset), &value, 16);
        }
    }
    auto context = Seed(image.base() + point.control, rsp);
    for (auto reg : Nonvolatile) {
        if (point.restoredGprs & (1u << reg)) { Register(context, reg) = 0x300000000ull + reg; gprs[reg] = true; }
    }
    for (int reg = 6; reg < 16; ++reg) {
        if (point.restoredVectors & (1u << reg)) { (&context.Xmm0)[reg] = {0x400000000ull + reg, 0x410000000ll + reg}; vectors[reg] = true; }
    }
    if (point.r11Offset != UINT32_MAX) context.R11 = rsp + static_cast<std::int32_t>(point.r11Offset);
    DWORD64 found{};
    Require(RtlLookupFunctionEntry(context.Rip, &found, nullptr) == &function && found == image.base(), "Pose point lookup differs.");
    PVOID handlerData{}; DWORD64 establisher{};
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, image.base(), context.Rip, &function, &context, &handlerData, &establisher, nullptr);
    if (context.Rip != returnPc || context.Rsp != rsp + point.returnOffset + 8) return false;
    for (auto reg : Nonvolatile)
        if (Register(context, reg) != (gprs[reg] ? 0x300000000ull : 0x100000000ull) + reg) return false;
    for (int reg = 6; reg < 16; ++reg) {
        const M128A value{(vectors[reg] ? 0x400000000ull : 0x200000000ull) + reg,
                          (vectors[reg] ? 0x410000000ll : 0x210000000ll) + reg};
        if (std::memcmp(&(&context.Xmm0)[reg], &value, sizeof(value)) != 0) return false;
    }
    return true;
}
unsigned int CheckMetadataMutations(Allocation& image, RUNTIME_FUNCTION& function, const Point& point, const std::vector<Save>& saves) {
    DWORD previous{};
    Require(VirtualProtect(image.data() + 0x8000, 4096, PAGE_READWRITE, &previous) != FALSE, "Cannot write owned pose metadata mutations.");
    auto* metadata = image.data() + function.UnwindData;
    bool allocation{}, save{};
    for (unsigned int slot = 0; slot < metadata[2];) {
        const auto position = 4 + slot * 2;
        const auto tag = metadata[position + 1];
        const auto op = tag & 15, info = tag >> 4;
        const auto extra = (op == 4 || op == 8 || (op == 1 && info == 0)) ? 1u : 0u;
        if ((op == 1 && !allocation) || ((op == 4 || op == 8) && !save)) {
            std::uint16_t original{};
            std::memcpy(&original, metadata + position + 2, 2);
            const auto changed = static_cast<std::uint16_t>(original - 1);
            std::memcpy(metadata + position + 2, &changed, 2);
            Require(!CheckUnwind(image, function, point, saves), "A stale pose frame metadata mutation escaped detection.");
            std::memcpy(metadata + position + 2, &original, 2);
            if (op == 1) allocation = true; else save = true;
        }
        slot += extra + 1;
    }
    DWORD ignored{};
    Require(VirtualProtect(image.data() + 0x8000, 4096, previous, &ignored) != FALSE, "Cannot restore owned pose metadata protection.");
    Require(allocation && save, "A pose frame lacks allocation or saved-register mutation coverage.");
    return 2;
}
}

int wmain(int argc, wchar_t** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    try {
        Require(argc == 3, "Supply the pose frame input and test mode.");
        const auto mode = std::wstring_view(argv[2]);
        const bool oldCookie = mode.starts_with(L"old-cookie-") && mode.size() == 12 && mode[11] >= L'0' && mode[11] <= L'5';
        const auto mutationFrame = oldCookie ? static_cast<unsigned int>(mode[11] - L'0') : 6u;
        Require(oldCookie || mode == L"correct", "Unknown pose frame mode.");
        std::ifstream input(argv[1], std::ios::binary);
        Require(Read<std::array<char,8>>(input) == std::array<char,8>{'B','O','3','P','O','S','E','1'}, "Unknown pose frame input.");
        const auto frames = Read<std::uint32_t>(input);
        Require(frames == 6, "The pose fixture needs all six owning frames.");
        unsigned int points{}, returns{}, exceptions{}, cookies{}, cleanups{}, records{}, threadReturns{}, metadataMutations{};
        std::vector<ThreadInput> stackGrowth;
        for (unsigned int index = 0; index < frames; ++index) {
            const auto header = Read<Header>(input);
            Require(header.end < 0x5000 && header.prolog < 255 && header.points < 64 && header.blobs >= 12 && header.blobs <= 21 && header.functions >= 4 && header.functions <= 12,
                    "Invalid pose frame extent.");
            Require(header.actors == 64 || header.actors == 500, "Unknown pose fixture capacity.");
            Actors = header.actors;
            Registration table;
            for (unsigned int function = 0; function < header.functions; ++function) table.functions.push_back(Read<RUNTIME_FUNCTION>(input));
            Allocation image;
            for (unsigned int blob = 0; blob < header.blobs; ++blob) {
                const auto offset = Read<std::uint32_t>(input), size = Read<std::uint32_t>(input);
                Require(offset + size < 65536, "A pose byte extent exceeds its allocation.");
                input.read(reinterpret_cast<char*>(image.data() + offset), size);
                Require(static_cast<bool>(input), "Incomplete pose frame bytes.");
            }
            if (oldCookie && index == mutationFrame) {
                auto* metadata = image.data() + 0x8000;
                const auto cookieOffset = 4 + ((metadata[2] + 1) & ~1u) * 2 + 8;
                std::uint32_t cookie{}; std::memcpy(&cookie, metadata + cookieOffset, 4); cookie += 8;
                std::memcpy(metadata + cookieOffset, &cookie, 4);
            }
            std::memcpy(image.data() + 0x9000, &Cookie, 8);
            Jump(image.data(), 0x5400, reinterpret_cast<std::uintptr_t>(&Body));
            Jump(image.data(), 0x5410, reinterpret_cast<std::uintptr_t>(&CheckCookie));
            Jump(image.data(), 0x5420, reinterpret_cast<std::uintptr_t>(&__CxxFrameHandler3));
            Jump(image.data(), 0x5430, reinterpret_cast<std::uintptr_t>(&Cleanup));
            image.protect(); table.add(image.base());
            for (unsigned int pointIndex = 0; pointIndex < header.points; ++pointIndex) {
                const auto point = Read<Point>(input);
                Require(point.returnOffset < 65536 && point.saves < 32 && point.functionIndex < table.functions.size(), "Invalid pose unwind point.");
                std::vector<Save> saves;
                for (unsigned int save = 0; save < point.saves; ++save) saves.push_back(Read<Save>(input));
                Require(CheckUnwind(image, table.functions[point.functionIndex], point, saves), "Windows pose unwinding differs from its active stack contract."); ++points;
                if (point.functionIndex == 0 && point.control == header.prolog)
                    metadataMutations += CheckMetadataMutations(image, table.functions[0], point, saves);
            }
            const auto caller = reinterpret_cast<void(*)()>(image.data());
            CookieChecks = CleanupCalls = 0; Object = nullptr; Throw = false;
            stackGrowth.push_back(CheckStackGrowth(caller, header.allocation));
            Require(CookieChecks == 1 && CleanupCalls == 0 && Object != nullptr, "An owned pose thread lost its normal return.");
            ++threadReturns;
            CookieChecks = CleanupCalls = 0; Object = nullptr; Throw = false;
            caller();
            Require(CookieChecks == 1 && CleanupCalls == 0 && Object != nullptr, "A native pose frame did not return normally.");
            ++returns; cookies += CookieChecks;
            CookieChecks = CleanupCalls = 0; Object = nullptr; Throw = true;
            bool caught{};
            try { caller(); } catch (int value) { caught = value == 37; }
            Require(caught && CookieChecks >= 2 && CleanupCalls == 1, "A captured pose GS/EH handler lost cleanup or catch.");
            ++exceptions; cookies += CookieChecks; cleanups += CleanupCalls;
            records += static_cast<unsigned int>(table.functions.size()); table.remove(image.base());
        }
        Require(input.peek() == std::char_traits<char>::eof() && !oldCookie, "Incomplete pose input escaped refusal.");
        std::cout << "{\"passed\":true,\"frames\":" << frames << ",\"instructionBoundaryProbes\":" << points
                  << ",\"normalReturns\":" << returns << ",\"caughtExceptions\":" << exceptions << ",\"cookieChecks\":" << cookies
                  << ",\"cleanupCalls\":" << cleanups << ",\"functionRecordsDeleted\":" << records
                  << ",\"ownedThreadReturns\":" << threadReturns
                  << ",\"wrongAllocationOrSaveMutationsRefused\":" << metadataMutations
                  << ",\"stackGrowth\":[";
        for (unsigned int index = 0; index < stackGrowth.size(); ++index) {
            if (index) std::cout << ',';
            const auto& observed = stackGrowth[index];
            std::cout << "{\"allocation\":" << observed.allocation << ",\"beforeLimit\":" << observed.beforeLimit
                      << ",\"bodyLimit\":" << observed.bodyLimit << ",\"bodyRsp\":" << observed.bodyRsp
                      << ",\"committedPages\":" << (observed.beforeLimit - observed.bodyLimit) / 4096
                      << ",\"accessiblePages\":" << observed.accessiblePages << '}';
        }
        std::cout << "],\"gameCrtVerified\":false,\"gameWrites\":0}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}

