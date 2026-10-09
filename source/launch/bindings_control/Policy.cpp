#include "Policy.h"
#include "../preentry/Identity.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "HelperBootProfile.h"
#include <bcrypt.h>
#include <array>
#include <algorithm>
#include <cstring>

namespace bo3::bindings_control {
namespace {
std::string Hex(const std::vector<unsigned char>& raw) {
    constexpr char digits[]="0123456789abcdef";std::string text; text.reserve(raw.size()*2);
    for(const auto byte:raw){text+=digits[byte>>4];text+=digits[byte&15];}return text;
}
std::string Hash(const std::vector<unsigned char>& raw) {
    std::vector<unsigned char> digest(32);
    Require(BCryptHash(BCRYPT_SHA256_ALG_HANDLE,nullptr,0,const_cast<unsigned char*>(raw.data()),
        static_cast<ULONG>(raw.size()),digest.data(),32)==0,"Cannot hash a stock instruction span.");return Hex(digest);
}
}
Selected Select(const late_startup::PreparedPlan& plan,std::uintptr_t image,const enhanced::MappedHelper& helper) {
    Require(plan.edits.size()==42 && plan.relay,"The fixed complete 42-edit plan is required.");
    auto originals=job_control::StockOriginals(image,helper);
    Selected selected;selected.stock.assign(originals.begin(),originals.begin()+33);
    const std::array<std::pair<std::uintptr_t,std::size_t>,9> permitted{{
        {helper.image.base+helper.state.stateBindings,48},{helper.image.base+helper.state.errorBindings,32},
        {helper.image.base+helper.migration.bindings,64},{helper.image.base+helper.migration.versionBranches,16},
        {helper.image.base+helper.migration.loadBindings,16},{helper.image.base+helper.migration.reentries,56},
        {helper.image.base+helper.migration.flushBindings,16},{plan.relay->Address(),64},{plan.relay->Address()+64,128}}};
    std::array<bool,9> found{};std::array<bool,33> gameFound{};
    for(const auto& edit:plan.edits) {
        bool matched=false;
        for(std::size_t i=0;i<permitted.size();++i) {
            if(edit.address!=permitted[i].first)continue;
            Require(!found[i] && edit.original.size()==permitted[i].second && edit.replacement.size()==permitted[i].second
                && std::all_of(edit.original.begin(),edit.original.end(),[](unsigned char b){return b==0;}),
                "A permitted helper or relay record differs from the fixed plan.");
            found[i]=true;matched=true;selected.publications.push_back(edit);break;
        }
        if(matched)continue;
        for(std::size_t i=0;i<selected.stock.size();++i) {
            const auto& original=selected.stock[i];
            if(edit.address!=original.address)continue;
            Require(!gameFound[i] && edit.original==original.bytes && edit.replacement.size()==original.bytes.size(),
                "A withheld game edit differs from the independent stock original.");
            gameFound[i]=true;matched=true;break;
        }
        Require(matched,"The fixed plan contains an unrecognized publication.");
    }
    Require(std::all_of(found.begin(),found.end(),[](bool b){return b;})
        && std::all_of(gameFound.begin(),gameFound.end(),[](bool b){return b;}),"The nine/33 partition is incomplete.");
    return selected;
}
void Capture(HANDLE process,const Selected& selected,const enhanced::MappedHelper& helper,Proof& proof,bool after) {
    job_control::VerifyOriginals(process,selected.stock);
    if(!after){proof.publications.reserve(9);proof.stock.reserve(33);}
    for(std::size_t i=0;i<selected.publications.size();++i) {
        const auto& edit=selected.publications[i];const auto raw=vm_startup::ReadStopped(process,edit.address,edit.original.size());
        Require(raw==(after?edit.replacement:edit.original),"A selected publication readback differs.");
        if(after)proof.publications[i].after=Hex(raw);else proof.publications.push_back({edit.address,Hex(raw),{}});
    }
    for(std::size_t i=0;i<selected.stock.size();++i) {
        const auto& row=selected.stock[i];const auto digest=Hash(vm_startup::ReadStopped(process,row.address,row.bytes.size()));
        if(after)proof.stock[i].after=digest;else proof.stock.push_back({row.address,digest,{}});
    }
    const auto boot=vm_startup::ReadStopped(process,helper.image.base+kHelperBootRva,sizeof(enhanced::BootRecord));
    enhanced::BootRecord value{};std::memcpy(&value,boot.data(),sizeof(value));
    Require(value.abi==enhanced::BootAbi && value.bytes==sizeof(value) && value.module==helper.image.base
        && value.ready==1 && value.reserved==0,"The helper Boot record differs.");
    if(after){proof.bootAfter=Hex(boot);Require(proof.bootBefore==proof.bootAfter,"Helper Boot changed during publication.");}
    else proof.bootBefore=Hex(boot);
}
}
