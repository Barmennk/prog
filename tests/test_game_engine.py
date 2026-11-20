import unittest

from game_engine import Match


def make_bot(action="TAKE_O"):
    def propose(board):
        center = len(board) // 2
        return [(center, center, "X"), (center, center + 1, "X"), (center + 1, center, "O")]

    def respond(board):
        return {"action": action if board else "INVALID"}

    def final_choice(board):
        return "X" if board else "O"

    def get_move(board, player):
        return (0, 0) if board and player in ("X", "O") else (-1, -1)

    return {
        "id": "test-bot",
        "name": "Test bots",
        "swap2_propose": propose,
        "swap2_respond": respond,
        "swap2_final_choice": final_choice,
        "get_move": get_move,
    }


class MatchTests(unittest.TestCase):
    def test_swap2_gives_human_color_choice_when_bot_places_two(self):
        match = Match(make_bot("PLACE_TWO"), human_first=False)

        match.perform_bot_action()
        self.assertEqual(match.phase, "response")
        match.human_respond("PLACE_TWO")
        match.human_place(6, 6)
        match.human_place(6, 7)
        self.assertEqual(match.phase, "final_choice")

        match.perform_bot_action()
        self.assertEqual(match.phase, "play")
        self.assertEqual(match.current_symbol, "O")
        self.assertEqual(match.colors["X"], "P1")
        self.assertEqual(match.colors["O"], "P2")

    def test_game_starts_with_o_and_detects_a_win(self):
        match = Match(make_bot(), human_first=True)
        match.human_place(7, 7)
        match.human_place(7, 8)
        match.human_place(8, 7)
        match.perform_bot_action()

        self.assertEqual(match.current_symbol, "O")
        self.assertEqual(match.current_actor, "bot")
        match.colors = {"X": "P1", "O": "P2"}
        match.board[9][3:7] = ["X", "X", "X", "X"]
        match.current_symbol = "X"
        match.human_place(9, 7)

        self.assertEqual(match.result, "win")
        self.assertEqual(match.winner, "P1")

    def test_full_board_without_five_in_a_row_is_a_draw(self):
        match = Match(make_bot(), human_first=True)
        match.colors = {"X": "P1", "O": "P2"}
        match.phase = "play"
        match.current_symbol = "X"

        for row in range(15):
            for col in range(15):
                if (row, col) != (14, 14):
                    match.board[row][col] = "X" if (row + 2 * col) % 5 < 3 else "O"

        match.human_place(14, 14)

        self.assertEqual(match.result, "draw")
        self.assertEqual(match.phase, "finished")


if __name__ == "__main__":
    unittest.main()
