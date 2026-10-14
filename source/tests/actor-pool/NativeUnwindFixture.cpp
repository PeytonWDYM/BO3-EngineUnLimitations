// Compare owned stubs with Windows unwinding of their captured native frames. Never execute game code.
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
void Require(bool condition, const char* message) {if (!condition) throw std::runtime_error(message);}
template<class T> T Read(std::ifstream& input) {
    T value{}; input.read(reinterpret_cast<char*>(&value), sizeof(value));
    Require(static_cast<bool>(input), "Incomplete owned native unwind input."); return value;
}
std::vector<unsigned char> Bytes(std::ifstream& input, std::uint32_t size) {
    Require(size < 65536, "The owned byte extent exceeds its allocation.");
    std::vector<unsigned char> result(size);
    input.read(reinterpret_cast<char*>(result.data()), size);
    Require(static_cast<bool>(input), "Incomplete owned byte interval."); return result;
}
struct Allocation {
    void* memory = VirtualAlloc(nullptr, 131072, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    ~Allocation() {if (memory) VirtualFree(memory, 0, MEM_RELEASE);}
    unsigned char* data() {Require(memory != nullptr, "Cannot allocate owned unwind memory."); return static_cast<unsigned char*>(memory);}
    DWORD64 base() {return reinterpret_cast<DWORD64>(data());}
    void protect() {DWORD previous{}; Require(VirtualProtect(data(), 131072, PAGE_EXECUTE_READ, &previous) != FALSE, "Cannot protect owned unwind memory.");}
};
struct Registration {
    PRUNTIME_FUNCTION table;
    bool active = false;
    ~Registration() {if (active) RtlDeleteFunctionTable(table);}
    void add(DWORD count, DWORD64 base) {active = RtlAddFunctionTable(table, count, base) != FALSE; Require(active, "Windows refused an owned function table.");}
    void remove(DWORD64 base) {
        Require(RtlDeleteFunctionTable(table) != FALSE, "Cannot delete an owned function table."); active = false;
        DWORD64 unused{}; Require(RtlLookupFunctionEntry(base + table->BeginAddress, &unused, nullptr) == nullptr, "An owned registration survived deletion.");
    }
};
#include "BranchExecution.h"
DWORD64& Register(CONTEXT& context, std::uint32_t index) {
    switch (index) {
    case 3:return context.Rbx; case 5:return context.Rbp; case 6:return context.Rsi; case 7:return context.Rdi;
    case 12:return context.R12; case 13:return context.R13; case 14:return context.R14; case 15:return context.R15;
    default:throw std::runtime_error("The owned contract requests a volatile register.");
    }
}
constexpr std::array<std::uint32_t,8> Nonvolatile{3,5,6,7,12,13,14,15};
CONTEXT Seed(DWORD64 rip, DWORD64 rsp) {
    CONTEXT context{}; context.ContextFlags = CONTEXT_ALL; context.Rip = rip; context.Rsp = rsp;
    for (auto index : Nonvolatile) Register(context, index) = 0x100000000ull + index;
    for (int index = 6; index < 16; ++index) (&context.Xmm0)[index] = {0x200000000ull + index, 0x210000000ll + index};
    return context;
}
void Unwind(DWORD64 base, RUNTIME_FUNCTION& function, CONTEXT& context) {
    PVOID handlerData{}; DWORD64 establisher{};
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, context.Rip, &function, &context, &handlerData, &establisher, nullptr);
}
bool Same(CONTEXT expected, CONTEXT actual) {
    if (expected.Rip != actual.Rip || expected.Rsp != actual.Rsp) return false;
    for (auto index : Nonvolatile) if (Register(expected, index) != Register(actual, index)) return false;
    return std::memcmp(&expected.Xmm6, &actual.Xmm6, 10 * sizeof(M128A)) == 0;
}
struct Header {std::uint32_t site, referenceBytes, begin, end, unwind, control, stackCount, returnOffset, codeBytes, phaseCount, procedureEnd;};
struct StackWrite {std::uint32_t offset, width, reg;};
struct Phase {std::uint32_t begin, end, depth, unwindBytes, savedCount, nativeBytes;};
struct Saved {std::uint32_t reg, offset;};
// Mutate the actual flattened native metadata, rather than a separate model of its expected result.
std::vector<unsigned char> Mutate(std::vector<unsigned char> bytes, bool allocation) {
    const auto count = bytes[2];
    for (unsigned int slot = 0; slot < count;) {
        const auto position = 4 + slot * 2;
        const auto op = bytes[position + 1] & 15, info = bytes[position + 1] >> 4;
        const auto extra = (op == 4 || op == 8 || (op == 1 && info == 0)) ? 1u : (op == 5 || op == 9 || (op == 1 && info == 1)) ? 2u : 0u;
        if (allocation && (op == 1 || op == 2)) {
            bytes.resize(4 + count * 2);
            bytes.erase(bytes.begin() + position, bytes.begin() + position + (extra + 1) * 2);
            bytes[2] = static_cast<unsigned char>(count - extra - 1);
            bytes.resize((bytes.size() + 3) & ~std::size_t{3}, 0); return bytes;
        }
        if (!allocation && op == 4) {++bytes[position + 2]; return bytes;}
        slot += extra + 1;
    }
    return {};
}
}

