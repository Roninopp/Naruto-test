import logging
import uuid
import random
import datetime
from datetime import timezone
from html import escape
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Daily Pack Loot Table ---
PACK_LOOT_TABLE = [
    (100, 'ryo', 'ryo', 50, "Common Ryo Pouch"),
    (100, 'ryo', 'ryo', 75, "Common Ryo Pouch"),
    (50,  'ryo', 'ryo', 150, "Uncommon Ryo Pouch"),
    (25,  'item', 'health_potion', 1, "Health Potion"),
    (10,  'ryo', 'ryo', 500, "Rare Ryo Chest"),
    (5,   'item', 'soldier_pill', 1, "Soldier Pill"),
    (1,   'exp', 'exp', 100, "Legendary EXP Scroll")
]

# --- Cooldowns ---
PACK_COOLDOWN_HOURS = 4

# --- 🆕 NEW GAME CONSTANTS ---
# Slot Machine
SLOT_COST = 50
SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🔔", "💎", "⭐", "🎰"]
SLOT_PAYOUTS = {
    ('💎', '💎', '💎'): 1000,  # Jackpot!
    ('⭐', '⭐', '⭐'): 500,
    ('🔔', '🔔', '🔔'): 300,
    ('🍊', '🍊', '🍊'): 150,
    ('🍋', '🍋', '🍋'): 100,
    ('🍒', '🍒', '🍒'): 75,
    'any_two': 25  # Any 2 matching
}

# Dice Battle
DICE_COST = 30
DICE_WIN_MULTIPLIER = 2.5

# Coin Flip
COINFLIP_COST = 40
COINFLIP_WIN = 75

# Scratch Card
SCRATCH_COST = 60
SCRATCH_PRIZES = [
    (60, 0, "Nothing"),      # 60% chance
    (25, 50, "50 Ryo"),      # 25% chance
    (10, 150, "150 Ryo"),    # 10% chance
    (4, 300, "300 Ryo"),     # 4% chance
    (1, 1000, "1000 Ryo!")   # 1% chance (Jackpot)
]

# Ninja Roulette
ROULETTE_COST = 100
ROULETTE_NUMBERS = list(range(0, 37))  # 0-36
ROULETTE_COLORS = {
    'red': [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36],
    'black': [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35],
    'green': [0]
}

# Treasure Hunt (Multi-choice mini RPG)
HUNT_COST = 75
# ----------------------------

def get_wallet_text(player):
    """Generates the HTML text for a player's wallet card."""
    is_hosp, _ = gl.get_hospital_status(player)
    status_text = "🏥 Hospitalized" if is_hosp else "❤️ Alive"
    wallet_text = (
        f"<b>--- 🥷 {escape(player['username'])}'s Wallet 🥷 ---</b>\n\n"
        f"<b>Rank:</b> {player['rank']}\n"
        f"<b>Level:</b> {player['level']}\n"
        f"<b>Ryo:</b> {player['ryo']:,} 💰\n"
        f"<b>Kills:</b> {player.get('kills', 0)} ☠️\n"
        f"<b>Status:</b> {status_text}"
    )
    return wallet_text

def get_top_killers_text():
    """Generates the HTML text for the Top 5 Killers."""
    text = "☠️ **Top 5 Deadliest Ninja** ☠️\n*(By Kills)*\n\n"
    top_players = db.get_top_players_by_kills(limit=5)
    if not top_players:
        text += "No successful kills yet..."
    else:
        for i, p in enumerate(top_players):
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
            mention = f'<a href="tg://user?id={p["user_id"]}">{escape(p["username"])}</a>'
            text += f"{rank} {mention} - {p['kills']} Kills\n"
    return text

def get_top_rich_text():
    """Generates the HTML text for the Top 5 Richest."""
    text = "💰 **Top 5 Richest Ninja** 💰\n*(By Total Ryo)*\n\n"
    top_players = db.get_top_players_by_ryo(limit=5)
    if not top_players:
        text += "No one has any Ryo..."
    else:
        for i, p in enumerate(top_players):
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
            mention = f'<a href="tg://user?id={p["user_id"]}">{escape(p["username"])}</a>'
            text += f"{rank} {mention} - {p['ryo']:,} Ryo\n"
    return text

