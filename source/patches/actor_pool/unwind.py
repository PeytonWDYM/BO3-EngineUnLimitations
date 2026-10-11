"""Record exact native frame owners and emitted stack changes for unwind admission."""

import hashlib
import json
from pathlib import Path
import struct

from captured_code import CapturedCode, Rewrite
from leaf_frames import verify_leaves
from leaf_unwind import prepare_leaf_phases
from native_unwind import read_frame, active_operations
from continuation_unwind import prepare_continuation_phases
from native_handlers import prepare_native_handler


def native_frames(code: CapturedCode) -> tuple[tuple[int,int,int], ...]:
    pe = struct.unpack('<I',code.read(0x3C,4))[0]
    optional = pe+24
    if struct.unpack('<H',code.read(optional,2))[0] != 0x20B:
        raise ValueError('The native unwind inventory requires a PE32+ image.')
    rva,size = struct.unpack('<II',code.read(optional+112+3*8,8))
    return tuple(struct.iter_unpack('<III',code.read(rva,size)))


def requirements(code: CapturedCode, edits: tuple[Rewrite, ...]) -> list[dict]:
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    frames = native_frames(code)
    leaves = verify_leaves(code,frames,json.loads((Path(__file__).parent/'leaf_frames.json').read_text())['functions'])
    records = []
    for edit in edits:
        if not edit.stub:
            continue
        owner = next((frame for frame in frames if frame[0]<=edit.guard.rva<frame[1]),None)
        transitions = []
        depth = 0
        for instruction in decoder.disasm(edit.stub,edit.stub_address):
            mnemonic,operand = instruction.mnemonic,instruction.op_str
            delta = 8 if mnemonic in ('push','pushfq') else -8 if mnemonic in ('pop','popfq') else 0
            if mnemonic in ('sub','add') and operand.startswith('rsp, '):
                delta = int(operand.split(', ')[1],0)*(1 if mnemonic=='sub' else -1)
            if mnemonic=='lea' and operand=='rsp, [rsp + 8]':
                delta = -8
            if delta:
                depth += delta
                transitions.append({'offset':instruction.address-edit.stub_address,'endOffset':instruction.address-edit.stub_address+instruction.size,
                                    'operation':mnemonic+' '+operand,'stackBytes':depth})
        record = {'siteRva':hex(edit.guard.rva),'stubAddress':hex(edit.stub_address),
                  'stubSha256':hashlib.sha256(edit.stub).hexdigest(),'stackTransitions':transitions,
                  'registrationVerified':False,'windowsVirtualUnwindVerified':False}
        if edit.name=='external_table_accessor':
            if owner is not None or edit.stub[:4] != bytes.fromhex('4883ec10') or depth != 0:
                raise ValueError('The accessor does not match the admitted leaf stack contract.')
            # Version1, four-byte prolog, ALLOC_SMALL16, padded to a DWORD.
            record.update(kind='leaf_allocation',proposedUnwindInfo='0104010004120000',
                          requirement='Register ALLOC_SMALL16. Verify the prolog, body and epilog with RtlVirtualUnwind.')
        elif owner is not None:
            header = code.read(owner[2],4)
            count = header[2]
            extent = 4+((count+1)//2)*4
            flags = header[0] >> 3
            extent += 12 if flags & 4 else 4 if flags & 3 else 0
            native = code.read(owner[2],extent)
            record.update(kind='native_frame_continuation',nativeRuntimeFunction={
                'beginRva':hex(owner[0]),'endRva':hex(owner[1]),'unwindRva':hex(owner[2]),
                'unwindBytes':extent,'unwindSha256':hashlib.sha256(native).hexdigest()},
                requirement='Describe every stack phase and the complete original native frame. Added fixed allocations cannot use grouped CHAININFO alone.')
            frame = read_frame(code, owner)
            if frame.has_handler:
                handler = prepare_native_handler(code, frame)
                record['preparedNativeHandler'] = {
                    'kind': 'gs_only', 'imageBase': hex(handler.image_base), 'rootRuntime': [hex(value) for value in handler.runtime],
                    'handlerAddress': hex(handler.handler_address), 'handlerDataAddress': hex(handler.handler_data_address),
                    'prologBytes': handler.prolog_bytes, 'cookieOffset': handler.cookie_offset,
                    'runtimeBindingVerified': False}
            phases = prepare_continuation_phases(edit, active_operations(frame, edit.guard.rva))
            lineage = []
            current = frame
            while current is not None:
                lineage.append(current.runtime)
                current = current.parent
            record['ownedLogicalProcedure'] = {'beginRva': hex(min(item[0] for item in lineage)),
                                               'endRva': hex(max(item[1] for item in lineage))}
            record['ownedContinuationPhases'] = [
                {'beginOffset': phase.begin, 'endOffset': phase.end, 'stackBytes': phase.stack_bytes,
                 'primaryUnwindInfo': phase.unwind_info.hex(),
                 'temporarySaves': [{'register': register, 'stackOffset': offset} for register, offset in phase.saved_registers],
                 'unscaledXmmOffsetNotRuntimeAdmitted': phase.unscaled_xmm_phase}
                for phase in phases
            ]
            record['ownedRecipe'] = 'A zero-code phase chains to its complete flattened frame using the logical native procedure bounds. Only owned fixture branches are rebased.'
            record['nativeHandlerDispatchVerified'] = False
            record['runtimeAbiAdmitted'] = False
        else:
            leaf = next((leaf for leaf in leaves if int(leaf['beginRva'],0)<=edit.guard.rva<int(leaf['endRva'],0)),None)
            if leaf is None:
                record.update(kind='unresolved_frame_owner',requirement='Determine the leaf or native continuation frame before registration.')
            else:
                record.update(kind='verified_native_leaf',nativeLeaf=leaf,
                              requirement='Describe each emitted stack phase and preserve the original leaf return. Dynamic runtime tables remain a startup admission check.')
        if record['kind'] in ('leaf_allocation', 'verified_native_leaf'):
            record['ownedPhaseRecords'] = [
                {'beginOffset': phase.begin, 'endOffset': phase.end, 'stackBytes': phase.stack_bytes,
                 'unwindInfo': phase.unwind_info.hex()}
                for phase in prepare_leaf_phases(edit)
            ]
        records.append(record)
    return records
