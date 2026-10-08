option casemap:none
EXTERN ClearNativeImportContext:PROC
EXTERN Bo3VmErrorBindings:BYTE
PUBLIC VmErrorPrelude
PUBLIC VmErrorPreludeBody
.code
; Preserve fixed arguments and the caller's untouched variadic stack layout.
VmErrorPrelude PROC FRAME
    sub rsp,48h
    .allocstack 48h
    .endprolog
VmErrorPreludeBody LABEL BYTE
    mov [rsp+20h],rcx
    mov [rsp+28h],rdx
    mov [rsp+30h],r8
    mov [rsp+38h],r9
    call ClearNativeImportContext
    mov rcx,[rsp+20h]
    mov rdx,[rsp+28h]
    mov r8,[rsp+30h]
    mov r9,[rsp+38h]
    add rsp,48h
    jmp QWORD PTR [Bo3VmErrorBindings+8]
VmErrorPrelude ENDP
END
