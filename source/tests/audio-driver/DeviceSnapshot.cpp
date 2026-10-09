#include "DeviceSnapshot.h"
#include <endpointvolume.h>
#include <iomanip>
#include <sstream>

namespace driver_probe {
namespace {
std::string Number(float value) {
    std::ostringstream out; out << std::setprecision(9) << value; return out.str();
}
}
std::string DeviceSnapshot(Trace& trace) {
    ComPtr<IMMDeviceEnumerator> enumerator;
    Check(trace,"snapshot.CoCreateInstance",CoCreateInstance(__uuidof(MMDeviceEnumerator),nullptr,CLSCTX_ALL,__uuidof(IMMDeviceEnumerator),reinterpret_cast<void**>(enumerator.GetAddressOf())));
    std::string snapshot="{\"renderDefaults\":[";
    for(const ERole role : {eConsole,eMultimedia,eCommunications}) {
        if(role!=eConsole) snapshot+=',';
        ComPtr<IMMDevice> device;
        Check(trace,"snapshot.GetDefaultAudioEndpoint",enumerator->GetDefaultAudioEndpoint(eRender,role,&device));
        LPWSTR rawId=nullptr;
        Check(trace,"snapshot.GetId",device->GetId(&rawId));
        const std::unique_ptr<wchar_t,decltype(&CoTaskMemFree)> id(rawId,CoTaskMemFree);
        ComPtr<IAudioEndpointVolume> volume;
        Check(trace,"snapshot.ActivateEndpointVolume",device->Activate(__uuidof(IAudioEndpointVolume),CLSCTX_ALL,nullptr,reinterpret_cast<void**>(volume.GetAddressOf())));
        float master=0; BOOL mute=FALSE; UINT channels=0;
        Check(trace,"snapshot.GetMasterVolume",volume->GetMasterVolumeLevelScalar(&master));
        Check(trace,"snapshot.GetMute",volume->GetMute(&mute));
        Check(trace,"snapshot.GetChannelCount",volume->GetChannelCount(&channels));
        snapshot+="{\"role\":"+std::to_string(role)+",\"id\":"+Quote(Utf8(id.get()))+",\"master\":"+Number(master)+
            ",\"mute\":"+(mute ? "true" : "false")+",\"channels\":[";
        for(UINT channel=0;channel<channels;++channel) {
            if(channel) snapshot+=',';
            float value=0;
            Check(trace,"snapshot.GetChannelVolume",volume->GetChannelVolumeLevelScalar(channel,&value));
            snapshot+=Number(value);
        }
        snapshot+="]}";
    }
    GUID playback{};
    Check(trace,"snapshot.GetDeviceID.defaultPlayback",GetDeviceID(&DSDEVID_DefaultPlayback,&playback));
    wchar_t guid[40]{}; StringFromGUID2(playback,guid,40);
    return snapshot+"],\"directSoundDefaultPlayback\":"+Quote(Utf8(guid))+'}';
}
}