int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 2, "Supply the owned native-unwind fixture file.");
        std::ifstream input(argv[1], std::ios::binary);
        const auto magic = Read<std::array<char,8>>(input);
        const bool sourceEntries = magic == std::array<char,8>{'B','O','3','N','F','U','W','2'};
        Require(sourceEntries || magic == std::array<char,8>{'B','O','3','N','F','U','W','1'}, "Unknown native unwind fixture format.");
        const auto cpuBranches = sourceEntries ? CheckBranchExecution() : 0;
        const auto stubs = Read<std::uint32_t>(input);
        const bool clientSnapshots = stubs == 2;
        const bool clientAllocation = stubs == 1;
        Require(clientSnapshots || clientAllocation || stubs == 6 || stubs == 65 || stubs == 66, "Supply a complete admitted client or server continuation plan.");
        std::uint32_t probes{}, depthMutations{}, allocationMutations{}, saveMutations{}, entryProbes{}, entryMutations{};
        for (std::uint32_t stub = 0; stub < stubs; ++stub) {
            const auto header = Read<Header>(input);
            Require(!clientSnapshots || header.site == (stub == 0 ? 0xfc57d5u : 0xfc57f2u),
                    "The client snapshot plan requires both exact sites in their fixed order.");
            Require(!clientAllocation || header.site == 0x840922u || header.site == 0x1b75227u,
                    "The allocation comparison requires an admitted exact native site.");
            Require(header.phaseCount && header.phaseCount < 1024 && header.returnOffset < 32768 && header.stackCount < 256, "Invalid owned frame extent.");
            auto referenceBytes = Bytes(input, header.referenceBytes), code = Bytes(input, header.codeBytes);
            const auto source = sourceEntries ? Bytes(input,Read<std::uint32_t>(input)) : std::vector<unsigned char>{};
            Require(header.begin < header.end && header.end <= header.referenceBytes && header.control >= header.begin && header.control < header.end && header.unwind < header.referenceBytes, "Invalid owned native function.");
            Allocation reference; std::memcpy(reference.data(), referenceBytes.data(), referenceBytes.size());
            RUNTIME_FUNCTION native{header.begin,header.end,header.unwind};
            Registration nativeRegistration{&native}; nativeRegistration.add(1, reference.base());
            alignas(16) std::array<std::uint64_t,8192> stack; stack.fill(0xdeadbeef11111111ull);
            const auto nativeRsp = reinterpret_cast<DWORD64>(&stack[512]) + (header.returnOffset % 16 == 0 ? 8 : 0);
            constexpr DWORD64 returnPc = 0x1234567812345678ull;
            std::memcpy(reinterpret_cast<void*>(nativeRsp + header.returnOffset), &returnPc, 8);
            std::array<bool,16> savedGprs{}, savedVectors{};
            for (std::uint32_t index = 0; index < header.stackCount; ++index) {
                const auto write = Read<StackWrite>(input);
                Require(write.offset + write.width < 40000 && (write.width == 8 || write.width == 16), "Invalid original stack write.");
                if (write.width == 8) {
                    Require(write.reg < 16, "Invalid original GPR save."); savedGprs[write.reg] = true;
                    auto value = 0x300000000ull + write.reg; std::memcpy(reinterpret_cast<void*>(nativeRsp + write.offset), &value, 8);
                } else {
                    Require(write.reg >= 6 && write.reg < 16, "Invalid original vector save."); savedVectors[write.reg] = true;
                    const M128A value{0x400000000ull + write.reg,0x410000000ll + write.reg};
                    std::memcpy(reinterpret_cast<void*>(nativeRsp + write.offset), &value, 16);
                }
            }
            auto expected = Seed(reference.base() + header.control, nativeRsp);
            Unwind(reference.base(), native, expected);
            Require(expected.Rip == returnPc && expected.Rsp == nativeRsp + header.returnOffset + 8, "The original Windows frame disagrees with its owned stack contract.");
            for (auto reg : Nonvolatile) Require(Register(expected, reg) == (savedGprs[reg] ? 0x300000000ull : 0x100000000ull) + reg,
                                                "The original Windows frame did not restore its native GPR save.");
            for (int reg = 6; reg < 16; ++reg) {
                const M128A value{(savedVectors[reg] ? 0x400000000ull : 0x200000000ull) + reg,
                                  (savedVectors[reg] ? 0x410000000ll : 0x210000000ll) + reg};
                Require(std::memcmp(&(&expected.Xmm0)[reg], &value, sizeof(value)) == 0, "The original Windows frame did not restore its native vector save.");
            }
            if (sourceEntries) {
                Require(source.size() >= 6 && header.control + source.size() <= header.end, "The complete source replacement exceeds its native frame.");
                Require(source[0]==0x40 && source[1]==0xE9,"The source continuation lacks its admitted neutral prefix.");
                std::memcpy(reference.data()+header.control,source.data(),source.size());
                auto actual = Seed(reference.base()+header.control,nativeRsp);
                Unwind(reference.base(),native,actual);
                if (!Same(expected,actual)) {
                    std::cerr << "sourceSite=" << std::hex << header.site << " expectedRip=" << expected.Rip << " actualRip=" << actual.Rip << '\n';
                    throw std::runtime_error("The actual source branch lost its active native frame.");
                }
                ++entryProbes;
                Allocation stale;
                std::memcpy(stale.data(),referenceBytes.data(),referenceBytes.size());
                auto* branch = stale.data()+header.control;
                *branch++ = 0xE9;
                std::int32_t displacement{};
                std::memcpy(&displacement,source.data()+2,4);
                Require(displacement < INT32_MAX,"The owned source mutation exceeds relative reach.");
                ++displacement;std::memcpy(branch,&displacement,4);
                auto invalid = Seed(stale.base()+header.control,nativeRsp);
                Unwind(stale.base(),native,invalid);
                Require(!Same(expected,invalid),"The plain external source jump escaped epilogue detection.");
                ++entryMutations;
            }
            constexpr std::uint32_t codeOffset = 0x10000;
            std::memcpy(reference.data() + codeOffset, code.data(), code.size());
            auto cursor = codeOffset + ((header.codeBytes + 3) & ~3u);
            std::vector<RUNTIME_FUNCTION> table; std::vector<Phase> phases;
            std::vector<std::vector<unsigned char>> nativeMetadata; std::vector<std::vector<Saved>> saved;
            table.reserve(header.phaseCount);
            for (std::uint32_t index = 0; index < header.phaseCount; ++index) {
                auto phase = Read<Phase>(input);
                Require(phase.begin < phase.end && phase.end <= code.size() && phase.depth <= 128 && phase.savedCount <= 8, "Invalid continuation phase.");
                Require(index == 0 ? phase.begin == 0 : phase.begin == phases.back().end, "Continuation phase coverage has a gap.");
                auto metadata = Bytes(input, phase.unwindBytes); nativeMetadata.push_back(Bytes(input, phase.nativeBytes));
                Require(cursor + metadata.size() + 16 < 131072, "Continuation metadata exceeds its allocation.");
                const auto primaryUnwind = cursor;
                std::memcpy(reference.data() + cursor, metadata.data(), metadata.size()); cursor += phase.unwindBytes;
                const std::array<unsigned char,4> chainHeader{0x21,0,0,0};
                std::memcpy(reference.data() + cursor, chainHeader.data(), chainHeader.size());
                const RUNTIME_FUNCTION primary{0,header.procedureEnd,primaryUnwind};
                std::memcpy(reference.data() + cursor + 4, &primary, sizeof(primary));
                table.push_back({codeOffset + phase.begin,codeOffset + phase.end,cursor}); cursor += 16; phases.push_back(phase);
                auto& registers = saved.emplace_back();
                for (std::uint32_t save = 0; save < phase.savedCount; ++save) registers.push_back(Read<Saved>(input));
            }
            Require(phases.back().end == code.size(), "The last continuation phase does not cover the stub."); reference.protect();
            Registration emittedRegistration{table.data()}; emittedRegistration.add(header.phaseCount, reference.base());
            for (std::uint32_t index = 0; index < header.phaseCount; ++index) {
                auto context = Seed(reference.base() + codeOffset + phases[index].begin, nativeRsp - phases[index].depth);
                for (const auto& save : saved[index]) {
                    Require(save.offset + 8 <= phases[index].depth, "A temporary save exceeds its stack allocation.");
                    const auto value = Register(context, save.reg); std::memcpy(reinterpret_cast<void*>(context.Rsp + save.offset), &value, 8);
                }
                DWORD64 foundBase{};
                Require(RtlLookupFunctionEntry(context.Rip, &foundBase, nullptr) == &table[index] && foundBase == reference.base(), "Continuation runtime lookup differs.");
                auto actual = context; Unwind(reference.base(), table[index], actual);
                if (!Same(expected, actual)) {
                    std::cerr << "site=" << std::hex << header.site << " phase=" << index
                              << " depth=" << phases[index].depth << " nativeReturnOffset=" << header.returnOffset
                              << " expectedRip=" << expected.Rip << " actualRip=" << actual.Rip
                              << " expectedRsp=" << expected.Rsp << " actualRsp=" << actual.Rsp << '\n';
                    for (auto reg : Nonvolatile) if (Register(expected, reg) != Register(actual, reg))
                        std::cerr << "gpr=" << reg << " expected=" << Register(expected, reg) << " actual=" << Register(actual, reg) << '\n';
                    for (int reg = 6; reg < 16; ++reg) if (std::memcmp(&(&expected.Xmm0)[reg], &(&actual.Xmm0)[reg], sizeof(M128A)))
                        std::cerr << "xmm=" << reg << " expected=" << (&expected.Xmm0)[reg].Low << " actual=" << (&actual.Xmm0)[reg].Low << '\n';
                    throw std::runtime_error("Windows continuation unwinding differs from the original native frame.");
                }
                ++probes;
                auto mutant = [&](const std::vector<unsigned char>& metadata) {
                    Allocation changed; std::memcpy(changed.data() + codeOffset, code.data(), code.size());
                    const auto offset = codeOffset + ((header.codeBytes + 3) & ~3u); std::memcpy(changed.data() + offset, metadata.data(), metadata.size());
                    const auto chainOffset = offset + static_cast<std::uint32_t>(metadata.size());
                    const std::array<unsigned char,4> chainHeader{0x21,0,0,0};
                    std::memcpy(changed.data() + chainOffset, chainHeader.data(), chainHeader.size());
                    const RUNTIME_FUNCTION primary{0,header.procedureEnd,offset};
                    std::memcpy(changed.data() + chainOffset + 4, &primary, sizeof(primary));
                    auto function = table[index]; function.UnwindData = chainOffset;
                    auto invalid = context; invalid.Rip = changed.base() + codeOffset + phases[index].begin;
                    Unwind(changed.base(), function, invalid); Require(!Same(expected, invalid), "A wrong continuation metadata mutation escaped detection.");
                };
                if (phases[index].depth) {mutant(nativeMetadata[index]); ++depthMutations;}
                if (index == 0) {
                    const auto omitted = Mutate(nativeMetadata[index], true);
                    if (!omitted.empty()) {mutant(omitted); ++allocationMutations;}
                    const auto wrongSave = Mutate(nativeMetadata[index], false);
                    if (!wrongSave.empty()) {mutant(wrongSave); ++saveMutations;}
                }
            }
            emittedRegistration.remove(reference.base()); nativeRegistration.remove(reference.base());
        }
        Require(input.peek() == std::char_traits<char>::eof(), "The owned fixture has trailing data.");
        std::cout << "{\"passed\":true,\"nativeContinuations\":" << stubs << ",\"instructionBoundaryProbes\":" << probes
                  << ",\"sourceEntryProbes\":" << entryProbes
                  << ",\"plainEntryMutationsRefused\":" << entryMutations
                  << ",\"cpuBranchComparisons\":" << cpuBranches
                  << ",\"wrongDepthMutationsRefused\":" << depthMutations << ",\"missingNativeAllocationMutationsRefused\":" << allocationMutations
                  << ",\"wrongNativeSaveMutationsRefused\":" << saveMutations << ",\"registrationsDeleted\":true,\"gameWrites\":0}\n";
        return 0;
    } catch (const std::exception& error) {std::cerr << error.what() << '\n'; return 2;}
}
