#!/usr/bin/env python3
"""
Hearts - A single-player card game with customizable NPC opponents.

NPC Personalities:
  - Cautious Carl  : Ultra risk-averse. Dumps high cards early, avoids points at all costs.
  - Moon Maniac     : Always tries to shoot the moon. Collects hearts and the Queen of Spades.
  - Balanced Betty  : Solid all-around player. Adapts strategy to the current hand.
  - Chaotic Charlie : Unpredictable. Mixes aggressive and defensive play randomly.
"""

import random
import os
import sys
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────
# Card model
# ──────────────────────────────────────────────

class Suit(IntEnum):
    CLUBS = 0
    DIAMONDS = 1
    SPADES = 2
    HEARTS = 3

SUIT_SYMBOLS = {
    Suit.CLUBS: "\u2663",
    Suit.DIAMONDS: "\u2666",
    Suit.SPADES: "\u2660",
    Suit.HEARTS: "\u2665",
}

SUIT_NAMES = {
    Suit.CLUBS: "Clubs",
    Suit.DIAMONDS: "Diamonds",
    Suit.SPADES: "Spades",
    Suit.HEARTS: "Hearts",
}

RANK_NAMES = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
    9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A",
}


@dataclass(frozen=True, order=True)
class Card:
    suit: Suit
    rank: int  # 2-14 (14 = Ace)

    def __str__(self):
        return f"{RANK_NAMES[self.rank]}{SUIT_SYMBOLS[self.suit]}"

    def short(self):
        return str(self)

    @property
    def points(self) -> int:
        if self.suit == Suit.HEARTS:
            return 1
        if self.suit == Suit.SPADES and self.rank == 12:
            return 13
        return 0

    @property
    def is_queen_of_spades(self) -> bool:
        return self.suit == Suit.SPADES and self.rank == 12


TWO_OF_CLUBS = Card(Suit.CLUBS, 2)
QUEEN_OF_SPADES = Card(Suit.SPADES, 12)


def make_deck() -> list[Card]:
    return [Card(suit, rank) for suit in Suit for rank in range(2, 15)]


def sort_hand(cards: list[Card]) -> list[Card]:
    return sorted(cards, key=lambda c: (c.suit, c.rank))


# ──────────────────────────────────────────────
# NPC Personality definitions
# ──────────────────────────────────────────────

class Personality:
    """Base NPC personality."""

    name: str = "Base"
    description: str = ""

    def choose_pass_cards(self, hand: list[Card]) -> list[Card]:
        raise NotImplementedError

    def choose_card(
        self,
        hand: list[Card],
        trick: list[tuple["Player", Card]],
        lead_suit: Optional[Suit],
        hearts_broken: bool,
        is_first_trick: bool,
        player: "Player",
        all_players: list["Player"],
    ) -> Card:
        raise NotImplementedError


class CautiousCarl(Personality):
    """Ultra risk-averse. Dumps dangerous cards, plays low, avoids points."""

    name = "Cautious Carl"
    description = "Risk-averse: dumps high cards, always plays it safe."

    def choose_pass_cards(self, hand: list[Card]) -> list[Card]:
        # Pass the most dangerous cards: QoS, high spades, high hearts, then highest cards
        scored = []
        for c in hand:
            danger = 0
            if c.is_queen_of_spades:
                danger = 1000
            elif c.suit == Suit.SPADES and c.rank >= 10:
                danger = 500 + c.rank
            elif c.suit == Suit.HEARTS:
                danger = 200 + c.rank
            else:
                danger = c.rank
            scored.append((danger, c))
        scored.sort(reverse=True)
        return [c for _, c in scored[:3]]

    def choose_card(self, hand, trick, lead_suit, hearts_broken, is_first_trick, player, all_players):
        playable = get_legal_plays(hand, lead_suit, hearts_broken, is_first_trick)

        # Leading
        if not trick:
            # Lead lowest non-heart, non-dangerous card
            safe = [c for c in playable if c.suit != Suit.HEARTS and not c.is_queen_of_spades]
            if safe:
                return min(safe, key=lambda c: c.rank)
            return min(playable, key=lambda c: c.rank)

        # Following suit
        if lead_suit is not None:
            following = [c for c in playable if c.suit == lead_suit]
            if following:
                # Play under the current winner if possible
                winning_rank = max(c.rank for _, c in trick if c.suit == lead_suit)
                under = [c for c in following if c.rank < winning_rank]
                if under:
                    return max(under, key=lambda c: c.rank)  # highest card that still loses
                # Must go over - play lowest
                return min(following, key=lambda c: c.rank)

        # Can't follow suit - dump dangerous cards
        if QUEEN_OF_SPADES in playable:
            return QUEEN_OF_SPADES
        hearts_in_hand = [c for c in playable if c.suit == Suit.HEARTS]
        if hearts_in_hand:
            return max(hearts_in_hand, key=lambda c: c.rank)
        return max(playable, key=lambda c: c.rank)


