import unittest
from bunker_bot.game import GameState, Player, GamePhase

class TestGameLogic(unittest.TestCase):
    def setUp(self):
        self.game = GameState(10, 12345, "en", 999)
        # Mock players
        self.p1 = Player(1, "P1", "en")
        self.p2 = Player(2, "P2", "en")
        self.p3 = Player(3, "P3", "en")
        self.game.players = [self.p1, self.p2, self.p3]
        self.game.bunker_spots = 1 # 1 spot, 3 players -> 2 must die

    def test_add_player(self):
        res = self.game.add_player(4, "P4")
        self.assertTrue(res)
        self.assertEqual(len(self.game.players), 4)

    def test_vote_elimination(self):
        # Setup votes: P1=0, P2=2, P3=1
        self.game.votes = {
            1: [2],
            3: [2],
            2: [3]
        }
        eliminated, text, is_draw = self.game.resolve_votes()
        
        self.assertFalse(is_draw)
        self.assertEqual(len(eliminated), 1)
        self.assertEqual(eliminated[0].user_id, 2)

    def test_vote_draw(self):
        # Setup tie: P2=1, P3=1
        self.game.votes = {
            1: [2],
            2: [3]
        }
        eliminated, text, is_draw = self.game.resolve_votes()
        
        self.assertTrue(is_draw)
        self.assertEqual(len(eliminated), 0)
        self.assertTrue(self.game.double_elim_next)

if __name__ == '__main__':
    unittest.main()