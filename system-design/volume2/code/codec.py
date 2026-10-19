"""Base62. Same number always becomes the same short code."""

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def encode(number: int) -> str:
    if number < 0:
        raise ValueError("number must be >= 0")
    if number == 0:
        return ALPHABET[0]
    chars: list[str] = []
    while number:
        number, remainder = divmod(number, 62)
        chars.append(ALPHABET[remainder])
    return "".join(reversed(chars))


def decode(code: str) -> int:
    if not code:
        raise ValueError("empty code")
    number = 0
    for char in code:
        index = ALPHABET.find(char)
        if index < 0:
            raise ValueError(f"bad character: {char}")
        number = number * 62 + index
    return number