class MoonManiac(Personality):
    """Always trying to shoot the moon. Keeps high hearts and QoS."""

    name = "Moon Maniac"
    description = "Aggressive: always tries to shoot the moon!"

    def choose_pass_cards(self, hand: list[Card]) -> list[Card]:
        # Pass low non-point cards to keep high cards for moon shooting
        non_dangerous = sorted(
            [c for c in hand if c.suit != Suit.HEARTS and not c.is_queen_of_spades],
            key=lambda c: c.rank,
        )
        # Pass the lowest cards
        return non_dangerous[:3] if len(non_dangerous) >= 3 else non_dangerous + sort_hand(
            [c for c in hand if c not in non_dangerous]
        )[:3 - len(non_dangerous)]

    def _is_moon_viable(self, player, all_players) -> bool:
        """Check if shooting the moon is still possible."""
        total_point_cards = 14  # 13 hearts + QoS
        my_points_taken = sum(c.points for c in player.tricks_taken)
        others_points = sum(
            sum(c.points for c in p.tricks_taken)
            for p in all_players if p is not player
        )
        # Still viable if no other player has taken points
        return others_points == 0 or my_points_taken > 5

    def choose_card(self, hand, trick, lead_suit, hearts_broken, is_first_trick, player, all_players):
        playable = get_legal_plays(hand, lead_suit, hearts_broken, is_first_trick)
        going_for_moon = self._is_moon_viable(player, all_players)

        if going_for_moon:
            return self._play_aggressive(playable, trick, lead_suit)
        else:
            # Fall back to cautious play
            return CautiousCarl().choose_card(hand, trick, lead_suit, hearts_broken, is_first_trick, player, all_players)

    def _play_aggressive(self, playable, trick, lead_suit):
        # Leading: lead high to win tricks
        if not trick:
            # Lead highest card, preferring hearts if broken
            return max(playable, key=lambda c: (c.points > 0, c.rank))

        # Following: try to win the trick, especially if it has points
        if lead_suit is not None:
            following = [c for c in playable if c.suit == lead_suit]
            if following:
                # Play highest to win
                return max(following, key=lambda c: c.rank)

        # Can't follow: dump low non-point cards or play QoS
        if QUEEN_OF_SPADES in playable:
            return QUEEN_OF_SPADES
        # Keep hearts, dump low off-suit
        non_hearts = [c for c in playable if c.suit != Suit.HEARTS]
        if non_hearts:
            return min(non_hearts, key=lambda c: c.rank)
        return min(playable, key=lambda c: c.rank)


