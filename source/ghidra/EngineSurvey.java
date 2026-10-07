// Export an analysis survey and selected function decompilation to a private directory.
// @category BO3Research

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;

public class EngineSurvey extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException("Use: EngineSurvey.java outputDirectory stringRegex [functionAddress ...]");
        }
        Path output = Path.of(args[0]).toAbsolutePath().normalize();
        Path repository = Path.of(getSourceFile().getAbsolutePath()).toRealPath().getParent().getParent().getParent();
        Path existingParent = output;
        while (!Files.exists(existingParent)) {
            existingParent = existingParent.getParent();
        }
        Path resolved = existingParent.toRealPath().resolve(existingParent.relativize(output)).normalize();
        if (resolved.startsWith(repository)) {
            throw new IllegalArgumentException("Write game-derived surveys outside the repository.");
        }
        if (Files.exists(output)) {
            throw new IllegalArgumentException("Choose a new survey output directory.");
        }
        Files.createDirectories(output);
        Pattern pattern = Pattern.compile(args[1], Pattern.CASE_INSENSITIVE);
        JsonObject report = new JsonObject();
        report.addProperty("program", currentProgram.getName());
        report.addProperty("executablePath", currentProgram.getExecutablePath());
        report.addProperty("format", currentProgram.getExecutableFormat());
        report.addProperty("language", currentProgram.getLanguageID().toString());
        report.addProperty("imageBase", currentProgram.getImageBase().toString());
        report.addProperty("functionCount", currentProgram.getFunctionManager().getFunctionCount());

        JsonArray blocks = new JsonArray();
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            JsonObject item = new JsonObject();
            item.addProperty("name", block.getName());
            item.addProperty("start", block.getStart().toString());
            item.addProperty("size", block.getSize());
            item.addProperty("initialized", block.isInitialized());
            item.addProperty("execute", block.isExecute());
            blocks.add(item);
        }
        report.add("blocks", blocks);

        JsonArray strings = new JsonArray();
        DataIterator data = currentProgram.getListing().getDefinedData(true);
        while (data.hasNext()) {
            monitor.checkCancelled();
            Data item = data.next();
            Object value = item.getValue();
            if (!(value instanceof String) || !pattern.matcher((String) value).find()) {
                continue;
            }
            JsonObject match = new JsonObject();
            match.addProperty("address", item.getAddress().toString());
            match.addProperty("value", (String) value);
            JsonArray refs = new JsonArray();
            for (Reference ref : getReferencesTo(item.getAddress())) {
                JsonObject source = new JsonObject();
                source.addProperty("address", ref.getFromAddress().toString());
                Function owner = getFunctionContaining(ref.getFromAddress());
                if (owner != null) {
                    source.addProperty("function", owner.getEntryPoint().toString());
                    source.addProperty("name", owner.getName());
                }
                refs.add(source);
            }
            match.add("references", refs);
            strings.add(match);
        }
        report.add("strings", strings);

        JsonArray functions = new JsonArray();
        DecompInterface decompiler = new DecompInterface();
        try {
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException(decompiler.getLastMessage());
            }
            for (int index = 2; index < args.length; index++) {
                monitor.checkCancelled();
                Address address = toAddr(args[index]);
                Function function = getFunctionAt(address);
                JsonObject item = new JsonObject();
                item.addProperty("requestedAddress", address.toString());
                if (function == null) {
                    item.addProperty("status", "No defined function at this address");
                } else {
                    item.addProperty("name", function.getName());
                    item.addProperty("entry", function.getEntryPoint().toString());
                    DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                    item.addProperty("complete", result.decompileCompleted());
                    item.addProperty("error", result.getErrorMessage());
                    if (result.decompileCompleted()) {
                        Path file = output.resolve("function-" + address + ".c");
                        Files.writeString(file, result.getDecompiledFunction().getC(), StandardCharsets.UTF_8);
                        item.addProperty("file", file.getFileName().toString());
                    }
                }
                functions.add(item);
            }
        } finally {
            decompiler.dispose();
        }
        report.add("functions", functions);
        Files.writeString(output.resolve("survey.json"),
            new GsonBuilder().setPrettyPrinting().create().toJson(report), StandardCharsets.UTF_8);
        println("Survey written: " + output);
    }
}
