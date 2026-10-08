option casemap:none
EXTERN ClearOwnedImport:PROC
PUBLIC ClearNativeImportContext
.code
; Deliberately clobber every fixed-argument register after the real owned TLS clear.
ClearNativeImportContext PROC FRAME
    sub rsp,28h
    .allocstack 28h
    .endprolog
    call ClearOwnedImport
    add rsp,28h
    mov rcx,1111111111111111h
    mov rdx,2222222222222222h
    mov r8,3333333333333333h
    mov r9,4444444444444444h
    ret
ClearNativeImportContext ENDP
END
