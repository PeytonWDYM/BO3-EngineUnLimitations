// Define captured, null-terminated ASCII strings from a private analysis manifest.
// @category BO3Research

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class DefineStrings extends GhidraScript {
    @Override
    public void run() throws Exception {
        for (JsonElement element : JsonParser.parseString(Files.readString(Path.of(getScriptArgs()[0]))).getAsJsonArray()) {
            monitor.checkCancelled();
            JsonObject item = element.getAsJsonObject();
            Address address = toAddr(item.get("address").getAsString());
            byte[] text = item.get("text").getAsString().getBytes(StandardCharsets.US_ASCII);
            byte[] actual = getBytes(address, text.length + 1);
            if (actual[text.length] != 0 || !Arrays.equals(text, Arrays.copyOf(actual, text.length))) {
                throw new IllegalArgumentException("Captured string mismatch at " + address);
            }
            clearListing(address, address.add(text.length));
            createAsciiString(address, text.length + 1);
        }
    }
}
