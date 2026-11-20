"""Steam demo seeding must match the requested game, not the first search hit."""
import unittest
from scripts.seed_demo import _matching_steam_app as match

def app(i,name):return {'type':'app','id':i,'name':name}

class MatchingTests(unittest.TestCase):
    def test_exact_game_beats_a_sequel_ranked_first(self):
        self.assertEqual(match([app(1,'OCTOPATH TRAVELER 0'),app(2,'OCTOPATH TRAVELER™')],'OCTOPATH TRAVELER')['id'],2)

    def test_substring_is_not_a_match(self):
        self.assertIsNone(match([app(1,'Please, Come Inside')],'INSIDE'))
        self.assertIsNone(match([app(2,'Grounded 2')],'Grounded'))
        self.assertIsNone(match([app(3,'Planet Zoo 2')],'Planet Zoo'))

    def test_dlc_cannot_stand_in_for_the_base_game(self):
        self.assertIsNone(match([app(1,'Overwatch® - Ultimate Battle Pass Bundle')],'Overwatch 2'))
        self.assertEqual(match([app(1,'Overwatch® - Ultimate Battle Pass Bundle'),app(2,'Overwatch®')],'Overwatch 2')['id'],2)

    def test_trademarks_and_named_editions_are_accepted(self):
        self.assertEqual(match([app(1,'HELLDIVERS™ 2')],'HELLDIVERS 2')['id'],1)
        self.assertEqual(match([app(2,'Spiritfarer®: Farewell Edition')],'Spiritfarer')['id'],2)
        self.assertEqual(match([app(3,'Nioh 2 – The Complete Edition')],'Nioh 2')['id'],3)
        self.assertEqual(match([app(4,'Disco Elysium - The Final Cut')],'Disco Elysium')['id'],4)

if __name__=='__main__':unittest.main()
