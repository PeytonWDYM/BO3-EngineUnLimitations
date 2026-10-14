// Execute only the guarded native stack-probe helper in owned Windows threads.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
void Require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
struct Allocation {
    void* memory = VirtualAlloc(nullptr, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    ~Allocation() { if (memory) VirtualFree(memory, 0, MEM_RELEASE); }
};
struct Registration {
    PRUNTIME_FUNCTION table;
    bool active = false;
    ~Registration() { if (active) RtlDeleteFunctionTable(table); }
};
struct Observation { std::uintptr_t entryRsp{}, bodyRsp{}, bodyStackLimit{}; };
static_assert(offsetof(Observation, bodyRsp) == 8 && offsetof(Observation, bodyStackLimit) == 16);
using ProbeWrapper = void (*)(Observation*);
struct ThreadInput {
    ProbeWrapper wrapper;
    Observation observation;
    std::uintptr_t beforeLimit{}, afterLimit{};
    MEMORY_BASIC_INFORMATION bodyPage{};
    SIZE_T queryBytes{};
};
DWORD WINAPI ProbeThread(void* parameter) {
    auto& input = *static_cast<ThreadInput*>(parameter);
    auto* tib = reinterpret_cast<volatile NT_TIB*>(NtCurrentTeb());
    input.beforeLimit = reinterpret_cast<std::uintptr_t>(tib->StackLimit);
    input.wrapper(&input.observation);
    input.afterLimit = reinterpret_cast<std::uintptr_t>(tib->StackLimit);
    input.queryBytes = VirtualQuery(reinterpret_cast<void*>(input.observation.bodyRsp), &input.bodyPage, sizeof(input.bodyPage));
    return 0;
}

template<class T> void Append(std::vector<unsigned char>& output, T value) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(&value);
    output.insert(output.end(), bytes, bytes + sizeof(value));
}
std::vector<unsigned char> Wrapper(std::uint32_t frame, std::uintptr_t helper) {
    std::vector<unsigned char> code{0x48,0x89,0x21, 0x48,0x83,0xec,0x28, 0xb8};
    Append(code, frame);
    code.insert(code.end(), {0x49,0xbb});
    Append(code, helper);
    code.insert(code.end(), {0x41,0xff,0xd3, 0x48,0x2b,0xe0, 0x48,0x89,0x61,0x08,
                            0x65,0x48,0x8b,0x04,0x25,0x10,0,0,0, 0x48,0x89,0x41,0x10,
                            0xc6,0x04,0x24,0, 0x48,0x81,0xc4});
    // One epilog adjustment restores both the call frame and the probed allocation.
    Append(code, frame + 0x28);
    code.push_back(0xc3);
    return code;
}
}

