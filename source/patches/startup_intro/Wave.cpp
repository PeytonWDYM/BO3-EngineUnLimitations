#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <mmsystem.h>
#include <cstdint>
#include <cstring>
#include "Wave.h"

namespace bo3::startup_intro {
namespace {
HWAVEOUT device{};
WAVEHDR header{};
unsigned char* storage{};
bool prepared=false;
std::uint32_t Word(const unsigned char* p) {std::uint32_t value;std::memcpy(&value,p,4);return value;}
}
void StopWave() {
    // Retain storage on a driver refusal; freeing a queued buffer is unsafe.
    if(device) {
        if(waveOutReset(device)!=MMSYSERR_NOERROR) return;
        if(prepared && waveOutUnprepareHeader(device,&header,sizeof(header))!=MMSYSERR_NOERROR) return;
        prepared=false;
        if(waveOutClose(device)!=MMSYSERR_NOERROR) return;
        device=nullptr;
    }
    if(storage) HeapFree(GetProcessHeap(),0,storage);
    storage=nullptr;header={};
}
bool StartWave() {
    if(storage || device) return false;
    const auto file=CreateFileW(L"video\\BO3_500K_Custom_Intro.wav",GENERIC_READ,FILE_SHARE_READ,
        nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER size{};
    if(!GetFileSizeEx(file,&size) || size.QuadPart<44 || size.QuadPart>16*1024*1024) {CloseHandle(file);return false;}
    const auto bytes=static_cast<DWORD>(size.QuadPart);
    storage=static_cast<unsigned char*>(HeapAlloc(GetProcessHeap(),0,bytes));
    DWORD read=0;
    const bool loaded=storage && ReadFile(file,storage,bytes,&read,nullptr) && read==bytes;
    CloseHandle(file);
    if(!loaded) {StopWave();return false;}
    WAVEFORMATEX format{};bool haveFormat=false;
    if(std::memcmp(storage,"RIFF",4)==0 && std::memcmp(storage+8,"WAVE",4)==0) {
        for(std::uint32_t offset=12;offset<=bytes-8;) {
            const auto length=Word(storage+offset+4),start=offset+8;
            if(length>bytes-start) break;
            if(std::memcmp(storage+offset,"fmt ",4)==0 && length>=16) {
                std::memcpy(&format,storage+start,16);haveFormat=true;
            }
            if(std::memcmp(storage+offset,"data",4)==0) {header.lpData=reinterpret_cast<char*>(storage+start);header.dwBufferLength=length;}
            const auto next=static_cast<std::uint64_t>(start)+length+(length&1);
            if(next>bytes) break;
            offset=static_cast<std::uint32_t>(next);
        }
    }
    if(!haveFormat || format.wFormatTag!=WAVE_FORMAT_PCM || format.nChannels!=2 ||
        format.nSamplesPerSec!=48000 || format.wBitsPerSample!=16 || format.nBlockAlign!=4 ||
        format.nAvgBytesPerSec!=192000 || !header.lpData || !header.dwBufferLength || header.dwBufferLength%4) {
        StopWave();return false;
    }
    if(waveOutOpen(&device,WAVE_MAPPER,&format,0,0,CALLBACK_NULL)!=MMSYSERR_NOERROR) {StopWave();return false;}
    prepared=waveOutPrepareHeader(device,&header,sizeof(header))==MMSYSERR_NOERROR;
    if(!prepared || waveOutWrite(device,&header,sizeof(header))!=MMSYSERR_NOERROR) {StopWave();return false;}
    return true;
}
}
