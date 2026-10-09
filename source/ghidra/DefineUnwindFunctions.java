// Define only the function ranges verified against captured x64 unwind metadata.
// @category BO3Research

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.plugin.core.analysis.ConstantPropagationAnalyzer;
import ghidra.app.script.GhidraScript;
import ghidra.app.util.importer.MessageLog;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.Files;
import java.nio.file.Path;

public class DefineUnwindFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        JsonObject manifest = JsonParser.parseString(Files.readString(Path.of(getScriptArgs()[0]))).getAsJsonObject();
        if (!manifest.get("sha256").getAsString().equalsIgnoreCase(currentProgram.getExecutableSHA256())) {
            throw new IllegalArgumentException("The function manifest has a different executable SHA256.");
        }
        if (!toAddr(manifest.get("moduleBase").getAsString()).equals(currentProgram.getImageBase())) {
            throw new IllegalArgumentException("The function manifest has a different module base.");
        }
        ConstantPropagationAnalyzer references = new ConstantPropagationAnalyzer(currentProgram.getLanguage().getProcessor().toString());
        if (!references.canAnalyze(currentProgram)) {
            throw new IllegalArgumentException("Constant propagation does not support this program.");
        }
        for (JsonElement element : manifest.getAsJsonArray("functions")) {
            monitor.checkCancelled();
            JsonObject item = element.getAsJsonObject();
            Address entry = toAddr(item.get("entry").getAsString());
            AddressSet body = new AddressSet();
            for (JsonElement rangeElement : item.getAsJsonArray("ranges")) {
                JsonObject range = rangeElement.getAsJsonObject();
                body.add(toAddr(range.get("start").getAsString()), toAddr(range.get("end").getAsString()));
            }
            if (!body.contains(entry) || !currentProgram.getMemory().contains(body)) {
                throw new IllegalArgumentException("A function body contains missing memory.");
            }
            DisassembleCommand command = new DisassembleCommand(entry, body, true);
            if (!command.applyTo(currentProgram, monitor)) {
                throw new IllegalArgumentException("Could not disassemble " + entry);
            }
            Function function = getFunctionAt(entry);
            if (function == null) {
                function = currentProgram.getFunctionManager().createFunction("candidate_" + entry, entry, body, SourceType.ANALYSIS);
            } else {
                function.setBody(body);
            }
            references.added(currentProgram, body, monitor, new MessageLog());
            println("Captured function boundary: " + entry + " (" + body.getNumAddresses() + " bytes)");
        }
    }
}