def get_daily_pack_prize(player):
    """Runs the loot table, returns the text and the db update dict."""
    prize = random.choices(PACK_LOOT_TABLE, weights=[p[0] for p in PACK_LOOT_TABLE], k=1)[0]
    _, p_type, p_key, p_amount, p_name = prize
    
    updates = {'inline_pack_cooldown': datetime.datetime.now(timezone.utc)}
    result_text = ""

    if p_type == 'ryo':
        updates['ryo'] = player['ryo'] + p_amount
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} opened a pack and found a **{p_name}**!\n💰 **You gain {p_amount} Ryo!**"
    
    elif p_type == 'item':
        inventory = player.get('inventory') or []
        inventory.append(p_key)
        updates['inventory'] = inventory
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} opened a pack and found a **{p_name}**!\n📦 It was added to your /inventory."

    elif p_type == 'exp':
        updates['exp'] = player['exp'] + p_amount
        updates['total_exp'] = player['total_exp'] + p_amount
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} opened a pack and found a **{p_name}**!\n✨ **You gain {p_amount} EXP!**"

    return result_text, updates

# 🆕 NEW GAME FUNCTIONS

def play_slot_machine(player):
    """Spins a 3-reel slot machine."""
    reel1 = random.choice(SLOT_SYMBOLS)
    reel2 = random.choice(SLOT_SYMBOLS)
    reel3 = random.choice(SLOT_SYMBOLS)
    
    result = (reel1, reel2, reel3)
    winnings = 0
    prize_text = "Nothing... Try again!"
    
    # Check for wins
    if result in SLOT_PAYOUTS:
        winnings = SLOT_PAYOUTS[result]
        prize_text = f"🎰 JACKPOT! You win {winnings} Ryo!"
    elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
        winnings = SLOT_PAYOUTS['any_two']
        prize_text = f"Two match! You win {winnings} Ryo!"
    
    net_gain = winnings - SLOT_COST
    
    result_text = (
        f"🎰 **SLOT MACHINE** 🎰\n\n"
        f"[ {reel1} | {reel2} | {reel3} ]\n\n"
        f"{prize_text}\n"
        f"Net: {'+' if net_gain >= 0 else ''}{net_gain} Ryo"
    )
    
    return result_text, {'ryo': player['ryo'] - SLOT_COST + winnings}