int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 2, "Supply the guarded probe fixture file.");
        std::ifstream input(argv[1], std::ios::binary);
        std::array<char, 8> magic{};
        std::uint32_t size{};
        input.read(magic.data(), magic.size());
        input.read(reinterpret_cast<char*>(&size), sizeof(size));
        Require(input && magic == std::array<char,8>{'B','O','3','P','R','O','B','1'} && size == 78,
                "The guarded probe fixture format differs.");
        std::vector<unsigned char> probe(size);
        input.read(reinterpret_cast<char*>(probe.data()), probe.size());
        Require(input && input.peek() == std::ifstream::traits_type::eof(), "The probe fixture extent differs.");
        const std::array<std::uint32_t, 3> frames{0x1dc8, 0x3dd0, 0x54e0};
        std::array<ThreadInput, 3> results{};
        for (std::size_t index = 0; index < frames.size(); ++index) {
            const auto frame = frames[index];
            Allocation allocation;
            Require(allocation.memory != nullptr, "Cannot allocate owned probe code.");
            auto* memory = static_cast<unsigned char*>(allocation.memory);
            const auto base = reinterpret_cast<DWORD64>(memory);
            const auto wrapper = Wrapper(frame, base + 512);
            Require(wrapper.size() == 57, "The authored wrapper layout differs.");
            std::memcpy(memory, wrapper.data(), wrapper.size());
            std::memcpy(memory + 512, probe.data(), probe.size());
            const auto scaled = static_cast<std::uint16_t>(frame / 8);
            const std::array<unsigned char, 12> wrapperUnwind{1,28,3,0,28,1,
                static_cast<unsigned char>(scaled), static_cast<unsigned char>(scaled >> 8),7,0x42,0,0};
            const std::array<unsigned char, 8> probeUnwind{1,4,1,0,4,0x12,0,0};
            std::memcpy(memory + 256, wrapperUnwind.data(), wrapperUnwind.size());
            std::memcpy(memory + 768, probeUnwind.data(), probeUnwind.size());
            DWORD previous{};
            Require(VirtualProtect(memory, 4096, PAGE_EXECUTE_READ, &previous) != FALSE, "Cannot protect owned probe code.");
            Require(FlushInstructionCache(GetCurrentProcess(), memory, 4096) != FALSE, "Cannot flush owned probe code.");
            std::array<RUNTIME_FUNCTION, 2> table{{{0,static_cast<DWORD>(wrapper.size()),256},{512,512 + size,768}}};
            Registration registration{table.data()};
            registration.active = RtlAddFunctionTable(table.data(), static_cast<DWORD>(table.size()), base) != FALSE;
            Require(registration.active, "Cannot register owned probe frames.");
            for (auto& function : table) {
                DWORD64 foundBase{};
                Require(RtlLookupFunctionEntry(base + function.BeginAddress, &foundBase, nullptr) == &function && foundBase == base,
                        "The owned probe frame lookup differs.");
            }
            ThreadInput parameters{reinterpret_cast<ProbeWrapper>(memory)};
            HANDLE thread = CreateThread(nullptr, 65536, ProbeThread, &parameters, STACK_SIZE_PARAM_IS_A_RESERVATION, nullptr);
            Require(thread != nullptr, "Cannot create the owned probe thread.");
            const DWORD waited = WaitForSingleObject(thread, INFINITE);
            DWORD exitCode{};
            const BOOL queried = GetExitCodeThread(thread, &exitCode);
            const BOOL closed = CloseHandle(thread);
            Require(waited == WAIT_OBJECT_0 && queried && closed && exitCode == 0, "The owned probe thread failed.");
            const auto& observed = parameters.observation;
            const auto page = observed.bodyRsp & ~std::uintptr_t{4095};
            Require(observed.entryRsp - observed.bodyRsp == frame + 0x28, "The probe wrapper stack extent differs.");
            Require(observed.bodyStackLimit < parameters.beforeLimit && observed.bodyStackLimit <= page,
                    "The native probe did not commit the complete lower stack before the frame touch.");
            Require(parameters.afterLimit == observed.bodyStackLimit && parameters.queryBytes == sizeof(MEMORY_BASIC_INFORMATION) &&
                    parameters.bodyPage.State == MEM_COMMIT && !(parameters.bodyPage.Protect & (PAGE_GUARD | PAGE_NOACCESS)),
                    "The probed stack page is not committed and accessible.");
            Require(RtlDeleteFunctionTable(table.data()) != FALSE, "Cannot delete owned probe frames.");
            registration.active = false;
            DWORD64 unused{};
            Require(RtlLookupFunctionEntry(base, &unused, nullptr) == nullptr &&
                    RtlLookupFunctionEntry(base + 512, &unused, nullptr) == nullptr, "The owned probe frames remain registered.");
            results[index] = parameters;
        }
        std::cout << "{\"passed\":true,\"scope\":\"Owned helper execution on new Windows threads. Game frames remain unverified.\",\"cases\":[";
        for (std::size_t index = 0; index < frames.size(); ++index) {
            const auto frame = frames[index];
            const auto& parameters = results[index];
            const auto& observed = parameters.observation;
            if (index) std::cout << ',';
            std::cout << "{\"frameBytes\":" << frame << ",\"entryRsp\":" << observed.entryRsp
                      << ",\"bodyRsp\":" << observed.bodyRsp << ",\"beforeStackLimit\":" << parameters.beforeLimit
                      << ",\"probedStackLimit\":" << observed.bodyStackLimit << ",\"committedPages\":"
                      << (parameters.beforeLimit - observed.bodyStackLimit) / 4096 << ",\"tablesDeleted\":true}";
        }
        std::cout << "],\"gameWrites\":0,\"activationAllowed\":false}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
