#include "Probe.h"
#include <ks.h>
#include <ksmedia.h>
#include <cstring>

namespace driver_probe {
SilenceFormat ValidateFormat(const WAVEFORMATEX& format) {
    WORD tag=format.wFormatTag;
    if(tag==WAVE_FORMAT_EXTENSIBLE) {
        if(format.cbSize!=22) throw Failure(AUDCLNT_E_UNSUPPORTED_FORMAT,"format.extension-size");
        const auto& extended=reinterpret_cast<const WAVEFORMATEXTENSIBLE&>(format);
        if(extended.Samples.wValidBitsPerSample!=format.wBitsPerSample) throw Failure(AUDCLNT_E_UNSUPPORTED_FORMAT,"format.valid-bits");
        if(extended.SubFormat==KSDATAFORMAT_SUBTYPE_PCM) tag=WAVE_FORMAT_PCM;
        else if(extended.SubFormat==KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) tag=WAVE_FORMAT_IEEE_FLOAT;
        else throw Failure(AUDCLNT_E_UNSUPPORTED_FORMAT,"format.subtype");
    } else if(format.cbSize) throw Failure(AUDCLNT_E_UNSUPPORTED_FORMAT,"format.extra-bytes");
    const bool supported=(tag==WAVE_FORMAT_PCM && (format.wBitsPerSample==8 || format.wBitsPerSample==16)) ||
        (tag==WAVE_FORMAT_IEEE_FLOAT && format.wBitsPerSample==32);
    const DWORD alignment=static_cast<DWORD>(format.nChannels)*(format.wBitsPerSample/8);
    if(!supported || !format.nChannels || !format.nSamplesPerSec || alignment!=format.nBlockAlign ||
        static_cast<ULONGLONG>(format.nSamplesPerSec)*alignment!=format.nAvgBytesPerSec)
        throw Failure(AUDCLNT_E_UNSUPPORTED_FORMAT,"format.layout");
    return {static_cast<BYTE>(tag==WAVE_FORMAT_PCM && format.wBitsPerSample==8 ? 0x80 : 0),format.nBlockAlign};
}
void FillSilence(void* data, size_t bytes, SilenceFormat format) {
    if(bytes%format.alignment) throw Failure(E_INVALIDARG,"format.partial-frame");
    if(bytes) std::memset(data,format.byte,bytes);
}
WAVEFORMATEX Wave(WORD tag, WORD bits) {
    const WORD alignment=static_cast<WORD>(2*(bits/8));
    return {tag,2,48000,static_cast<DWORD>(48000*alignment),alignment,bits,0};
}
std::string FormatJson(const WAVEFORMATEX& format) {
    std::string text="{\"tag\":"+std::to_string(format.wFormatTag)+",\"channels\":"+std::to_string(format.nChannels)+
        ",\"sampleRate\":"+std::to_string(format.nSamplesPerSec)+",\"bits\":"+std::to_string(format.wBitsPerSample)+
        ",\"blockAlign\":"+std::to_string(format.nBlockAlign)+",\"averageBytes\":"+std::to_string(format.nAvgBytesPerSec)+
        ",\"extraBytes\":"+std::to_string(format.cbSize);
    if(format.wFormatTag==WAVE_FORMAT_EXTENSIBLE && format.cbSize==22) {
        const auto& ext=reinterpret_cast<const WAVEFORMATEXTENSIBLE&>(format);
        text+=",\"validBits\":"+std::to_string(ext.Samples.wValidBitsPerSample)+",\"channelMask\":"+std::to_string(ext.dwChannelMask)+
            ",\"subtype\":"+Quote(ext.SubFormat==KSDATAFORMAT_SUBTYPE_PCM ? "PCM" : ext.SubFormat==KSDATAFORMAT_SUBTYPE_IEEE_FLOAT ? "IEEE_FLOAT" : "unsupported");
    }
    return text+'}';
}
}
