#include "Internal.h"

// The reused memory provider needs only this HRESULT check, not the old report writer or its CRT initializers.
namespace fixture {
void Ok(HRESULT result) {
    if (FAILED(result)) StopSdk(result, Stage::Error);
}
}
