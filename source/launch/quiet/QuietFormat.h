#pragma once
#include "QuietBoundary.h"

namespace quiet {
struct SoundContract {
    DWORD bufferBytes;
    BYTE silenceByte;
};
HRESULT ReadSoundContract(IDirectSoundBuffer8* sink, SoundContract& contract);
}
