#pragma once
#include "ErrorOwned.h"

// This code owns the complete executable page. No external process memory is accepted.
class ErrorHooks {
    unsigned char* page_;
public:
    ErrorHooks();
    ~ErrorHooks();
    void InstallLater();
    bo3::vm::ErrorFunction Entry() const;
    bo3::vm::ErrorFunction Original() const;
    bo3::vm::ErrorFunction LaterOriginal() const;
    ErrorHooks(const ErrorHooks&)=delete;
    ErrorHooks& operator=(const ErrorHooks&)=delete;
};
