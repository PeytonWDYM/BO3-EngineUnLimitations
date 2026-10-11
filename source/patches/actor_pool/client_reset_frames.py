"""Emit only the two admitted client reset templates and their static PE frames."""
import struct

from client_snapshot_reset import ClientResetFrame


def emit_client_reset_frames(frames: tuple[ClientResetFrame,...]) -> str:
    """Build owned loader evidence. Native startup bindings and live activation remain separate."""
    if len(frames)!=2:
        raise ValueError('Both complete client reset templates are required.')
    names=('Bo3ClientStartupResetTemplate','Bo3ClientShutdownResetTemplate')
    bindings=[]
    for index,frame in enumerate(frames):
        rewrite=frame.rewrite
        prefix=bytes.fromhex('458bce' if index==0 else '448b4c2408')
        body=rewrite.stub[len(prefix):]
        instructions=((0,'4883ec38'),(4,'48894c2420'),(9,'4c894c2428'),(14,'e8'),
                      (19,'488b4c2428'),(24,'4869c9'),(31,'48b8'),(41,'4801c1'),
                      (44,'33d2'),(46,'41b8'),(52,'e8'),(57,'488b442420'),(62,'4883c438c3'))
        prolog=len(prefix)+4
        expected_name='client_snapshot_startup_reset' if index==0 else 'client_snapshot_shutdown_reset'
        expected_site=0x8F0AB4 if index==0 else 0x92EC08
        if (rewrite.name!=expected_name or rewrite.guard.rva!=expected_site
                or rewrite.stub_address is None or rewrite.stub_address<=0 or rewrite.stub_address&15
                or rewrite.stub[:len(prefix)]!=prefix or len(body)!=67
                or frame.unwind!=bytes((1,prolog,1,0,prolog,0x62,0,0))
                or any(body[offset:offset+len(bytes.fromhex(raw))]!=bytes.fromhex(raw) for offset,raw in instructions)):
            raise ValueError('A client reset template or static frame differs.')
        count=struct.unpack_from('<I',body,27)[0]
        base=struct.unpack_from('<Q',body,33)[0]
        endpoint=rewrite.stub_address+len(prefix)+19+struct.unpack_from('<i',body,15)[0]
        endpoint2=rewrite.stub_address+len(prefix)+57+struct.unpack_from('<i',body,53)[0]
        native_base=endpoint-0x2BC53B0
        if (count not in (1205184,1237184) or struct.unpack_from('<I',body,48)[0]!=count
                or base<=0 or base&4095 or base+2*count>0x800000000000 or endpoint!=endpoint2
                or native_base<=0 or len(rewrite.replacement)!=5
                or rewrite.replacement[0]!=(0xE8 if index==0 else 0xE9)
                or native_base+expected_site+5+struct.unpack_from('<i',rewrite.replacement,1)[0]!=rewrite.stub_address):
            raise ValueError('The client reset template has an unsupported extent or call binding.')
        bindings.append((count,base,endpoint))
    if bindings[0]!=bindings[1]:
        raise ValueError('Both client reset frames must bind the same complete snapshot pool.')

    def row(raw: bytes) -> str:
        return '\n'.join('DB '+','.join(f'0{value:02X}h' for value in raw[start:start+16])
                         for start in range(0,len(raw),16))
    lines=['option casemap:none','option dotname']
    exports=(*names,'Bo3OwnedMemsetRelay','Bo3OwnedClearTarget','Bo3OwnedNonvolatile',
             'Bo3OwnedInvoke','Bo3StartupClientClear','Bo3ShutdownClientClear')
    lines.extend('PUBLIC '+name for name in exports)
    lines.extend(('.data','ALIGN 8','Bo3OwnedClearTarget DQ 0','Bo3OwnedNonvolatile DQ 8 DUP(0)', '.code'))
    for name,frame in zip(names,frames):
        lines.extend(('ALIGN 16',name+' LABEL BYTE',row(frame.rewrite.stub),name+'End LABEL BYTE'))
    lines.extend(('ALIGN 16','Bo3OwnedMemsetRelay LABEL BYTE','jmp QWORD PTR [Bo3OwnedClearTarget]',
                  'Bo3StartupClientClear PROC FRAME','push r14','.pushreg r14','sub rsp,20h','.allocstack 20h',
                  '.endprolog','mov r14d,r9d','call NEAR PTR Bo3ClientStartupResetTemplate','add rsp,20h','pop r14','ret',
                  'Bo3StartupClientClear ENDP','Bo3ShutdownClientClear LABEL BYTE',
                  'mov DWORD PTR [rsp+8],r9d','jmp NEAR PTR Bo3ClientShutdownResetTemplate',
                  'Bo3OwnedInvoke PROC FRAME'))
    registers=('rbx','rbp','rsi','rdi','r12','r13','r14','r15')
    for register in registers:lines.extend(('push '+register,'.pushreg '+register))
    lines.extend(('sub rsp,28h','.allocstack 28h','.endprolog'))
    values=(0x11001100,0x44004400,0x22002200,0x33003300,0x55005500,0x66006600,0x77007700,0x88008800)
    lines.extend(f'mov {register},0{value:X}h' for register,value in zip(registers,values))
    # The fifth argument was at entry RSP+40, before 64 bytes of saves and 40 bytes of allocation.
    lines.extend(('mov rax,QWORD PTR [rsp+90h]','call rax'))
    lines.extend(f'mov QWORD PTR [Bo3OwnedNonvolatile+{index*8}],{register}' for index,register in enumerate(registers))
    lines.append('add rsp,28h')
    lines.extend('pop '+register for register in reversed(registers))
    lines.extend(('ret','Bo3OwnedInvoke ENDP','.xdata SEGMENT READONLY'))
    for name,frame in zip(names,frames):lines.extend(('ALIGN 4',name+'Unwind LABEL BYTE',row(frame.unwind)))
    lines.extend(('.xdata ENDS','.pdata SEGMENT READONLY','ALIGN 4'))
    lines.extend(f'DD IMAGEREL {name},IMAGEREL {name}End,IMAGEREL {name}Unwind' for name in names)
    lines.extend(('.pdata ENDS','END',''))
    return '\n'.join(lines)