def play_dice_battle(player):
    """Roll 2 dice, higher total wins."""
    player_roll = random.randint(1, 6) + random.randint(1, 6)
    bot_roll = random.randint(1, 6) + random.randint(1, 6)
    
    if player_roll > bot_roll:
        winnings = int(DICE_COST * DICE_WIN_MULTIPLIER)
        result_text = (
            f"🎲 **DICE BATTLE** 🎲\n\n"
            f"Your Roll: {player_roll}\n"
            f"Bot Roll: {bot_roll}\n\n"
            f"🎉 **YOU WIN!** +{winnings} Ryo"
        )
        updates = {'ryo': player['ryo'] - DICE_COST + winnings}
    elif player_roll < bot_roll:
        result_text = (
            f"🎲 **DICE BATTLE** 🎲\n\n"
            f"Your Roll: {player_roll}\n"
            f"Bot Roll: {bot_roll}\n\n"
            f"😢 **YOU LOSE!** -{DICE_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - DICE_COST}
    else:
        result_text = (
            f"🎲 **DICE BATTLE** 🎲\n\n"
            f"Your Roll: {player_roll}\n"
            f"Bot Roll: {bot_roll}\n\n"
            f"🤝 **TIE!** No money lost or gained."
        )
        updates = {}
    
    return result_text, updates

def play_coin_flip(player, choice):
    """Flip a coin, guess correctly to win."""
    flip = random.choice(['Heads', 'Tails'])
    
    if choice.lower() == flip.lower():
        result_text = (
            f"🪙 **COIN FLIP** 🪙\n\n"
            f"Result: {flip}\n"
            f"Your Guess: {choice}\n\n"
            f"✅ **CORRECT!** +{COINFLIP_WIN} Ryo"
        )
        updates = {'ryo': player['ryo'] - COINFLIP_COST + COINFLIP_WIN}
    else:
        result_text = (
            f"🪙 **COIN FLIP** 🪙\n\n"
            f"Result: {flip}\n"
            f"Your Guess: {choice}\n\n"
            f"❌ **WRONG!** -{COINFLIP_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - COINFLIP_COST}
    
    return result_text, updates

def play_scratch_card(player):
    """Scratch a card for random prize."""
    weights = [p[0] for p in SCRATCH_PRIZES]
    prize = random.choices(SCRATCH_PRIZES, weights=weights, k=1)[0]
    _, prize_ryo, prize_name = prize
    
    if prize_ryo > 0:
        result_text = (
            f"🎫 **SCRATCH CARD** 🎫\n\n"
            f"🎉 You won: **{prize_name}**!\n"
            f"Net: +{prize_ryo - SCRATCH_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - SCRATCH_COST + prize_ryo}
    else:
        result_text = (
            f"🎫 **SCRATCH CARD** 🎫\n\n"
            f"😢 No prize this time...\n"
            f"Net: -{SCRATCH_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - SCRATCH_COST}
    
    return result_text, updates

def play_ninja_roulette(player, bet_type, bet_value=None):
    """Roulette with color/number betting."""
    winning_number = random.choice(ROULETTE_NUMBERS)
    
    # Determine color
    if winning_number in ROULETTE_COLORS['red']:
        winning_color = 'red'
        color_emoji = "🔴"
    elif winning_number in ROULETTE_COLORS['black']:
        winning_color = 'black'
        color_emoji = "⚫"
    else:
        winning_color = 'green'
        color_emoji = "🟢"
    
    won = False
    winnings = 0
    
    if bet_type == 'color' and bet_value == winning_color:
        won = True
        winnings = ROULETTE_COST * 2  # 2x payout
    elif bet_type == 'number' and bet_value == winning_number:
        won = True
        winnings = ROULETTE_COST * 35  # 35x payout (like real roulette!)
    
    if won:
        result_text = (
            f"🎰 **NINJA ROULETTE** 🎰\n\n"
            f"Winning Number: {color_emoji} **{winning_number}**\n"
            f"Your Bet: {bet_value}\n\n"
            f"🎉 **YOU WIN!** +{winnings} Ryo"
        )
        updates = {'ryo': player['ryo'] - ROULETTE_COST + winnings}
    else:
        result_text = (
            f"🎰 **NINJA ROULETTE** 🎰\n\n"
            f"Winning Number: {color_emoji} **{winning_number}**\n"
            f"Your Bet: {bet_value}\n\n"
            f"😢 **YOU LOSE!** -{ROULETTE_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - ROULETTE_COST}
    
    return result_text, updates

def play_treasure_hunt(player, choice):
    """Mini RPG treasure hunt with 3 paths."""
    paths = {
        'cave': {
            'outcomes': [
                (50, 100, "🦇 You found a hidden stash! +100 Ryo"),
                (30, 0, "🕷️ Spider trap! You escape but found nothing."),
                (20, 200, "💎 Ancient treasure! +200 Ryo")
            ]
        },
        'forest': {
            'outcomes': [
                (60, 50, "🌳 You found some herbs! +50 Ryo"),
                (25, 150, "🦌 You helped a deer and it led you to treasure! +150 Ryo"),
                (15, 0, "🐍 Snake attack! You barely escaped.")
            ]
        },
        'temple': {
            'outcomes': [
                (40, 75, "🏛️ Small offering box. +75 Ryo"),
                (40, 0, "⛩️ The temple is empty..."),
                (20, 300, "📜 Ancient scroll with hidden Ryo! +300 Ryo")
            ]
        }
    }
    
    if choice not in paths:
        choice = 'cave'
    
    weights = [o[0] for o in paths[choice]['outcomes']]
    outcome = random.choices(paths[choice]['outcomes'], weights=weights, k=1)[0]
    _, reward, message = outcome
    
    result_text = (
        f"🗺️ **TREASURE HUNT** 🗺️\n\n"
        f"You chose: **{choice.title()}**\n\n"
        f"{message}\n"
        f"Net: {'+' if reward - HUNT_COST >= 0 else ''}{reward - HUNT_COST} Ryo"
    )
    
    updates = {'ryo': player['ryo'] - HUNT_COST + reward}
    
    return result_text, updates


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline queries (@BotName ...)."""
    query = update.inline_query
    if not query:
        return

    user_id = query.from_user.id
    player = db.get_player(user_id)
    results = []

    if player:
        is_hosp, _ = gl.get_hospital_status(player)
        
        # --- 1. Show My Wallet ---
        wallet_text = get_wallet_text(player)
        results.append(
            InlineQueryResultArticle(
                id="wallet",
                title="🥷 Show My Wallet (Flex!)",
                description=f"Post your Lvl {player['level']} | {player['ryo']} Ryo | {player.get('kills', 0)} Kills card",
                input_message_content=InputTextMessageContent(wallet_text, parse_mode="HTML")
            )
        )
        
        # --- 2. Show Top Killers ---
        killers_text = get_top_killers_text()
        results.append(
            InlineQueryResultArticle(
                id="top_killers",
                title="☠️ Show Top 5 Killers",
                description="Post the 'Top Killers' leaderboard here.",
                input_message_content=InputTextMessageContent(killers_text, parse_mode="HTML")
            )
        )
        
        # --- 3. Show Top Richest ---
        rich_text = get_top_rich_text()
        results.append(
            InlineQueryResultArticle(
                id="top_rich",
                title="💰 Show Top 5 Richest",
                description="Post the 'Top Richest' leaderboard here.",
                input_message_content=InputTextMessageContent(rich_text, parse_mode="HTML")
            )
        )
        
        # --- 4. Daily Shinobi Pack ---
        now = datetime.datetime.now(timezone.utc)
        last_claim_time = player.get('inline_pack_cooldown')
        
        if last_claim_time and not isinstance(last_claim_time, datetime.datetime):
            try:
                last_claim_time = datetime.datetime.fromisoformat(last_claim_time)
            except:
                last_claim_time = None
        
        if last_claim_time and last_claim_time.tzinfo is None:
            last_claim_time = last_claim_time.replace(tzinfo=timezone.utc)
        
        if last_claim_time and (now - last_claim_time) < datetime.timedelta(hours=PACK_COOLDOWN_HOURS):
            remaining = (last_claim_time + datetime.timedelta(hours=PACK_COOLDOWN_HOURS)) - now
            remaining_hours = int(remaining.total_seconds() // 3600)
            remaining_minutes = int((remaining.total_seconds() % 3600) // 60)
            
            results.append(
                InlineQueryResultArticle(
                    id="daily_pack_claimed",
                    title="❌ Daily Pack on Cooldown",
                    description=f"Come back in {remaining_hours}h {remaining_minutes}m.",
                    input_message_content=InputTextMessageContent(
                        f"I've already claimed my daily pack. I can claim again in {remaining_hours}h {remaining_minutes}m."
                    )
                )
            )
        else:
            result_text, updates_to_be_done = get_daily_pack_prize(player)
            db.update_player(user_id, updates_to_be_done)

            results.append(
                InlineQueryResultArticle(
                    id="daily_pack_open",
                    title="🎁 Open your Daily Shinobi Pack!",
                    description=f"Get a free random reward! (Resets every {PACK_COOLDOWN_HOURS} hours)",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # --- 🆕 5. SLOT MACHINE ---
        if is_hosp:
            results.append(
                InlineQueryResultArticle(
                    id="slot_fail_hosp",
                    title=f"❌ Cannot play while hospitalized",
                    description="Use /heal to recover.",
                    input_message_content=InputTextMessageContent("I can't play right now, I'm in the hospital!")
                )
            )
        elif player['ryo'] < SLOT_COST:
            results.append(
                InlineQueryResultArticle(
                    id="slot_fail_ryo",
                    title=f"🎰 Slot Machine (Need {SLOT_COST} Ryo)",
                    description="Not enough Ryo!",
                    input_message_content=InputTextMessageContent(f"I need {SLOT_COST} Ryo to play the slots!")
                )
            )
        else:
            result_text, updates = play_slot_machine(player)
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id=f"slot_{uuid.uuid4()}",
                    title=f"🎰 Slot Machine (Cost: {SLOT_COST} Ryo)",
                    description="Spin to win big! 3 matching = JACKPOT!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # --- 🆕 6. DICE BATTLE ---
        if not is_hosp and player['ryo'] >= DICE_COST:
            result_text, updates = play_dice_battle(player)
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id=f"dice_{uuid.uuid4()}",
                    title=f"🎲 Dice Battle (Cost: {DICE_COST} Ryo)",
                    description="Roll 2 dice! Beat the bot to win!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # --- 🆕 7. COIN FLIP (Heads) ---
        if not is_hosp and player['ryo'] >= COINFLIP_COST:
            result_text_h, updates_h = play_coin_flip(player, 'Heads')
            db.update_player(user_id, updates_h)
            results.append(
                InlineQueryResultArticle(
                    id=f"coin_heads_{uuid.uuid4()}",
                    title=f"🪙 Coin Flip: HEADS (Cost: {COINFLIP_COST} Ryo)",
                    description="Guess correctly to win!",
                    input_message_content=InputTextMessageContent(result_text_h, parse_mode="HTML")
                )
            )
        
        # --- 🆕 8. COIN FLIP (Tails) ---
        if not is_hosp and player['ryo'] >= COINFLIP_COST:
            result_text_t, updates_t = play_coin_flip(player, 'Tails')
            db.update_player(user_id, updates_t)
            results.append(
                InlineQueryResultArticle(
                    id=f"coin_tails_{uuid.uuid4()}",
                    title=f"🪙 Coin Flip: TAILS (Cost: {COINFLIP_COST} Ryo)",
                    description="Guess correctly to win!",
                    input_message_content=InputTextMessageContent(result_text_t, parse_mode="HTML")
                )
            )
        
        # --- 🆕 9. SCRATCH CARD ---
        if not is_hosp and player['ryo'] >= SCRATCH_COST:
            result_text, updates = play_scratch_card(player)
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id=f"scratch_{uuid.uuid4()}",
                    title=f"🎫 Scratch Card (Cost: {SCRATCH_COST} Ryo)",
                    description="Instant win! Up to 1000 Ryo!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # --- 🆕 10. NINJA ROULETTE (Red) ---
        if not is_hosp and player['ryo'] >= ROULETTE_COST:
            result_text, updates = play_ninja_roulette(player, 'color', 'red')
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id=f"roulette_red_{uuid.uuid4()}",
                    title=f"🎰 Roulette: Bet RED (Cost: {ROULETTE_COST} Ryo)",
                    description="2x payout if red wins!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # --- 🆕 11. NINJA ROULETTE (Black) ---
        if not is_hosp and player['ryo'] >= ROULETTE_COST:
            result_text, updates = play_ninja_roulette(player, 'color', 'black')
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id=f"roulette_black_{uuid.uuid4()}",
                    title=f"🎰 Roulette: Bet BLACK (Cost: {ROULETTE_COST} Ryo)",
                    description="2x payout if black wins!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # --- 🆕 12. TREASURE HUNT (Cave) ---
        if not is_hosp and player['ryo'] >= HUNT_COST:
            result_text, updates = play_treasure_hunt(player, 'cave')
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id=f"hunt_cave_{uuid.uuid4()}",
                    title=f"🗺️ Treasure Hunt: CAVE (Cost: {HUNT_COST} Ryo)",
                    description="Explore a dark cave for treasure!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # --- 🆕 13. TREASURE HUNT (Forest) ---
        if not is_hosp and player['ryo'] >= HUNT_COST:
            result_text, updates = play_treasure_hunt(player, 'forest')
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id=f"hunt_forest_{uuid.uuid4()}",
                    title=f"🗺️ Treasure Hunt: FOREST (Cost: {HUNT_COST} Ryo)",
                    description="Search the dense forest!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # --- 🆕 14. TREASURE HUNT (Temple) ---
        if not is_hosp and player['ryo'] >= HUNT_COST:
            result_text, updates = play_treasure_hunt(player, 'temple')
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id=f"hunt_temple_{uuid.uuid4()}",
                    title=f"🗺️ Treasure Hunt: TEMPLE (Cost: {HUNT_COST} Ryo)",
                    description="Explore an ancient temple!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
            
    else:
        # --- Not registered ---
        results.append(
            InlineQueryResultArticle(
                id="register",
                title="❌ You are not registered!",
                description="Click here to ask how to join.",
                input_message_content=InputTextMessageContent(
                    f"Hey everyone, how do I /register for @{context.bot.username}?"
                )
            )
        )

    # cache_time=0 is important for games
    await query.answer(results, cache_time=0)