class BalancedBetty(Personality):
    """Solid all-around player with reasonable heuristics."""

    name = "Balanced Betty"
    description = "Solid all-around play. Adapts to the hand."

    def choose_pass_cards(self, hand: list[Card]) -> list[Card]:
        # Pass QoS if we don't have enough spade cover, high hearts, then high cards
        scored = []
        spade_count = sum(1 for c in hand if c.suit == Suit.SPADES)
        for c in hand:
            danger = 0
            if c.is_queen_of_spades and spade_count < 4:
                danger = 800
            elif c.suit == Suit.HEARTS and c.rank >= 11:
                danger = 300 + c.rank
            elif c.suit == Suit.HEARTS:
                danger = 100 + c.rank
            elif c.rank >= 12:
                danger = 200 + c.rank
            else:
                danger = c.rank
            scored.append((danger, c))
        scored.sort(reverse=True)
        return [c for _, c in scored[:3]]

    def choose_card(self, hand, trick, lead_suit, hearts_broken, is_first_trick, player, all_players):
        playable = get_legal_plays(hand, lead_suit, hearts_broken, is_first_trick)

        # Leading
        if not trick:
            safe = [c for c in playable if c.suit != Suit.HEARTS and not c.is_queen_of_spades]
            if safe:
                # Lead a medium card
                safe.sort(key=lambda c: c.rank)
                idx = len(safe) // 3
                return safe[idx]
            return min(playable, key=lambda c: c.rank)

        # Following suit
        if lead_suit is not None:
            following = [c for c in playable if c.suit == lead_suit]
            if following:
                trick_points = sum(c.points for _, c in trick)
                winning_rank = max(c.rank for _, c in trick if c.suit == lead_suit)
                under = [c for c in following if c.rank < winning_rank]

                # If trick has no points, we can play higher
                if trick_points == 0 and under:
                    return max(under, key=lambda c: c.rank)
                elif under:
                    return max(under, key=lambda c: c.rank)
                return min(following, key=lambda c: c.rank)

        # Can't follow suit
        if QUEEN_OF_SPADES in playable:
            return QUEEN_OF_SPADES
        # Dump highest point card or highest card
        point_cards = [c for c in playable if c.points > 0]
        if point_cards:
            return max(point_cards, key=lambda c: c.points)
        return max(playable, key=lambda c: c.rank)


class ChaoticCharlie(Personality):
    """Unpredictable mix of strategies."""

    name = "Chaotic Charlie"
    description = "Wildcard: unpredictable mix of aggressive and defensive play."

    def __init__(self):
        self._cautious = CautiousCarl()
        self._moon = MoonManiac()
        self._balanced = BalancedBetty()

    def choose_pass_cards(self, hand: list[Card]) -> list[Card]:
        choice = random.choice([self._cautious, self._moon, self._balanced])
        return choice.choose_pass_cards(hand)

    def choose_card(self, hand, trick, lead_suit, hearts_broken, is_first_trick, player, all_players):
        playable = get_legal_plays(hand, lead_suit, hearts_broken, is_first_trick)

        # 40% cautious, 30% moon, 30% random
        r = random.random()
        if r < 0.4:
            return self._cautious.choose_card(hand, trick, lead_suit, hearts_broken, is_first_trick, player, all_players)
        elif r < 0.7:
            return self._moon.choose_card(hand, trick, lead_suit, hearts_broken, is_first_trick, player, all_players)
        else:
            return random.choice(playable)


PERSONALITIES = {
    "cautious": CautiousCarl,
    "moon": MoonManiac,
    "balanced": BalancedBetty,
    "chaotic": ChaoticCharlie,
}


# ──────────────────────────────────────────────
# Player model
# ──────────────────────────────────────────────

@dataclass
class Player:
    name: str
    is_human: bool = False
    personality: Optional[Personality] = None
    hand: list[Card] = field(default_factory=list)
    tricks_taken: list[Card] = field(default_factory=list)
    total_score: int = 0

    def round_points(self) -> int:
        return sum(c.points for c in self.tricks_taken)

    def reset_round(self):
        self.hand.clear()
        self.tricks_taken.clear()


# ──────────────────────────────────────────────
# Game logic helpers
# ──────────────────────────────────────────────

def get_legal_plays(
    hand: list[Card],
    lead_suit: Optional[Suit],
    hearts_broken: bool,
    is_first_trick: bool,
) -> list[Card]:
    """Return list of cards that can be legally played."""
    if not hand:
        return []

    # Must lead 2 of clubs on first trick
    if lead_suit is None and is_first_trick:
        if TWO_OF_CLUBS in hand:
            return [TWO_OF_CLUBS]

    # Leading
    if lead_suit is None:
        if hearts_broken:
            return list(hand)
        non_hearts = [c for c in hand if c.suit != Suit.HEARTS]
        return non_hearts if non_hearts else list(hand)

    # Must follow suit
    following = [c for c in hand if c.suit == lead_suit]
    if following:
        return following

    # Can't follow suit - play anything EXCEPT:
    # On first trick, no hearts or QoS
    if is_first_trick:
        safe = [c for c in hand if c.points == 0]
        return safe if safe else list(hand)

    return list(hand)


