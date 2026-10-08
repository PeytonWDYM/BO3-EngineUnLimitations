"""Read Valve KeyValues while retaining every original text span."""
from __future__ import annotations
from dataclasses import dataclass

from patcher.errors import PatchError


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int
    quoted: bool = False


@dataclass(frozen=True)
class Block:
    entries: tuple[tuple[Token, Token | Block], ...]
    close: Token

    def get(self, name: str) -> Token | Block | None:
        matches = [entry for entry in self.entries if entry[0].value.casefold() == name.casefold()]
        if len(matches) > 1:
            raise PatchError("Steam configuration contains duplicate scoped keys.")
        return matches[0][1] if matches else None


def quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"'


def tokens(text: str) -> list[Token]:
    result = []
    position = 1 if text.startswith('\ufeff') else 0
    escapes = {'n': '\n', 'r': '\r', 't': '\t', '\\': '\\', '"': '"'}
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        if text.startswith('//', position):
            end = text.find('\n', position)
            position = len(text) if end < 0 else end + 1
            continue
        start = position
        character = text[position]
        position += 1
        if character in '{}':
            result.append(Token(character, start, position))
        elif character == '"':
            decoded = []
            while position < len(text) and text[position] != '"':
                character = text[position]
                position += 1
                if character == '\\':
                    if position == len(text):
                        raise PatchError("Steam VDF has an unfinished quoted string.")
                    escaped = text[position]
                    position += 1
                    decoded.append(escapes.get(escaped, '\\' + escaped))
                else:
                    decoded.append(character)
            if position == len(text):
                raise PatchError("Steam VDF has an unfinished quoted string.")
            position += 1
            result.append(Token(''.join(decoded), start, position, True))
        else:
            while position < len(text) and not text[position].isspace() and text[position] not in '{}':
                position += 1
            result.append(Token(text[start:position], start, position))
    return result


def parse(text: str) -> Block:
    stream = tokens(text)
    position = 0
    def block(nested: bool) -> Block:
        nonlocal position
        entries = []
        while position < len(stream):
            key = stream[position]
            position += 1
            if key.value == '}' and not key.quoted:
                if not nested:
                    raise PatchError("Steam VDF contains an unexpected closing brace.")
                return Block(tuple(entries), key)
            if key.value == '{' and not key.quoted or position == len(stream):
                raise PatchError("Steam VDF has an invalid key/value pair.")
            value = stream[position]
            position += 1
            if value.value == '{' and not value.quoted:
                entries.append((key, block(True)))
            elif value.value == '}' and not value.quoted:
                raise PatchError("Steam VDF has a missing value.")
            else:
                entries.append((key, value))
        if nested:
            raise PatchError("Steam VDF has an unclosed block.")
        return Block(tuple(entries), Token('', len(text), len(text)))
    return block(False)


@dataclass(frozen=True)
class LaunchField:
    text: str
    app: Block
    entry: tuple[Token, Token] | None

    @property
    def value(self) -> str | None:
        return self.entry[1].value if self.entry else None

    def snapshot(self) -> dict:
        token = self.entry[1] if self.entry else None
        return {"present": token is not None, "value": token.value if token else None,
                "raw": self.text[token.start:token.end] if token else None}

    def insertion(self, raw: str) -> tuple[int, str]:
        close = self.app.close.start
        line = self.text.rfind('\n', 0, close) + 1
        indent = self.text[line:close]
        if indent.strip():
            return close, ' "LaunchOptions" ' + raw + ' '
        newline = '\r\n' if '\r\n' in self.text else '\n'
        return line, indent + '\t"LaunchOptions"\t\t' + raw + newline

    def with_raw(self, raw: str) -> bytes:
        if self.entry:
            token = self.entry[1]
            return (self.text[:token.start] + raw + self.text[token.end:]).encode('utf-8')
        position, inserted = self.insertion(raw)
        return (self.text[:position] + inserted + self.text[position:]).encode('utf-8')

    def with_value(self, value: str) -> bytes:
        return self.with_raw(quote(value))

    def without(self, inserted: str) -> bytes:
        key, value = self.entry
        start = key.start - inserted.index('"LaunchOptions"')
        if self.text[start:start + len(inserted)] == inserted:
            return (self.text[:start] + self.text[start + len(inserted):]).encode('utf-8')
        # Steam can reformat the owned field. Retain any later comment or other text.
        return (self.text[:key.start] + self.text[value.end:]).encode('utf-8')


def launch_field(data: bytes) -> LaunchField:
    text = data.decode('utf-8')
    current = parse(text)
    for name in ('UserLocalConfigStore', 'Software', 'Valve', 'Steam', 'apps', '311210'):
        child = current.get(name)
        if not isinstance(child, Block):
            raise PatchError("Steam configuration is missing the exact Black Ops III app block.")
        current = child
    value = current.get('LaunchOptions')
    if value is not None and (not isinstance(value, Token) or not value.quoted):
        raise PatchError("Black Ops III LaunchOptions must be a quoted string.")
    entry = next((entry for entry in current.entries if entry[0].value.casefold() == 'launchoptions'), None)
    return LaunchField(text, current, entry)
