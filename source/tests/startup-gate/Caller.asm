EXTERN __imp_GetStartupInfoW:QWORD
.code
PUBLIC OwnedCaller,OwnedReturn,OwnedCrtCaller,OwnedCrtReturn
OwnedCaller PROC FRAME
    sub rsp,98h
    .allocstack 98h
    .endprolog
    lea rcx,[rsp+20h]
    call QWORD PTR [__imp_GetStartupInfoW]
OwnedReturn LABEL BYTE
    test BYTE PTR [rsp+5ch],1
    movzx ecx,WORD PTR [rsp+60h]
    mov eax,10
    cmovne eax,ecx
    add rsp,98h
    ret
OwnedCaller ENDP
OwnedCrtCaller PROC FRAME
    sub rsp,28h
    .allocstack 28h
    .endprolog
    call OwnedCaller
OwnedCrtReturn LABEL BYTE
    add rsp,28h
    ret
OwnedCrtCaller ENDP
END