def trick_winner(trick: list[tuple[Player, Card]], lead_suit: Suit) -> int:
    """Return index into trick of the winning card."""
    best_idx = 0
    best_rank = -1
    for i, (_, card) in enumerate(trick):
        if card.suit == lead_suit and card.rank > best_rank:
            best_rank = card.rank
            best_idx = i
    return best_idx


# ──────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def display_header(round_num: int, players: list[Player]):
    print("=" * 60)
    print(f"  HEARTS  -  Round {round_num}")
    print("=" * 60)
    print()
    print("  Scores:", end="")
    for p in players:
        marker = " (You)" if p.is_human else f" [{p.personality.name}]" if p.personality else ""
        print(f"  {p.name}: {p.total_score}{marker}", end="")
    print()
    print("-" * 60)


def display_trick(trick: list[tuple[Player, Card]], lead_player_name: str):
    if not trick:
        print("  Trick: (empty)")
        return
    parts = []
    for player, card in trick:
        parts.append(f"{player.name}: {card}")
    print(f"  Trick: {' | '.join(parts)}")


def display_hand(hand: list[Card]):
    sorted_hand = sort_hand(hand)
    suits_display = {}
    for c in sorted_hand:
        suit_name = SUIT_NAMES[c.suit]
        if suit_name not in suits_display:
            suits_display[suit_name] = []
        suits_display[suit_name].append(c)

    print("\n  Your hand:")
    idx = 1
    card_map = {}
    for suit_name in ["Clubs", "Diamonds", "Spades", "Hearts"]:
        if suit_name in suits_display:
            cards_str = ""
            for c in suits_display[suit_name]:
                cards_str += f"  [{idx:2d}] {c}"
                card_map[idx] = c
                idx += 1
            print(f"    {suit_name}: {cards_str}")
    return card_map


def display_round_scores(players: list[Player], shot_moon_player: Optional[Player] = None):
    print("\n" + "=" * 60)
    print("  ROUND RESULTS")
    print("=" * 60)
    if shot_moon_player:
        print(f"\n  {shot_moon_player.name} SHOT THE MOON!")
        print("  Everyone else gets 26 points!")
    print()
    for p in players:
        pts = p.round_points()
        marker = " (You)" if p.is_human else ""
        if shot_moon_player:
            if p is shot_moon_player:
                print(f"    {p.name}{marker}: 0 pts this round (total: {p.total_score})")
            else:
                print(f"    {p.name}{marker}: +26 pts this round (total: {p.total_score})")
        else:
            print(f"    {p.name}{marker}: +{pts} pts this round (total: {p.total_score})")
    print()


# ──────────────────────────────────────────────
# Game class
# ──────────────────────────────────────────────

