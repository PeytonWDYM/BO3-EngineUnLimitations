// Exercise Windows runtime lookup and virtual unwinding in owned allocations only.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <array>
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
template<class T> T Read(std::ifstream& input) {
    T value{};
    input.read(reinterpret_cast<char*>(&value), sizeof(value));
    Require(static_cast<bool>(input), "The owned fixture input is incomplete.");
    return value;
}
struct Phase {std::uint32_t begin, end, depth, unwindBytes;};
struct Allocation {
    void* memory = VirtualAlloc(nullptr, 65536, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    ~Allocation() {if (memory) VirtualFree(memory, 0, MEM_RELEASE);}
};
struct Registration {
    PRUNTIME_FUNCTION table;
    bool active = false;
    ~Registration() {if (active) RtlDeleteFunctionTable(table);}
};
bool Probe(DWORD64 base, RUNTIME_FUNCTION& function, std::uint32_t depth) {
    alignas(16) std::array<std::uint64_t, 128> stack;
    stack.fill(0xdeadbeef11111111ull);
    constexpr DWORD64 returnPc = 0x1234567812345678ull;
    const auto returnStack = reinterpret_cast<DWORD64>(&stack[64]);
    stack[64] = returnPc;
    CONTEXT context{};
    context.ContextFlags = CONTEXT_ALL;
    context.Rip = base + function.BeginAddress;
    context.Rsp = returnStack - depth;
    context.Rbx = 0x101; context.Rbp = 0x202; context.Rsi = 0x303; context.Rdi = 0x404;
    context.R12 = 0x505; context.R13 = 0x606; context.R14 = 0x707; context.R15 = 0x808;
    auto* vectors = &context.Xmm0;
    for (int index = 0; index < 16; ++index) {
        vectors[index].Low = static_cast<ULONGLONG>(0xabcdef00 + index);
        vectors[index].High = static_cast<LONGLONG>(0x12345600 + index);
    }
    const auto original = context;
    PVOID handlerData{};
    DWORD64 establisher{};
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, context.Rip, &function, &context,
                     &handlerData, &establisher, nullptr);
    return context.Rip == returnPc && context.Rsp == returnStack + 8 &&
        context.Rbx == original.Rbx && context.Rbp == original.Rbp &&
        context.Rsi == original.Rsi && context.Rdi == original.Rdi &&
        context.R12 == original.R12 && context.R13 == original.R13 &&
        context.R14 == original.R14 && context.R15 == original.R15 &&
        std::memcmp(&context.Xmm6, &original.Xmm6, sizeof(M128A) * 10) == 0;
}
}

int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 2, "Supply the owned leaf-unwind fixture file.");
        std::ifstream input(argv[1], std::ios::binary);
        Require(static_cast<bool>(input), "Cannot read the owned fixture file.");
        std::array<char,8> magic{};
        input.read(magic.data(), magic.size());
        Require(magic == std::array<char,8>{'B','O','3','L','F','U','W','1'}, "Unknown fixture format.");
        const auto stubs = Read<std::uint32_t>(input);
        Require(stubs == 17, "The guarded plan must supply seventeen leaf stubs.");
        std::uint32_t probes = 0;
        std::uint32_t mutations = 0;
        for (std::uint32_t stub = 0; stub < stubs; ++stub) {
            const auto codeBytes = Read<std::uint32_t>(input);
            const auto phaseCount = Read<std::uint32_t>(input);
            Require(codeBytes && codeBytes < 4096 && phaseCount && phaseCount < 1024, "Invalid fixture extent.");
            std::vector<unsigned char> code(codeBytes);
            input.read(reinterpret_cast<char*>(code.data()), code.size());
            Require(static_cast<bool>(input), "Incomplete fixture code.");
            Allocation allocation;
            Require(allocation.memory != nullptr, "Cannot allocate owned unwind memory.");
            auto* memory = static_cast<unsigned char*>(allocation.memory);
            std::memcpy(memory, code.data(), code.size());
            std::uint32_t cursor = (codeBytes + 3) & ~3u;
            std::vector<RUNTIME_FUNCTION> table;
            std::vector<Phase> phases;
            table.reserve(phaseCount);
            for (std::uint32_t index = 0; index < phaseCount; ++index) {
                const auto phase = Read<Phase>(input);
                Require(phase.begin < phase.end && phase.end <= codeBytes && phase.depth <= 128 &&
                        (phase.unwindBytes == 4 || phase.unwindBytes == 8), "Invalid phase contract.");
                Require(index == 0 ? phase.begin == 0 : phase.begin == phases.back().end, "Phase coverage has a gap.");
                input.read(reinterpret_cast<char*>(memory + cursor), phase.unwindBytes);
                Require(static_cast<bool>(input), "Incomplete unwind metadata.");
                table.push_back({phase.begin, phase.end, cursor});
                phases.push_back(phase);
                cursor += phase.unwindBytes;
            }
            Require(phases.back().end == codeBytes, "The final phase does not cover the stub.");
            DWORD previous{};
            Require(VirtualProtect(memory, 65536, PAGE_EXECUTE_READ, &previous) != FALSE, "Cannot protect owned stub memory.");
            const auto base = reinterpret_cast<DWORD64>(memory);
            Registration registration{table.data()};
            registration.active = RtlAddFunctionTable(table.data(), phaseCount, base) != FALSE;
            Require(registration.active, "Windows refused owned runtime function registration.");
            for (std::uint32_t index = 0; index < phaseCount; ++index) {
                DWORD64 foundBase{};
                const auto found = RtlLookupFunctionEntry(base + table[index].BeginAddress, &foundBase, nullptr);
                Require(found == &table[index] && foundBase == base, "Windows runtime lookup differs.");
                Require(Probe(base, table[index], phases[index].depth), "Windows leaf unwinding differs.");
                ++probes;
                // At the first push instruction, the owned metadata must not invent a stack slot.
                if (index == 0 && code[0] == 0x9c) {
                    auto wrong = table[index];
                    const std::array<unsigned char,8> invalid{1,0,1,0,0,2,0,0};
                    Allocation mutant;
                    Require(mutant.memory != nullptr, "Cannot allocate the metadata mutant.");
                    auto* changed = static_cast<unsigned char*>(mutant.memory);
                    std::memcpy(changed, code.data(), code.size());
                    wrong.UnwindData = (codeBytes + 3) & ~3u;
                    std::memcpy(changed + wrong.UnwindData, invalid.data(), invalid.size());
                    Require(!Probe(reinterpret_cast<DWORD64>(changed), wrong, 0), "The wrong stack phase escaped detection.");
                    ++mutations;
                }
            }
            Require(RtlDeleteFunctionTable(table.data()) != FALSE, "Cannot delete owned runtime function registration.");
            registration.active = false;
            DWORD64 unused{};
            Require(RtlLookupFunctionEntry(base, &unused, nullptr) == nullptr, "The owned table survived deletion.");
        }
        Require(input.peek() == std::char_traits<char>::eof(), "The fixture has trailing data.");
        std::cout << "{\"passed\":true,\"leafStubs\":" << stubs
                  << ",\"instructionBoundaryProbes\":" << probes
                  << ",\"wrongPhaseMutationsRefused\":" << mutations
                  << ",\"registrationDeleted\":true,\"gameWrites\":0}" << '\n';
        return 0;
    } catch (const std::exception& error) {std::cerr << error.what() << '\n'; return 2;}
}
