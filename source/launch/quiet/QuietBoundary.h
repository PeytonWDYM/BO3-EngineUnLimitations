#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <audioclient.h>
#include <dsound.h>

namespace quiet {
// The caller surrenders raw aliases. Only these SDK interfaces remain exposed.
HRESULT WrapRenderClient(IAudioRenderClient* sink, IAudioRenderClient** output);

// Wrap a stopped secondary buffer before Play, without effects or raw locks.
// Supports PCM8, PCM16, and float32. Lock writes use private scratch memory.
// One Lock/Unlock pair is allowed, with the exact returned pointers and sizes.
HRESULT WrapSoundBuffer(IDirectSoundBuffer8* sink, IDirectSoundBuffer8** output);
}
