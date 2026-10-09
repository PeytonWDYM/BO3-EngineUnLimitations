#include "../../patches/code_integrity/Plan.h"
#include <array>
#include <cstring>
#include <stdexcept>
#include <vector>

struct Registers { std::uint64_t ax, dx, cx, flags; };
extern "C" void RunEvaluator(const void*, const std::uint32_t*, const std::uint32_t*, Registers*);

void Check(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

// Execute only authored snippets, never bytes copied from a captured game image.
void ProveSemantics() {
    constexpr std::uint64_t zeroFlag = 0x40;
    constexpr std::uint64_t comparisonFlags = 0x8d5; // OF,SF,ZF,AF,PF,CF
    constexpr std::array<std::array<std::uint32_t,2>,9> pairs{{
        {0,0}, {1,1}, {0xffffffff,0xffffffff},
        {0x80000000,0x80000000}, {0,1}, {1,0}, {0xffffffff,1},
        {0x80000000,0x7fffffff}, {0x12345678,0x87654321}}};
    for (const auto family : {bo3::code_integrity::Family::Xor,
        bo3::code_integrity::Family::NegAdd, bo3::code_integrity::Family::Compare}) {
        const auto original = bo3::code_integrity::Original(family);
        const auto replacement = bo3::code_integrity::Replacement(family);
        for (const auto& pair : pairs) {
            auto Execute = [&](std::span<const unsigned char> instructions,
                std::uint32_t left, std::uint32_t right) {
                auto* code = static_cast<unsigned char*>(VirtualAlloc(nullptr,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
                Check(code != nullptr, "Cannot allocate authored snippet.");
                std::memcpy(code,instructions.data(),instructions.size());
                code[instructions.size()] = 0xc3;
                DWORD prior{};
                Check(VirtualProtect(code,4096,PAGE_EXECUTE_READ,&prior) != FALSE,"Cannot protect authored snippet.");
                Check(FlushInstructionCache(GetCurrentProcess(),code,instructions.size()+1) != FALSE,"Cannot flush authored snippet.");
                Registers result{};
                RunEvaluator(code,&left,&right,&result);
                if(family!=bo3::code_integrity::Family::Compare) {
                    Check(result.dx==reinterpret_cast<std::uintptr_t>(&left),"An endpoint changed its RDX input pointer.");
                    result.dx=0; // Separate snippet calls have distinct authored input cells.
                }
                Check(VirtualFree(code,0,MEM_RELEASE) != FALSE,"Cannot free authored snippet.");
                return result;
            };
            const auto matched = Execute(original,pair[0],pair[0]);
            const auto patched = Execute(replacement,pair[0],pair[1]);
            if (family == bo3::code_integrity::Family::Compare) {
                Check(patched.ax == pair[0] && patched.dx == pair[1],"CMP changed a loaded register.");
                Check((patched.flags & comparisonFlags) == (matched.flags & comparisonFlags),"CMP matched flags differ.");
                Check(patched.cx == matched.cx,"CMP changed RCX.");
            } else {
                Check(patched.cx == 0 && matched.cx == 0,"An endpoint changed the matched ECX result.");
                Check((patched.flags & zeroFlag) == (matched.flags & zeroFlag),"The live zero flag differs.");
                Check(patched.ax == matched.ax && patched.dx == matched.dx,"An endpoint changed unrelated registers.");
            }
        }
    }
}
