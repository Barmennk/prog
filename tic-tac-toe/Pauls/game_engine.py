import copy
import time


BOARD_SIZE = 15
WIN_LEN = 5
MOVE_TIMEOUT = 1.0
EMPTY = "_"


def create_board() -> list[list[str]]:
    return [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]


def check_winner(board: list[list[str]], row: int, col: int, player: str) -> bool:
    for row_step, col_step in ((0, 1), (1, 0), (1, 1), (1, -1)):
        count = 1
        for direction in (1, -1):
            current_row = row + row_step * direction
            current_col = col + col_step * direction
            while (
                0 <= current_row < BOARD_SIZE
                and 0 <= current_col < BOARD_SIZE
                and board[current_row][current_col] == player
            ):
                count += 1
                current_row += row_step * direction
                current_col += col_step * direction
        if count >= WIN_LEN:
            return True
    return False


class Match:
    """Game state and Swap2 rules for a human-versus-bot match."""

    def __init__(self, bot: dict, human_first: bool = True):
        self.board = create_board()
        self.players = {
            "P1": {"name": "Tu", "bot": None},
            "P2": {"name": bot["name"], "bot": bot},
        }
        if not human_first:
            self.players["P1"], self.players["P2"] = self.players["P2"], self.players["P1"]

        self.phase = "opening"
        self.opening_symbols = ("X", "X", "O")
        self.opening_index = 0
        self.extra_symbols = ("X", "O")
        self.extra_index = 0
        self.colors: dict[str, str] = {}
        self.current_symbol = None
        self.winner = None
        self.result = None

    @property
    def current_actor(self) -> str:
        if self.phase == "opening":
            player_id = "P1"
        elif self.phase in ("response", "place_two"):
            player_id = "P2"
        elif self.phase == "final_choice":
            player_id = "P1"
        elif self.phase == "play":
            player_id = self.colors[self.current_symbol]
        else:
            return "none"
        return "bot" if self.players[player_id]["bot"] is not None else "human"

    @property
    def expected_symbol(self) -> str | None:
        if self.phase == "opening":
            return self.opening_symbols[self.opening_index]
        if self.phase == "place_two":
            return self.extra_symbols[self.extra_index]
        if self.phase == "play":
            return self.current_symbol
        return None

    def human_place(self, row: int, col: int) -> None:
        self._require_human_phase(("opening", "place_two", "play"))
        symbol = self.expected_symbol
        self._place(row, col, symbol)
        if self.phase == "opening":
            self.opening_index += 1
            if self.opening_index == len(self.opening_symbols):
                self.phase = "response"
        elif self.phase == "place_two":
            self.extra_index += 1
            if self.extra_index == len(self.extra_symbols):
                self.phase = "final_choice"
        else:
            self._finish_turn(row, col, symbol)

    def human_respond(self, action: str) -> None:
        self._require_human_phase(("response",))
        self._apply_response({"action": action})

    def human_choose_color(self, symbol: str) -> None:
        self._require_human_phase(("final_choice",))
        self._apply_final_choice(symbol)

    def perform_bot_action(self) -> None:
        if self.current_actor != "bot":
            raise ValueError("Pašlaik nav bota gājiens.")

        player_id = self._acting_player_id()
        bot = self.players[player_id]["bot"]
        safe_board = copy.deepcopy(self.board)
        started = time.monotonic()

        if self.phase == "opening":
            result = bot["swap2_propose"](safe_board)
        elif self.phase == "response":
            result = bot["swap2_respond"](safe_board)
        elif self.phase == "final_choice":
            result = bot["swap2_final_choice"](safe_board)
        else:
            result = bot["get_move"](safe_board, self.current_symbol)

        if time.monotonic() - started > MOVE_TIMEOUT:
            raise TimeoutError(f"{bot['name']} pārsniedza {MOVE_TIMEOUT:.1f} sekundes gājiena limitu.")

        if self.phase == "opening":
            moves = self._validate_moves(result, ("X", "X", "O"))
            for row, col, symbol in moves:
                self.board[row][col] = symbol
            self.phase = "response"
        elif self.phase == "response":
            if not isinstance(result, dict) or result.get("action") not in ("TAKE_X", "TAKE_O", "PLACE_TWO"):
                raise ValueError(f"{bot['name']} atgrieza nederīgu Swap2 atbildi.")
            if result["action"] == "PLACE_TWO":
                moves = self._validate_moves(result.get("moves"), ("X", "O"))
                for row, col, symbol in moves:
                    self.board[row][col] = symbol
                self.phase = "final_choice"
            else:
                self._set_colors(result["action"])
        elif self.phase == "final_choice":
            self._apply_final_choice(result)
        else:
            row, col = self._validate_move(result)
            self.board[row][col] = self.current_symbol
            self._finish_turn(row, col, self.current_symbol)

    def _acting_player_id(self) -> str:
        if self.phase in ("opening", "final_choice"):
            return "P1"
        if self.phase in ("response", "place_two"):
            return "P2"
        return self.colors[self.current_symbol]

    def _require_human_phase(self, phases: tuple[str, ...]) -> None:
        if self.phase not in phases or self.current_actor != "human":
            raise ValueError("Šo darbību pašlaik nevar veikt.")

    def _place(self, row: int, col: int, symbol: str) -> None:
        if type(row) is not int or type(col) is not int or not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            raise ValueError("Izvēlies rūtiņu uz laukuma.")
        if self.board[row][col] != EMPTY:
            raise ValueError("Šī rūtiņa jau ir aizņemta.")
        self.board[row][col] = symbol

    def _validate_move(self, move) -> tuple[int, int]:
        if not isinstance(move, (list, tuple)) or len(move) != 2:
            raise ValueError("Bots atgrieza nederīgu gājiena formātu.")
        row, col = move
        if type(row) is not int or type(col) is not int or not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            raise ValueError("Bots izvēlējās koordinātas ārpus laukuma.")
        if self.board[row][col] != EMPTY:
            raise ValueError("Bots izvēlējās aizņemtu rūtiņu.")
        return row, col

    def _validate_moves(self, moves, expected_symbols: tuple[str, ...]) -> list[tuple[int, int, str]]:
        if not isinstance(moves, (list, tuple)) or len(moves) != len(expected_symbols):
            raise ValueError("Bots atgrieza nederīgu Swap2 gājienu skaitu.")
        validated = []
        seen = set()
        symbols = []
        for move in moves:
            if not isinstance(move, (list, tuple)) or len(move) != 3:
                raise ValueError("Bots atgrieza nederīgu Swap2 gājiena formātu.")
            row, col, symbol = move
            if type(row) is not int or type(col) is not int or not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
                raise ValueError("Bots izvēlējās Swap2 koordinātas ārpus laukuma.")
            if symbol not in ("X", "O") or self.board[row][col] != EMPTY or (row, col) in seen:
                raise ValueError("Bots izvēlējās nederīgu Swap2 rūtiņu vai simbolu.")
            seen.add((row, col))
            symbols.append(symbol)
            validated.append((row, col, symbol))
        if sorted(symbols) != sorted(expected_symbols):
            raise ValueError("Bots Swap2 gājienos neizvietoja vajadzīgos simbolus.")
        return validated

    def _apply_response(self, response: dict) -> None:
        action = response["action"]
        if action in ("TAKE_X", "TAKE_O"):
            self._set_colors(action)
        elif action == "PLACE_TWO":
            self.phase = "place_two"
        else:
            raise ValueError("Izvēlies TAKE_X, TAKE_O vai PLACE_TWO.")

    def _set_colors(self, action: str) -> None:
        self.colors = (
            {"X": "P1", "O": "P2"}
            if action == "TAKE_O"
            else {"X": "P2", "O": "P1"}
        )
        self._start_play()

    def _apply_final_choice(self, symbol: str) -> None:
        if symbol not in ("X", "O"):
            raise ValueError("Krāsas izvēlei jābūt X vai O.")
        other_symbol = "O" if symbol == "X" else "X"
        self.colors = {symbol: "P1", other_symbol: "P2"}
        self._start_play()

    def _start_play(self) -> None:
        self.current_symbol = "O"
        self.phase = "play"

    def _finish_turn(self, row: int, col: int, symbol: str) -> None:
        if check_winner(self.board, row, col, symbol):
            self.winner = self.colors[symbol]
            self.result = "win"
            self.phase = "finished"
        elif all(cell != EMPTY for board_row in self.board for cell in board_row):
            self.result = "draw"
            self.phase = "finished"
        else:
            self.current_symbol = "X" if symbol == "O" else "O"
