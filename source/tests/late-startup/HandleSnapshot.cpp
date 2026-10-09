#include "HandleSnapshot.h"
#include "../../launch/preentry/Identity.h"
#include <ProcessSnapshot.h>
#include <fstream>
#include <sstream>

std::vector<std::string> SaveHandles(const std::filesystem::path& path) {
    struct Snapshot {HPSS value{};~Snapshot(){if(value)PssFreeSnapshot(GetCurrentProcess(),value);}} snapshot;
    struct Marker {HPSSWALK value{};~Marker(){if(value)PssWalkMarkerFree(value);}} marker;
    const auto flags=static_cast<PSS_CAPTURE_FLAGS>(PSS_CAPTURE_HANDLES|PSS_CAPTURE_HANDLE_BASIC_INFORMATION|PSS_CAPTURE_HANDLE_TYPE_SPECIFIC_INFORMATION);
    Require(PssCaptureSnapshot(GetCurrentProcess(),flags,0,&snapshot.value)==ERROR_SUCCESS,"Cannot capture owned handle information.");
    Require(PssWalkMarkerCreate(nullptr,&marker.value)==ERROR_SUCCESS,"Cannot create the handle walk marker.");
    std::ofstream file(path);std::vector<std::string> rows;
    for(;;) {
        PSS_HANDLE_ENTRY entry{};const auto result=PssWalkSnapshot(snapshot.value,PSS_WALK_HANDLES,marker.value,&entry,sizeof(entry));
        if(result==ERROR_NO_MORE_ITEMS)break;
        Require(result==ERROR_SUCCESS,"Cannot walk owned handle information.");
        std::ostringstream row;row<<std::hex<<reinterpret_cast<std::uintptr_t>(entry.Handle)<<std::dec<<'\t'<<entry.ObjectType<<'\t';
        if(entry.TypeName)for(unsigned int i=0;i<entry.TypeNameLength/sizeof(wchar_t);++i)
            if(entry.TypeName[i])row<<static_cast<char>(entry.TypeName[i]<128 ? entry.TypeName[i] : L'?');
        if(entry.Flags&PSS_HANDLE_HAVE_TYPE_SPECIFIC_INFORMATION) {
            if(entry.ObjectType==PSS_OBJECT_TYPE_PROCESS)row<<"\tpid="<<entry.TypeSpecificInformation.Process.ProcessId;
            if(entry.ObjectType==PSS_OBJECT_TYPE_THREAD)row<<"\tpid="<<entry.TypeSpecificInformation.Thread.ProcessId<<"\ttid="<<entry.TypeSpecificInformation.Thread.ThreadId;
        }
        rows.push_back(row.str());file<<row.str()<<'\n';
    }
    Require(file.good(),"Cannot save owned handle information.");
    return rows;
}
