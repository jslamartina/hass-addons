class _Color:
    BLACK: str
    RED: str
    GREEN: str
    YELLOW: str
    BLUE: str
    MAGENTA: str
    CYAN: str
    WHITE: str
    RESET: str
    RESET_ALL: str

Fore: _Color
Back: _Color
Style: _Color

def init(autoreset: bool | None = ...) -> None: ...
