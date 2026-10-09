#include "../../patches/vm_startup/PausedPatch.h"
#include "../preentry/Identity.h"

namespace vm_startup {
// The passive binary links only this process reader. It does not link the patch writer.
std::vector<unsigned char> ReadStopped(HANDLE process,std::uintptr_t address,std::size_t length) {
    std::vector<unsigned char> bytes(length);SIZE_T count{};
    Require(ReadProcessMemory(process,reinterpret_cast<void*>(address),bytes.data(),length,&count)
        && count==length,"Cannot read the complete passive observation range.");
    return bytes;
}
}
