import copy
import glob
import importlib.util
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

# === KONFIGURĀCIJA ===
BOARD_SIZE = 15
WIN_LEN = 5
MOVE_TIMEOUT = 1.0  # Sekundes vienam gājienam / Swap2 lēmumam
BOTS_PATTERN = "tic-tac-toe/*/bot.py"
STUDENT_BOTS_PATTERN = "studenti/*/bot.py"


def create_board() -> list[list[str]]:
    return [["_" for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]


def is_valid_coord(r: int, c: int) -> bool:
    return isinstance(r, int) and isinstance(c, int) and 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


def check_winner(board: list[list[str]], last_r: int, last_c: int, player: str) -> bool:
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for dr, dc in directions:
        count = 1
        r, c = last_r + dr, last_c + dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
            count += 1
            r += dr
            c += dc

        r, c = last_r - dr, last_c - dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
            count += 1
            r -= dr
            c -= dc

        if count >= WIN_LEN:
            return True
    return False


def load_bots(pattern: str) -> list[dict]:
    """Noskenē tic-tac-toe/<studenta_vards>/bot.py un ielādē derīgos botus."""
    bots = []
    required_funcs = ["get_move", "swap2_propose", "swap2_respond", "swap2_final_choice"]

    for file_str in sorted(glob.glob(pattern)):
        path = Path(file_str)
        student_folder = path.parent.name
        try:
            spec = importlib.util.spec_from_file_location(f"bot_{student_folder}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            missing = [f for f in required_funcs if not hasattr(module, f)]
            if missing:
                print(f"[IZLAISTS] {file_str} — trūkst funkciju: {', '.join(missing)}")
                continue

            bots.append({
                "id": student_folder,
                "name": getattr(module, "BOT_NAME", student_folder),
                "get_move": module.get_move,
                "swap2_propose": module.swap2_propose,
                "swap2_respond": module.swap2_respond,
                "swap2_final_choice": module.swap2_final_choice,
            })
        except Exception as e:
            print(f"[IELĀDES KĻŪDA] {file_str}: {e}")

    return bots


def run_with_timeout(func, *args):
    """Izsauc bota funkciju ar dziļajām argumentu kopijām un laika limitu."""
    safe_args = [copy.deepcopy(a) for a in args]
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *safe_args)
        return future.result(timeout=MOVE_TIMEOUT)


def validate_moves_list(board: list[list[str]], moves, expected_symbols: list[str]) -> bool:
    """Pārbauda Swap2 gājienu sarakstu (garums, simboli, koordinātu brīvība un unikalitāte)."""
    if not isinstance(moves, (list, tuple)) or len(moves) != len(expected_symbols):
        return False

    seen_coords = set()
    symbols = []
    for item in moves:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return False
        r, c, sym = item
        if not is_valid_coord(r, c) or board[r][c] != "_" or (r, c) in seen_coords:
            return False
        seen_coords.add((r, c))
        symbols.append(sym)

    return sorted(symbols) == sorted(expected_symbols)


def play_match(p1: dict, p2: dict) -> tuple[str, str]:
    """
    Izspēlē vienu pilnu partiju (Swap2 atklātne + pamatspēle).
    p1 = 1. spēlētājs (izliek pirmās 3 figūras), p2 = 2. spēlētājs.
    Atgriež: (uzvarētāja_id vai 'DRAW', apraksts)
    """
    board = create_board()

    # === 1. SOLIS: Swap2 — 1. spēlētājs uzliek 2x 'X' un 1x 'O' ===
    try:
        opening_moves = run_with_timeout(p1["swap2_propose"], board)
    except TimeoutError:
        return p2["id"], f"{p1['name']} pārsniedza laiku (swap2_propose)"
    except Exception as e:
        return p2["id"], f"{p1['name']} kļūda swap2_propose: {e}"

    if not validate_moves_list(board, opening_moves, ["X", "X", "O"]):
        return p2["id"], f"{p1['name']} nelegāls sākuma izvietojums: {opening_moves}"

    for r, c, sym in opening_moves:
        board[r][c] = sym

    # === 2. SOLIS: Swap2 — 2. spēlētājs izvēlas darbību ===
    try:
        response = run_with_timeout(p2["swap2_respond"], board)
    except TimeoutError:
        return p1["id"], f"{p2['name']} pārsniedza laiku (swap2_respond)"
    except Exception as e:
        return p1["id"], f"{p2['name']} kļūda swap2_respond: {e}"

    if not isinstance(response, dict) or "action" not in response:
        return p1["id"], f"{p2['name']} atgrieza nederīgu Swap2 atbildi"

    action = response["action"]
    bot_x = None
    bot_o = None

    if action == "TAKE_O":
        bot_x, bot_o = p1, p2
    elif action == "TAKE_X":
        bot_x, bot_o = p2, p1
    elif action == "PLACE_TWO":
        extra_moves = response.get("moves")
        if not validate_moves_list(board, extra_moves, ["X", "O"]):
            return p1["id"], f"{p2['name']} nelegāli papildgājieni (PLACE_TWO)"
        for r, c, sym in extra_moves:
            board[r][c] = sym

        # === 3. SOLIS: 1. spēlētājs izvēlas galīgo krāsu ===
        try:
            final_sym = run_with_timeout(p1["swap2_final_choice"], board)
        except TimeoutError:
            return p2["id"], f"{p1['name']} pārsniedza laiku (swap2_final_choice)"
        except Exception as e:
            return p2["id"], f"{p1['name']} kļūda swap2_final_choice: {e}"

        if final_sym == "X":
            bot_x, bot_o = p1, p2
        elif final_sym == "O":
            bot_x, bot_o = p2, p1
        else:
            return p2["id"], f"{p1['name']} nederīga krāsas izvēle: {final_sym}"
    else:
        return p1["id"], f"{p2['name']} nezināma Swap2 darbība: {action}"

    # === 4. SOLIS: Pamatspēli sāk 'O' (4. vai 6. gājiens). ===
    placed_count = sum(cell != "_" for row in board for cell in row)
    turn_order = [("O", bot_o), ("X", bot_x)]

    for step in range(BOARD_SIZE * BOARD_SIZE - placed_count):
        symbol, current_bot = turn_order[step % 2]
        opponent_bot = turn_order[(step + 1) % 2][1]

        try:
            move = run_with_timeout(current_bot["get_move"], board, symbol)
        except TimeoutError:
            return opponent_bot["id"], f"{current_bot['name']} pārsniedza laiku ({MOVE_TIMEOUT}s)"
        except Exception as e:
            return opponent_bot["id"], f"{current_bot['name']} kļūda kodā: {e}"

        if not isinstance(move, (tuple, list)) or len(move) != 2:
            return opponent_bot["id"], f"{current_bot['name']} nederīgs gājiena formāts: {move}"

        r, c = move
        if not is_valid_coord(r, c) or board[r][c] != "_":
            return opponent_bot["id"], f"{current_bot['name']} nelegāls gājiens: {(r, c)}"

        board[r][c] = symbol
        total_moves = placed_count + step + 1

        if check_winner(board, r, c, symbol):
            return current_bot["id"], f"5 rindā ({symbol}, {total_moves}. gājienā)"

    return "DRAW", "Laukums pilns (neizšķirts)"


def print_standings(stats: dict, title: str = "PAŠREIZĒJĀ TABULA"):
    ranking = sorted(stats.values(), key=lambda x: (x["pts"], x["w"], -x["err"]), reverse=True)
    print(f"\n--- {title} ---")
    print(f"{'Vieta':<6} {'Dalībnieks / Bots':<30} {'Pkt':<6} {'Spēles':<7} {'U':<4} {'N':<4} {'Z':<4} {'Tech.Z'}")
    print("-" * 74)
    for pos, row in enumerate(ranking, start=1):
        games = row["w"] + row["d"] + row["l"]
        print(
            f"{pos:<6} {row['label'][:29]:<30} {row['pts']:<6.1f} "
            f"{games:<7} {row['w']:<4} {row['d']:<4} {row['l']:<4} {row['err']}"
        )
    print("-" * 74 + "\n")


def run_tournament():
    bots_by_id = {
        bot["id"]: bot
        for pattern in (BOTS_PATTERN, STUDENT_BOTS_PATTERN)
        for bot in load_bots(pattern)
    }
    bots = list(bots_by_id.values())
    n = len(bots)

    if n < 2:
        print(f"Atrasti tikai {n} derīgi boti. Turnīram vajag vismaz 2.")
        return

    print("=" * 74)
    print(f"ATRASKTI {n} DALĪBNIEKI:")
    for b in bots:
        print(f"  • {b['id']} -> {b['name']}")
    print("=" * 74)

    stats = {
        b["id"]: {
            "label": f"{b['name']} ({b['id']})",
            "pts": 0.0,
            "w": 0,
            "d": 0,
            "l": 0,
            "err": 0,
        }
        for b in bots
    }

    # Katrs ar katru izspēlē 2 spēles (mainoties lomām: P1 un P2 Swap2 atklātnē)
    total_matches = n * (n - 1)
    match_num = 0

    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            match_num += 1
            p1 = bots[i]
            p2 = bots[j]

            print(f"[{match_num}/{total_matches}] Spēlē: {p1['name']} (P1) vs {p2['name']} (P2) ... ", end="", flush=True)
            t_start = time.time()
            winner_id, reason = play_match(p1, p2)
            elapsed = time.time() - t_start

            if winner_id == "DRAW":
                print(f"NEIZŠĶIRTS ({elapsed:.1f}s) — {reason}")
                stats[p1["id"]]["pts"] += 0.5
                stats[p2["id"]]["pts"] += 0.5
                stats[p1["id"]]["d"] += 1
                stats[p2["id"]]["d"] += 1
            else:
                loser_id = p2["id"] if winner_id == p1["id"] else p1["id"]
                winner_name = stats[winner_id]["label"]
                print(f"UZVARA: {winner_name} ({elapsed:.1f}s) — {reason}")

                stats[winner_id]["pts"] += 1.0
                stats[winner_id]["w"] += 1
                stats[loser_id]["l"] += 1

                if "5 rindā" not in reason:
                    stats[loser_id]["err"] += 1

            # Parāda aktuālo līderu tabulu pēc katras partijas
            print_standings(stats, title=f"STĀVOKLIS PĒC {match_num}. PARTIJAS")
            time.sleep(0.4)  # Neliela pauze, lai ekrānā var izsekot gaitai

    print_standings(stats, title="TURNĪRA GALA REZULTĀTI")


if __name__ == "__main__":
    run_tournament()
