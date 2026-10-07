// Define explicitly selected candidate entries for a bounded decompiler pass.
// @category BO3Research

import ghidra.app.script.GhidraScript;
import ghidra.app.plugin.core.analysis.ConstantPropagationAnalyzer;
import ghidra.app.util.importer.MessageLog;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DefineFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        ConstantPropagationAnalyzer references = new ConstantPropagationAnalyzer(
            currentProgram.getLanguage().getProcessor().toString());
        if (!references.canAnalyze(currentProgram)) {
            throw new IllegalArgumentException("Constant propagation does not support this program.");
        }
        for (String argument : getScriptArgs()) {
            monitor.checkCancelled();
            Address entry = toAddr(argument);
            if (!currentProgram.getMemory().contains(entry)) {
                throw new IllegalArgumentException("The capture does not contain " + entry);
            }
            if (!disassemble(entry)) {
                throw new IllegalArgumentException("Could not disassemble " + entry);
            }
            Function function = getFunctionAt(entry);
            if (function == null) {
                function = createFunction(entry, "candidate_" + entry);
            }
            if (function == null) {
                throw new IllegalArgumentException("Could not define a function at " + entry);
            }
            references.added(currentProgram, function.getBody(), monitor, new MessageLog());
            println("Candidate function: " + function.getEntryPoint());
        }
    }
}
