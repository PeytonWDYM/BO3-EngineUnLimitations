// Replace disk bytes with captured module ranges. Missing pages stay unmapped.
// @category BO3Research

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class LoadDumpRanges extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("Use: LoadDumpRanges.java module.json");
        }
        Path manifestPath = Path.of(args[0]).toAbsolutePath().normalize();
        JsonObject manifest = JsonParser.parseString(Files.readString(manifestPath)).getAsJsonObject();
        JsonArray ranges = manifest.getAsJsonArray("ranges");
        if (ranges.size() == 0) {
            throw new IllegalArgumentException("The dump has no captured module ranges.");
        }
        for (JsonElement element : ranges) {
            JsonObject range = element.getAsJsonObject();
            Path file = manifestPath.getParent().resolve(range.get("file").getAsString()).normalize();
            if (!file.getParent().equals(manifestPath.getParent()) || Files.size(file) != range.get("size").getAsLong()) {
                throw new IllegalArgumentException("Invalid captured range file: " + file);
            }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[1024 * 1024];
                int length;
                while ((length = input.read(buffer)) != -1) {
                    digest.update(buffer, 0, length);
                }
            }
            if (!HexFormat.of().formatHex(digest.digest()).equals(range.get("sha256").getAsString())) {
                throw new IllegalArgumentException("Captured range hash mismatch: " + file);
            }
        }
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            memory.removeBlock(block, monitor);
        }
        Address base = toAddr(manifest.get("baseAddress").getAsString());
        currentProgram.setImageBase(base, true);
        int index = 0;
        for (JsonElement element : ranges) {
            monitor.checkCancelled();
            JsonObject range = element.getAsJsonObject();
            Address start = toAddr(range.get("address").getAsString());
            long size = range.get("size").getAsLong();
            Path file = manifestPath.getParent().resolve(range.get("file").getAsString());
            try (InputStream input = Files.newInputStream(file)) {
                MemoryBlock block = memory.createInitializedBlock("capture_" + index++, start, input, size, monitor, false);
                block.setRead(true);
                boolean executable = false;
                for (JsonElement sectionElement : manifest.getAsJsonArray("sections")) {
                    JsonObject section = sectionElement.getAsJsonObject();
                    Address sectionStart = toAddr(section.get("address").getAsString());
                    Address sectionEnd = sectionStart.add(section.get("size").getAsLong() - 1);
                    if (section.get("executable").getAsBoolean()
                            && start.compareTo(sectionEnd) <= 0
                            && block.getEnd().compareTo(sectionStart) >= 0) {
                        executable = true;
                    }
                }
                block.setExecute(executable);
            }
        }
        println("Loaded " + ranges.size() + " captured ranges at " + base + ". Missing pages remain unmapped.");
    }
}
