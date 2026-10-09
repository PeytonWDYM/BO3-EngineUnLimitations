#include "QuietFormat.h"
#include <mmreg.h>
#include <ks.h>
#include <ksmedia.h>

namespace quiet {
HRESULT ReadSoundContract(IDirectSoundBuffer8* sink, SoundContract& contract) {
    DSBCAPS caps{};
    caps.dwSize = sizeof(caps);
    HRESULT result = sink->GetCaps(&caps);
    if (FAILED(result)) return result;
    constexpr DWORD supportedCaps = DSBCAPS_STATIC | DSBCAPS_LOCHARDWARE | DSBCAPS_LOCSOFTWARE |
        DSBCAPS_CTRLFREQUENCY | DSBCAPS_CTRLPAN | DSBCAPS_CTRLVOLUME | DSBCAPS_STICKYFOCUS |
        DSBCAPS_GLOBALFOCUS | DSBCAPS_GETCURRENTPOSITION2 | DSBCAPS_TRUEPLAYPOSITION;
    if (caps.dwFlags & ~supportedCaps) return DSERR_CONTROLUNAVAIL;
    DWORD status = 0;
    result = sink->GetStatus(&status);
    if (FAILED(result)) return result;
    if (status & DSBSTATUS_PLAYING) return DSERR_INVALIDCALL;
    if (status & DSBSTATUS_BUFFERLOST) return DSERR_BUFFERLOST;
    DWORD formatBytes = 0;
    result = sink->GetFormat(nullptr, 0, &formatBytes);
    if (FAILED(result)) return result;
    if (formatBytes < sizeof(WAVEFORMATEX) || formatBytes > sizeof(WAVEFORMATEXTENSIBLE)) return DSERR_BADFORMAT;
    WAVEFORMATEXTENSIBLE format{};
    result = sink->GetFormat(&format.Format, sizeof(format), nullptr);
    if (FAILED(result)) return result;
    const auto& wave = format.Format;
    WORD tag = wave.wFormatTag;
    if (tag == WAVE_FORMAT_EXTENSIBLE) {
        if (formatBytes != sizeof(format) || wave.cbSize != 22 || format.Samples.wValidBitsPerSample != wave.wBitsPerSample) return DSERR_BADFORMAT;
        if (format.SubFormat == KSDATAFORMAT_SUBTYPE_PCM) tag = WAVE_FORMAT_PCM;
        else if (format.SubFormat == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) tag = WAVE_FORMAT_IEEE_FLOAT;
        else return DSERR_BADFORMAT;
    } else if (wave.cbSize != 0 || formatBytes != sizeof(WAVEFORMATEX)) return DSERR_BADFORMAT;
    const bool supported = (tag == WAVE_FORMAT_PCM && (wave.wBitsPerSample == 8 || wave.wBitsPerSample == 16)) ||
        (tag == WAVE_FORMAT_IEEE_FLOAT && wave.wBitsPerSample == 32);
    const DWORD alignment = static_cast<DWORD>(wave.nChannels) * (wave.wBitsPerSample / 8);
    if (!supported || !wave.nChannels || !wave.nSamplesPerSec || alignment != wave.nBlockAlign ||
        static_cast<ULONGLONG>(wave.nSamplesPerSec) * alignment != wave.nAvgBytesPerSec ||
        !caps.dwBufferBytes || caps.dwBufferBytes % alignment) return DSERR_BADFORMAT;
    contract = {caps.dwBufferBytes, static_cast<BYTE>(tag == WAVE_FORMAT_PCM && wave.wBitsPerSample == 8 ? 0x80 : 0)};
    return S_OK;
}
}
