option casemap:none
EXTERN Bo3VmStateBindings:BYTE
PUBLIC NativeOriginalReader, NativeOriginalWriter, NativeOriginalInsert, NativeOriginalError
PUBLIC NativeOriginalInsertBody
.code
; Exact-build entry prefixes. The native continuation owns its remaining prologue.
NativeOriginalReader PROC FRAME
    .endprolog
    mov [rsp+10h],rbx
    mov rax,QWORD PTR [Bo3VmStateBindings]
    add rax,12d52f5h
    jmp rax
NativeOriginalReader ENDP
NativeOriginalWriter PROC FRAME
    .endprolog
    mov [rsp+8h],rbx
    mov rax,QWORD PTR [Bo3VmStateBindings]
    add rax,12d5f25h
    jmp rax
NativeOriginalWriter ENDP
NativeOriginalInsert PROC FRAME
    db 40h,53h
    .pushreg rbx
    .endprolog
    db 49h,8bh,0d8h
NativeOriginalInsertBody LABEL BYTE
    mov rax,QWORD PTR [Bo3VmStateBindings]
    add rax,12d9425h
    jmp rax
NativeOriginalInsert ENDP
NativeOriginalError PROC FRAME
    .endprolog
    mov [rsp+20h],r9
    mov rax,QWORD PTR [Bo3VmStateBindings]
    add rax,20ec0b5h
    jmp rax
NativeOriginalError ENDP
END