class HeartsGame:
    def __init__(self, player_name: str, npc_configs: list[tuple[str, str]]):
        """
        npc_configs: list of (name, personality_key) for the 3 NPCs.
        """
        self.human = Player(name=player_name, is_human=True)
        self.npcs = []
        for npc_name, personality_key in npc_configs:
            cls = PERSONALITIES[personality_key]
            self.npcs.append(Player(name=npc_name, personality=cls()))

        self.players = [self.human] + self.npcs
        self.round_num = 0
        self.hearts_broken = False
        self.target_score = 100

    def run(self):
        """Main game loop."""
        print("\n  Welcome to Hearts!")
        print(f"  Playing to {self.target_score} points. Lowest score wins.\n")
        print("  Your opponents:")
        for npc in self.npcs:
            print(f"    - {npc.name}: {npc.personality.description}")
        print()
        input("  Press Enter to start...")

        while True:
            self.round_num += 1
            self._play_round()

            # Check for game over
            if any(p.total_score >= self.target_score for p in self.players):
                break

        self._show_final_results()

    def _play_round(self):
        """Play a single round of Hearts."""
        for p in self.players:
            p.reset_round()
        self.hearts_broken = False

        # Deal
        deck = make_deck()
        random.shuffle(deck)
        for i, card in enumerate(deck):
            self.players[i % 4].hand.append(card)
        for p in self.players:
            p.hand = sort_hand(p.hand)

        # Pass cards (skip every 4th round)
        pass_dir = (self.round_num - 1) % 4  # 0=left, 1=right, 2=across, 3=none
        if pass_dir < 3:
            self._pass_phase(pass_dir)

        # Determine who has 2 of clubs
        lead_idx = next(i for i, p in enumerate(self.players) if TWO_OF_CLUBS in p.hand)

        # Play 13 tricks
        for trick_num in range(13):
            is_first_trick = (trick_num == 0)
            lead_idx = self._play_trick(lead_idx, is_first_trick)

        # Score the round
        self._score_round()

    def _pass_phase(self, direction: int):
        """Handle card passing. 0=left, 1=right, 2=across."""
        dir_names = ["left", "right", "across"]
        dir_name = dir_names[direction]

        clear_screen()
        display_header(self.round_num, self.players)
        print(f"\n  Passing 3 cards to the {dir_name}.")

        # Human picks 3 cards
        card_map = display_hand(self.human.hand)
        human_pass = self._human_pick_pass_cards(card_map)

        # NPCs pick cards
        npc_passes = {}
        for npc in self.npcs:
            npc_passes[npc] = npc.personality.choose_pass_cards(npc.hand)

        # Determine recipients
        all_passes = {self.human: human_pass}
        all_passes.update(npc_passes)

        offsets = {0: 1, 1: 3, 2: 2}  # left, right, across
        offset = offsets[direction]

        received = {p: [] for p in self.players}
        for i, giver in enumerate(self.players):
            receiver_idx = (i + offset) % 4
            receiver = self.players[receiver_idx]
            cards_to_pass = all_passes[giver]
            received[receiver].extend(cards_to_pass)
            for c in cards_to_pass:
                giver.hand.remove(c)

        for p in self.players:
            p.hand.extend(received[p])
            p.hand = sort_hand(p.hand)

        # Show human what they received
        print(f"\n  You received: {', '.join(str(c) for c in received[self.human])}")
        input("  Press Enter to continue...")

    def _human_pick_pass_cards(self, card_map: dict[int, Card]) -> list[Card]:
        """Get 3 cards from human to pass."""
        chosen = []
        while len(chosen) < 3:
            remaining = 3 - len(chosen)
            try:
                prompt = f"\n  Select card {len(chosen)+1} of 3 to pass (enter number): "
                raw = input(prompt).strip()
                num = int(raw)
                if num not in card_map:
                    print("  Invalid number. Try again.")
                    continue
                card = card_map[num]
                if card in chosen:
                    print("  Already selected that card. Try again.")
                    continue
                chosen.append(card)
                print(f"    Selected: {card}")
            except (ValueError, EOFError):
                print("  Please enter a valid number.")
        return chosen

    def _play_trick(self, lead_idx: int, is_first_trick: bool) -> int:
        """Play one trick. Returns index of winner (who leads next)."""
        trick: list[tuple[Player, Card]] = []
        lead_suit: Optional[Suit] = None

        for i in range(4):
            current_idx = (lead_idx + i) % 4
            current_player = self.players[current_idx]

            clear_screen()
            display_header(self.round_num, self.players)

            # Show points taken this round
            pts_line = "  Points taken: "
            for p in self.players:
                pts_line += f" {p.name}: {p.round_points()} |"
            print(pts_line.rstrip("|"))
            print()

            display_trick(trick, self.players[lead_idx].name)

            if current_player.is_human:
                card = self._human_play_card(
                    current_player, trick, lead_suit, is_first_trick
                )
            else:
                card = current_player.personality.choose_card(
                    current_player.hand, trick, lead_suit,
                    self.hearts_broken, is_first_trick,
                    current_player, self.players,
                )
                print(f"\n  {current_player.name} plays {card}")

            if i == 0:
                lead_suit = card.suit

            current_player.hand.remove(card)
            trick.append((current_player, card))

            if card.suit == Suit.HEARTS:
                self.hearts_broken = True

        # Show completed trick
        clear_screen()
        display_header(self.round_num, self.players)
        print()
        display_trick(trick, self.players[lead_idx].name)

        # Determine winner
        winner_idx = trick_winner(trick, lead_suit)
        winner_player = trick[winner_idx][0]
        trick_cards = [c for _, c in trick]
        trick_points = sum(c.points for c in trick_cards)
        winner_player.tricks_taken.extend(trick_cards)

        print(f"\n  {winner_player.name} wins the trick! (+{trick_points} pts)")
        input("  Press Enter to continue...")

        return self.players.index(winner_player)

    def _human_play_card(
        self,
        player: Player,
        trick: list[tuple[Player, Card]],
        lead_suit: Optional[Suit],
        is_first_trick: bool,
    ) -> Card:
        """Get a card choice from the human player."""
        legal = get_legal_plays(player.hand, lead_suit, self.hearts_broken, is_first_trick)
        card_map = display_hand(player.hand)

        # Build reverse map
        num_for_card = {c: n for n, c in card_map.items()}

        while True:
            try:
                raw = input("\n  Your play (enter number): ").strip()
                num = int(raw)
                if num not in card_map:
                    print("  Invalid number. Try again.")
                    continue
                card = card_map[num]
                if card not in legal:
                    print(f"  You can't play {card} right now. Legal plays: {', '.join(str(c) for c in sort_hand(legal))}")
                    continue
                return card
            except (ValueError, EOFError):
                print("  Please enter a valid number.")

    def _score_round(self):
        """Score the round, checking for shooting the moon."""
        # Check for shoot the moon
        moon_shooter = None
        for p in self.players:
            if p.round_points() == 26:
                moon_shooter = p
                break

        if moon_shooter:
            for p in self.players:
                if p is not moon_shooter:
                    p.total_score += 26
        else:
            for p in self.players:
                p.total_score += p.round_points()

        clear_screen()
        display_round_scores(self.players, moon_shooter)
        input("  Press Enter to continue...")

    def _show_final_results(self):
        clear_screen()
        print("\n" + "=" * 60)
        print("  GAME OVER!")
        print("=" * 60)
        ranked = sorted(self.players, key=lambda p: p.total_score)
        for i, p in enumerate(ranked):
            marker = " (You)" if p.is_human else ""
            medal = ["1st", "2nd", "3rd", "4th"][i]
            print(f"    {medal}: {p.name}{marker} - {p.total_score} pts")
        print()
        if ranked[0].is_human:
            print("  Congratulations, you win!")
        else:
            print(f"  {ranked[0].name} wins!")
        print()


# ──────────────────────────────────────────────
# Setup & main
# ──────────────────────────────────────────────

def show_personality_menu() -> list[tuple[str, str]]:
    """Let the player configure their 3 NPC opponents."""
    print("\n" + "=" * 60)
    print("  NPC OPPONENT SETUP")
    print("=" * 60)
    print()
    print("  Available personalities:")
    print("    1. Cautious Carl  - Risk-averse: dumps high cards, avoids points")
    print("    2. Moon Maniac    - Aggressive: always tries to shoot the moon")
    print("    3. Balanced Betty - Solid all-around adaptive play")
    print("    4. Chaotic Charlie- Wildcard: unpredictable mix of strategies")
    print()

    keys = ["cautious", "moon", "balanced", "chaotic"]
    default_names = ["Cautious Carl", "Moon Maniac", "Balanced Betty", "Chaotic Charlie"]

    configs = []

    # Option for quick start with defaults
    print("  Press Enter for default opponents (Carl, Maniac, Betty),")
    raw = input("  or type 'c' to customize: ").strip().lower()

    if raw != "c":
        return [
            ("Carl", "cautious"),
            ("Luna", "moon"),
            ("Betty", "balanced"),
        ]

    for i in range(3):
        while True:
            try:
                choice = input(f"\n  Choose personality for NPC {i+1} (1-4): ").strip()
                idx = int(choice) - 1
                if 0 <= idx <= 3:
                    name_input = input(f"  Name for this NPC (Enter for '{default_names[idx]}'): ").strip()
                    name = name_input if name_input else default_names[idx]
                    configs.append((name, keys[idx]))
                    print(f"    -> {name} ({keys[idx]})")
                    break
                else:
                    print("  Pick 1-4.")
            except (ValueError, EOFError):
                print("  Pick 1-4.")

    return configs


def main():
    clear_screen()
    print()
    print("  " + "=" * 40)
    print("  |        H E A R T S               |")
    print("  |   A classic card game             |")
    print("  " + "=" * 40)
    print()

    player_name = input("  Enter your name (Enter for 'You'): ").strip()
    if not player_name:
        player_name = "You"

    npc_configs = show_personality_menu()

    game = HeartsGame(player_name, npc_configs)
    game.run()


if __name__ == "__main__":
    main()
